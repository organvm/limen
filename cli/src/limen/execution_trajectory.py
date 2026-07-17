"""Immutable, receipt-backed execution-attempt records.

``limen.execution_trajectory.v1`` is deliberately separate from task-board lifecycle
events.  A task may reopen, be reconciled by another keeper, or change classification;
none of those operations rewrites who executed one historical attempt or whether that
attempt produced verified value.

This module validates terminal records and deduplicates a JSONL corpus by ``attempt_id``.
Exact duplicates count once.  Conflicting rows for one attempt fail closed: that attempt
is excluded from value calculations and surfaced as corpus debt.
"""

from __future__ import annotations

import json
import fcntl
import hashlib
import os
import stat
import tempfile
import uuid
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SCHEMA = "limen.execution_trajectory.v1"
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class FrozenTaskClassification(BaseModel):
    """The task classification observed when the attempt began, never a live board lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_type: str = Field(min_length=1, max_length=128)
    labels: tuple[str, ...] = ()
    workstream: str | None = Field(default=None, max_length=128)

    @field_validator("labels", mode="before")
    @classmethod
    def normalize_labels(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("labels must be a sequence")
        labels = {str(item).strip() for item in value if str(item).strip()}
        return tuple(sorted(labels))


class ExecutionSpend(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Unknown spend is not zero spend. Providers that do not expose a trustworthy
    # terminal usage receipt leave amount null and name the missing unit explicitly.
    amount: float | None = Field(default=None, ge=0.0)
    unit: str = Field(default="unreported", min_length=1, max_length=64)

    @model_validator(mode="after")
    def unknown_spend_is_explicit(self) -> "ExecutionSpend":
        if self.amount is None and self.unit != "unreported":
            raise ValueError("unknown spend must use the unreported unit")
        if self.amount is not None and self.unit == "unreported":
            raise ValueError("reported spend must name its measurement unit")
        return self


class PredicateVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str = Field(min_length=1)
    passed: bool
    checked_at: datetime
    head_sha: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("checked_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("checked_at must include a timezone")
        return value


class VerifiedReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str = Field(min_length=1)
    digest: str = Field(min_length=1, max_length=256)
    verified: bool
    head_sha: str | None = Field(default=None, min_length=1, max_length=128)


class ExecutionTrajectory(BaseModel):
    """One terminal execution attempt; provider routing and keeper attribution are independent."""

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
    repository: str | None = Field(default=None, min_length=1, max_length=256)
    exact_commit: str | None = Field(default=None, min_length=1, max_length=128)
    pull_request: str | None = Field(default=None, min_length=1)
    terminal_predicate: PredicateVerification | None = None
    receipt: VerifiedReceipt | None = None

    @field_validator("started_at", "ended_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("trajectory timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def end_not_before_start(self) -> "ExecutionTrajectory":
        if self.ended_at < self.started_at:
            raise ValueError("ended_at precedes started_at")
        if self.repository is not None and not _REPOSITORY.fullmatch(self.repository):
            raise ValueError("repository must be an exact OWNER/NAME identity")
        if self.exact_commit is not None:
            if not _GIT_SHA.fullmatch(self.exact_commit) or self.repository is None:
                raise ValueError("exact_commit requires a 40-hex SHA and repository identity")
        if self.pull_request is not None:
            expected = f"https://github.com/{self.repository}/pull/"
            if self.exact_commit is None or not self.pull_request.startswith(expected):
                raise ValueError("pull_request must match repository and bind an exact commit")
        return self


@dataclass(frozen=True)
class TrajectoryCorpus:
    records: tuple[ExecutionTrajectory, ...]
    duplicate_rows: int = 0
    duplicate_attempt_ids: tuple[str, ...] = ()
    conflicting_attempt_ids: tuple[str, ...] = ()
    invalid_rows: tuple[dict[str, Any], ...] = ()
    source_missing: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "unique_attempts": len(self.records),
            "duplicate_rows": self.duplicate_rows,
            "duplicate_attempt_ids": list(self.duplicate_attempt_ids),
            "conflicting_attempt_ids": list(self.conflicting_attempt_ids),
            "invalid_rows": list(self.invalid_rows),
            "source_missing": self.source_missing,
        }


def new_attempt_id() -> str:
    """Generate an opaque attempt identity; task IDs and provider run IDs are not attempts."""

    return f"attempt-{uuid.uuid4()}"


ReceiptAuthority = Callable[[ExecutionTrajectory], bool]


def verified_value_credit(
    trajectory: ExecutionTrajectory,
    *,
    receipt_authority: ReceiptAuthority | None = None,
) -> int:
    """Return one verified value unit only after owner-native receipt verification.

    Success prose is insufficient.  The terminal predicate and durable receipt must both
    be verified against the exact commit recorded by the attempt. The trajectory's
    ``receipt.verified`` field is transported through the mutable board, so it is evidence,
    not authority. Until an owner-native adapter independently verifies that reference,
    the conservative production result is zero even when every structural field agrees.
    """

    predicate = trajectory.terminal_predicate
    receipt = trajectory.receipt
    commit = trajectory.exact_commit
    if trajectory.outcome != "succeeded" or not commit:
        return 0
    if predicate is None or not predicate.passed or predicate.head_sha != commit:
        return 0
    if receipt is None or not receipt.verified or receipt.head_sha != commit:
        return 0
    if receipt_authority is None:
        return 0
    try:
        return 1 if receipt_authority(trajectory) else 0
    except Exception:
        return 0


def _canonical_record(record: ExecutionTrajectory) -> str:
    return json.dumps(record.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":"))


def _validation_message(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in exc.errors(include_url=False)
    )


def build_corpus(
    rows: Iterable[Any],
    *,
    initial_invalid_rows: Iterable[dict[str, Any]] = (),
    source_missing: bool = False,
) -> TrajectoryCorpus:
    """Validate and deduplicate rows, excluding every conflicting attempt identity."""

    accepted: dict[str, tuple[ExecutionTrajectory, str]] = {}
    duplicate_ids: set[str] = set()
    conflicts: set[str] = set()
    invalid = list(initial_invalid_rows)
    duplicate_rows = 0

    for row_number, raw in enumerate(rows, start=1):
        try:
            record = raw if isinstance(raw, ExecutionTrajectory) else ExecutionTrajectory.model_validate(raw)
        except ValidationError as exc:
            invalid.append(
                {
                    "row": row_number,
                    "error": _validation_message(exc),
                }
            )
            continue

        attempt_id = record.attempt_id
        canonical = _canonical_record(record)
        if attempt_id in conflicts:
            duplicate_rows += 1
            continue
        previous = accepted.get(attempt_id)
        if previous is None:
            accepted[attempt_id] = (record, canonical)
            continue
        duplicate_rows += 1
        duplicate_ids.add(attempt_id)
        if previous[1] != canonical:
            conflicts.add(attempt_id)
            accepted.pop(attempt_id, None)

    records = tuple(accepted[key][0] for key in sorted(accepted))
    return TrajectoryCorpus(
        records=records,
        duplicate_rows=duplicate_rows,
        duplicate_attempt_ids=tuple(sorted(duplicate_ids)),
        conflicting_attempt_ids=tuple(sorted(conflicts)),
        invalid_rows=tuple(invalid),
        source_missing=source_missing,
    )


def load_jsonl(path: Path) -> TrajectoryCorpus:
    """Load a bounded JSONL trajectory corpus without treating a missing shadow source as truth."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return TrajectoryCorpus(records=(), source_missing=True)
    except OSError as exc:
        return TrajectoryCorpus(
            records=(),
            invalid_rows=({"row": 0, "error": f"cannot read trajectory corpus: {exc}"},),
        )

    rows: list[Any] = []
    invalid: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError as exc:
            invalid.append({"row": line_number, "error": f"invalid JSON: {exc}"})
            continue
        try:
            rows.append(ExecutionTrajectory.model_validate(raw))
        except ValidationError as exc:
            invalid.append({"row": line_number, "error": _validation_message(exc)})
    return build_corpus(rows, initial_invalid_rows=invalid)


