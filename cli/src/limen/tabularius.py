"""TABVLARIVS — the one record-keeper over the board (`tasks.yaml`).

The disease this dissolves: ~32 uncoordinated writers each do *read-whole-board → mutate →
rewrite-whole-board* on the single `tasks.yaml` blob. `io.atomic_write_text` already stops torn
*bytes* (temp-file + `os.replace`), but two writers that both `load→save` still lost-update-clobber
(last-writer-wins on the whole board), and the worst offenders (the MCP server) skip even the
atomic write. Locking every `save` would give write-*atomicity* but not read-modify-write
*isolation* — the clobber survives. The only correct cure is the **single-writer principle**:
workers stop mutating shared state and instead APPEND one immutable *ticket* per unit of work to a
lock-free inbox; exactly **one** keeper drains the inbox, folds the tickets onto the board in
timestamp order, validates (per-task + the collapse-guard), and seals the result with the atomic
write. It is the only process that ever holds the write lock, so there is no interleave to tear.

This is Step 2+3 of `board-is-event-log-projection` (PR#543): `materialize.fold` is the proven pure
reducer — this module gives it a live stream to consume. A ticket **is** a `materialize` Event with
provenance (who did the work, when), and the archived ticket files are the append-only event log
that the board is a projection of (`board = fold(events)`).

Ticket lifecycle::

    logs/tickets/inbox/<id>.json  --drain-->  applied → archive/   (the event log)
                                              rejected → rejected/  (+ <id>.reason.txt)

Design invariants (each carried over from a shipped safety precedent):
  * **A worker never touches `tasks.yaml`.** It calls `submit_ticket`, an exclusive atomic create
    into the inbox — no read, no lock, no collapse risk, no interleave. (Preserves the one writer
    the fleet must never starve, `ingest-backlog.py`, which deliberately skipped the lock.)
  * **One bad ticket never rejects the batch.** Each ticket is applied + validated individually;
    a bad one is quarantined to `rejected/` and the rest still land (the `_sanitize_dispatch_logs`
    tolerate-and-salvage philosophy from `io.py`).
  * **The seal is collapse-guarded.** The board is written through `save_limen_file`, so the
    2026-06-26 shrink-to-1 clobber remains impossible; a batch that would collapse the board is
    rejected whole and the good board is left intact.
  * **Never dead-stop the beat.** If the queue lock is held (a legacy writer, mid-migration), the
    keeper defers to the next beat rather than blocking — exactly like `heal-board.py`.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from limen.io import BoardCollapseError, load_limen_file, queue_lock, save_limen_file
from limen.materialize import (
    EV_BOARD_META,
    EV_BOARD_ORDER,
    EV_TASK_REMOVE,
    EV_TASK_UPSERT,
    Event,
    canonical_board_text,
    events_from_jsonl,
    events_to_jsonl,
    fold,
    seed_events_from_board,
)
from limen.models import VALID_STATUSES, LimenFile, Task

# --- ticket intents (a superset of materialize's Event tags, plus the status convenience) --------
INTENT_UPSERT = "task.upsert"  # create-or-merge a task field-set (patch may be full or partial)
INTENT_STATUS = "task.status"  # the common worker ticket: set status + append a dispatch_log entry
INTENT_REMOVE = "task.remove"  # drop a task id (prune/archive-out)
INTENT_ORDER = "board.order"  # set the task display order (patch = {"ids": [...]})
INTENT_META = "board.meta"  # set board version/portal (patch = {"version":..,"portal":..})
_INTENTS = frozenset({INTENT_UPSERT, INTENT_STATUS, INTENT_REMOVE, INTENT_ORDER, INTENT_META})
EVENT_LOG_MANIFEST_KIND = "tabularius.compacted-seed"
EVENT_LOG_MANIFEST_SCHEMA_VERSION = 1


class Ticket(BaseModel):
    """One immutable unit of board work a worker hands to the record-keeper.

    A worker builds a Ticket describing the transition it performed ("here's the work I did") and
    drops it into the inbox via `submit_ticket`. It is an Event with provenance — the `patch` is a
    *field-level delta*, never a whole-board rewrite, so a torn ticket can at worst be quarantined
    and never corrupts the SSOT.
    """

    ticket_id: str
    timestamp: datetime
    agent: str
    session_id: str = "unknown"
    intent: str
    task_id: str | None = None
    # field-level delta: for upsert/status the task field-patch; for board.order {"ids": [...]};
    # for board.meta {"version": .., "portal": ..}.
    patch: dict[str, Any] | None = None
    # optional dispatch_log payload appended to the task's log — {"status": .., "output"?: ..}.
    log: dict[str, Any] | None = None
    # optional equality guard against stale tickets, e.g. {"status": "open"}.
    precondition: dict[str, Any] | None = None
    # optional budget accounting delta applied by the keeper with the status transition.
    budget_delta: dict[str, Any] | None = None


def new_ticket_id(session_id: str = "unknown", now: datetime | None = None) -> str:
    """A sortable, collision-free ticket id: `<utc-timestamp>-<session>-<rand>`. The timestamp
    prefix makes a plain filename sort chronological (the keeper's drain order), and the random
    tail guarantees two tickets from the same session in the same microsecond never collide."""
    now = now or datetime.now(timezone.utc)
    safe_session = "".join(c if c.isalnum() or c in "._-" else "_" for c in session_id)[:40]
    return f"{now.strftime('%Y%m%dT%H%M%S_%f')}Z-{safe_session}-{uuid.uuid4().hex[:8]}"


# --- inbox geometry ------------------------------------------------------------------------------
def tickets_root(board_path: Path) -> Path:
    return Path(board_path).parent / "logs" / "tickets"


def _inbox(board_path: Path) -> Path:
    return tickets_root(board_path) / "inbox"


def _archive(board_path: Path) -> Path:
    return tickets_root(board_path) / "archive"


def event_log_path(board_path: Path) -> Path:
    return tickets_root(board_path) / "events.jsonl"


def event_log_manifest_path(log_path: Path) -> Path:
    return Path(f"{Path(log_path)}.manifest.json")


def _rejected(board_path: Path) -> Path:
    return tickets_root(board_path) / "rejected"


def submit_ticket(board_path: Path, ticket: Ticket) -> Path:
    """Append a ticket to the inbox — the worker's *only* board-write surface.

    Exclusive + atomic: write to a temp file, fsync, then `os.link` it into place. `os.link` fails
    if the destination exists, so a duplicate `ticket_id` raises instead of clobbering, and a reader
    can never observe a half-written ticket. No lock, no board read — many workers submit
    concurrently without contending.
    """
    if ticket.intent not in _INTENTS:
        raise ValueError(f"unknown ticket intent: {ticket.intent!r}")
    inbox = _inbox(board_path)
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / f"{ticket.ticket_id}.json"
    fd, tmp = tempfile.mkstemp(dir=inbox, prefix=f".{ticket.ticket_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(ticket.model_dump_json())
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, dest)  # atomic exclusive create — raises FileExistsError on a duplicate id
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return dest


def submit_task_upsert(
    board_path: Path,
    task: "Task | dict[str, Any]",
    *,
    agent: str,
    session_id: str = "unknown",
    precondition: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Path:
    """One-line producer: hand the keeper a whole task field-set as an upsert ticket.

    This is the conversion target for every writer that used to `load → extend → save_limen_file`.
    A generator/miner drops the ``save_limen_file`` and instead calls this once per NEW task; the
    keeper folds it onto the board on the next beat. The full field-set becomes the ticket ``patch``.

    The task is validated HERE (fail-fast, exactly like the old ``Task(**t)`` before a direct write),
    so a producer never emits an invalid task — the keeper's per-ticket validation stays a second
    line of defense, not the first. Dedup remains the caller's responsibility: read the board and
    submit only genuinely-new ids, because an upsert MERGES onto any existing task ({**base, **patch})
    and blind-upserting a live id would overwrite its fields (e.g. flip a `done` task back to `open`).
    A producer that allocates ids from a stale read can pass a guard such as ``{"status": None}``
    so the keeper rejects the ticket if the id appears before the drain.
    """
    validated = task if isinstance(task, Task) else Task.model_validate(task)
    fields = validated.model_dump(mode="json", exclude_none=True)
    tid = fields.get("id")
    if not tid:
        raise ValueError("task upsert requires an 'id'")
    now = now or datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_UPSERT,
        task_id=tid,
        patch=fields,
        precondition=dict(precondition or {}),
    )
    return submit_ticket(board_path, ticket)


def submit_task_status(
    board_path: Path,
    task_id: str,
    status: str,
    *,
    agent: str,
    session_id: str = "unknown",
    output: str | None = None,
    patch: dict[str, Any] | None = None,
    precondition: dict[str, Any] | None = None,
    log_status: str | None = None,
    budget_cost: int | None = None,
    budget_agent: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Hand the keeper a status transition for an existing task.

    This is the conversion target for writers that used to mutate an existing task in place:
    ``task.status = ...; task.dispatch_log.append(...); save_limen_file(...)``. A status ticket
    carries only the transition plus an optional field-level patch such as ``target_agent`` or
    ``labels``. It deliberately does not accept whole-task identity/log fields; the keeper owns
    ``id``, ``updated``, and ``dispatch_log`` so every transition has one provenance shape.
    ``precondition`` is an optional equality guard for stale producers; if the task changed before
    the keeper drains the ticket, the ticket is quarantined instead of overwriting newer state.
    ``log_status`` lets dispatch-result producers record statuses such as ``failed->agy`` while the
    task itself lands on a canonical status such as ``open``.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
    if not task_id:
        raise ValueError("task status transition requires a task_id")

    patch = dict(patch or {})
    reserved = {"id", "updated", "dispatch_log"}
    forbidden = sorted(reserved.intersection(patch))
    if forbidden:
        raise ValueError(f"task status patch cannot set keeper-owned field(s): {', '.join(forbidden)}")
    if log_status is not None and not str(log_status).strip():
        raise ValueError("log_status must be a non-empty string")
    if log_status is not None and log_status != status:
        patch.setdefault("status", status)
    budget_delta = None
    if budget_cost is not None:
        if budget_cost < 0:
            raise ValueError("budget_cost cannot be negative")
        budget_delta = {"spent": budget_cost, "agent": budget_agent or agent, "agent_spent": budget_cost}

    now = now or datetime.now(timezone.utc)
    log = {"status": log_status or status}
    if output is not None:
        log["output"] = output
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_STATUS,
        task_id=task_id,
        patch=patch,
        log=log,
        precondition=dict(precondition or {}),
        budget_delta=budget_delta,
    )
    return submit_ticket(board_path, ticket)


def submit_board_meta(
    board_path: Path,
    *,
    agent: str,
    session_id: str = "unknown",
    version: str | None = None,
    portal: Any | None = None,
    now: datetime | None = None,
) -> Path:
    """Hand the keeper a board-level metadata update.

    This is for changes that are not owned by one task, such as budget-window resets. ``portal``
    may be a pydantic model or a plain mapping; the keeper validates the resulting whole board.
    """
    patch: dict[str, Any] = {}
    if version is not None:
        patch["version"] = version
    if portal is not None:
        patch["portal"] = (
            portal.model_dump(mode="json", exclude_none=True) if hasattr(portal, "model_dump") else dict(portal)
        )
    if not patch:
        raise ValueError("board meta ticket requires version and/or portal")
    now = now or datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_META,
        patch=patch,
    )
    return submit_ticket(board_path, ticket)


@dataclass
class DrainResult:
    """The outcome of one drain pass — counts only (safe to log)."""

    pending: int = 0
    applied: int = 0
    rejected: int = 0
    wrote: bool = False
    deferred: bool = False
    note: str = ""
    applied_ids: list[str] = field(default_factory=list)
    rejected_ids: list[str] = field(default_factory=list)


@dataclass
class EventLogResult:
    """Result of compacting or verifying the TABVLARIVS event projection."""

    event_log: Path
    events: int = 0
    archive_tickets: int = 0
    archive_replay_tickets: int = 0
    verified: bool = False
    note: str = ""
    manifest: Path | None = None


def pending_count(board_path: Path) -> int:
    inbox = _inbox(board_path)
    return len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0


def archive_count(board_path: Path) -> int:
    archive = _archive(board_path)
    return len(list(archive.glob("*.json"))) if archive.is_dir() else 0


def _archive_ticket_entries(board_path: Path) -> list[tuple[Path, Ticket]]:
    archive = _archive(board_path)
    if not archive.is_dir():
        return []
    entries: list[tuple[Path, Ticket]] = []
    for path in sorted(archive.glob("*.json")):
        entries.append((path, Ticket.model_validate_json(path.read_text())))
    entries.sort(key=lambda pt: (pt[1].timestamp, pt[1].ticket_id))
    return entries


def _archive_watermark(board_path: Path) -> dict[str, Any]:
    entries = _archive_ticket_entries(board_path)
    if not entries:
        return {"archive_count": 0, "last_ticket_id": None, "last_ticket_file": None}
    last_path, last_ticket = entries[-1]
    return {
        "archive_count": len(entries),
        "last_ticket_id": last_ticket.ticket_id,
        "last_ticket_file": last_path.name,
    }


def _write_event_log_manifest(board_path: Path, log_path: Path) -> Path:
    manifest_path = event_log_manifest_path(log_path)
    payload = {
        "schema_version": EVENT_LOG_MANIFEST_SCHEMA_VERSION,
        "kind": EVENT_LOG_MANIFEST_KIND,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **_archive_watermark(board_path),
    }
    manifest_errors = _validate_event_log_manifest(payload)
    if manifest_errors:
        raise ValueError("; ".join(manifest_errors))
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return manifest_path


def _validate_event_log_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("kind") != EVENT_LOG_MANIFEST_KIND:
        errors.append(f"event log manifest kind must be {EVENT_LOG_MANIFEST_KIND!r}")
    if data.get("schema_version") != EVENT_LOG_MANIFEST_SCHEMA_VERSION:
        errors.append(f"event log manifest schema_version must be {EVENT_LOG_MANIFEST_SCHEMA_VERSION}")
    created_at = data.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        errors.append("event log manifest created_at must be a non-empty string")
    archive_count_value = data.get("archive_count")
    if isinstance(archive_count_value, bool) or not isinstance(archive_count_value, int) or archive_count_value < 0:
        errors.append("event log manifest archive_count must be a non-negative integer")
        archive_count = 0
    else:
        archive_count = archive_count_value
    last_ticket_id = data.get("last_ticket_id")
    last_ticket_file = data.get("last_ticket_file")
    if archive_count == 0:
        if last_ticket_id is not None or last_ticket_file is not None:
            errors.append("event log manifest empty archive watermark must not name a last ticket")
    else:
        if not isinstance(last_ticket_id, str) or not last_ticket_id.strip():
            errors.append("event log manifest last_ticket_id must be a non-empty string when archive_count > 0")
        if not isinstance(last_ticket_file, str) or not last_ticket_file.strip():
            errors.append("event log manifest last_ticket_file must be a non-empty string when archive_count > 0")
    return errors


def _load_event_log_manifest(log_path: Path) -> dict[str, Any] | None:
    manifest_path = event_log_manifest_path(log_path)
    if not manifest_path.exists():
        return None
    data = json.loads(manifest_path.read_text())
    if not isinstance(data, dict):
        raise ValueError("event log manifest must be a JSON object")
    manifest_errors = _validate_event_log_manifest(data)
    if manifest_errors:
        raise ValueError("; ".join(manifest_errors))
    return data


def _state_from_board(board: LimenFile) -> tuple[OrderedDict[str, dict[str, Any]], dict[str, Any]]:
    board_json = board.model_dump(mode="json", exclude_none=True)
    tasks: OrderedDict[str, dict[str, Any]] = OrderedDict((t["id"], t) for t in board_json.get("tasks", []))
    meta: dict[str, Any] = {"version": board_json.get("version", "1.0"), "portal": board_json.get("portal")}
    return tasks, meta


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _board_meta_event(meta: dict[str, Any]) -> Event:
    return {"type": EV_BOARD_META, "data": {"version": meta.get("version", "1.0"), "portal": meta.get("portal")}}


def _projection_events_for_ticket(
    ticket: Ticket,
    tasks: OrderedDict[str, dict[str, Any]],
    meta: dict[str, Any],
    before_meta: dict[str, Any],
) -> list[Event]:
    events: list[Event] = []
    if _board_meta_event(meta) != _board_meta_event(before_meta):
        events.append(_board_meta_event(meta))
    if ticket.intent == INTENT_REMOVE:
        events.append({"type": EV_TASK_REMOVE, "task_id": ticket.task_id})
        return events
    if ticket.intent in (INTENT_UPSERT, INTENT_STATUS):
        events.append({"type": EV_TASK_UPSERT, "task_id": ticket.task_id, "data": tasks[ticket.task_id or ""]})
        return events
    if ticket.intent == INTENT_META:
        return events or [_board_meta_event(meta)]
    if ticket.intent == INTENT_ORDER:
        events.append({"type": EV_BOARD_ORDER, "data": {"ids": meta.get("order", [])}})
        return events
    raise ValueError(f"unknown ticket intent: {ticket.intent!r}")


def archive_projection_events_after_watermark(
    board_path: Path,
    seed_events: list[Event],
    last_ticket_id: str | None,
) -> tuple[list[Event], int]:
    """Compile archived tickets after ``last_ticket_id`` into materialize events.

    A compacted event log is a seed. The archive is the delta stream after that seed. This helper
    replays only tickets beyond the seed watermark and emits full materialize events so
    ``fold(seed + archive_delta)`` can prove the cache projection without mutating ``tasks.yaml``.
    """
    seed_board = fold(seed_events)
    tasks, meta = _state_from_board(seed_board)
    events: list[Event] = []
    replayed = 0
    seen_watermark = last_ticket_id is None
    for _, ticket in _archive_ticket_entries(board_path):
        if not seen_watermark:
            if ticket.ticket_id == last_ticket_id:
                seen_watermark = True
            continue
        before_meta = _json_clone(meta)
        _apply(ticket, tasks, meta)
        events.extend(_projection_events_for_ticket(ticket, tasks, meta, before_meta))
        replayed += 1
    if not seen_watermark:
        raise ValueError(f"event log archive watermark not found: {last_ticket_id}")
    return events, replayed


def compact_event_log(board_path: Path, out_path: Path | None = None) -> EventLogResult:
    """Compact the current keeper projection into a canonical replayable event log.

    This is the first safe Step-3 bridge: the archived tickets remain provenance, while
    ``events.jsonl`` becomes a compacted projection seed that ``materialize.fold`` can replay
    without needing pre-TABVLARIVS history. The sidecar manifest records the archive watermark, so
    later verification can replay archived tickets that landed after the seed.
    """
    board_path = Path(board_path)
    out_path = Path(out_path) if out_path is not None else event_log_path(board_path)
    board = load_limen_file(board_path)
    events = seed_events_from_board(board)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(events_to_jsonl(events))
    manifest = _write_event_log_manifest(board_path, out_path)
    result = verify_event_log(board_path, out_path)
    result.archive_tickets = archive_count(board_path)
    result.manifest = manifest
    return result


def verify_event_log(board_path: Path, in_path: Path | None = None) -> EventLogResult:
    """Verify a compacted event log folds back to the current board projection.

    If a compacted-seed manifest exists, verification replays archived tickets after the manifest
    watermark before comparing with ``tasks.yaml``. That is the reversible Step-3 shape:
    snapshot seed + keeper-owned archive deltas, never a direct board mutation.
    """
    rebuilt, result = folded_event_log_board(board_path, in_path)
    if rebuilt is None:
        return result
    return result


def folded_event_log_board(board_path: Path, in_path: Path | None = None) -> tuple[LimenFile | None, EventLogResult]:
    """Fold the compacted event log plus archive deltas into a board projection.

    This is the reversible Step-3 cache-regeneration primitive. It proves the event log can rebuild
    a ``tasks.yaml``-shaped board without writing the live board; callers can compare or emit the
    result to a side path while ``tasks.yaml`` remains the current cache.
    """
    board_path = Path(board_path)
    in_path = Path(in_path) if in_path is not None else event_log_path(board_path)
    manifest_path = event_log_manifest_path(in_path)
    if not in_path.exists():
        return None, EventLogResult(
            in_path,
            archive_tickets=archive_count(board_path),
            manifest=manifest_path if manifest_path.exists() else None,
            note="event log missing",
        )
    events = events_from_jsonl(in_path.read_text())
    board = load_limen_file(board_path)
    replayed = 0
    note_prefix = "fold(events)"
    try:
        manifest = _load_event_log_manifest(in_path)
        if manifest is not None:
            archive_events, replayed = archive_projection_events_after_watermark(
                board_path,
                events,
                manifest.get("last_ticket_id"),
            )
            events = events + archive_events
            if replayed:
                note_prefix = "fold(events + archive tickets after watermark)"
    except Exception as exc:
        return None, EventLogResult(
            in_path,
            events=len(events),
            archive_tickets=archive_count(board_path),
            archive_replay_tickets=replayed,
            verified=False,
            note=f"event log archive replay failed: {exc}",
            manifest=manifest_path if manifest_path.exists() else None,
        )
    rebuilt = fold(events)
    verified = canonical_board_text(rebuilt) == canonical_board_text(board)
    return rebuilt, EventLogResult(
        in_path,
        events=len(events),
        archive_tickets=archive_count(board_path),
        archive_replay_tickets=replayed,
        verified=verified,
        note=f"{note_prefix} == tasks.yaml bytes" if verified else f"{note_prefix} != tasks.yaml bytes",
        manifest=manifest_path if manifest_path.exists() else None,
    )


def write_event_log_board(board_path: Path, out_path: Path, in_path: Path | None = None) -> EventLogResult:
    """Write a folded event-log board projection to ``out_path``.

    The function refuses to overwrite the live board. It only writes after proving the folded
    projection is byte-identical to the current cache, keeping this rung a cache-regeneration proof
    rather than a source-of-truth flip.
    """
    board_path = Path(board_path)
    out_path = Path(out_path)
    if out_path.resolve() == board_path.resolve():
        target = event_log_path(board_path) if in_path is None else Path(in_path)
        return EventLogResult(
            target,
            archive_tickets=archive_count(board_path),
            verified=False,
            note="refusing to overwrite live tasks.yaml cache",
            manifest=event_log_manifest_path(target) if event_log_manifest_path(target).exists() else None,
        )
    rebuilt, result = folded_event_log_board(board_path, in_path)
    if rebuilt is None or not result.verified:
        return result
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(canonical_board_text(rebuilt))
    result.note = f"wrote materialized board cache; {result.note}"
    return result


def sync_event_log_from_archive(board_path: Path, in_path: Path | None = None) -> EventLogResult:
    """Append archived ticket deltas after the manifest watermark into ``events.jsonl``.

    This is the next reversible Step-3 rung after verification: keep the compacted seed, append
    keeper-owned archive deltas, then advance the manifest watermark. The live board remains the
    checked projection; this function only makes the replay log less stale.
    """
    board_path = Path(board_path)
    in_path = Path(in_path) if in_path is not None else event_log_path(board_path)
    if not in_path.exists():
        return compact_event_log(board_path, in_path)
    manifest_path = event_log_manifest_path(in_path)
    events = events_from_jsonl(in_path.read_text())
    manifest = _load_event_log_manifest(in_path)
    if manifest is None:
        return EventLogResult(
            in_path,
            events=len(events),
            archive_tickets=archive_count(board_path),
            verified=False,
            note="event log manifest missing; run tabularius-events --write once before --sync-archive",
        )
    archive_events, replayed = archive_projection_events_after_watermark(
        board_path,
        events,
        manifest.get("last_ticket_id"),
    )
    if archive_events:
        with in_path.open("a", encoding="utf-8") as handle:
            handle.write(events_to_jsonl(archive_events))
        _write_event_log_manifest(board_path, in_path)
    result = verify_event_log(board_path, in_path)
    result.manifest = manifest_path
    result.note = f"synced {replayed} archived ticket(s); {result.note}"
    return result


def _parse_pending(inbox: Path) -> tuple[list[tuple[Path, Ticket]], list[tuple[Path, str]]]:
    """Load every inbox ticket, splitting parseable from garbage, then order the good ones by
    (timestamp, id) so concurrent submissions replay in a single deterministic total order."""
    good: list[tuple[Path, Ticket]] = []
    bad: list[tuple[Path, str]] = []
    for p in sorted(inbox.glob("*.json")):
        try:
            good.append((p, Ticket.model_validate_json(p.read_text())))
        except Exception as exc:  # a torn/invalid ticket is quarantined, never fatal
            bad.append((p, f"unparseable/invalid ticket: {exc}"))
    good.sort(key=lambda pt: (pt[1].timestamp, pt[1].ticket_id))
    return good, bad


def _apply(ticket: Ticket, tasks: OrderedDict[str, dict[str, Any]], meta: dict[str, Any]) -> None:
    """Fold one ticket onto the in-memory board state (mutates `tasks`/`meta` in place).

    Validates the resulting single task so a malformed ticket raises HERE and is quarantined alone,
    rather than failing the whole-board validation at seal time and taking good tickets down with it.
    """
    if ticket.intent == INTENT_REMOVE:
        if not ticket.task_id:
            raise ValueError("task.remove requires task_id")
        tasks.pop(ticket.task_id, None)
        return

    if ticket.intent in (INTENT_UPSERT, INTENT_STATUS):
        if not ticket.task_id:
            raise ValueError(f"{ticket.intent} requires task_id")
        base = dict(tasks.get(ticket.task_id, {}))
        for key, expected in (ticket.precondition or {}).items():
            actual = base.get(key)
            if actual != expected:
                raise ValueError(f"precondition failed for {ticket.task_id}: {key}={actual!r} != {expected!r}")
        merged = {**base, **(ticket.patch or {})}
        merged["id"] = ticket.task_id
        merged["updated"] = ticket.timestamp.isoformat()
        if ticket.log:
            status = ticket.log.get("status") or merged.get("status")
            entry = {
                "timestamp": ticket.timestamp.isoformat(),
                "agent": ticket.agent,
                "session_id": ticket.session_id,
                "status": status,
                "output": ticket.log.get("output"),
            }
            merged["dispatch_log"] = list(base.get("dispatch_log", [])) + [entry]
            # a task.status ticket carries the transition in its log payload; honor it as the status
            if ticket.intent == INTENT_STATUS and "status" not in (ticket.patch or {}) and status:
                merged["status"] = status
        Task.model_validate(merged)  # reject a bad ticket individually
        next_portal = None
        if ticket.budget_delta:
            delta = ticket.budget_delta
            spent = int(delta.get("spent", 0) or 0)
            agent = str(delta.get("agent") or ticket.agent)
            agent_spent = int(delta.get("agent_spent", spent) or 0)
            if spent < 0 or agent_spent < 0:
                raise ValueError("budget_delta cannot be negative")
            portal = dict(meta.get("portal") or {})
            budget = dict(portal.get("budget") or {})
            track = dict(budget.get("track") or {})
            per_agent = dict(track.get("per_agent") or {})
            track["spent"] = int(track.get("spent") or 0) + spent
            per_agent[agent] = int(per_agent.get(agent) or 0) + agent_spent
            track["per_agent"] = per_agent
            budget["track"] = track
            portal["budget"] = budget
            next_portal = portal
        if next_portal is not None:
            meta["portal"] = next_portal
        tasks[ticket.task_id] = merged  # dict update keeps first-seen position; new id appends
        return

    if ticket.intent == INTENT_META:
        p = ticket.patch or {}
        candidate = dict(meta)
        if "version" in p:
            candidate["version"] = p["version"]
        if "portal" in p:
            if p["portal"] is not None and not isinstance(p["portal"], dict):
                raise ValueError("board.meta portal must be a mapping")
            candidate["portal"] = p["portal"]
        LimenFile.model_validate(
            {
                "version": candidate.get("version", "1.0"),
                "portal": candidate.get("portal"),
                "tasks": list(tasks.values()),
            }
        )
        meta.clear()
        meta.update(candidate)
        return

    if ticket.intent == INTENT_ORDER:
        ids = (ticket.patch or {}).get("ids", [])
        if not isinstance(ids, list) or any(not isinstance(tid, str) for tid in ids):
            raise ValueError("board.order ids must be a list of task id strings")
        meta["order"] = list(ids)
        return

    raise ValueError(f"unknown ticket intent: {ticket.intent!r}")


def _move(paths: list[Path], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        try:
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def _quarantine(rejected: list[tuple[Path, str]], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p, reason in rejected:
        try:
            (dest_dir / f"{p.name}.reason.txt").write_text(reason)
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def _drain_pending(
    board_path: Path,
    *,
    pending: int,
    good: list[tuple[Path, Ticket]],
    bad: list[tuple[Path, str]],
) -> DrainResult:
    board = load_limen_file(board_path)
    board_json = board.model_dump(mode="json", exclude_none=True)
    tasks: OrderedDict[str, dict[str, Any]] = OrderedDict((t["id"], t) for t in board_json.get("tasks", []))
    meta: dict[str, Any] = {"version": board_json.get("version", "1.0"), "portal": board_json.get("portal")}

    applied: list[tuple[Path, Ticket]] = []
    rejected: list[tuple[Path, str]] = list(bad)
    for p, ticket in good:
        try:
            _apply(ticket, tasks, meta)
            applied.append((p, ticket))
        except Exception as exc:
            rejected.append((p, f"apply failed: {exc}"))

    wrote = False
    if applied:
        events: list[Event] = [{"type": EV_BOARD_META, "data": {"version": meta["version"], "portal": meta["portal"]}}]
        for tid, fields in tasks.items():
            events.append({"type": EV_TASK_UPSERT, "task_id": tid, "data": fields})
        if meta.get("order"):
            events.append({"type": EV_BOARD_ORDER, "data": {"ids": meta["order"]}})
        try:
            new_board = fold(events)  # the proven reducer assembles + validates the whole board
        except Exception as exc:
            rejected.extend((p, f"batch rejected by board validation: {exc}") for p, _ in applied)
            applied = []
        else:
            try:
                save_limen_file(board_path, new_board)  # collapse-guard + atomic seal
                wrote = True
            except BoardCollapseError as exc:
                # the batch would collapse the board — never write; quarantine it whole, board intact
                rejected.extend((p, f"batch rejected by collapse-guard: {exc}") for p, _ in applied)
                applied = []

    _move([p for p, _ in applied], _archive(board_path))
    _quarantine(rejected, _rejected(board_path))

    return DrainResult(
        pending=pending,
        applied=len(applied),
        rejected=len(rejected),
        wrote=wrote,
        note=("sealed" if wrote else "no board change"),
        applied_ids=[t.ticket_id for _, t in applied],
        rejected_ids=[p.stem for p, _ in rejected],
    )


def drain_once_locked(board_path: Path, *, dry_run: bool = False) -> DrainResult:
    """Drain pending tickets while the caller already holds ``queue_lock(board_path)``.

    Reservation producers need the keeper's seal before they start external work. This entrypoint
    keeps the single writer logic inside TABVLARIVS without nesting the non-reentrant queue lock.
    """
    board_path = Path(board_path)
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return DrainResult(note="inbox empty")

    good, bad = _parse_pending(inbox)
    pending = len(good) + len(bad)
    if pending == 0:
        return DrainResult(note="inbox empty")

    if dry_run:
        return DrainResult(
            pending=pending,
            applied=len(good),
            rejected=len(bad),
            note=f"dry-run: {len(good)} applicable, {len(bad)} unparseable",
        )

    return _drain_pending(board_path, pending=pending, good=good, bad=bad)


def drain_once(board_path: Path, *, dry_run: bool = False, lock_timeout: int = 20) -> DrainResult:
    """Drain the inbox once: fold every pending ticket onto the board, seal, archive.

    The whole load→fold→seal runs under the queue lock, and the keeper is the only drainer, so there
    is no read-modify-write race. An empty inbox is an instant no-op (no lock, no board I/O) — which
    is what makes it safe to run every beat while no producers exist yet.
    """
    board_path = Path(board_path)
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return DrainResult(note="inbox empty")

    good, bad = _parse_pending(inbox)
    pending = len(good) + len(bad)
    if pending == 0:
        return DrainResult(note="inbox empty")

    if dry_run:
        return DrainResult(
            pending=pending,
            applied=len(good),
            rejected=len(bad),
            note=f"dry-run: {len(good)} applicable, {len(bad)} unparseable",
        )

    with queue_lock(board_path, timeout=lock_timeout) as locked:
        if not locked:
            return DrainResult(pending=pending, deferred=True, note="queue lock held; deferred to next beat")

        return _drain_pending(board_path, pending=pending, good=good, bad=bad)
