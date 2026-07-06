from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile
from limen.tabularius import archive_count, pending_count


ROOT = Path(__file__).resolve().parents[2]


def _task(task_id: str, repo: str) -> dict[str, object]:
    return {
        "id": task_id,
        "title": task_id,
        "repo": repo,
        "target_agent": "jules",
        "status": "open",
        "created": "2026-07-05",
        "dispatch_log": [],
    }


def test_rewrite_owners_apply_routes_task_changes_through_tabularius(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.yaml"
    save_limen_file(
        tasks,
        LimenFile.model_validate(
            {
                "version": "1.0",
                "tasks": [
                    _task("OLD", "4444J99/limen"),
                    _task("EXTERNAL", "external/project"),
                ],
            }
        ),
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = {
        **os.environ,
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_TASKS": str(tasks),
        "LIMEN_WORKDIR": str(workspace),
        "PYTHONPATH": str(ROOT / "cli" / "src"),
    }

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "rewrite-owners.py"), "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "through TABVLARIVS" in result.stdout
    board = load_limen_file(tasks)
    by_id = {task.id: task for task in board.tasks}
    assert by_id["OLD"].repo == "organvm/limen"
    assert by_id["OLD"].dispatch_log[-1].agent == "rewrite-owners"
    assert by_id["OLD"].dispatch_log[-1].status == "owner-rewrite"
    assert by_id["EXTERNAL"].repo == "external/project"
    assert pending_count(tasks) == 0
    assert archive_count(tasks) == 1
