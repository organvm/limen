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
    launch_attempt_id,
    launch_identity_digest,
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
CONTRACT_HASH = "c" * 64
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
    execution_profile: dict[str, object] | None = None,
) -> dict[str, object]:
    classification = {
        "task_type": "analysis",
        "labels": ["receipt-audit"],
        "workstream": "reacceptance",
    }
    execution_profile = execution_profile or {"reasoning_depth": 0.8, "mode": "bounded"}
    started_at = datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc)
    executing_session = f"session-{attempt_id}"
    route_selection_source = "dispatch_target_agent"
    launch_facts = {
        "task_id": task_id,
        "contract_hash": CONTRACT_HASH,
        "classification": classification,
        "repository": repository,
        "execution_profile": execution_profile,
        "executing_keeper": keeper,
        "executing_session": executing_session,
        "provider_route": route,
        "route_selection_source": route_selection_source,
        "started_at": started_at,
    }
    bound_attempt_id = launch_attempt_id(**launch_facts)
    row: dict[str, object] = {
        "schema": "limen.execution_trajectory.v2",
        "attempt_id": bound_attempt_id,
        "task_id": task_id,
        "classification": classification,
        "executing_keeper": keeper,
        "executing_session": executing_session,
        "provider_route": route,
        "route_selection_source": route_selection_source,
        "attempt_contract_hash": CONTRACT_HASH,
        "execution_profile": execution_profile,
        "spend": {"amount": 3.5, "unit": "token-k"},
        "started_at": started_at,
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
            "attempt_id": bound_attempt_id,
            "task_id": task_id,
            "repository": repository,
            "predicate_digest": predicate_digest,
        },
    }
    row["attempt_identity_digest"] = launch_identity_digest(
        attempt_id=bound_attempt_id,
        **launch_facts,
    )
    return row


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


@pytest.mark.parametrize(
    ("checked_at", "expected"),
    [
        ("2026-07-16T17:59:59Z", 0),
        ("2026-07-16T18:00:00Z", 1),
        ("2026-07-16T18:20:00Z", 1),
        ("2026-07-16T18:20:01Z", 0),
    ],
)
def test_predicate_must_be_checked_within_attempt_interval(checked_at: str, expected: int) -> None:
    row = trajectory()
    row["terminal_predicate"]["checked_at"] = checked_at
    record = ExecutionTrajectory.model_validate(row)

    assert verified_value_credit(record, authority=Authority(verified_at=FRESH_NOW), now=FRESH_NOW) == expected


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
    first = trajectory()
    corpus = build_corpus([first, trajectory(outcome="failed")])
    assert corpus.records == ()
    assert corpus.conflicting_attempt_ids == (first["attempt_id"],)


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
    attempt_ids = tuple(sorted(str(row["attempt_id"]) for row in rows))

    first = publish_bounded(rows, owner, max_records=2, max_bytes=10_000)
    second = publish_bounded(reversed(rows), owner, max_records=2, max_bytes=10_000)

    assert [item.attempt_id for item in first.published] == list(attempt_ids)
    assert second.published == ()
    assert second.already_present == attempt_ids
    assert set(owner.records) == set(attempt_ids)


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

    def exactly_bounded_stream():
        for index in range(3):
            consumed.append(str(index))
            yield trajectory(attempt_id=f"attempt-exact-{index}")

    exact = build_corpus(exactly_bounded_stream(), max_input_rows=3)
    assert len(exact.records) == 3
    assert consumed == ["0", "1", "2"]

    consumed.clear()

    def one_over_stream():
        for index in range(10):
            consumed.append(str(index))
            yield trajectory(attempt_id="attempt-duplicate")
            if index == 3:
                raise AssertionError("publisher drained input beyond the N+1 overflow row")

    with pytest.raises(TrajectoryPublicationError, match="input row bound"):
        publish_bounded(
            one_over_stream(),
            owner,
            max_records=1,
            max_input_rows=3,
        )
    assert consumed == ["0", "1", "2", "3"]
    assert owner.records == {}


def test_execution_profile_is_deeply_immutable_and_canonical_json() -> None:
    mutable_profile = {
        "nested": {"z": [3, {"a": True}], "a": None},
        "mode": "bounded",
    }
    row = trajectory(execution_profile=mutable_profile)
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

    reordered = trajectory(
        execution_profile={
            "mode": "bounded",
            "nested": {"a": None, "z": [3, {"a": True}]},
        }
    )
    assert record_digest(ExecutionTrajectory.model_validate(reordered)) == digest

    non_json = trajectory()
    non_json["execution_profile"] = {"routes": {"b", "a"}}
    with pytest.raises(ValidationError, match="non-JSON type set"):
        ExecutionTrajectory.model_validate(non_json)


def test_attempt_identifier_binds_every_launch_attribution() -> None:
    facts = {
        "task_id": "TASK-bound",
        "contract_hash": CONTRACT_HASH,
        "classification": {"task_type": "verification", "labels": ["receipt-audit"]},
        "repository": "signal-garden/orbit-index",
        "execution_profile": {"reasoning_depth": 0.8},
        "executing_keeper": "keeper-cerulean",
        "executing_session": "launch-session",
        "provider_route": "provider-lane",
        "route_selection_source": "dispatch_target_agent",
        "started_at": datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc),
    }
    original = launch_attempt_id(**facts)

    for field, replacement in (
        ("executing_keeper", "keeper-mutated"),
        ("executing_session", "session-mutated"),
        ("provider_route", "provider-mutated"),
        ("route_selection_source", "source-mutated"),
    ):
        assert launch_attempt_id(**{**facts, field: replacement}) != original


