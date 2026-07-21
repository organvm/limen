from __future__ import annotations

import pytest

from limen.work_loan import WorkLoanV1, task_source_lineage, task_work_loan_readiness


def task(**overrides):
    value = {
        "id": "WL-1",
        "repo": "organvm/limen",
        "budget_cost": 2,
        "labels": ["origin:human-prompt", "horizon:present"],
        "value_case": "Deliver one bounded, owner-receipted outcome",
        "predicate": "pytest -q cli/tests/test_work_loan.py",
        "receipt_target": "github:organvm/limen:pull-request:WL-1",
    }
    value.update(overrides)
    return value


def test_task_work_loan_derives_only_explicit_registry_fields() -> None:
    readiness = task_work_loan_readiness(task())

    assert readiness.ready
    assert readiness.reason_code is None
    assert readiness.loan == WorkLoanV1(
        source_origin="human_prompt",
        horizon="present",
        value_case="Deliver one bounded, owner-receipted outcome",
        budget_cost=2,
        owner_surface="organvm/limen",
    )


def test_missing_fields_are_stable_and_title_prose_never_underwrites() -> None:
    readiness = task_work_loan_readiness(
        task(
            title="Urgent human ask with huge value",
            repo=None,
            budget_cost=0,
            labels=[],
            value_case=None,
            predicate="should pass",
            receipt_target="receipt.txt",
        )
    )

    assert readiness.missing_fields == (
        "source_origin",
        "horizon",
        "value_case",
        "budget_cost",
        "owner_surface",
        "predicate",
        "receipt_target",
    )
    assert readiness.reason_code == (
        "task-not-underwritten:source_origin,horizon,value_case,budget_cost,owner_surface,predicate,receipt_target"
    )


def test_external_deadline_requires_due_at_but_ordinary_work_does_not() -> None:
    missing = task_work_loan_readiness(task(external_deadline=True))
    assert missing.reason_code == "task-not-underwritten:due_at"

    ready = task_work_loan_readiness(task(external_deadline=True, due_at="2026-08-01T12:00:00Z"))
    assert ready.ready
    assert ready.loan is not None and ready.loan.external_deadline is True

    with pytest.raises(ValueError, match="due_at is required"):
        WorkLoanV1(
            source_origin="obligation",
            horizon="present",
            value_case="Meet the external deadline",
            budget_cost=1,
            owner_surface="github:organvm/limen#1",
            external_deadline=True,
        )


def test_source_lineage_is_never_inferred_from_title_or_repo() -> None:
    assert task_source_lineage(task(title="Feed cohort 7")) == "unknown"
    assert task_source_lineage(task(source_lineage="prompt-lineage-7")) == "prompt-lineage-7"
    assert task_source_lineage(task(labels=["lineage:feed-42"])) == "feed-42"
