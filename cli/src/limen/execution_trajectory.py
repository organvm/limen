"""Owner-native, immutable execution-attempt trajectories.

The task board transports attempt lifecycle events; it is not value authority and
is not the publication owner. Terminal trajectories are published through an
owner adapter that provides atomic compare-and-set custody. No default local
shadow store exists.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Sized
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Iterable, Literal, Mapping, Protocol, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)


SCHEMA = "limen.execution_trajectory.v1"
RECEIPT_VERIFICATION_MAX_AGE = timedelta(minutes=5)
RECEIPT_VERIFICATION_FUTURE_SKEW = timedelta(seconds=30)
_TERMINAL_OUTCOMES = frozenset({"succeeded", "failed", "blocked", "superseded"})
_STATUS_OUTCOME = {
    "done": "succeeded",
    "failed": "failed",
    "failed_blocked": "blocked",
    "needs_human": "blocked",
}
_SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"


def _is_sha(value: str | None) -> bool:
    return bool(value and len(value) == 40 and all(character in "0123456789abcdef" for character in value))


def _is_repository(value: str | None) -> bool:
    if not value:
        return False
    parts = value.split("/")
    return len(parts) == 2 and all(parts)


@dataclass(frozen=True)
class FrozenJsonObject(Mapping[str, object]):
    """Recursively immutable JSON object with stable key order."""

    _items: tuple[tuple[str, object], ...] = ()

    def __getitem__(self, key: str) -> object:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self):
        return (key for key, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)


def _freeze_json(value: object, *, path: str = "$", active: set[int] | None = None) -> object:
    """Validate JSON data while replacing every mutable container."""

    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{path} contains invalid Unicode") from exc
        return value
    if isinstance(value, FrozenJsonObject):
        return value

    active = active if active is not None else set()
    identity = id(value)
    if isinstance(value, Mapping):
        if identity in active:
            raise ValueError(f"{path} contains a reference cycle")
        active.add(identity)
        try:
            items: list[tuple[str, object]] = []
            keys = tuple(value)
            if not all(isinstance(key, str) for key in keys):
                raise ValueError(f"{path} contains a non-string object key")
            for key in sorted(keys):
                items.append((key, _freeze_json(value[key], path=f"{path}.{key}", active=active)))
            return FrozenJsonObject(tuple(items))
        finally:
            active.remove(identity)
    if isinstance(value, (list, tuple)):
        if identity in active:
            raise ValueError(f"{path} contains a reference cycle")
        active.add(identity)
        try:
            return tuple(_freeze_json(item, path=f"{path}[{index}]", active=active) for index, item in enumerate(value))
        finally:
            active.remove(identity)
    raise ValueError(f"{path} contains non-JSON type {type(value).__name__}")


def _thaw_json(value: object) -> object:
    if isinstance(value, FrozenJsonObject):
        return {key: _thaw_json(item) for key, item in value._items}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_bytes(record: "ExecutionTrajectory") -> bytes:
    payload = record.model_dump(mode="json", by_alias=True)
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


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

    command_digest: str = Field(pattern=_SHA256_PATTERN)
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
    digest: str = Field(pattern=_SHA256_PATTERN)
    head_sha: str | None = None
    attempt_id: str = Field(min_length=1, max_length=192)
    task_id: str = Field(min_length=1, max_length=192)
    repository: str = Field(min_length=3, max_length=256)
    predicate_digest: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def exact_head_if_present(self) -> "OwnerReceiptClaim":
        if self.head_sha is not None and not _is_sha(self.head_sha):
            raise ValueError("owner receipt head_sha must be a 40-hex commit")
        if not _is_repository(self.repository):
            raise ValueError("owner receipt repository must be exact OWNER/NAME")
        return self


class OwnerReceiptSnapshot(BaseModel):
    """Fresh evidence returned by the owner adapter, never copied from the board."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str = Field(min_length=1, max_length=128)
    reference: str = Field(min_length=1, max_length=2048)
    digest: str = Field(pattern=_SHA256_PATTERN)
    head_sha: str = Field(min_length=40, max_length=40)
    attempt_id: str = Field(min_length=1, max_length=192)
    task_id: str = Field(min_length=1, max_length=192)
    repository: str = Field(min_length=3, max_length=256)
    predicate_digest: str = Field(pattern=_SHA256_PATTERN)
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

    @field_validator("repository")
    @classmethod
    def exact_repository(cls, value: str) -> str:
        if not _is_repository(value):
            raise ValueError("owner snapshot repository must be exact OWNER/NAME")
        return value


