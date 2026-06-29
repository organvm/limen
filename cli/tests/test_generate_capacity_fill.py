from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from limen.models import LimenFile, Task


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "generate-capacity-fill.py"


def _load_script(name: str = "generate_capacity_fill_under_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snapshot(agent: str, expected: int, productive: int, open_work: int = 0):
    return {
        "generated_at": "2026-06-29T22:00:00+00:00",
        "status": "blocked",
        "blockers": [{"id": f"lane-fill-{agent}", "evidence": "underfilled"}],
        "rows": [
            {
                "agent": agent,
                "status": "no_work",
                "expected_now": expected,
                "productive": productive,
                "open_work": open_work,
                "attempts": productive,
                "target": expected,
                "active_work": 0,
                "remaining": expected - productive,
                "reachable": True,
                "evidence": "underfilled",
                "action": "generate work",
            }
        ],
    }


def _multi_snapshot():
    rows = []
    for agent in ("jules", "claude", "opencode", "agy", "gemini"):
        rows.append(_snapshot(agent, 10, 0)["rows"][0])
    return {
        "generated_at": "2026-06-29T22:00:00+00:00",
        "status": "blocked",
        "blockers": [{"id": f"lane-fill-{row['agent']}", "evidence": "underfilled"} for row in rows],
        "rows": rows,
    }


def test_capacity_fill_generator_creates_lane_specific_packets(monkeypatch):
    mod = _load_script()
    monkeypatch.setattr(mod, "_down_lanes", lambda: set())
    monkeypatch.setattr(mod, "capacity_fill_snapshot", lambda lf, down_lanes: _snapshot("claude", 15, 0))

    planned, info = mod.plan_capacity_fill_tasks(LimenFile(), max_new=4, per_lane_cap=4)

    assert len(planned) == 4
    assert {task.target_agent for task in planned} == {"claude"}
    assert all("capacity-fill" in task.labels for task in planned)
    assert info["lanes"][0]["deficit"] == 15


def test_capacity_fill_generator_is_idempotent_for_existing_daily_slots(monkeypatch):
    mod = _load_script("generate_capacity_fill_under_test_idempotent")
    monkeypatch.setattr(mod, "_down_lanes", lambda: set())
    monkeypatch.setattr(mod, "capacity_fill_snapshot", lambda lf, down_lanes: _snapshot("opencode", 3, 0))
    compact = date.today().isoformat().replace("-", "")
    existing = Task(
        id=f"CAPFILL-opencode-{compact}-01",
        title="existing",
        target_agent="opencode",
        status="open",
        labels=["capacity-fill", "lane:opencode"],
        created=date.today(),
    )

    planned, info = mod.plan_capacity_fill_tasks(LimenFile(tasks=[existing]), max_new=10, per_lane_cap=3)

    assert [task.id for task in planned] == [
        f"CAPFILL-opencode-{compact}-02",
        f"CAPFILL-opencode-{compact}-03",
    ]
    assert info["lanes"][0]["existing"] == 1


def test_capacity_fill_generator_round_robins_lanes_before_filling_one(monkeypatch):
    mod = _load_script("generate_capacity_fill_under_test_round_robin")
    monkeypatch.setattr(mod, "_down_lanes", lambda: set())
    monkeypatch.setattr(mod, "capacity_fill_snapshot", lambda lf, down_lanes: _multi_snapshot())

    planned, _ = mod.plan_capacity_fill_tasks(LimenFile(), max_new=5, per_lane_cap=10)

    assert [task.target_agent for task in planned] == ["jules", "claude", "opencode", "agy", "gemini"]
