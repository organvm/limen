import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile, Task
from limen.tabularius import drain_once, pending_count


ROOT = Path(__file__).resolve().parents[2]
RECOVER = ROOT / "scripts" / "recover.py"


def test_recover_apply_can_emit_tabularius_status_tickets(tmp_path):
    board = tmp_path / "tasks.yaml"
    tasks = [
        Task(
            id="FAILED-1",
            title="failed task",
            target_agent="agy",
            status="failed",
            labels=["noop", "tried:agy"],
            created=date(2026, 7, 5),
        )
    ] + [
        Task(id=f"FILLER-{i}", title=f"filler {i}", target_agent="codex", status="open", created=date(2026, 7, 5))
        for i in range(5)
    ]
    save_limen_file(board, LimenFile(tasks=tasks))

    env = {**os.environ, "LIMEN_TICKETS_PRODUCE": "1"}
    result = subprocess.run(
        [sys.executable, str(RECOVER), "--tasks", str(board), "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "APPLIED -> TABVLARIVS tickets" in result.stdout
    unchanged = {task.id: task for task in load_limen_file(board).tasks}
    assert unchanged["FAILED-1"].status == "failed"
    assert pending_count(board) == 1

    drained = drain_once(board)
    assert drained.applied == 1
    updated = {task.id: task for task in load_limen_file(board).tasks}
    task = updated["FAILED-1"]
    assert task.status == "open"
    assert task.target_agent == "codex"
    assert task.labels == ["noop"]
    assert task.dispatch_log[-1].status == "open"
    assert task.dispatch_log[-1].output == "recover: reopened failed -> fresh cascade"
