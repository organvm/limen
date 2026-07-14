"""reclassify-needs-human DEBT bucket: a chronic (reopened >=3x, no PR) needs_human task is FLEET
debt — --apply parks it in failed_chronic, NEVER flips it to open (flipping chronic->open is the
ping-pong that re-escalated 252/290 straight back to needs_human within a day). A real lever-tagged
task stays KEEP; --debt-only (the beat guard) moves ONLY debt and never touches buildable FLIP work."""

import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reclassify-needs-human.py"


def _board(tmp: Path, tasks: list[dict]) -> Path:
    p = tmp / "tasks.yaml"
    p.write_text(yaml.safe_dump({"version": "1.0", "portal": {"name": "t"}, "tasks": tasks}))
    return p


def _run(tmp: Path, p: Path, *args: str) -> None:
    env = dict(os.environ, LIMEN_ROOT=str(tmp), LIMEN_TASKS=str(p))
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(p), *args],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr


def _chronic_log() -> list[dict]:
    # reopened 3x, never a PR — the structural chronic signature _is_fleet_debt detects
    return [
        {"timestamp": "2026-06-21T00:00:00+00:00", "agent": "limen", "session_id": "heal", "status": "open"}
        for _ in range(3)
    ]


def _tasks() -> list[dict]:
    return [
        {"id": "CHRONIC", "title": "chronic build", "created": "2026-06-01", "status": "needs_human",
         "target_agent": "codex", "type": "code", "repo": "o/r", "dispatch_log": _chronic_log()},
        {"id": "LEVER", "title": "needs-human (L-SOCIAL-SEND) pull the publish", "created": "2026-06-01",
         "status": "needs_human", "target_agent": "claude", "dispatch_log": []},
        {"id": "BUILDABLE", "title": "add a README", "created": "2026-06-01", "status": "needs_human",
         "target_agent": "codex", "type": "code", "repo": "o/r", "dispatch_log": []},
    ]


def test_debt_bucket_parks_chronic_in_failed_chronic(tmp_path) -> None:
    p = _board(tmp_path, _tasks())
    _run(tmp_path, p, "--apply")
    out = {t["id"]: t for t in yaml.safe_load(p.read_text())["tasks"]}
    assert out["CHRONIC"]["status"] == "failed_chronic"  # DEBT -> failed_chronic, NOT open (no ping-pong)
    assert out["LEVER"]["status"] == "needs_human"  # KEEP: a real human gate is never auto-moved
    assert out["BUILDABLE"]["status"] == "open"  # FLIP: buildable non-chronic -> open


def test_debt_only_moves_debt_but_never_flips_buildable(tmp_path) -> None:
    p = _board(tmp_path, _tasks())
    _run(tmp_path, p, "--apply", "--debt-only")
    out = {t["id"]: t for t in yaml.safe_load(p.read_text())["tasks"]}
    assert out["CHRONIC"]["status"] == "failed_chronic"  # DEBT still parked (the beat guard's job)
    assert out["BUILDABLE"]["status"] == "needs_human"  # FLIP untouched under --debt-only
    assert out["LEVER"]["status"] == "needs_human"