class TrajectoryConflictError(RuntimeError):
    """One attempt identity was presented with divergent immutable payloads."""


@dataclass(frozen=True)
class PublicationReceipt:
    attempt_id: str
    path: Path
    published: bool


class TrajectoryStore:
    """Atomic, append-only, one-file-per-attempt trajectory custody.

    The SHA-256 filename avoids putting provider/session identifiers in paths. A
    process lock serializes collision checks and publication. Exact duplicates are
    idempotent; a different payload for the same attempt fails closed.
    """

    def __init__(self, root: Path):
        self.root = root
        self.lock_path = root / ".publish.lock"

    @staticmethod
    def _filename(attempt_id: str) -> str:
        return f"{hashlib.sha256(attempt_id.encode('utf-8')).hexdigest()}.json"

    def publish(self, raw: ExecutionTrajectory | dict[str, Any]) -> PublicationReceipt:
        record = raw if isinstance(raw, ExecutionTrajectory) else ExecutionTrajectory.model_validate(raw)
        payload = (_canonical_record(record) + "\n").encode("utf-8")
        if self.root.is_symlink():
            raise TrajectoryConflictError("trajectory store root is symlinked")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_stat = self.root.lstat()
        if not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.geteuid():
            raise TrajectoryConflictError("trajectory store root is not an effective-user-owned directory")
        os.chmod(self.root, 0o700)
        target = self.root / self._filename(record.attempt_id)

        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            if target.is_symlink():
                raise TrajectoryConflictError(f"attempt {record.attempt_id} custody path is symlinked")
            if target.exists():
                target_stat = target.lstat()
                if (
                    not stat.S_ISREG(target_stat.st_mode)
                    or target_stat.st_uid != os.geteuid()
                    or target_stat.st_nlink != 1
                    or target_stat.st_mode & 0o077
                ):
                    raise TrajectoryConflictError(
                        f"attempt {record.attempt_id} custody file is not a private single-link regular file"
                    )
                try:
                    existing = target.read_bytes()
                except OSError as exc:
                    raise TrajectoryConflictError(
                        f"cannot read existing trajectory for {record.attempt_id}: {exc}"
                    ) from exc
                if existing != payload:
                    raise TrajectoryConflictError(
                        f"attempt {record.attempt_id} already has a divergent terminal record"
                    )
                return PublicationReceipt(record.attempt_id, target, False)

            temporary_descriptor, temporary_name = tempfile.mkstemp(prefix=".trajectory.", dir=self.root)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(temporary_descriptor, "wb") as handle:
                    os.fchmod(handle.fileno(), 0o600)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
                directory_descriptor = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
            finally:
                temporary.unlink(missing_ok=True)
            return PublicationReceipt(record.attempt_id, target, True)
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def load(self) -> TrajectoryCorpus:
        if self.root.is_symlink():
            return TrajectoryCorpus(
                records=(),
                invalid_rows=({"row": 0, "error": "trajectory store root is symlinked"},),
            )
        if not self.root.exists():
            return TrajectoryCorpus(records=(), source_missing=True)
        try:
            paths = sorted(self.root.glob("*.json"))
        except OSError as exc:
            return TrajectoryCorpus(
                records=(),
                invalid_rows=({"row": 0, "error": f"cannot enumerate trajectory store: {exc}"},),
            )
        rows: list[Any] = []
        invalid: list[dict[str, Any]] = []
        for row_number, path in enumerate(paths, start=1):
            try:
                path_stat = path.lstat()
                if (
                    path.is_symlink()
                    or not stat.S_ISREG(path_stat.st_mode)
                    or path_stat.st_uid != os.geteuid()
                    or path_stat.st_nlink != 1
                    or path_stat.st_mode & 0o077
                ):
                    raise OSError("trajectory record is not a private single-link regular file")
                raw = json.loads(path.read_text(encoding="utf-8"))
                record = ExecutionTrajectory.model_validate(raw)
            except (OSError, ValueError, ValidationError) as exc:
                invalid.append({"row": row_number, "path": path.name, "error": str(exc)})
                continue
            if path.name != self._filename(record.attempt_id):
                invalid.append(
                    {
                        "row": row_number,
                        "path": path.name,
                        "error": "trajectory filename does not match attempt identity",
                    }
                )
                continue
            rows.append(record)
        return build_corpus(rows, initial_invalid_rows=invalid)


