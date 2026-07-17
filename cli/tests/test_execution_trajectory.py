"""Owner-native execution trajectory contract tests."""

from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from limen.execution_trajectory import (
    ExecutionTrajectory,
    OwnerPublication,
    OwnerReceiptSnapshot,
    OwnerTrajectorySnapshot,
    TrajectoryPublicationError,
    build_corpus,
    publish_bounded,
    record_digest,
    trajectory_from_log_entries,
    verified_value_credit,
)
from limen.models import DispatchLogEntry


HEAD = "d47a" * 10
OTHER_HEAD = "e58b" * 10
RECEIPT_DIGEST = "sha256:" + "a" * 64
PREDICATE_DIGEST = "sha256:" + "b" * 64
FRESH_NOW = datetime(2026, 7, 16, 18, 21, tzinfo=timezone.utc)


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
    task_id: str = "TASK-amber-4",
    repository: str = "signal-garden/orbit-index",
    predicate_digest: str = PREDICATE_DIGEST,
) -> dict[str, object]:
    return {
        "schema": "limen.execution_trajectory.v1",
        "attempt_id": attempt_id,
        "task_id": task_id,
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
        "repository": repository,
        "exact_commit": exact_commit,
        "pull_request": (f"https://github.com/{repository}/pull/731" if exact_commit is not None else None),
        "terminal_predicate": {
            "command_digest": predicate_digest,
            "passed": predicate_passed,
            "checked_at": "2026-07-16T18:19:00Z",
            "head_sha": predicate_head,
        },
        "owner_receipt": {
            "owner": "github",
            "reference": "https://github.com/signal-garden/orbit-index/pull/731",
            "digest": RECEIPT_DIGEST,
            "head_sha": receipt_head,
            "attempt_id": attempt_id,
            "task_id": task_id,
            "repository": repository,
            "predicate_digest": predicate_digest,
        },
    }