class ExecutionTrajectory(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    schema_version: Literal["limen.execution_trajectory.v1"] = Field(
        default="limen.execution_trajectory.v1",
        alias="schema",
        serialization_alias="schema",
    )
    attempt_id: str = Field(min_length=1, max_length=192)
    task_id: str = Field(min_length=1, max_length=192)
    classification: FrozenTaskClassification
    executing_keeper: str = Field(min_length=1, max_length=128)
    executing_session: str = Field(min_length=1, max_length=256)
    provider_route: str = Field(min_length=1, max_length=256)
    execution_profile: FrozenJsonObject = Field(default_factory=FrozenJsonObject)
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

    @field_validator("execution_profile", mode="before")
    @classmethod
    def freeze_execution_profile(cls, value: object) -> FrozenJsonObject:
        frozen = _freeze_json(value)
        if not isinstance(frozen, FrozenJsonObject):
            raise ValueError("execution_profile must be a JSON object")
        return frozen

    @field_serializer("execution_profile")
    def serialize_execution_profile(self, value: FrozenJsonObject) -> object:
        return _thaw_json(value)

    @model_validator(mode="after")
    def identities_are_exact(self) -> "ExecutionTrajectory":
        if self.ended_at < self.started_at:
            raise ValueError("ended_at precedes started_at")
        if self.repository is not None and not _is_repository(self.repository):
            raise ValueError("repository must be exact OWNER/NAME")
        if self.exact_commit is not None and (not _is_sha(self.exact_commit) or self.repository is None):
            raise ValueError("exact_commit requires a repository and 40-hex SHA")
        if self.pull_request is not None:
            expected = f"https://github.com/{self.repository}/pull/"
            if self.exact_commit is None or not self.pull_request.startswith(expected):
                raise ValueError("pull_request must match repository and exact_commit")
        if self.owner_receipt is not None:
            if self.repository is None or self.terminal_predicate is None:
                raise ValueError("owner receipt requires repository and terminal predicate")
            binding = (
                self.owner_receipt.attempt_id,
                self.owner_receipt.task_id,
                self.owner_receipt.repository,
                self.owner_receipt.predicate_digest,
            )
            expected_binding = (
                self.attempt_id,
                self.task_id,
                self.repository,
                self.terminal_predicate.command_digest,
            )
            if binding != expected_binding:
                raise ValueError("owner receipt binding does not match trajectory identity")
        return self


class ReceiptAuthority(Protocol):
    def verify(
        self,
        claim: OwnerReceiptClaim,
        *,
        attempt_id: str,
        task_id: str,
        repository: str,
        predicate_digest: str,
    ) -> OwnerReceiptSnapshot | None: ...


def verified_value_credit(
    trajectory: ExecutionTrajectory,
    *,
    authority: ReceiptAuthority | None = None,
    now: datetime | None = None,
    max_receipt_age: timedelta = RECEIPT_VERIFICATION_MAX_AGE,
) -> int:
    """Grant one unit only from fresh owner evidence bound to the exact attempt head."""

    commit = trajectory.exact_commit
    repository = trajectory.repository
    predicate = trajectory.terminal_predicate
    claim = trajectory.owner_receipt
    if (
        trajectory.outcome != "succeeded"
        or not commit
        or repository is None
        or predicate is None
        or not predicate.passed
        or predicate.head_sha != commit
        or claim is None
        or claim.head_sha != commit
        or authority is None
    ):
        return 0
    if max_receipt_age <= timedelta(0):
        raise ValueError("max_receipt_age must be positive")
    verified_now = now or datetime.now(timezone.utc)
    if verified_now.tzinfo is None:
        raise ValueError("now must include a timezone")
    try:
        snapshot = authority.verify(
            claim,
            attempt_id=trajectory.attempt_id,
            task_id=trajectory.task_id,
            repository=repository,
            predicate_digest=predicate.command_digest,
        )
    except Exception:
        return 0
    if snapshot is None:
        return 0
    verification_age = verified_now - snapshot.verified_at
    return int(
        snapshot.owner == claim.owner
        and snapshot.reference == claim.reference
        and snapshot.digest == claim.digest
        and snapshot.head_sha == commit
        and snapshot.attempt_id == trajectory.attempt_id
        and snapshot.task_id == trajectory.task_id
        and snapshot.repository == repository
        and snapshot.predicate_digest == predicate.command_digest
        and snapshot.terminal
        and snapshot.predicate_passed
        and snapshot.verified_at >= predicate.checked_at
        and -RECEIPT_VERIFICATION_FUTURE_SKEW <= verification_age <= max_receipt_age
    )


@dataclass(frozen=True)
class TrajectoryCorpus:
    records: tuple[ExecutionTrajectory, ...]
    duplicate_rows: int = 0
    duplicate_attempt_ids: tuple[str, ...] = ()
    conflicting_attempt_ids: tuple[str, ...] = ()
    invalid_rows: tuple[dict[str, object], ...] = ()

    def value_by_executor(
        self,
        *,
        authority: ReceiptAuthority | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        credit: dict[str, int] = {}
        for record in self.records:
            value = verified_value_credit(record, authority=authority, now=now)
            credit[record.executing_keeper] = credit.get(record.executing_keeper, 0) + value
        return credit


def build_corpus(
    rows: Iterable[object],
    *,
    max_records: int | None = None,
    max_bytes: int | None = None,
    max_input_rows: int | None = None,
) -> TrajectoryCorpus:
    """Deduplicate by attempt identity and exclude every divergent identity."""

    for name, bound in (
        ("max_records", max_records),
        ("max_bytes", max_bytes),
        ("max_input_rows", max_input_rows),
    ):
        if bound is not None and bound < 1:
            raise ValueError(f"{name} must be positive")
    accepted: dict[str, tuple[ExecutionTrajectory, bytes]] = {}
    duplicates: set[str] = set()
    conflicts: set[str] = set()
    invalid: list[dict[str, object]] = []
    duplicate_rows = 0
    byte_count = 0
    known_input_rows = len(rows) if isinstance(rows, Sized) else None
    if max_input_rows is not None and known_input_rows is not None and known_input_rows > max_input_rows:
        raise TrajectoryPublicationError("trajectory publication exceeds input row bound")
    iterator = iter(rows)
    row_number = 0
    while True:
        if max_input_rows is not None and row_number >= max_input_rows:
            if known_input_rows is not None:
                break
            raise TrajectoryPublicationError("trajectory publication exceeds input row bound")
        try:
            raw = next(iterator)
        except StopIteration:
            break
        row_number += 1
        try:
            record = raw if isinstance(raw, ExecutionTrajectory) else ExecutionTrajectory.model_validate(raw)
        except ValidationError as exc:
            invalid.append({"row": row_number, "error": str(exc)[:2000]})
            continue
        payload = _canonical_bytes(record)
        if record.attempt_id in conflicts:
            duplicate_rows += 1
            continue
        previous = accepted.get(record.attempt_id)
        if previous is None:
            if max_records is not None and len(accepted) >= max_records:
                raise TrajectoryPublicationError("trajectory publication exceeds record bound")
            if max_bytes is not None and byte_count + len(payload) > max_bytes:
                raise TrajectoryPublicationError("trajectory publication exceeds byte bound")
            accepted[record.attempt_id] = (record, payload)
            byte_count += len(payload)
            continue
        duplicate_rows += 1
        duplicates.add(record.attempt_id)
        if previous[1] != payload:
            conflicts.add(record.attempt_id)
            accepted.pop(record.attempt_id, None)
            byte_count -= len(previous[1])
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


@dataclass(frozen=True)
class OwnerTrajectorySnapshot:
    """One operation's immutable owner read and opaque compare-and-set token."""

    token: str
    records: Mapping[str, bytes]

    def __post_init__(self) -> None:
        if not self.token:
            raise ValueError("owner snapshot token must be non-empty")
        copied: dict[str, bytes] = {}
        for attempt_id, payload in self.records.items():
            if not isinstance(attempt_id, str) or not attempt_id:
                raise ValueError("owner snapshot attempt identity is invalid")
            if not isinstance(payload, bytes):
                raise ValueError("owner snapshot payload must be bytes")
            copied[attempt_id] = payload
        object.__setattr__(self, "records", MappingProxyType(copied))


class OwnerTrajectoryAdapter(Protocol):
    """Owner-native compare-and-set publication boundary."""

    def read_many(self, attempt_ids: Sequence[str]) -> OwnerTrajectorySnapshot: ...

    def publish_atomic(
        self,
        payloads: Mapping[str, bytes],
        *,
        snapshot_token: str,
    ) -> Mapping[str, OwnerPublication]: ...


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
    max_input_rows: int = 1_000,
) -> PublicationBatch:
    """Atomically publish a finite, conflict-free batch through its owner adapter."""

    corpus = build_corpus(
        rows,
        max_records=max_records,
        max_bytes=max_bytes,
        max_input_rows=max_input_rows,
    )
    if corpus.invalid_rows or corpus.conflicting_attempt_ids:
        raise TrajectoryPublicationError("trajectory batch contains invalid or conflicting attempts")
    payloads = {record.attempt_id: _canonical_bytes(record) for record in corpus.records}
    byte_count = sum(len(payload) for payload in payloads.values())

    snapshot = adapter.read_many(tuple(sorted(payloads)))
    if not isinstance(snapshot, OwnerTrajectorySnapshot):
        raise TrajectoryPublicationError("owner read did not return an explicit CAS snapshot")
    existing = dict(snapshot.records)
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

    publications = dict(adapter.publish_atomic(pending, snapshot_token=snapshot.token)) if pending else {}
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
    executing_keeper = getattr(launch, "executing_keeper", None) or getattr(launch, "agent", None)
    executing_session = getattr(launch, "executing_session", None) or getattr(launch, "session_id", None)
    provider_route = (
        getattr(launch, "selected_model", None)
        or getattr(terminal, "selected_model", None)
        or getattr(launch, "selection_source", None)
        or getattr(terminal, "selection_source", None)
        or getattr(launch, "provider_route", None)
    )
    status = str(getattr(terminal, "status", "") or "")
    explicit_outcome = str(getattr(terminal, "trajectory_outcome", "") or "")
    outcome = explicit_outcome or _STATUS_OUTCOME.get(status, "")
    if not launch_attempt or terminal_attempt != launch_attempt:
        raise ValueError("terminal attempt does not match launch identity")
    if not isinstance(classification, Mapping) or not isinstance(profile, Mapping):
        raise ValueError("attempt launch lacks frozen classification or execution profile")
    if not executing_keeper or not executing_session:
        raise ValueError("attempt launch lacks frozen executor identity")
    if not provider_route:
        raise ValueError("attempt launch lacks independent provider-route evidence")
    if outcome not in _TERMINAL_OUTCOMES:
        raise ValueError("dispatch row is not a terminal attempt outcome")
    spend = getattr(terminal, "actual_spend", None) or getattr(launch, "actual_spend", None)
    return ExecutionTrajectory.model_validate(
        {
            "schema": SCHEMA,
            "attempt_id": launch_attempt,
            "task_id": task_id,
            "classification": dict(classification),
            "executing_keeper": executing_keeper,
            "executing_session": executing_session,
            "provider_route": provider_route,
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
