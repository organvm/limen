"""Owner-native execution trajectory contract tests."""

from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from limen.execution_trajectory import (
    ExecutionTrajectory,
    OwnerPublication,
    OwnerReceiptSnapshot,
    TrajectoryPublicationError,
    build_corpus,
    publish_bounded,
    trajectory_from_log_entries,
    verified_value_credit,
)
from limen.models import DispatchLogEntry


HEAD = "d47a" * 10
OTHER_HEAD = "e58b" * 10
RECEIPT_DIGEST = "sha256:" + "a" * 64


def trajectory(
    *,
    attempt_id: str = "attempt-orchid-17",
    keeper: str = "keeper-cerulean",
    route: str = "provider-quartz-auto",
    outcome: str = "succeeded",
    exact_commit: str | None = HEAD,
    predicate_passed: bool = True,
    predicate_head: str | None = HEAD,
    receipt_head: str | None = HEAD,
) -> dict[str, object]:
    return {
        "schema": "limen.execution_trajectory.v1",
        "attempt_id": attempt_id,
        "task_id": "TASK-amber-4",
        "classification": {
            "task_type": "analysis",
            "labels": ["receipt-audit"],
            "workstream": "reacceptance",
        },
        "executing_keeper": keeper,
        "executing_session": "session-mauve-82",
        "provider_route": route,
        "execution_profile": {"reasoning_depth": 0.8, "mode": "bounded"},
        "spend": {"amount": 3.5, "unit": "token-k"},
        "started_at": "2026-07-16T18:00:00Z",
        "ended_at": "2026-07-16T18:20:00Z",
        "outcome": outcome,
        "repository": "signal-garden/orbit-index",
        "exact_commit": exact_commit,
        "pull_request": ("https://github.com/signal-garden/orbit-index/pull/731" if exact_commit is not None else None),
        "terminal_predicate": {
            "command_digest": "sha256:predicate-violet",
            "passed": predicate_passed,
            "checked_at": "2026-07-16T18:19:00Z",
            "head_sha": predicate_head,
        },
        "owner_receipt": {
            "owner": "github",
            "reference": "https://github.com/signal-garden/orbit-index/pull/731",
            "digest": RECEIPT_DIGEST,
            "head_sha": receipt_head,
        },
    }


class Authority:
    def __init__(self, *, head: str = HEAD, terminal: bool = True, predicate_passed: bool = True):
        self.head = head
        self.terminal = terminal
        self.predicate_passed = predicate_passed

    def verify(self, claim):
        return OwnerReceiptSnapshot(
            owner=claim.owner,
            reference=claim.reference,
            digest=claim.digest,
            head_sha=self.head,
            terminal=self.terminal,
            predicate_passed=self.predicate_passed,
            verified_at="2026-07-16T18:21:00Z",
        )


def test_one_attempt_counts_once_and_credit_belongs_to_executor_not_route() -> None:
    row = trajectory()
    corpus = build_corpus([row, deepcopy(row)])

    assert len(corpus.records) == 1
    assert corpus.duplicate_rows == 1
    record = corpus.records[0]
    assert record.executing_keeper == "keeper-cerulean"
    assert record.provider_route == "provider-quartz-auto"
    assert corpus.value_by_executor(authority=Authority()) == {"keeper-cerulean": 1}
    assert "provider-quartz-auto" not in corpus.value_by_executor(authority=Authority())


@pytest.mark.parametrize(
    "changes",
    [
        {"outcome": "failed"},
        {"exact_commit": None},
        {"predicate_passed": False},
        {"predicate_head": OTHER_HEAD},
        {"receipt_head": OTHER_HEAD},
    ],
)
def test_motion_or_non_exact_evidence_earns_zero(changes: dict[str, object]) -> None:
    record = ExecutionTrajectory.model_validate(trajectory(**changes))
    assert verified_value_credit(record, authority=Authority()) == 0


def test_owner_claim_is_not_self_verifying() -> None:
    record = ExecutionTrajectory.model_validate(trajectory())
    assert verified_value_credit(record) == 0
    assert verified_value_credit(record, authority=Authority(head=OTHER_HEAD)) == 0
    assert verified_value_credit(record, authority=Authority(terminal=False)) == 0
    assert verified_value_credit(record, authority=Authority(predicate_passed=False)) == 0


def test_conflicting_duplicate_attempt_is_excluded_fail_closed() -> None:
    corpus = build_corpus([trajectory(), trajectory(outcome="failed")])
    assert corpus.records == ()
    assert corpus.conflicting_attempt_ids == ("attempt-orchid-17",)


