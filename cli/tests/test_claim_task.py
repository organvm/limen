from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claim-task.py"


def load_claim_module():
    spec = importlib.util.spec_from_file_location("claim_task", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def board(budget_cost=2):
    return {
        "portal": {"budget": {"track": {"spent": 3, "per_agent": {"codex": 1}}}},
        "tasks": [
            {
                "id": "TASK-1",
                "title": "Claim me",
                "target_agent": "any",
                "status": "open",
                "budget_cost": budget_cost,
                "dispatch_log": [],
            }
        ],
    }


def test_claim_task_reserves_open_task_and_budget() -> None:
    claim = load_claim_module()
    data = board()

    task = claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert task["target_agent"] == "codex"
    assert task["status"] == "dispatched"
    assert data["portal"]["budget"]["track"]["spent"] == 5
    assert data["portal"]["budget"]["track"]["per_agent"]["codex"] == 3
    assert task["dispatch_log"][-1]["session_id"] == "session-1"


def test_claim_task_rejects_unknown_agent_without_mutating() -> None:
    claim = load_claim_module()
    data = board()
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "goose", "session-1")

    assert data == before


def test_claim_task_rejects_malformed_budget_without_mutating() -> None:
    claim = load_claim_module()
    data = board(budget_cost="not-an-int")
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_rejects_boolean_budget_without_mutating() -> None:
    claim = load_claim_module()
    data = board(budget_cost=False)
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_live_uses_tabularius(tmp_path, monkeypatch) -> None:
    from limen.tabularius import pending_count

    claim = load_claim_module()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {"budget": {"track": {"date": "2026-07-02", "spent": 3, "per_agent": {"codex": 1}}}},
                "tasks": [
                    {
                        "id": "TASK-1",
                        "title": "Claim me",
                        "target_agent": "any",
                        "status": "open",
                        "budget_cost": 2,
                        "created": "2026-07-02",
                        "dispatch_log": [],
                    }
                ],
            },
            sort_keys=False,
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["claim-task.py", "TASK-1", "codex", "--tasks", str(tasks), "--session-id", "session-1", "--live"],
    )

    assert claim.main() == 0

    data = yaml.safe_load(tasks.read_text())
    task = data["tasks"][0]
    assert task["status"] == "dispatched"
    assert task["target_agent"] == "codex"
    assert data["portal"]["budget"]["track"]["spent"] == 5
    assert data["portal"]["budget"]["track"]["per_agent"]["codex"] == 3
    assert task["dispatch_log"][-1]["session_id"] == "session-1"
    assert pending_count(tasks) == 0