class Authority:
    def __init__(
        self,
        *,
        head: str = HEAD,
        terminal: bool = True,
        predicate_passed: bool = True,
        verified_at: datetime | None = None,
        binding_overrides: dict[str, str] | None = None,
    ):
        self.head = head
        self.terminal = terminal
        self.predicate_passed = predicate_passed
        self.verified_at = verified_at or datetime.now(timezone.utc)
        self.binding_overrides = binding_overrides or {}
        self.requests: list[dict[str, str]] = []

    def verify(
        self,
        claim,
        *,
        attempt_id: str,
        task_id: str,
        repository: str,
        predicate_digest: str,
    ):
        self.requests.append(
            {
                "attempt_id": attempt_id,
                "task_id": task_id,
                "repository": repository,
                "predicate_digest": predicate_digest,
            }
        )
        return OwnerReceiptSnapshot(
            owner=claim.owner,
            reference=claim.reference,
            digest=claim.digest,
            head_sha=self.head,
            attempt_id=self.binding_overrides.get("attempt_id", claim.attempt_id),
            task_id=self.binding_overrides.get("task_id", claim.task_id),
            repository=self.binding_overrides.get("repository", claim.repository),
            predicate_digest=self.binding_overrides.get(
                "predicate_digest",
                claim.predicate_digest,
            ),
            terminal=self.terminal,
            predicate_passed=self.predicate_passed,
            verified_at=self.verified_at,
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


@pytest.mark.parametrize(
    ("binding", "other"),
    [
        ("attempt_id", "attempt-replayed"),
        ("task_id", "TASK-replayed"),
        ("repository", "other-owner/other-repo"),
        ("predicate_digest", "sha256:" + "c" * 64),
    ],
)
def test_owner_authority_must_bind_every_attempt_identity(binding: str, other: str) -> None:
    record = ExecutionTrajectory.model_validate(trajectory())
    authority = Authority(binding_overrides={binding: other})

    assert verified_value_credit(record, authority=authority) == 0
    assert authority.requests == [
        {
            "attempt_id": record.attempt_id,
            "task_id": record.task_id,
            "repository": record.repository,
            "predicate_digest": record.terminal_predicate.command_digest,
        }
    ]


def test_owner_receipt_cannot_be_replayed_for_another_attempt() -> None:
    original = ExecutionTrajectory.model_validate(trajectory(attempt_id="attempt-original"))
    replayed = ExecutionTrajectory.model_validate(trajectory(attempt_id="attempt-replayed"))
    original_snapshot = Authority(verified_at=FRESH_NOW).verify(
        original.owner_receipt,
        attempt_id=original.attempt_id,
        task_id=original.task_id,
        repository=original.repository,
        predicate_digest=original.terminal_predicate.command_digest,
    )

    class ReplayAuthority:
        def verify(self, _claim, **_binding):
            return original_snapshot

    authority = ReplayAuthority()
    assert verified_value_credit(original, authority=authority, now=FRESH_NOW) == 1
    assert verified_value_credit(replayed, authority=authority, now=FRESH_NOW) == 0


def test_owner_snapshot_must_be_fresh_and_postdate_the_predicate() -> None:
    record = ExecutionTrajectory.model_validate(trajectory())

    assert (
        verified_value_credit(
            record,
            authority=Authority(verified_at=FRESH_NOW - timedelta(minutes=6)),
            now=FRESH_NOW,
        )
        == 0
    )
    assert (
        verified_value_credit(
            record,
            authority=Authority(verified_at=datetime(2026, 7, 16, 18, 18, tzinfo=timezone.utc)),
            now=FRESH_NOW,
        )
        == 0
    )
    assert (
        verified_value_credit(
            record,
            authority=Authority(verified_at=FRESH_NOW),
            now=FRESH_NOW,
        )
        == 1
    )


def test_receipt_claim_binding_and_predicate_digest_fail_closed() -> None:
    mismatched = trajectory()
    mismatched["owner_receipt"]["attempt_id"] = "attempt-other"
    with pytest.raises(ValidationError, match="binding"):
        ExecutionTrajectory.model_validate(mismatched)

    weak_digest = trajectory()
    weak_digest["terminal_predicate"]["command_digest"] = "sha256:not-a-digest"
    weak_digest["owner_receipt"]["predicate_digest"] = "sha256:not-a-digest"
    with pytest.raises(ValidationError, match="command_digest"):
        ExecutionTrajectory.model_validate(weak_digest)


def test_conflicting_duplicate_attempt_is_excluded_fail_closed() -> None:
    corpus = build_corpus([trajectory(), trajectory(outcome="failed")])
    assert corpus.records == ()
    assert corpus.conflicting_attempt_ids == ("attempt-orchid-17",)


class AtomicOwner:
    def __init__(self) -> None:
        self.records: dict[str, bytes] = {}
        self.lock = threading.Lock()
        self.version = 0

    def read_many(self, attempt_ids):
        with self.lock:
            return OwnerTrajectorySnapshot(
                token=str(self.version),
                records={
                    attempt_id: self.records[attempt_id] for attempt_id in attempt_ids if attempt_id in self.records
                },
            )

    def publish_atomic(self, payloads, *, snapshot_token):
        with self.lock:
            if snapshot_token != str(self.version):
                raise TrajectoryPublicationError("compare-and-set lost")
            if any(attempt_id in self.records for attempt_id in payloads):
                raise TrajectoryPublicationError("compare-and-set lost")
            self.records.update(payloads)
            self.version += 1
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


def test_publication_stops_at_record_and_raw_input_bounds_without_draining() -> None:
    owner = AtomicOwner()
    consumed: list[str] = []

    def too_many_records():
        consumed.append("a")
        yield trajectory(attempt_id="attempt-a")
        consumed.append("b")
        yield trajectory(attempt_id="attempt-b")
        raise AssertionError("publisher drained input after crossing record bound")

    with pytest.raises(TrajectoryPublicationError, match="record bound"):
        publish_bounded(too_many_records(), owner, max_records=1)
    assert consumed == ["a", "b"]

    consumed.clear()

    def duplicate_stream():
        for index in range(10):
            consumed.append(str(index))
            yield trajectory(attempt_id="attempt-duplicate")
        raise AssertionError("publisher drained unbounded duplicate input")

    with pytest.raises(TrajectoryPublicationError, match="input row bound"):
        publish_bounded(
            duplicate_stream(),
            owner,
            max_records=1,
            max_input_rows=3,
        )
    assert consumed == ["0", "1", "2"]
    assert owner.records == {}


def test_execution_profile_is_deeply_immutable_and_canonical_json() -> None:
    row = trajectory()
    mutable_profile = {
        "nested": {"z": [3, {"a": True}], "a": None},
        "mode": "bounded",
    }
    row["execution_profile"] = mutable_profile
    record = ExecutionTrajectory.model_validate(row)
    digest = record_digest(record)

    mutable_profile["nested"]["z"][1]["a"] = False
    mutable_profile["new"] = "late mutation"
    assert record_digest(record) == digest
    assert record.model_dump(mode="json")["execution_profile"] == {
        "mode": "bounded",
        "nested": {"a": None, "z": [3, {"a": True}]},
    }
    with pytest.raises(TypeError):
        record.execution_profile["mode"] = "mutated"
    with pytest.raises(TypeError):
        record.execution_profile["nested"]["z"][1]["a"] = False

    reordered = trajectory()
    reordered["execution_profile"] = {
        "mode": "bounded",
        "nested": {"a": None, "z": [3, {"a": True}]},
    }
    assert record_digest(ExecutionTrajectory.model_validate(reordered)) == digest

    non_json = trajectory()
    non_json["execution_profile"] = {"routes": {"b", "a"}}
    with pytest.raises(ValidationError, match="non-JSON type set"):
        ExecutionTrajectory.model_validate(non_json)


def test_log_conversion_freezes_launch_executor_session_and_provider_route() -> None:
    launch = DispatchLogEntry(
        timestamp="2026-07-16T18:00:00Z",
        agent="reservation-observer",
        session_id="reservation-row",
        status="dispatched",
        attempt_id="attempt-runtime",
        attempt_classification={"task_type": "verification", "labels": ["receipt-audit"]},
        attempt_repository="signal-garden/orbit-index",
        execution_profile={"reasoning_depth": 0.8},
        executing_keeper="keeper-cerulean",
        executing_session="launch-session",
        provider_route="provider-lane",
    )
    terminal = DispatchLogEntry(
        timestamp="2026-07-16T18:05:00Z",
        agent="different-observer",
        session_id="provider-session",
        status="done",
        attempt_id="attempt-runtime",
        selected_model="provider/model-x",
        trajectory_exact_commit=HEAD,
        trajectory_pull_request="https://github.com/signal-garden/orbit-index/pull/731",
        trajectory_predicate={
            "command_digest": PREDICATE_DIGEST,
            "passed": True,
            "checked_at": "2026-07-16T18:04:00Z",
            "head_sha": HEAD,
        },
        trajectory_owner_receipt={
            "owner": "github",
            "reference": "https://github.com/signal-garden/orbit-index/pull/731",
            "digest": RECEIPT_DIGEST,
            "head_sha": HEAD,
            "attempt_id": "attempt-runtime",
            "task_id": "TASK-runtime",
            "repository": "signal-garden/orbit-index",
            "predicate_digest": PREDICATE_DIGEST,
        },
    )

    record = trajectory_from_log_entries(task_id="TASK-runtime", launch=launch, terminal=terminal)

    assert record.executing_keeper == "keeper-cerulean"
    assert record.executing_session == "launch-session"
    assert record.provider_route == "provider/model-x"
    terminal.attempt_id = "attempt-other"
    with pytest.raises(ValueError, match="does not match"):
        trajectory_from_log_entries(task_id="TASK-runtime", launch=launch, terminal=terminal)