def load_trajectory_source(path: Path) -> TrajectoryCorpus:
    """Load atomic attempt custody, with legacy JSONL retained as a read-only fixture format."""

    return TrajectoryStore(path).load() if path.is_dir() else load_jsonl(path)


_TERMINAL_OUTCOME = {
    "done": "succeeded",
    "failed": "failed",
    "failed_blocked": "blocked",
    "needs_human": "blocked",
}


def trajectory_from_log_entries(
    *,
    task_id: str,
    launch: object,
    terminal: object,
    terminal_attempt_id: str | None = None,
) -> ExecutionTrajectory:
    """Build one terminal attempt without consulting mutable task classification.

    Every attribution field comes from launch metadata. Missing launch metadata is
    a hard error instead of an invitation to infer history from the current board.
    """

    attempt_id = str(getattr(launch, "attempt_id", "") or "")
    classification = getattr(launch, "attempt_classification", None)
    profile = getattr(launch, "execution_profile", None)
    repository = getattr(launch, "attempt_repository", None)
    terminal_attempt = str(getattr(terminal, "attempt_id", "") or terminal_attempt_id or "")
    status = str(getattr(terminal, "status", "") or "")
    explicit_outcome = str(getattr(terminal, "trajectory_outcome", "") or "")
    if not attempt_id or terminal_attempt != attempt_id:
        raise ValueError("terminal attempt does not match its launch identity")
    if not isinstance(classification, dict) or not isinstance(profile, dict):
        raise ValueError("attempt launch lacks frozen classification or execution profile")
    if status not in _TERMINAL_OUTCOME and explicit_outcome not in {
        "succeeded",
        "failed",
        "blocked",
        "superseded",
    }:
        raise ValueError(f"dispatch status {status!r} is not a terminal attempt outcome")

    spend = getattr(terminal, "actual_spend", None) or getattr(launch, "actual_spend", None)
    if spend is None:
        spend = {"amount": None, "unit": "unreported"}
    predicate = getattr(terminal, "trajectory_predicate", None)
    receipt = getattr(terminal, "trajectory_receipt", None)
    return ExecutionTrajectory.model_validate(
        {
            "schema": SCHEMA,
            "attempt_id": attempt_id,
            "task_id": task_id,
            "classification": classification,
            "executing_keeper": str(getattr(launch, "agent", "") or ""),
            "executing_session": str(getattr(terminal, "session_id", "") or getattr(launch, "session_id", "") or ""),
            "provider_route": str(getattr(launch, "agent", "") or ""),
            "execution_profile": profile,
            "spend": spend,
            "started_at": getattr(launch, "timestamp", None),
            "ended_at": getattr(terminal, "timestamp", None),
            "outcome": explicit_outcome or _TERMINAL_OUTCOME[status],
            "repository": repository,
            "exact_commit": getattr(terminal, "trajectory_exact_commit", None),
            "pull_request": getattr(terminal, "trajectory_pull_request", None),
            "terminal_predicate": predicate,
            "receipt": receipt,
        }
    )


