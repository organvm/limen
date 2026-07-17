"""Hermetic contract tests for limen.execution_trajectory.v1."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.execution_trajectory import (  # noqa: E402
    ExecutionTrajectory,
    TrajectoryConflictError,
    TrajectoryStore,
    build_corpus,
    load_jsonl,
    publish_terminal_attempts,
    verified_value_credit,
)
from limen.models import DispatchLogEntry  # noqa: E402


HEAD = "d47a" * 10
OTHER_HEAD = "e58b" * 10


def trajectory(
    *,
    attempt_id="attempt-orchid-17",
    task_id="TASK-amber-4",
    task_type="analysis",
    labels=("receipt-audit",),
    keeper="keeper-cerulean",
    route="provider-quartz-auto",
    outcome="succeeded",
    predicate_passed=True,
    predicate_head=HEAD,
    receipt_verified=True,
    receipt_head=HEAD,
    exact_commit=HEAD,
):
    return {
        "schema": "limen.execution_trajectory.v1",
        "attempt_id": attempt_id,
        "task_id": task_id,
        "classification": {
            "task_type": task_type,
            "labels": list(labels),
            "workstream": "reacceptance",
        },
        "executing_keeper": keeper,
        "executing_session": "session-mauve-82",
        "provider_route": route,
        "execution_profile": {"capability": "repository-repair", "mode": "bounded"},
        "spend": {"amount": 3.5, "unit": "token-k"},
        "started_at": "2026-07-16T18:00:00Z",
        "ended_at": "2026-07-16T18:20:00Z",
        "outcome": outcome,
        "repository": "signal-garden/orbit-index",
        "exact_commit": exact_commit,
        "pull_request": ("https://github.com/signal-garden/orbit-index/pull/731" if exact_commit is not None else None),
        "terminal_predicate": {
            "command": "verify-orchid --exact-head",
            "passed": predicate_passed,
            "checked_at": "2026-07-16T18:19:00Z",
            "head_sha": predicate_head,
        },
        "receipt": {
            "reference": "receipt://orchid/17",
            "digest": "sha256:umber-citrine",
            "verified": receipt_verified,
            "head_sha": receipt_head,
        },
    }


def test_schema_separates_keeper_attribution_from_provider_route():
    record = ExecutionTrajectory.model_validate(trajectory())
    assert record.schema_version == "limen.execution_trajectory.v1"
    assert record.model_dump(mode="json", by_alias=True)["schema"] == "limen.execution_trajectory.v1"
    assert record.executing_keeper == "keeper-cerulean"
    assert record.provider_route == "provider-quartz-auto"
    assert record.executing_keeper != record.provider_route
    assert verified_value_credit(record) == 0
    assert verified_value_credit(record, receipt_authority=lambda _record: True) == 1


def test_exact_duplicate_attempt_id_counts_once():
    row = trajectory()
    corpus = build_corpus([row, deepcopy(row)])
    assert [record.attempt_id for record in corpus.records] == ["attempt-orchid-17"]
    assert corpus.duplicate_rows == 1
    assert corpus.duplicate_attempt_ids == ("attempt-orchid-17",)
    assert corpus.conflicting_attempt_ids == ()


def test_conflicting_duplicate_attempt_is_excluded_fail_closed():
    first = trajectory()
    conflict = trajectory(outcome="failed")
    corpus = build_corpus([first, conflict])
    assert corpus.records == ()
    assert corpus.conflicting_attempt_ids == ("attempt-orchid-17",)


def test_frozen_classification_cannot_be_rewritten_after_attempt():
    record = ExecutionTrajectory.model_validate(trajectory(task_type="research", labels=("violet", "violet", "amber")))
    assert record.classification.task_type == "research"
    assert record.classification.labels == ("amber", "violet")
    with pytest.raises(ValidationError):
        record.classification.task_type = "code"


@pytest.mark.parametrize(
    "overrides",
    [
        {"outcome": "failed"},
        {"predicate_passed": False},
        {"predicate_head": OTHER_HEAD},
        {"receipt_verified": False},
        {"receipt_head": OTHER_HEAD},
        {"exact_commit": None},
    ],
    ids=[
        "non-success-outcome",
        "predicate-failed",
        "predicate-stale",
        "receipt-unverified",
        "receipt-stale",
        "commit-missing",
    ],
)
def test_unverified_or_non_exact_motion_earns_zero_value(overrides):
    record = ExecutionTrajectory.model_validate(trajectory(**overrides))
    assert verified_value_credit(record) == 0


def test_missing_predicate_or_receipt_earns_zero_value():
    no_predicate = trajectory()
    no_predicate["terminal_predicate"] = None
    no_receipt = trajectory(attempt_id="attempt-orchid-18")
    no_receipt["receipt"] = None
    assert verified_value_credit(ExecutionTrajectory.model_validate(no_predicate)) == 0
    assert verified_value_credit(ExecutionTrajectory.model_validate(no_receipt)) == 0


def test_board_verified_claim_never_substitutes_for_owner_native_receipt_authority():
    record = ExecutionTrajectory.model_validate(trajectory())

    assert record.receipt is not None and record.receipt.verified is True
    assert verified_value_credit(record) == 0
    assert verified_value_credit(record, receipt_authority=lambda _record: False) == 0
    assert (
        verified_value_credit(
            record,
            receipt_authority=lambda _record: (_ for _ in ()).throw(RuntimeError("adapter unavailable")),
        )
        == 0
    )


def test_jsonl_loader_surfaces_invalid_rows_and_deduplicates(tmp_path):
    path = tmp_path / "trajectories.jsonl"
    row = trajectory()
    path.write_text(
        json.dumps(row) + "\n" + "not-json\n" + json.dumps(row) + "\n",
        encoding="utf-8",
    )
    corpus = load_jsonl(path)
    assert len(corpus.records) == 1
    assert corpus.duplicate_rows == 1
    assert corpus.invalid_rows[0]["row"] == 2


def test_wrong_schema_is_invalid_not_silently_coerced():
    row = trajectory()
    row["schema"] = "limen.execution_trajectory.v0"
    corpus = build_corpus([row])
    assert corpus.records == ()
    assert len(corpus.invalid_rows) == 1


def test_missing_source_is_observable_not_zero_work_proof(tmp_path):
    corpus = load_jsonl(tmp_path / "absent.jsonl")
    assert corpus.records == ()
    assert corpus.source_missing is True
    assert corpus.summary()["source_missing"] is True


def _launch(attempt_id: str = "attempt-runtime-orchid") -> DispatchLogEntry:
    return DispatchLogEntry(
        timestamp="2026-07-16T18:00:00Z",
        agent="keeper-cerulean",
        session_id="session-mauve-82",
        status="dispatched",
        attempt_id=attempt_id,
        attempt_classification={"task_type": "verification", "labels": ["receipt-audit"]},
        attempt_repository="signal-garden/orbit-index",
        execution_profile={"mode": "bounded", "verification_strength": 1.0},
    )


def test_runtime_publisher_records_unverified_failure_with_unknown_spend(tmp_path):
    launch = _launch()
    terminal = DispatchLogEntry(
        timestamp="2026-07-16T18:05:00Z",
        agent=launch.agent,
        session_id=launch.session_id,
        status="failed",
        attempt_id=launch.attempt_id,
    )
    task = SimpleNamespace(id="TASK-runtime-1", dispatch_log=[launch, terminal])
    store = TrajectoryStore(tmp_path / "attempts")

    publications, errors = publish_terminal_attempts([task], store)

    assert errors == []
    assert len(publications) == 1
    record = store.load().records[0]
    assert record.outcome == "failed"
    assert record.spend.amount is None
    assert record.spend.unit == "unreported"
    assert verified_value_credit(record) == 0


def test_runtime_publisher_attributes_the_terminal_provider_session(tmp_path):
    launch = _launch("attempt-runtime-session")
    launch.session_id = "reserve"
    terminal = DispatchLogEntry(
        timestamp="2026-07-16T18:05:00Z",
        agent=launch.agent,
        session_id="provider-session-saffron-91",
        status="failed",
        attempt_id=launch.attempt_id,
    )
    store = TrajectoryStore(tmp_path / "attempts")

    _publications, errors = publish_terminal_attempts(
        [SimpleNamespace(id="TASK-runtime-session", dispatch_log=[launch, terminal])],
        store,
    )

    assert errors == []
    assert store.load().records[0].executing_session == "provider-session-saffron-91"


def test_runtime_publisher_infers_legacy_terminal_only_from_single_active_launch(tmp_path):
    launch = _launch("attempt-runtime-inferred")
    terminal = DispatchLogEntry(
        timestamp="2026-07-16T18:05:00Z",
        agent=launch.agent,
        session_id=launch.session_id,
        status="failed_blocked",
    )
    task = SimpleNamespace(id="TASK-runtime-2", dispatch_log=[launch, terminal])

    publications, errors = publish_terminal_attempts([task], TrajectoryStore(tmp_path / "attempts"))

    assert errors == []
    assert [item.attempt_id for item in publications] == ["attempt-runtime-inferred"]


def test_atomic_store_is_idempotent_and_rejects_divergent_attempt_payload(tmp_path):
    store = TrajectoryStore(tmp_path / "attempts")
    record = ExecutionTrajectory.model_validate(trajectory(attempt_id="attempt-atomic-violet"))

    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _index: store.publish(record), range(8)))

    assert sum(item.published for item in receipts) == 1
    assert len(store.load().records) == 1
    conflicting = ExecutionTrajectory.model_validate(trajectory(attempt_id="attempt-atomic-violet", outcome="failed"))
    with pytest.raises(TrajectoryConflictError, match="divergent terminal record"):
        store.publish(conflicting)


def test_runtime_verified_exact_head_receipt_can_earn_one_value_unit(tmp_path):
    launch = _launch("attempt-runtime-verified")
    terminal = DispatchLogEntry(
        timestamp="2026-07-16T18:05:00Z",
        agent=launch.agent,
        session_id=launch.session_id,
        status="done",
        attempt_id=launch.attempt_id,
        trajectory_exact_commit=HEAD,
        trajectory_predicate={
            "command": "sha256:predicate-violet",
            "passed": True,
            "checked_at": "2026-07-16T18:04:00Z",
            "head_sha": HEAD,
        },
        trajectory_receipt={
            "reference": "receipt://runtime/violet",
            "digest": "sha256:receipt-violet",
            "verified": True,
            "head_sha": HEAD,
        },
    )
    task = SimpleNamespace(id="TASK-runtime-3", dispatch_log=[launch, terminal])
    store = TrajectoryStore(tmp_path / "attempts")

    _publications, errors = publish_terminal_attempts([task], store)

    assert errors == []
    record = store.load().records[0]
    assert verified_value_credit(record) == 0
    assert verified_value_credit(record, receipt_authority=lambda _record: True) == 1


def test_heartbeat_does_not_publish_legacy_board_event_credit_claims():
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")

    assert 'scripts/score-dispatch.py"' not in heartbeat
    assert 'scripts/ledger.py"' not in heartbeat
    assert "limen.execution_trajectory.v1" in heartbeat
