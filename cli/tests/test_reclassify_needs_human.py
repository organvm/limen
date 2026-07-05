from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from limen.tabularius import pending_count

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reclassify-needs-human.py"


def test_reclassify_apply_uses_tabularius(tmp_path) -> None:
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "FALSE-GATE",
                        "title": "Update README",
                        "type": "docs",
                        "repo": "organvm/limen",
                        "target_agent": "any",
                        "status": "needs_human",
                        "created": "2026-07-05",
                        "labels": [],
                        "dispatch_log": [],
                    },
                    {
                        "id": "SECRET-GATE",
                        "title": "Add Cloudflare credential",
                        "type": "docs",
                        "repo": "organvm/limen",
                        "target_agent": "any",
                        "status": "needs_human",
                        "created": "2026-07-05",
                        "labels": [],
                        "dispatch_log": [],
                    },
                ],
            },
            sort_keys=False,
        )
    )
    env = dict(os.environ, LIMEN_ROOT=str(tmp_path), LIMEN_TASKS=str(tasks))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(tasks), "--apply"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "via TABVLARIVS" in result.stdout
    data = yaml.safe_load(tasks.read_text())
    by_id = {task["id"]: task for task in data["tasks"]}
    assert by_id["FALSE-GATE"]["status"] == "open"
    assert by_id["FALSE-GATE"]["labels"] == ["reclassified-from-needs-human"]
    assert by_id["FALSE-GATE"]["dispatch_log"][-1]["agent"] == "limen"
    assert by_id["FALSE-GATE"]["dispatch_log"][-1]["status"] == "open"
    assert by_id["SECRET-GATE"]["status"] == "needs_human"
    assert pending_count(tasks) == 0
