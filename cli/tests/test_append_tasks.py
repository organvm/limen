from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile
from limen.tabularius import archive_count, pending_count


ROOT = Path(__file__).resolve().parents[2]


def test_append_tasks_uses_tabularius_and_is_idempotent(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.yaml"
    save_limen_file(tasks, LimenFile.model_validate({"version": "1.0", "tasks": []}))

    first = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "append-tasks.py")],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert "through TABVLARIVS" in first.stdout
    board = load_limen_file(tasks)
    assert len(board.tasks) == 41
    assert {task.status for task in board.tasks} == {"dispatched"}
    assert pending_count(tasks) == 0
    assert archive_count(tasks) == 41

    second = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "append-tasks.py")],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert second.returncode == 0, second.stdout + second.stderr
    assert "Added 0 tasks" in second.stdout
    assert len(load_limen_file(tasks).tasks) == 41
    assert pending_count(tasks) == 0
