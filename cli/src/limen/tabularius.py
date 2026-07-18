"""TABVLARIVS compatibility relay for the authenticated conduct keeper.

The historical implementation made this process a local ``tasks.yaml`` writer. That still allowed
the laptop cache to diverge from the GitHub-backed owner and gave local Git plumbing an independent
authority path. The conduct broker is now the sole logical record keeper: producers may append
immutable outbound tickets locally, but this module can only translate them into bounded conduct
packets and archive a ticket after the remote projection receipt is acknowledged.

Ticket lifecycle::

    logs/tickets/inbox/<id>.json  --relay-->  acknowledged → archive/
                                              invalid      → rejected/ (+ <id>.reason.txt)
                                              unavailable  → remains in inbox

The local board is read only as an optimistic cache for exact revision guards. A stale cache is
fenced by the remote owner. Broker absence leaves valid tickets pending and acknowledges no
transition. Unsupported metadata, ordering, removal, and server-owned field mutations fail closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from limen.conduct.broker import ConductError
from limen.conduct.client import BrokerUnavailable, client_from_env
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    FanoutBoundsV1,
    ResourceClaimV1,
    RetryPolicyV1,
    SpendEnvelopeV1,
    WorkPacketV1,
    canonical_hash,
)
from limen.intake import validate_intake_contract
from limen.io import load_limen_file, queue_lock
from limen.materialize import (
    EV_BOARD_META,
    EV_BOARD_ORDER,
    EV_TASK_REMOVE,
    EV_TASK_UPSERT,
    Event,
    diff_boards,
)
from limen.models import VALID_STATUSES, LimenFile, Task

# --- ticket intents (a superset of materialize's Event tags, plus the status convenience) --------
INTENT_UPSERT = "task.upsert"  # create-or-merge a task field-set (patch may be full or partial)
INTENT_STATUS = "task.status"  # the common worker ticket: set status + append a dispatch_log entry
INTENT_REMOVE = "task.remove"  # drop a task id (prune/archive-out)
INTENT_ORDER = "board.order"  # set the task display order (patch = {"ids": [...]})
INTENT_META = "board.meta"  # set board version/portal (patch = {"version":..,"portal":..})
_INTENTS = frozenset({INTENT_UPSERT, INTENT_STATUS, INTENT_REMOVE, INTENT_ORDER, INTENT_META})
_PATCHABLE_TASK_FIELDS = frozenset(
    {
        "title",
        "description",
        "repo",
        "type",
        "target_agent",
        "workstream",
        "priority",
        "budget_cost",
        "status",
        "labels",
        "urls",
        "context",
        "predicate",
        "receipt_target",
        "execution_requirements",
        "workstream_contract",
        "claude_tier",
        "depends_on",
    }
)


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
    # Optional optimistic concurrency guard, evaluated by the keeper against
    # the exact current task immediately before this ticket is folded.  A
    # migration can therefore never archive a task that another ticket claimed
    # after compilation.
    precondition: dict[str, Any] | None = None


def task_state_sha256(fields: dict[str, Any]) -> str:
    """Content hash for one JSON-mode task state, including its append-only log."""

    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    """
    validated = task if isinstance(task, Task) else Task.model_validate(task)
    validate_intake_contract(validated, is_new=True)
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
    )
    return submit_ticket(board_path, ticket)