def publish_terminal_attempts(
    tasks: Sequence[object],
    store: TrajectoryStore,
) -> tuple[list[PublicationReceipt], list[str]]:
    """Publish every newly terminal, launch-identified attempt from a board snapshot.

    The board transports lifecycle metadata; it is not the value source. Value is
    granted only by the exact predicate and verified receipt embedded in the
    immutable terminal trajectory.
    """

    publications: list[PublicationReceipt] = []
    errors: list[str] = []
    for task in tasks:
        task_id = str(getattr(task, "id", "") or "")
        groups: dict[str, list[object]] = {}
        inferred_terminals: dict[str, list[object]] = {}
        active_attempt_id: str | None = None
        for entry in list(getattr(task, "dispatch_log", None) or []):
            attempt_id = str(getattr(entry, "attempt_id", "") or "")
            if attempt_id:
                groups.setdefault(attempt_id, []).append(entry)
                status = str(getattr(entry, "status", "") or "")
                if status == "dispatched":
                    active_attempt_id = attempt_id
                elif (
                    status in _TERMINAL_OUTCOME
                    or str(getattr(entry, "trajectory_outcome", "") or "")
                    in {"succeeded", "failed", "blocked", "superseded"}
                ) and active_attempt_id == attempt_id:
                    active_attempt_id = None
            elif active_attempt_id and (
                str(getattr(entry, "status", "") or "") in _TERMINAL_OUTCOME
                or str(getattr(entry, "trajectory_outcome", "") or "")
                in {"succeeded", "failed", "blocked", "superseded"}
            ):
                # Legacy/direct terminal writers may not know the new field yet. Association is
                # allowed only to the single active launch in log order; classification and profile
                # still come exclusively from that launch, never the current task row.
                inferred_terminals.setdefault(active_attempt_id, []).append(entry)
                active_attempt_id = None
        for attempt_id, entries in groups.items():
            launches = [
                entry
                for entry in entries
                if isinstance(getattr(entry, "attempt_classification", None), dict)
                and isinstance(getattr(entry, "execution_profile", None), dict)
            ]
            terminals = [
                entry
                for entry in entries
                if str(getattr(entry, "status", "") or "") in _TERMINAL_OUTCOME
                or str(getattr(entry, "trajectory_outcome", "") or "")
                in {"succeeded", "failed", "blocked", "superseded"}
            ] + inferred_terminals.get(attempt_id, [])
            if not terminals:
                continue
            if not launches:
                errors.append(f"{task_id}:{attempt_id}: terminal attempt lacks frozen launch metadata")
                continue
            launch = min(launches, key=lambda entry: getattr(entry, "timestamp"))
            terminal = max(terminals, key=lambda entry: getattr(entry, "timestamp"))
            try:
                record = trajectory_from_log_entries(
                    task_id=task_id,
                    launch=launch,
                    terminal=terminal,
                    terminal_attempt_id=attempt_id,
                )
                publications.append(store.publish(record))
            except (TrajectoryConflictError, ValidationError, ValueError, OSError) as exc:
                errors.append(f"{task_id}:{attempt_id}: {exc}")
    return publications, errors
