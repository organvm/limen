"""Owner-native, immutable execution-attempt trajectories.

The task board transports attempt lifecycle events; it is not value authority and
is not the publication owner. Terminal trajectories are published through an
owner adapter that provides atomic compare-and-set custody. No default local
shadow store exists.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Literal, Mapping, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SCHEMA = "limen.execution_trajectory.v1"
_TERMINAL_OUTCOMES = frozenset({"succeeded", "failed", "blocked", "superseded"})
_STATUS_OUTCOME = {
    "done": "succeeded",
    "failed": "failed",
    "failed_blocked": "blocked",
    "needs_human": "blocked",
}


def _is_sha(value: str | None) -> bool:
    return bool(value and len(value) == 40 and all(character in "0123456789abcdef" for character in value))


def _canonical_bytes(record: "ExecutionTrajectory") -> bytes:
    payload = record.model_dump(mode="json", by_alias=True)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def record_digest(record: "ExecutionTrajectory") -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(record)).hexdigest()


class FrozenTaskClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_type: str = Field(min_length=1, max_length=128)
    labels: tuple[str, ...] = ()
    workstream: str | None = Field(default=None, max_length=128)

    @field_validator("labels", mode="before")
    @classmethod
    def normalize_labels(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("labels must be a sequence")
        return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


class ExecutionSpend(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: float | None = Field(default=None, ge=0)
    unit: str = Field(default="unreported", min_length=1, max_length=64)

    @model_validator(mode="after")
    def unknown_is_not_zero(self) -> "ExecutionSpend":
        if (self.amount is None) != (self.unit == "unreported"):
            raise ValueError("unknown spend uses amount=null and unit=unreported")
        return self


class PredicateVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_digest: str = Field(min_length=8, max_length=256)
    passed: bool
    checked_at: datetime
    head_sha: str | None = None

    @field_validator("checked_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("checked_at must include a timezone")
        return value


class OwnerReceiptClaim(BaseModel):
    """Untrusted receipt identity transported by the attempt event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str = Field(min_length=1, max_length=128)
    reference: str = Field(min_length=1, max_length=2048)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    head_sha: str | None = None

    @model_validator(mode="after")
    def exact_head_if_present(self) -> "OwnerReceiptClaim":
        if self.head_sha is not None and not _is_sha(self.head_sha):
            raise ValueError("owner receipt head_sha must be a 40-hex commit")
        return self


