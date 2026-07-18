"""Bounded production publication of terminal execution attempts.

The board is transport and retry state. GitHub is the durable trajectory owner.
Publication failures remain on the exact terminal event and are retried by later
harvest passes without changing task lifecycle or granting value.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping

from limen.execution_trajectory import (
    ExecutionTrajectory,
    TrajectoryPublicationError,
    publish_bounded,
    record_digest,
    trajectory_from_log_entries,
)
from limen.execution_trajectory_github import GitHubTrajectoryAdapter
from limen.execution_trajectory_github import load_system_trajectory_adapter
from limen.models import DispatchLogEntry, Task


_TERMINAL_STATUSES = frozenset({"done", "failed", "failed_blocked", "needs_human"})


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        value = int(env.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _system_adapter(env: Mapping[str, str]) -> GitHubTrajectoryAdapter | None:
    if env.get("LIMEN_TRAJECTORY_PUBLICATION", "1").strip().lower() in {"0", "false", "no", "off"}:
        return None
    return load_system_trajectory_adapter()


def _launch_for(task: Task, attempt_id: str) -> DispatchLogEntry | None:
    return next(
        (
            entry
            for entry in task.dispatch_log
            if entry.attempt_id == attempt_id
            and entry.attempt_classification is not None
            and entry.execution_profile is not None
        ),
        None,
    )


def _terminal_events(task: Task) -> list[DispatchLogEntry]:
    latest: dict[str, DispatchLogEntry] = {}
    for entry in task.dispatch_log:
        if not entry.attempt_id:
            continue
        if entry.trajectory_outcome or entry.status in _TERMINAL_STATUSES:
            latest[entry.attempt_id] = entry
    return [latest[key] for key in sorted(latest)]


def _exact_owner_reference(adapter: GitHubTrajectoryAdapter, attempt_id: str, head_sha: str) -> str:
    filename = hashlib.sha256(attempt_id.encode()).hexdigest() + ".json"
    return f"https://github.com/{adapter.repository}/blob/{head_sha}/{adapter.root}/{filename}"


def publish_task_trajectories(
    task: Task,
    *,
    adapter: GitHubTrajectoryAdapter | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Publish every unacknowledged terminal attempt and annotate its exact receipt.

    Returns whether board transport metadata changed. A disabled publisher is an
    explicit operator state and leaves the board untouched.
    """

    settings = env if env is not None else os.environ
    try:
        owner = adapter if adapter is not None else _system_adapter(settings)
    except ValueError as exc:
        error = f"trajectory owner configuration blocked: {str(exc)[:400]}"
        changed = False
        for terminal in _terminal_events(task):
            if terminal.trajectory_publication_error != error:
                terminal.trajectory_publication_error = error
                changed = True
        return changed
    if owner is None:
        return False

    pending: list[tuple[DispatchLogEntry, ExecutionTrajectory]] = []
    changed = False
    for terminal in _terminal_events(task):
        if terminal.trajectory_publication_reference and terminal.trajectory_publication_digest:
            if terminal.trajectory_publication_error is not None:
                terminal.trajectory_publication_error = None
                changed = True
            continue
        launch = _launch_for(task, str(terminal.attempt_id))
        try:
            if launch is None:
                raise ValueError("registered attempt launch is missing")
            record = trajectory_from_log_entries(task_id=task.id, launch=launch, terminal=terminal)
        except (TypeError, ValueError) as exc:
            error = f"trajectory conversion blocked: {str(exc)[:400]}"
            if terminal.trajectory_publication_error != error:
                terminal.trajectory_publication_error = error
                changed = True
            continue
        pending.append((terminal, record))

    if not pending:
        return changed

    max_records = _positive_int(settings, "LIMEN_TRAJECTORY_MAX_RECORDS", 25)
    max_bytes = _positive_int(settings, "LIMEN_TRAJECTORY_MAX_BYTES", 262_144)
    try:
        batch = publish_bounded(
            [record for _terminal, record in pending],
            owner,
            max_records=max_records,
            max_bytes=max_bytes,
            max_input_rows=max_records,
        )
        publications = {receipt.attempt_id: receipt for receipt in batch.published}
        already_present = set(batch.already_present)
        exact_snapshot = owner.read_many(tuple(sorted(already_present))) if already_present else None
    except (OSError, TypeError, ValueError, TrajectoryPublicationError) as exc:
        error = f"trajectory owner publication blocked: {str(exc)[:400]}"
        for terminal, _record in pending:
            if terminal.trajectory_publication_error != error:
                terminal.trajectory_publication_error = error
                changed = True
        return changed

    for terminal, record in pending:
        publication = publications.get(record.attempt_id)
        if publication is not None:
            reference = publication.reference
            digest = publication.digest
        else:
            if exact_snapshot is None or record.attempt_id not in exact_snapshot.records:
                error = "trajectory owner publication returned no exact custody receipt"
                if terminal.trajectory_publication_error != error:
                    terminal.trajectory_publication_error = error
                    changed = True
                continue
            reference = _exact_owner_reference(owner, record.attempt_id, exact_snapshot.token)
            digest = record_digest(record)
        terminal.trajectory_publication_reference = reference
        terminal.trajectory_publication_digest = digest
        terminal.trajectory_publication_error = None
        changed = True
    return changed
