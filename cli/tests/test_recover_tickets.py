import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile, Task
from limen.tabularius import pending_count


ROOT = Path(__file__).resolve().parents[2]
RECOVER = ROOT / "scripts" / "recover.py"


def test_recover_apply_drains_tabularius_status_tickets(tmp_path):
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

    env = {**os.environ}
    env.pop("LIMEN_TICKETS_PRODUCE", None)
    result = subprocess.run(
        [sys.executable, str(RECOVER), "--tasks", str(board), "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "through TABVLARIVS" in result.stdout
    assert pending_count(board) == 0
    updated = {task.id: task for task in load_limen_file(board).tasks}
    task = updated["FAILED-1"]
    assert task.status == "open"
    assert task.target_agent == "codex"
    assert task.labels == ["noop"]
    assert task.dispatch_log[-1].status == "open"
    assert task.dispatch_log[-1].output == "recover: reopened failed -> fresh cascade"


def test_recover_apply_restores_prior_done_through_tabularius(tmp_path):
    board = tmp_path / "tasks.yaml"
    save_limen_file(
        board,
        LimenFile(
            tasks=[
                Task(
                    id="DONE-1",
                    title="stale reopened task",
                    target_agent="codex",
                    status="open",
                    created=date(2026, 7, 5),
                    dispatch_log=[
                        {
                            "timestamp": "2026-07-05T00:00:00+00:00",
                            "agent": "codex",
                            "session_id": "old",
                            "status": "done",
                        }
                    ],
                )
            ]
        ),
    )

    env = {**os.environ}
    env.pop("LIMEN_TICKETS_PRODUCE", None)
    result = subprocess.run(
        [sys.executable, str(RECOVER), "--tasks", str(board), "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "through TABVLARIVS" in result.stdout
    assert pending_count(board) == 0
    task = load_limen_file(board).tasks[0]
    assert task.status == "done"
    assert task.dispatch_log[-1].status == "done"
    assert task.dispatch_log[-1].output == "recover: prior done transition wins; restored terminal status"
