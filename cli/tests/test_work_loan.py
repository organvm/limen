from __future__ import annotations

from pathlib import Path

import pytest

from limen.work_loan import (
    WorkLoanV1,
    packet_work_loan_missing,
    task_source_lineage,
    task_work_loan_readiness,
)


ROOT = Path(__file__).resolve().parents[2]


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


def test_packet_work_loan_requires_canonical_origin_horizon_and_bound_cost() -> None:
    packet = {
        "predicate": "pytest -q cli/tests/test_work_loan.py",
        "receipt_target": "github:organvm/limen:pull-request:WL-PACKET",
        "spend": {"limit": 2},
        "work_loan": {
            "source_origin": "urgent",
            "horizon": "soon",
            "value_case": "Deliver one bounded packet",
            "budget_cost": 3,
            "owner_surface": "organvm/limen",
        },
    }

    assert packet_work_loan_missing(packet) == ("source_origin", "horizon", "budget_cost")


def test_source_lineage_is_never_inferred_from_title_or_repo() -> None:
    assert task_source_lineage(task(title="Feed cohort 7")) == "unknown"
    assert task_source_lineage(task(source_lineage="prompt-lineage-7")) == "prompt-lineage-7"
    assert task_source_lineage(task(labels=["lineage:feed-42"])) == "feed-42"


def test_sanctioned_producers_adopt_explicit_work_loan_collateral() -> None:
    task_producers = (
        "cli/src/limen/observatory/lever.py",
        "scripts/always-working.py",
        "scripts/append-tasks.py",
        "scripts/auto-scale.py",
        "scripts/batch-dispatch.py",
        "scripts/converge-organ.py",
        "scripts/corpus-converge.py",
        "scripts/discover-value.py",
        "scripts/generate-backlog.py",
        "scripts/generate-experience-backlog.py",
        "scripts/generate-organ-backlog.py",
        "scripts/generate-revenue-backlog.py",
        "scripts/generate-seo-backlog.py",
        "scripts/ingest-backlog.py",
        "scripts/insight-route.py",
        "scripts/mine-backlog.py",
        "scripts/overnight-watch.py",
    )
    for relative in task_producers:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "origin" in source, relative
        assert "horizon" in source, relative
        assert "value_case" in source, relative

    packet_producers = (
        "cli/src/limen/conduct/campaign.py",
        "scripts/current-session-fanout.py",
    )
    for relative in packet_producers:
        assert "WorkLoanV1(" in (ROOT / relative).read_text(encoding="utf-8"), relative