class OwnerReceiptSnapshot(BaseModel):
    """Fresh evidence returned by the owner adapter, never copied from the board."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str = Field(min_length=1, max_length=128)
    reference: str = Field(min_length=1, max_length=2048)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    head_sha: str = Field(min_length=40, max_length=40)
    terminal: bool
    predicate_passed: bool
    verified_at: datetime

    @field_validator("head_sha")
    @classmethod
    def exact_head(cls, value: str) -> str:
        if not _is_sha(value):
            raise ValueError("owner snapshot head_sha must be a 40-hex commit")
        return value

    @field_validator("verified_at")
    @classmethod
    def verified_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("verified_at must include a timezone")
        return value


class ExecutionTrajectory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: Literal["limen.execution_trajectory.v1"] = Field(
        default=SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    attempt_id: str = Field(min_length=1, max_length=192)
    task_id: str = Field(min_length=1, max_length=192)
    classification: FrozenTaskClassification
    executing_keeper: str = Field(min_length=1, max_length=128)
    executing_session: str = Field(min_length=1, max_length=256)
    provider_route: str = Field(min_length=1, max_length=128)
    execution_profile: dict[str, Any] = Field(default_factory=dict)
    spend: ExecutionSpend = Field(default_factory=ExecutionSpend)
    started_at: datetime
    ended_at: datetime
    outcome: Literal["succeeded", "failed", "blocked", "superseded"]
    repository: str | None = Field(default=None, min_length=3, max_length=256)
    exact_commit: str | None = None
    pull_request: str | None = Field(default=None, min_length=1, max_length=2048)
    terminal_predicate: PredicateVerification | None = None
    owner_receipt: OwnerReceiptClaim | None = None

    @field_validator("started_at", "ended_at")
    @classmethod
    def trajectory_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("trajectory timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def identities_are_exact(self) -> "ExecutionTrajectory":
        if self.ended_at < self.started_at:
            raise ValueError("ended_at precedes started_at")
        if self.repository is not None:
            parts = self.repository.split("/")
            if len(parts) != 2 or not all(parts):
                raise ValueError("repository must be exact OWNER/NAME")
        if self.exact_commit is not None and (not _is_sha(self.exact_commit) or self.repository is None):
            raise ValueError("exact_commit requires a repository and 40-hex SHA")
        if self.pull_request is not None:
            expected = f"https://github.com/{self.repository}/pull/"
            if self.exact_commit is None or not self.pull_request.startswith(expected):
                raise ValueError("pull_request must match repository and exact_commit")
        return self


class ReceiptAuthority(Protocol):
    def verify(self, claim: OwnerReceiptClaim) -> OwnerReceiptSnapshot | None: ...


def verified_value_credit(
    trajectory: ExecutionTrajectory,
    *,
    authority: ReceiptAuthority | None = None,
) -> int:
    """Grant one unit only from fresh owner evidence bound to the exact attempt head."""

    commit = trajectory.exact_commit
    predicate = trajectory.terminal_predicate
    claim = trajectory.owner_receipt
    if (
        trajectory.outcome != "succeeded"
        or not commit
        or predicate is None
        or not predicate.passed
        or predicate.head_sha != commit
        or claim is None
        or claim.head_sha != commit
        or authority is None
    ):
        return 0
    try:
        snapshot = authority.verify(claim)
    except Exception:
        return 0
    if snapshot is None:
        return 0
    return int(
        snapshot.owner == claim.owner
        and snapshot.reference == claim.reference
        and snapshot.digest == claim.digest
        and snapshot.head_sha == commit
        and snapshot.terminal
        and snapshot.predicate_passed
    )


@dataclass(frozen=True)
class TrajectoryCorpus:
    records: tuple[ExecutionTrajectory, ...]
    duplicate_rows: int = 0
    duplicate_attempt_ids: tuple[str, ...] = ()
    conflicting_attempt_ids: tuple[str, ...] = ()
    invalid_rows: tuple[dict[str, object], ...] = ()

    def value_by_executor(self, *, authority: ReceiptAuthority | None = None) -> dict[str, int]:
        credit: dict[str, int] = {}
        for record in self.records:
            value = verified_value_credit(record, authority=authority)
            credit[record.executing_keeper] = credit.get(record.executing_keeper, 0) + value
        return credit


def build_corpus(rows: Iterable[object]) -> TrajectoryCorpus:
    """Deduplicate by attempt identity and exclude every divergent identity."""

    accepted: dict[str, tuple[ExecutionTrajectory, bytes]] = {}
    duplicates: set[str] = set()
    conflicts: set[str] = set()
    invalid: list[dict[str, object]] = []
    duplicate_rows = 0
    for row_number, raw in enumerate(rows, start=1):
        try:
            record = raw if isinstance(raw, ExecutionTrajectory) else ExecutionTrajectory.model_validate(raw)
        except ValidationError as exc:
            invalid.append({"row": row_number, "error": str(exc)})
            continue
        payload = _canonical_bytes(record)
        if record.attempt_id in conflicts:
            duplicate_rows += 1
            continue
        previous = accepted.get(record.attempt_id)
        if previous is None:
            accepted[record.attempt_id] = (record, payload)
            continue
        duplicate_rows += 1
        duplicates.add(record.attempt_id)
        if previous[1] != payload:
            conflicts.add(record.attempt_id)
            accepted.pop(record.attempt_id, None)
    return TrajectoryCorpus(
        records=tuple(accepted[key][0] for key in sorted(accepted)),
        duplicate_rows=duplicate_rows,
        duplicate_attempt_ids=tuple(sorted(duplicates)),
        conflicting_attempt_ids=tuple(sorted(conflicts)),
        invalid_rows=tuple(invalid),
    )


def new_attempt_id() -> str:
    return f"attempt-{uuid.uuid4()}"


@dataclass(frozen=True)
class OwnerPublication:
    attempt_id: str
    reference: str
    digest: str
    published_at: datetime


class OwnerTrajectoryAdapter(Protocol):
    """Owner-native compare-and-set publication boundary."""

    def read_many(self, attempt_ids: Sequence[str]) -> Mapping[str, bytes]: ...

    def publish_atomic(self, payloads: Mapping[str, bytes]) -> Mapping[str, OwnerPublication]: ...


class TrajectoryPublicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicationBatch:
    published: tuple[OwnerPublication, ...]
    already_present: tuple[str, ...]
    record_count: int
    byte_count: int


def publish_bounded(
    rows: Iterable[object],
    adapter: OwnerTrajectoryAdapter,
    *,
    max_records: int = 100,
    max_bytes: int = 1_000_000,
) -> PublicationBatch:
    """Atomically publish a finite, conflict-free batch through its owner adapter."""

    corpus = build_corpus(rows)
    if corpus.invalid_rows or corpus.conflicting_attempt_ids:
        raise TrajectoryPublicationError("trajectory batch contains invalid or conflicting attempts")
    if len(corpus.records) > max_records:
        raise TrajectoryPublicationError("trajectory publication exceeds record bound")
    payloads = {record.attempt_id: _canonical_bytes(record) for record in corpus.records}
    byte_count = sum(len(payload) for payload in payloads.values())
    if byte_count > max_bytes:
        raise TrajectoryPublicationError("trajectory publication exceeds byte bound")

    existing = dict(adapter.read_many(tuple(sorted(payloads))))
    already_present: list[str] = []
    pending: dict[str, bytes] = {}
    for attempt_id, payload in payloads.items():
        prior = existing.get(attempt_id)
        if prior is None:
            pending[attempt_id] = payload
        elif prior == payload:
            already_present.append(attempt_id)
        else:
            raise TrajectoryPublicationError(f"owner already contains divergent attempt {attempt_id}")

    publications = dict(adapter.publish_atomic(pending)) if pending else {}
    if set(publications) != set(pending):
        raise TrajectoryPublicationError("owner atomic publication receipt set is incomplete")
    for attempt_id, publication in publications.items():
        expected_digest = "sha256:" + hashlib.sha256(pending[attempt_id]).hexdigest()
        if (
            publication.attempt_id != attempt_id
            or publication.digest != expected_digest
            or not publication.reference.startswith("https://")
            or publication.published_at.tzinfo is None
        ):
            raise TrajectoryPublicationError(f"owner publication receipt is invalid for {attempt_id}")
    return PublicationBatch(
        published=tuple(publications[key] for key in sorted(publications)),
        already_present=tuple(sorted(already_present)),
        record_count=len(payloads),
        byte_count=byte_count,
    )


def trajectory_from_log_entries(
    *,
    task_id: str,
    launch: object,
    terminal: object,
) -> ExecutionTrajectory:
    """Create one immutable attempt using only facts frozen on its launch and terminal rows."""

    launch_attempt = str(getattr(launch, "attempt_id", "") or "")
    terminal_attempt = str(getattr(terminal, "attempt_id", "") or "")
    classification = getattr(launch, "attempt_classification", None)
    profile = getattr(launch, "execution_profile", None)
    status = str(getattr(terminal, "status", "") or "")
    explicit_outcome = str(getattr(terminal, "trajectory_outcome", "") or "")
    outcome = explicit_outcome or _STATUS_OUTCOME.get(status, "")
    if not launch_attempt or terminal_attempt != launch_attempt:
        raise ValueError("terminal attempt does not match launch identity")
    if not isinstance(classification, dict) or not isinstance(profile, dict):
        raise ValueError("attempt launch lacks frozen classification or execution profile")
    if outcome not in _TERMINAL_OUTCOMES:
        raise ValueError("dispatch row is not a terminal attempt outcome")
    spend = getattr(terminal, "actual_spend", None) or getattr(launch, "actual_spend", None)
    return ExecutionTrajectory.model_validate(
        {
            "schema": SCHEMA,
            "attempt_id": launch_attempt,
            "task_id": task_id,
            "classification": classification,
            "executing_keeper": getattr(launch, "agent", None),
            "executing_session": getattr(terminal, "session_id", None) or getattr(launch, "session_id", None),
            "provider_route": getattr(launch, "agent", None),
            "execution_profile": profile,
            "spend": spend or {"amount": None, "unit": "unreported"},
            "started_at": getattr(launch, "timestamp", None),
            "ended_at": getattr(terminal, "timestamp", None),
            "outcome": outcome,
            "repository": getattr(launch, "attempt_repository", None),
            "exact_commit": getattr(terminal, "trajectory_exact_commit", None),
            "pull_request": getattr(terminal, "trajectory_pull_request", None),
            "terminal_predicate": getattr(terminal, "trajectory_predicate", None),
            "owner_receipt": getattr(terminal, "trajectory_owner_receipt", None),
        }
    )