def test_recomputed_digest_cannot_authorize_an_arbitrary_attempt_identifier() -> None:
    row = trajectory()
    forged_attempt_id = "attempt-forged"
    row["attempt_id"] = forged_attempt_id
    row["owner_receipt"]["attempt_id"] = forged_attempt_id
    row["attempt_identity_digest"] = launch_identity_digest(
        attempt_id=forged_attempt_id,
        task_id=row["task_id"],
        contract_hash=row["attempt_contract_hash"],
        classification=row["classification"],
        repository=row["repository"],
        execution_profile=row["execution_profile"],
        executing_keeper=row["executing_keeper"],
        executing_session=row["executing_session"],
        provider_route=row["provider_route"],
        route_selection_source=row["route_selection_source"],
        started_at=row["started_at"],
    )

    with pytest.raises(ValidationError, match="attempt identifier"):
        ExecutionTrajectory.model_validate(row)


def test_log_conversion_freezes_launch_executor_session_and_provider_route() -> None:
    started_at = datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc)
    classification = {"task_type": "verification", "labels": ["receipt-audit"]}
    profile = {"reasoning_depth": 0.8}
    launch_facts = {
        "task_id": "TASK-runtime",
        "contract_hash": CONTRACT_HASH,
        "classification": classification,
        "repository": "signal-garden/orbit-index",
        "execution_profile": profile,
        "executing_keeper": "keeper-cerulean",
        "executing_session": "launch-session",
        "provider_route": "provider-lane",
        "route_selection_source": "dispatch_target_agent",
        "started_at": started_at,
    }
    attempt_id = launch_attempt_id(**launch_facts)
    launch = DispatchLogEntry(
        timestamp=started_at,
        agent="reservation-observer",
        session_id="reservation-row",
        status="dispatched",
        attempt_id=attempt_id,
        attempt_classification=classification,
        attempt_repository="signal-garden/orbit-index",
        attempt_contract_hash=CONTRACT_HASH,
        attempt_identity_digest=launch_identity_digest(attempt_id=attempt_id, **launch_facts),
        execution_profile=profile,
        executing_keeper="keeper-cerulean",
        executing_session="launch-session",
        provider_route="provider-lane",
        route_selection_source="dispatch_target_agent",
    )
    terminal = launch.model_copy(
        update={
            "timestamp": "2026-07-16T18:05:00Z",
            "agent": "different-observer",
            "session_id": "provider-session",
            "status": "done",
            "selected_model": "provider/model-x",
            "trajectory_exact_commit": HEAD,
            "trajectory_pull_request": "https://github.com/signal-garden/orbit-index/pull/731",
            "trajectory_predicate": {
                "command_digest": PREDICATE_DIGEST,
                "passed": True,
                "checked_at": "2026-07-16T18:04:00Z",
                "head_sha": HEAD,
            },
            "trajectory_owner_receipt": {
                "owner": "github",
                "reference": "https://github.com/signal-garden/orbit-index/pull/731",
                "digest": RECEIPT_DIGEST,
                "head_sha": HEAD,
                "attempt_id": attempt_id,
                "task_id": "TASK-runtime",
                "repository": "signal-garden/orbit-index",
                "predicate_digest": PREDICATE_DIGEST,
            },
        }
    )

    record = trajectory_from_log_entries(task_id="TASK-runtime", launch=launch, terminal=terminal)

    assert record.executing_keeper == "keeper-cerulean"
    assert record.executing_session == "launch-session"
    assert record.provider_route == "provider-lane"
    assert record.route_selection_source == "dispatch_target_agent"
    assert record.outcome == "succeeded"

    for status, explicit_outcome in (
        ("done", "failed"),
        ("failed", "succeeded"),
        ("failed_blocked", "failed"),
        ("needs_human", "succeeded"),
    ):
        mismatched_lifecycle = terminal.model_copy(
            update={
                "status": status,
                "trajectory_outcome": explicit_outcome,
            }
        )
        with pytest.raises(ValueError, match="status and trajectory outcome disagree"):
            trajectory_from_log_entries(
                task_id="TASK-runtime",
                launch=launch,
                terminal=mismatched_lifecycle,
            )

    for nonterminal_status in ("open", "dispatched", "in_progress", "archived"):
        nonterminal = terminal.model_copy(
            update={
                "status": nonterminal_status,
                "trajectory_outcome": "succeeded",
            }
        )
        with pytest.raises(ValueError, match="canonical terminal lifecycle status"):
            trajectory_from_log_entries(task_id="TASK-runtime", launch=launch, terminal=nonterminal)

    with pytest.raises(ValueError, match="persisted identity"):
        trajectory_from_log_entries(task_id="TASK-other", launch=launch, terminal=terminal)

    for field, mutation in (
        ("executing_keeper", "post-launch-mutator"),
        ("executing_session", "post-launch-session"),
        ("provider_route", "post-launch-provider"),
        ("route_selection_source", "post-launch-source"),
    ):
        mutated_launch = launch.model_copy(update={field: mutation})
        with pytest.raises(ValueError, match="persisted identity"):
            trajectory_from_log_entries(task_id="TASK-runtime", launch=mutated_launch, terminal=terminal)

    for field in (
        "attempt_classification",
        "attempt_repository",
        "attempt_contract_hash",
        "attempt_identity_digest",
        "execution_profile",
        "executing_keeper",
        "executing_session",
        "provider_route",
        "route_selection_source",
    ):
        missing_terminal_field = terminal.model_copy(update={field: None})
        with pytest.raises(ValueError, match=f"terminal {field} diverges"):
            trajectory_from_log_entries(
                task_id="TASK-runtime",
                launch=launch,
                terminal=missing_terminal_field,
            )

    terminal.attempt_id = "attempt-other"
    with pytest.raises(ValueError, match="does not match"):
        trajectory_from_log_entries(task_id="TASK-runtime", launch=launch, terminal=terminal)
