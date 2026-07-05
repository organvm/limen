from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from limen.io import save_limen_file
from limen.models import LimenFile
from limen.tabularius import submit_task_status


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)


def _load_organ_module(monkeypatch):
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    monkeypatch.delenv("LIMEN_TASKS", raising=False)
    spec = importlib.util.spec_from_file_location("tabularius_organ_uut", ROOT / "scripts" / "tabularius-organ.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _task(tid: str) -> dict[str, str]:
    return {"id": tid, "title": f"task {tid}", "target_agent": "codex", "status": "open", "created": "2026-07-05"}


def _seed_board(tmp_path: Path) -> Path:
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile.model_validate({"version": "1.0", "tasks": [_task(f"T-{i}") for i in range(6)]}))
    return board


def _run_organ(tmp_path: Path, board: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_TASKS": str(board),
    }
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "tabularius-organ.py")],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_tabularius_organ_defaults_to_checkout_root(monkeypatch) -> None:
    module = _load_organ_module(monkeypatch)

    assert module.ROOT == ROOT
    assert module.BOARD == ROOT / "tasks.yaml"
    assert module.STATE == ROOT / "logs" / "tabularius-organ-state.json"


def test_tabularius_organ_stamps_event_log_cache_proof_streak(tmp_path: Path) -> None:
    board = _seed_board(tmp_path)
    state_path = tmp_path / "logs" / "tabularius-organ-state.json"
    submit_task_status(board, "T-1", "done", agent="limen", session_id="proof-1", now=NOW)

    first = _run_organ(tmp_path, board)

    assert first.returncode == 0, first.stdout + first.stderr
    assert "event-log proof ok (streak 1)" in first.stdout
    state = json.loads(state_path.read_text())
    assert state["event_log_verified"] is True
    assert state["event_log_cache_verified"] is True
    assert state["event_log_streak"] == 1
    assert state["event_log_events"] >= 1
    assert (tmp_path / "logs" / "tickets" / "events.jsonl").exists()

    submit_task_status(board, "T-2", "done", agent="limen", session_id="proof-2", now=NOW)
    second = _run_organ(tmp_path, board)

    assert second.returncode == 0, second.stdout + second.stderr
    assert "event-log proof ok (streak 2)" in second.stdout
    state = json.loads(state_path.read_text())
    assert state["event_log_streak"] == 2
