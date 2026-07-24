from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import limen_mcp.server as server


def write_board(path: Path, tasks: list[dict], budget: dict | None = None) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "Universal Task Intake",
                    "budget": budget
                    or {
                        "daily": 100,
                        "unit": "runs",
                        "per_agent": {},
                        "track": {"date": "", "spent": 0, "per_agent": {}},
                    },
                },
                "tasks": tasks,
            },
            sort_keys=False,
        )
    )


@pytest.fixture
def tasks_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tasks.yaml"
    write_board(path, [])
    monkeypatch.setenv("LIMEN_TASKS", str(path))
    monkeypatch.setattr(server, "TASK_LOOP_TRACKER", {})
    monkeypatch.setattr(server, "CIRCUIT_BREAKER_TRIPPED", False)
    monkeypatch.setattr(server, "_save_state", lambda: None)
    return path


def test_validation_helpers_enforce_expected_constraints() -> None:
    assert server._validate_task_id("LIMEN-001") == "LIMEN-001"
    assert server._validate_optional_enum(None, {"open", "done"}, "status") is None
    assert server._validate_optional_enum("done", {"open", "done"}, "status") == "done"

    assert server._validate_text("hello", "title", 10) == "hello"

    with pytest.raises(ValueError):
        server._validate_task_id("")
    with pytest.raises(ValueError):
        server._validate_task_id("bad id!")
    with pytest.raises(ValueError):
        server._validate_text("nope\u0001", "title", 10)
    with pytest.raises(ValueError):
        server._validate_optional_enum("bad", {"open", "done"}, "status")


def test_get_tasks_path_prefers_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tasks_path = tmp_path / "custom-tasks.yaml"
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    assert server._get_tasks_path() == tasks_path


def test_list_tasks_filters_by_status_and_agent(tasks_file: Path) -> None:
    write_board(
        tasks_file,
        [
            {"id": "LIMEN-001", "title": "local", "target_agent": "codex", "status": "open", "created": "2026-01-01", "budget_cost": 1},
            {"id": "LIMEN-002", "title": "done", "target_agent": "jules", "status": "done", "created": "2026-01-01", "budget_cost": 1},
        ],
    )

    rows = server.list_tasks(status="done", agent="jules")
    assert len(rows) == 1
    assert rows[0]["id"] == "LIMEN-002"
    assert rows[0]["status"] == "done"
    assert rows[0]["target_agent"] == "jules"


def test_get_budget_status_uses_board_payload(tasks_file: Path) -> None:
    write_board(
        tasks_file,
        [],
        budget={
            "daily": 12,
            "unit": "runs",
            "per_agent": {"codex": 5},
            "track": {"date": "2026-06-01", "spent": 7, "per_agent": {"codex": 2}},
        },
    )

    status = server.get_budget_status()
    assert status["daily"] == 12
    assert status["track"]["spent"] == 7
    assert status["per_agent"]["codex"] == 5


def test_get_task_enforces_loop_limit(tasks_file: Path) -> None:
    write_board(
        tasks_file,
        [{"id": "LIMEN-001", "title": "retry", "target_agent": "jules", "status": "open", "created": "2026-01-01", "budget_cost": 1}],
    )

    for _ in range(3):
        task = server.get_task("LIMEN-001")
        assert task["id"] == "LIMEN-001"

    with pytest.raises(ValueError, match="HARD LOOP LIMIT REACHED"):
        server.get_task("LIMEN-001")


def test_get_task_reports_missing_task(tasks_file: Path) -> None:
    with pytest.raises(ValueError, match="Task LIMEN-MISSING not found"):
        server.get_task("LIMEN-MISSING")


def test_add_task_generates_sequential_id(tasks_file: Path) -> None:
    write_board(
        tasks_file,
        [
            {"id": "LIMEN-007", "title": "old", "target_agent": "jules", "status": "done", "created": "2026-01-01", "budget_cost": 2},
            {"id": "LIMEN-004", "title": "older", "target_agent": "codex", "status": "open", "created": "2026-01-01", "budget_cost": 1},
        ],
    )

    result = server.add_task(
        title="new",
        repo="organvm/limen",
        agent="claude",
        priority="high",
        budget_cost=3,
    )
    assert result == "Created task LIMEN-008"

    payload = yaml.safe_load(tasks_file.read_text())
    assert payload["tasks"][-1]["id"] == "LIMEN-008"
    assert payload["tasks"][-1]["repo"] == "organvm/limen"
    assert payload["tasks"][-1]["status"] == "open"
    assert payload["tasks"][-1]["target_agent"] == "claude"


def test_update_task_status_doubles_cost_for_failed_in_progress(tasks_file: Path) -> None:
    write_board(
        tasks_file,
        [
            {
                "id": "LIMEN-009",
                "title": "slow task",
                "target_agent": "codex",
                "status": "in_progress",
                "budget_cost": 4,
                "created": "2026-01-01",
            }
        ],
    )

    result = server.update_task_status("LIMEN-009", "failed", context="infra timeout")
    assert result == "Updated LIMEN-009 to failed. New budget cost: 8"

    payload = yaml.safe_load(tasks_file.read_text())
    task = next(t for t in payload["tasks"] if t["id"] == "LIMEN-009")
    assert task["status"] == "failed"
    assert task["budget_cost"] == 8
    assert task["context"] == "infra timeout"


def test_trip_circuit_breaker_blocks_and_reset_restores_tasks(tasks_file: Path) -> None:
    assert server.trip_circuit_breaker() == "Circuit breaker TRIPPED. System offline."
    with pytest.raises(RuntimeError, match="SYSTEM OFFLINE - GO TO SLEEP"):
        server.list_tasks()
    assert server.reset_circuit_breaker() == "Circuit breaker RESET. System online."
    # Verify regular operation resumes with the default board after reset.
    assert server.list_tasks() is not None