class AtomicOwner:
    def __init__(self) -> None:
        self.records: dict[str, bytes] = {}
        self.lock = threading.Lock()

    def read_many(self, attempt_ids):
        with self.lock:
            return {attempt_id: self.records[attempt_id] for attempt_id in attempt_ids if attempt_id in self.records}

    def publish_atomic(self, payloads):
        with self.lock:
            if any(attempt_id in self.records for attempt_id in payloads):
                raise TrajectoryPublicationError("compare-and-set lost")
            self.records.update(payloads)
            now = datetime.now(timezone.utc)
            return {
                attempt_id: OwnerPublication(
                    attempt_id=attempt_id,
                    reference=f"https://owner.example/attempts/{attempt_id}",
                    digest="sha256:" + hashlib.sha256(payload).hexdigest(),
                    published_at=now,
                )
                for attempt_id, payload in payloads.items()
            }


def test_owner_publication_is_atomic_bounded_and_idempotent() -> None:
    owner = AtomicOwner()
    rows = [trajectory(attempt_id="attempt-a"), trajectory(attempt_id="attempt-b")]

    first = publish_bounded(rows, owner, max_records=2, max_bytes=10_000)
    second = publish_bounded(reversed(rows), owner, max_records=2, max_bytes=10_000)

    assert [item.attempt_id for item in first.published] == ["attempt-a", "attempt-b"]
    assert second.published == ()
    assert second.already_present == ("attempt-a", "attempt-b")
    assert set(owner.records) == {"attempt-a", "attempt-b"}


def test_parallel_publication_never_creates_duplicate_attempts() -> None:
    owner = AtomicOwner()
    row = trajectory(attempt_id="attempt-concurrent")

    def publish() -> str:
        try:
            batch = publish_bounded([row], owner)
            return "published" if batch.published else "present"
        except TrajectoryPublicationError:
            return "lost-cas"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _index: publish(), range(8)))

    assert outcomes.count("published") == 1
    assert len(owner.records) == 1


def test_publication_rejects_divergence_and_bounds_before_owner_write() -> None:
    owner = AtomicOwner()
    publish_bounded([trajectory()], owner)
    with pytest.raises(TrajectoryPublicationError, match="divergent"):
        publish_bounded([trajectory(outcome="failed")], owner)
    with pytest.raises(TrajectoryPublicationError, match="record bound"):
        publish_bounded([trajectory(attempt_id="attempt-a"), trajectory(attempt_id="attempt-b")], owner, max_records=1)
    with pytest.raises(TrajectoryPublicationError, match="byte bound"):
        publish_bounded([trajectory(attempt_id="attempt-c")], owner, max_bytes=10)


def test_log_conversion_freezes_executor_and_rejects_mismatched_attempt() -> None:
    launch = DispatchLogEntry(
        timestamp="2026-07-16T18:00:00Z",
        agent="keeper-cerulean",
        session_id="reserve",
        status="dispatched",
        attempt_id="attempt-runtime",
        attempt_classification={"task_type": "verification", "labels": ["receipt-audit"]},
        attempt_repository="signal-garden/orbit-index",
        execution_profile={"reasoning_depth": 0.8},
    )
    terminal = DispatchLogEntry(
        timestamp="2026-07-16T18:05:00Z",
        agent="different-observer",
        session_id="provider-session",
        status="done",
        attempt_id="attempt-runtime",
        trajectory_exact_commit=HEAD,
        trajectory_pull_request="https://github.com/signal-garden/orbit-index/pull/731",
        trajectory_predicate={
            "command_digest": "sha256:predicate",
            "passed": True,
            "checked_at": "2026-07-16T18:04:00Z",
            "head_sha": HEAD,
        },
        trajectory_owner_receipt={
            "owner": "github",
            "reference": "https://github.com/signal-garden/orbit-index/pull/731",
            "digest": RECEIPT_DIGEST,
            "head_sha": HEAD,
        },
    )

    record = trajectory_from_log_entries(task_id="TASK-runtime", launch=launch, terminal=terminal)

    assert record.executing_keeper == "keeper-cerulean"
    assert record.executing_session == "provider-session"
    terminal.attempt_id = "attempt-other"
    with pytest.raises(ValueError, match="does not match"):
        trajectory_from_log_entries(task_id="TASK-runtime", launch=launch, terminal=terminal)
