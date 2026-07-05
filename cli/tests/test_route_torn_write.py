"""route.py must TOLERATE torn writes and never perpetuate them.

A recurring corruption writes a whole Task object into some task's dispatch_log (an entry missing
timestamp/agent/session_id). Before the fix, route.py read tasks.yaml with raw yaml.safe_load and
re-encoded that garbage every beat — spamming a pydantic "Field required" trace and keeping the
corruption alive. route.py now reads through the resilient loader (sanitizes) and writes through the
validated save under the queue lock, so the trace stops AND the file is healed on write.
"""

from __future__ import annotations

import os
import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "route.py"
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import LimenFile, Task  # noqa: E402
from limen.tabularius import drain_once, pending_count  # noqa: E402


def _board_with_torn_write(path: Path) -> None:
    tasks = [
        {
            "id": "SEED-1",
            "title": "seed",
            "repo": "o/r1",
            "target_agent": "codex",
            "priority": "medium",
            "budget_cost": 1,
            "status": "open",
            "created": "2026-06-01",
            "dispatch_log": [
                {"timestamp": "2026-06-01T00:00:00", "agent": "codex", "session_id": "s1", "status": "dispatched"},
                # the torn write: a whole Task dict landed INSIDE the dispatch_log
                {"id": "GEN-x", "title": "garbage", "repo": "o/r1", "status": "open"},
            ],
        },
    ]
    doc = {
        "version": "1.0",
        "portal": {
            "name": "t",
            "budget": {
                "daily": 600,
                "unit": "runs",
                "per_agent": {"codex": 100, "claude": 100, "agy": 100},
                "track": {"date": "", "spent": 0, "per_agent": {}},
            },
        },
        "tasks": tasks,
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def _run(path: Path, *args: str) -> subprocess.CompletedProcess:
    # LIMEN_ROOT=tmp -> no real usage.json/lanes bleed; LIMEN_DISPATCH_LANES=codex keeps probing bounded.
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(path), *args],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            "LIMEN_ORGS": "",
            "LIMEN_ROOT": str(path.parent),
            "LIMEN_DISPATCH_LANES": "codex",
            "LIMEN_TICKETS_PRODUCE": "",
        },
    )


def test_route_tolerates_torn_write_dry_run(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board_with_torn_write(p)
    r = _run(p)
    assert r.returncode == 0, r.stderr
    assert "Field required" not in r.stderr, f"pydantic trace leaked: {r.stderr}"
    assert "tolerated 1 malformed" in r.stderr


def test_route_apply_heals_the_file(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board_with_torn_write(p)
    r = _run(p, "--apply")
    assert r.returncode == 0, r.stderr
    assert "Field required" not in r.stderr
    # the rewritten file must be CLEAN: the malformed dispatch_log entry is gone, the valid one stays.
    doc = yaml.safe_load(p.read_text())
    dls = [e for t in doc["tasks"] for e in (t.get("dispatch_log") or [])]
    assert len(dls) == 1, f"garbage dispatch_log entry survived the rewrite: {dls}"
    assert {"timestamp", "agent", "session_id", "status"}.issubset(dls[0].keys())


def test_route_ticket_mode_waits_for_tabularius(tmp_path: Path, monkeypatch):
    board = tmp_path / "tasks.yaml"
    save_limen_file(
        board,
        LimenFile(
            tasks=[
                Task(
                    id=f"R-{i}",
                    title="route me",
                    repo="o/r",
                    target_agent="claude",
                    status="open",
                    created="2026-07-01",
                )
                for i in range(6)
            ]
        ),
    )
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(board))
    monkeypatch.setenv("LIMEN_TICKETS_PRODUCE", "1")
    monkeypatch.setenv("LIMEN_DISPATCH_LANES", "codex")
    monkeypatch.setenv("LIMEN_ORGS", "")

    spec = importlib.util.spec_from_file_location("route_ticket_uut", SCRIPT)
    route = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(route)
    monkeypatch.setattr(route, "ROOT", tmp_path)
    monkeypatch.setattr(route, "_refresh_self_improve_proposal", lambda: None)
    monkeypatch.setattr(route, "capacity_census", lambda data: [{"agent": "codex", "reachable": True}])
    monkeypatch.setattr(route, "format_capacity_census", lambda rows: "capacity: codex")
    monkeypatch.setattr(route, "_fleet_health", lambda data: {"codex": True})
    monkeypatch.setattr(route, "_down_lanes", lambda: set())
    monkeypatch.setattr(route, "_vendor_runway", lambda: {})
    monkeypatch.setattr(route, "select_lanes", lambda selector, data, down_lanes=None: ["codex"])
    monkeypatch.setattr(route, "assign_channel", lambda task, root: route.UNASSIGNED)
    monkeypatch.setattr(
        sys,
        "argv",
        ["route", "--tasks", str(board), "--workdir", str(tmp_path), "--apply"],
    )

    assert route.main() == 0
    assert {task.target_agent for task in load_limen_file(board).tasks} == {"claude"}
    assert pending_count(board) == 6

    drained = drain_once(board)
    assert drained.applied == 6
    tasks = load_limen_file(board).tasks
    assert {task.target_agent for task in tasks} == {"codex"}
    assert all(task.dispatch_log[-1].agent == "limen" for task in tasks)
    assert all(task.dispatch_log[-1].session_id == "route" for task in tasks)
