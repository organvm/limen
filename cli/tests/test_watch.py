from __future__ import annotations

import sys
from pathlib import Path

import yaml
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.cli import main


def write_board(path: Path, tasks: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "Universal Task Intake",
                    "budget": {
                        "daily": 100,
                        "unit": "runs",
                        "per_agent": {"codex": 10},
                        "track": {
                            "date": "2026-06-19",
                            "spent": 1,
                            "per_agent": {"codex": 1},
                        },
                    },
                },
                "tasks": tasks,
            },
            sort_keys=False,
        )
    )


def test_watch_once_renders_without_error(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "CLI-watch-subcommand",
                "title": "cli watch subcommand",
                "repo": "limen",
                "type": "code",
                "target_agent": "codex",
                "priority": "high",
                "budget_cost": 1,
                "status": "in_progress",
                "created": "2026-06-19",
                "dispatch_log": [],
            }
        ],
    )

    result = CliRunner().invoke(
        main,
        ["watch", "--once", "--no-color"],
        env={"LIMEN_ROOT": str(tmp_path), "LIMEN_TASKS": str(tasks_path)},
    )

    assert result.exit_code == 0, result.output
    assert "LIMEN FLEET - live" in result.output
    assert "CLI-watch-subcommand" not in result.output
    assert (tmp_path / "logs" / "fleet-status.json").exists()


def test_watch_compact_once_is_one_line(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-001",
                "title": "Done task",
                "repo": "limen",
                "target_agent": "codex",
                "status": "done",
                "created": "2026-06-19",
            }
        ],
    )

    result = CliRunner().invoke(
        main,
        ["watch", "--once", "--compact"],
        env={"LIMEN_ROOT": str(tmp_path), "LIMEN_TASKS": str(tasks_path)},
    )

    assert result.exit_code == 0, result.output
    assert result.output.count("\n") == 1
    assert "LIMEN FLEET | done=1 | in_flight=0 | open=0 | total=1" in result.output