def submit_task_status(
    board_path: Path,
    task_id: str,
    *,
    status: str,
    agent: str,
    session_id: str = "unknown",
    output: str | None = None,
    patch: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Path:
    """One-line producer for status/result writers.

    A dispatcher/harvester that used to mutate ``task.status`` and append a dispatch log can hand
    the transition to TABVLARIVS instead. The optional ``patch`` is a field-level delta folded with
    the status; it must not carry a conflicting status.
    """
    if not task_id:
        raise ValueError("task status requires a task_id")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
    fields = dict(patch or {})
    if "status" in fields and fields["status"] != status:
        raise ValueError("status patch conflicts with status argument")
    fields["status"] = status
    now = now or datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_STATUS,
        task_id=task_id,
        patch=fields,
        log={"status": status, "output": output},
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
class PreserveResult:
    changed: bool = False
    pushed: bool = False
    deferred: bool = False
    skipped: bool = False
    reason: str = ""
    commit: str = ""


def pending_count(board_path: Path) -> int:
    inbox = _inbox(board_path)
    return len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0


def pending_upsert_patches(board_path: Path) -> list[dict[str, Any]]:
    """Return valid pending upsert patches without mutating the board.

    Producers use this as a read-side dedup hint: a task can be absent from the board but already
    waiting in the keeper inbox. Malformed tickets are ignored here; the drain pass owns quarantine.
    """
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return []
    patches: list[dict[str, Any]] = []
    for path in sorted(inbox.glob("*.json")):
        try:
            ticket = Ticket.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if ticket.intent == INTENT_UPSERT and isinstance(ticket.patch, dict):
            patches.append(ticket.patch)
    return patches


def pending_task_ids(board_path: Path) -> set[str]:
    ids: set[str] = set()
    for patch in pending_upsert_patches(board_path):
        tid = patch.get("id")
        if isinstance(tid, str) and tid:
            ids.add(tid)
    return ids


def _ticket_from_event(event: Event, *, agent: str, session_id: str, now: datetime) -> Ticket:
    """Translate one pure projection delta into its immutable keeper receipt."""

    event_type = str(event.get("type") or "")
    common = {
        "ticket_id": new_ticket_id(session_id, now),
        "timestamp": now,
        "agent": agent,
        "session_id": session_id,
    }
    if event_type == EV_BOARD_META:
        return Ticket(intent=INTENT_META, patch=dict(event.get("data") or {}), **common)
    if event_type == EV_BOARD_ORDER:
        return Ticket(intent=INTENT_ORDER, patch=dict(event.get("data") or {}), **common)
    if event_type == EV_TASK_UPSERT:
        return Ticket(
            intent=INTENT_UPSERT,
            task_id=str(event["task_id"]),
            patch=dict(event.get("data") or {}),
            **common,
        )
    if event_type == EV_TASK_REMOVE:
        return Ticket(intent=INTENT_REMOVE, task_id=str(event["task_id"]), **common)
    raise ValueError(f"unknown event type: {event_type!r}")


def _safe_identifier(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._:/@+-]+", "-", str(value)).strip("-")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = fallback
    return cleaned[:256]


def _canonical_revision(fields: dict[str, Any]) -> str:
    value: Any = fields.get("updated")
    if value is None and fields.get("dispatch_log"):
        value = fields["dispatch_log"][-1].get("timestamp")
    if value is None:
        value = fields.get("created") or fields.get("status")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    rendered = str(value)
    if re.match(r"^\d{4}-\d{2}-\d{2}T", rendered):
        try:
            parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
    return rendered


def _compatibility_intent(ticket: Ticket, base: dict[str, Any] | None) -> dict[str, Any]:
    if ticket.intent in {INTENT_REMOVE, INTENT_META, INTENT_ORDER}:
        raise ValueError(
            f"{ticket.intent} has no authenticated remote compatibility transition; "
            "file a bounded broker protocol extension instead of mutating the local projection"
        )
    if not ticket.task_id:
        raise ValueError(f"{ticket.intent} requires task_id")
    patch = dict(ticket.patch or {})
    if base is None:
        if ticket.intent != INTENT_UPSERT:
            raise ValueError(f"task {ticket.task_id} is absent from the hot projection")
        supplied = {**patch, "id": ticket.task_id}
        return {
            "kind": "task.upsert",
            "task_id": ticket.task_id,
            "expected_absent": True,
            "task": supplied,
            "log": {"output": (ticket.log or {}).get("output")},
        }

    precondition = ticket.precondition or {}
    if precondition.get("absent") is True:
        raise ValueError(f"task precondition failed: {ticket.task_id} is no longer absent")
    if "status" in precondition and base.get("status") != precondition["status"]:
        raise ValueError(
            f"task precondition failed: {ticket.task_id} status is {base.get('status')!r}, "
            f"expected {precondition['status']!r}"
        )
    if "task_sha256" in precondition and task_state_sha256(base) != precondition["task_sha256"]:
        raise ValueError(f"task precondition failed: {ticket.task_id} exact state changed")

    desired = {**base, **patch}
    changed = {key: value for key, value in desired.items() if key in _PATCHABLE_TASK_FIELDS and base.get(key) != value}
    unsupported = sorted(
        key
        for key, value in desired.items()
        if key not in _PATCHABLE_TASK_FIELDS | {"id", "created", "updated", "dispatch_log"} and base.get(key) != value
    )
    if unsupported:
        raise ValueError(f"task {ticket.task_id} changes unsupported remote fields: {', '.join(unsupported)}")
    prior_status = str(base.get("status") or "")
    next_status = str(desired.get("status") or prior_status)
    if prior_status == "open" and next_status == "dispatched":
        kind = "task.claim"
    elif next_status != prior_status:
        kind = "task.status"
    else:
        kind = "task.mutate"
    return {
        "kind": kind,
        "task_id": ticket.task_id,
        "expected_status": prior_status,
        "expected_revision": _canonical_revision(base),
        "patch": changed,
        "log": {"output": (ticket.log or {}).get("output")},
    }


def _relay_ticket(
    ticket: Ticket,
    base: dict[str, Any] | None,
    *,
    client=None,
) -> dict[str, Any]:
    intent = _compatibility_intent(ticket, base)
    identity = AgentIdentityV1(
        agent=_safe_identifier(ticket.agent, "tabularius-relay"),
        surface="tabularius-relay",
        session_id=_safe_identifier(
            f"{ticket.agent}-{ticket.session_id}",
            "tabularius-relay-session",
        ),
        provider_identity="limen-cli",
    )
    registration_now = datetime.now(timezone.utc)
    session = ConductorSessionV1(
        session_id=identity.session_id,
        identity=identity,
        origin="relay",
        capabilities=frozenset({"task-submit"}),
        transport="ianva",
        harvest_method="receipt",
        registered_at=registration_now,
        heartbeat_at=registration_now,
    )
    owner = os.environ.get("LIMEN_GITHUB_REPO", "").strip() or "organvm/limen"
    execution = {"adapter": "tabularius", "projection": "tasks.yaml", "observed_heads": {}}
    work_id = f"ticket-{_safe_identifier(ticket.ticket_id, 'ticket')}"
    work_key = f"task-compat-{canonical_hash({'intent': intent, 'execution': execution})}"
    packet = WorkPacketV1(
        work_id=work_id,
        work_key=work_key,
        intent=intent,
        execution=execution,
        initiator=identity,
        conductor=identity,
        preferred_agent="tabularius",
        required_capabilities=frozenset({"board-write"}),
        resource_claims=(ResourceClaimV1(key=f"task/{ticket.task_id}", mode="exclusive"),),
        predicate="python3 scripts/validate-task-board.py --tasks tasks.yaml",
        receipt_target=f"git:{owner}:tasks.yaml#{ticket.task_id}",
        authority=AuthorityEnvelopeV1(
            actions=frozenset({str(intent["kind"])}),
            repositories=frozenset({owner}),
            path_prefixes=frozenset({"tasks.yaml"}),
            may_delegate=False,
        ),
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        spend=SpendEnvelopeV1(limit=0),
        retry=RetryPolicyV1(max_attempts=1, transient_only=True),
        fanout=FanoutBoundsV1(max_children=0, max_depth=0),
        effect="write",
        task_id=ticket.task_id,
    )
    remote = client or client_from_env()
    remote.register(session)
    result = remote.submit(packet)
    receipts = result.get("projection_receipts")
    receipt = receipts[-1] if isinstance(receipts, list) and receipts else None
    projected = receipt.get("task") if isinstance(receipt, dict) else None
    if not isinstance(projected, dict):
        raise RuntimeError(
            f"conduct broker did not acknowledge canonical projection for {ticket.task_id}; "
            f"status={result.get('status')}"
        )
    return projected


def apply_limen_file_sync(
    board_path: Path,
    limen: LimenFile,
    *,
    agent: str,
    session_id: str = "unknown",
    allow_shrink: bool = False,
    before: LimenFile | None = None,
    now: datetime | None = None,
) -> DrainResult:
    """Submit a legacy in-memory delta to the authenticated conduct keeper.

    ``tasks.yaml`` is only a hot local projection. This compatibility seam
    derives bounded per-task packets and waits for remote projection receipts;
    it never writes, commits, pushes, or refreshes the local file. Unsupported
    board metadata, ordering, removal, or field mutations fail closed.
    """

    board_path = Path(board_path)
    del allow_shrink
    previous = before
    if previous is None and board_path.exists():
        previous = load_limen_file(board_path)
    events = diff_boards(previous, limen)
    if not events:
        return DrainResult(note="no board change")

    timestamp = now or datetime.now(timezone.utc)
    previous_data = (
        previous.model_dump(mode="json", exclude_none=True)
        if previous is not None
        else {"version": "1.0", "portal": None, "tasks": []}
    )
    desired_data = limen.model_dump(mode="json", exclude_none=True)
    prior_portal = dict(previous_data.get("portal") or {})
    desired_portal = dict(desired_data.get("portal") or {})
    for portal in (prior_portal, desired_portal):
        budget = portal.get("budget")
        if isinstance(budget, dict):
            budget = dict(budget)
            budget.pop("track", None)
            portal["budget"] = budget
    if prior_portal != desired_portal or previous_data.get("version") != desired_data.get("version"):
        raise RuntimeError("board metadata mutation has no authenticated remote compatibility transition")

    prior_by_id = {str(task["id"]): task for task in previous_data.get("tasks", [])}
    tickets = []
    for event in events:
        event_type = str(event.get("type") or "")
        if event_type == EV_BOARD_META:
            continue
        if event_type in {EV_BOARD_ORDER, EV_TASK_REMOVE}:
            raise RuntimeError(f"{event_type} has no authenticated remote compatibility transition")
        tickets.append(_ticket_from_event(event, agent=agent, session_id=session_id, now=timestamp))
    if not tickets:
        return DrainResult(note="no task transition; budget-window metadata is derived by the remote keeper")
    for ticket in tickets:
        task = _relay_ticket(ticket, prior_by_id.get(str(ticket.task_id)))
        prior_by_id[str(ticket.task_id)] = task
    return DrainResult(
        pending=len(tickets),
        applied=len(tickets),
        wrote=False,
        note="broker-committed",
        applied_ids=[ticket.ticket_id for ticket in tickets],
    )


def restore_limen_projection_text(
    board_path: Path,
    text: str,
    *,
    agent: str,
    session_id: str,
    now: datetime | None = None,
) -> DrainResult:
    """Reject local cache replacement; refetch the canonical remote projection."""

    del board_path, text, agent, session_id, now
    raise RuntimeError(
        "local tasks.yaml recovery is retired; refetch the GitHub-backed projection "
        "through the authenticated conduct owner"
    )


def preserve_board_projection(
    board_path: Path,
    *,
    branch: str = "main",
    remote: str = "origin",
    dry_run: bool = False,
    lock_timeout: int = 2,
) -> PreserveResult:
    """Retired local Git bridge.

    The authenticated remote projection performs GitHub SHA compare-and-swap before acknowledging
    a transition. A local process must never commit, push, reset, or advance the canonical board.
    """

    del board_path, branch, remote, dry_run, lock_timeout
    return PreserveResult(skipped=True, reason="remote-keeper-owns-projection")


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


def _admit_exact_preconditions(
    pending: list[tuple[Path, Ticket]],
) -> tuple[list[tuple[Path, Ticket]], list[tuple[Path, str]]]:
    """Reject exact-state tickets that conflict anywhere in the captured batch.

    Sequential optimistic checks are insufficient: an archive ticket at T can
    satisfy its precondition and then a same-task claim at T+1 can reopen it in
    the same keeper drain.  Admission therefore inspects the entire
    lock-captured batch before folding any task.  Any other pending state event
    for the same task invalidates a ``task_sha256`` precondition regardless of
    timestamp order.  Only the guarded ticket is rejected; unrelated tickets
    and the conflicting owner event retain their normal append-only custody.
    """

    task_mutations = {INTENT_UPSERT, INTENT_STATUS, INTENT_REMOVE}
    by_task: dict[str, list[tuple[Path, Ticket]]] = {}
    for path, ticket in pending:
        if ticket.task_id and ticket.intent in task_mutations:
            by_task.setdefault(ticket.task_id, []).append((path, ticket))

    rejected: list[tuple[Path, str]] = []
    rejected_paths: set[Path] = set()
    for path, ticket in pending:
        if not ticket.task_id or "task_sha256" not in (ticket.precondition or {}):
            continue
        peers = [(peer_path, peer) for peer_path, peer in by_task.get(ticket.task_id, []) if peer_path != path]
        if not peers:
            continue
        peer_ids = sorted(peer.ticket_id for _, peer in peers)
        rejected_paths.add(path)
        rejected.append(
            (
                path,
                f"batch precondition failed: {ticket.task_id} has {len(peers)} other pending state event(s) "
                f"{peer_ids}; exact task state is invalidated regardless of timestamp order",
            )
        )
    return [(path, ticket) for path, ticket in pending if path not in rejected_paths], rejected


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
        is_new = ticket.task_id not in tasks
        base = dict(tasks.get(ticket.task_id, {}))
        precondition = ticket.precondition or {}
        unknown_preconditions = set(precondition) - {"absent", "status", "task_sha256"}
        if unknown_preconditions:
            raise ValueError(f"unknown task preconditions: {sorted(unknown_preconditions)}")
        if precondition.get("absent") is True and not is_new:
            raise ValueError(f"task precondition failed: {ticket.task_id} is no longer absent")
        if "task_sha256" in precondition:
            if is_new:
                raise ValueError(f"task precondition failed: {ticket.task_id} is absent")
            actual_hash = task_state_sha256(base)
            if actual_hash != precondition["task_sha256"]:
                raise ValueError(
                    f"task precondition failed: {ticket.task_id} exact state changed "
                    f"({actual_hash[:12]} != {str(precondition['task_sha256'])[:12]})"
                )
        if "status" in precondition and base.get("status") != precondition["status"]:
            raise ValueError(
                f"task precondition failed: {ticket.task_id} status is {base.get('status')!r}, "
                f"expected {precondition['status']!r}"
            )
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
        validated = Task.model_validate(merged)  # reject a bad ticket individually
        # A caller can bypass ``submit_task_upsert`` by constructing a raw Ticket.
        # The keeper repeats admission independently so that ticket is quarantined
        # alone while valid siblings still land.
        validate_intake_contract(validated, is_new=is_new)
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


def drain_once(board_path: Path, *, dry_run: bool = False, lock_timeout: int = 20) -> DrainResult:
    """Relay one inbox snapshot to the authenticated keeper.

    The queue lock serializes only local ticket custody. ``tasks.yaml`` is read as an optimistic
    cache and remains byte-identical. A ticket moves to ``archive`` only after a projection receipt
    names the canonical task. Invalid tickets are quarantined; broker unavailability leaves the
    current ticket and every unattempted suffix in the inbox for an idempotent retry.
    """
    board_path = Path(board_path)
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return DrainResult(note="inbox empty")

    pending_hint = len(list(inbox.glob("*.json")))
    if pending_hint == 0:
        return DrainResult(note="inbox empty")

    if dry_run:
        good, bad = _parse_pending(inbox)
        admitted, precondition_rejections = _admit_exact_preconditions(good)
        tasks: dict[str, dict[str, Any]] = {}
        if board_path.exists():
            board = load_limen_file(board_path)
            tasks = {task.id: task.model_dump(mode="json", exclude_none=True) for task in board.tasks}
        applicable: list[tuple[Path, Ticket]] = []
        rejected: list[tuple[Path, str]] = [*bad, *precondition_rejections]
        for path, ticket in admitted:
            try:
                intent = _compatibility_intent(ticket, tasks.get(str(ticket.task_id)))
                if intent["kind"] == "task.upsert":
                    tasks[str(ticket.task_id)] = dict(intent["task"])
                else:
                    tasks[str(ticket.task_id)] = {
                        **tasks[str(ticket.task_id)],
                        **dict(intent.get("patch") or {}),
                    }
                applicable.append((path, ticket))
            except Exception as exc:
                rejected.append((path, f"compatibility validation failed: {exc}"))
        pending = len(good) + len(bad)
        return DrainResult(
            pending=pending,
            applied=len(applicable),
            rejected=len(rejected),
            note=(f"dry-run: {len(applicable)} broker-compatible, {len(rejected)} invalid/conflicting"),
            applied_ids=[ticket.ticket_id for _, ticket in applicable],
            rejected_ids=[path.stem for path, _ in rejected],
        )

    with queue_lock(board_path, timeout=lock_timeout) as locked:
        if not locked:
            return DrainResult(pending=pending_hint, deferred=True, note="queue lock held; deferred to next beat")

        # Parse only after taking the same lock used by phase publishers.  A
        # keeper can therefore observe either the complete published phase or
        # none of it, never an in-flight prefix captured before the lock.
        good, bad = _parse_pending(inbox)
        pending = len(good) + len(bad)
        if pending == 0:
            return DrainResult(note="inbox empty")

        tasks: dict[str, dict[str, Any]] = {}
        if board_path.exists():
            board = load_limen_file(board_path)
            tasks = {task.id: task.model_dump(mode="json", exclude_none=True) for task in board.tasks}
        applied: list[tuple[Path, Ticket]] = []
        admitted, precondition_rejections = _admit_exact_preconditions(good)
        rejected: list[tuple[Path, str]] = [*bad, *precondition_rejections]
        try:
            remote = client_from_env()
        except BrokerUnavailable as exc:
            _quarantine(rejected, _rejected(board_path))
            return DrainResult(
                pending=pending,
                rejected=len(rejected),
                deferred=True,
                note=f"conduct broker unavailable; valid tickets remain pending: {exc}",
                rejected_ids=[path.stem for path, _ in rejected],
            )

        deferred_reason = ""
        for path, ticket in admitted:
            try:
                projected = _relay_ticket(
                    ticket,
                    tasks.get(str(ticket.task_id)),
                    client=remote,
                )
                tasks[str(ticket.task_id)] = projected
                applied.append((path, ticket))
            except BrokerUnavailable as exc:
                deferred_reason = str(exc)
                break
            except (ConductError, RuntimeError, ValueError) as exc:
                rejected.append((path, f"broker rejected compatibility ticket: {exc}"))
            except Exception as exc:
                rejected.append((path, f"unexpected compatibility relay failure: {exc}"))

        _move([p for p, _ in applied], _archive(board_path))
        _quarantine(rejected, _rejected(board_path))

    return DrainResult(
        pending=pending,
        applied=len(applied),
        rejected=len(rejected),
        wrote=False,
        deferred=bool(deferred_reason),
        note=(
            f"conduct broker unavailable after {len(applied)} acknowledgment(s); unacknowledged tickets remain pending"
            if deferred_reason
            else ("broker-committed" if applied else "no remote projection")
        ),
        applied_ids=[t.ticket_id for _, t in applied],
        rejected_ids=[p.stem for p, _ in rejected],
    )
