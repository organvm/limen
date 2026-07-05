#!/usr/bin/env python3
"""tabularius-organ.py — TABVLARIVS, the board's record-keeper, as a per-beat organ.

The single writer of `tasks.yaml`. Each beat it drains the lock-free ticket inbox
(`logs/tickets/inbox`) that workers append to, folds every ticket onto the healed board under the
queue lock, and seals the result through the collapse-guarded atomic write. The engine lives in
`limen.tabularius`; this is the thin beat wrapper (the same shape as `heal-board.py`).

Idempotent and beat-safe: an empty inbox is an instant no-op (no lock, no board I/O), so it is
harmless to fire every beat while no producers exist yet. If the queue lock is held by a legacy
writer mid-migration, it defers to the next beat rather than blocking.

  python3 scripts/tabularius-organ.py            # drain the inbox, else no-op (exit 0)
  python3 scripts/tabularius-organ.py --check    # report pending count only; never mutate
  python3 scripts/tabularius-organ.py --dry-run  # report what WOULD be applied; make no writes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.tabularius import drain_once, pending_count, sync_event_log_from_archive, write_event_log_board  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
BOARD = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
ENABLED = os.environ.get("LIMEN_TABVLARIVS", "1") != "0"
STATE = ROOT / "logs" / "tabularius-organ-state.json"


def _read_state() -> dict[str, object]:
    try:
        data = json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _previous_event_log_streak() -> int:
    data = _read_state()
    streak = data.get("event_log_streak")
    return streak if isinstance(streak, int) and streak > 0 else 0


def _event_log_proof() -> dict[str, object]:
    """Refresh the event log and prove it can regenerate the live cache without touching it."""
    tmp_path: Path | None = None
    try:
        sync_result = sync_event_log_from_archive(BOARD)
        fd, raw_tmp = tempfile.mkstemp(prefix="limen-tabularius-cache.", suffix=".yaml")
        os.close(fd)
        tmp_path = Path(raw_tmp)
        cache_result = write_event_log_board(BOARD, tmp_path)
        verified = sync_result.verified and cache_result.verified
        return {
            "event_log_verified": sync_result.verified,
            "event_log_cache_verified": cache_result.verified,
            "event_log_streak": _previous_event_log_streak() + 1 if verified else 0,
            "event_log_events": cache_result.events or sync_result.events,
            "event_log_archive_tickets": cache_result.archive_tickets or sync_result.archive_tickets,
            "event_log_archive_replay_tickets": cache_result.archive_replay_tickets,
            "event_log_note": cache_result.note,
        }
    except Exception as exc:  # noqa: BLE001 - heartbeat proof is fail-open
        return {
            "event_log_verified": False,
            "event_log_cache_verified": False,
            "event_log_streak": 0,
            "event_log_error": str(exc)[:240],
        }
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _stamp(**fields: object) -> None:
    """Write the counts-only liveness stamp organ-health.py probes (no task content — PII-clean)."""
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        payload: dict[str, object] = {"updated": now, **fields}
        has_proof = any(key.startswith("event_log_") for key in fields)
        if has_proof:
            payload["event_log_updated"] = now
        else:
            previous = _read_state()
            for key, value in previous.items():
                if key.startswith("event_log_"):
                    payload[key] = value
            if "event_log_updated" not in payload and "event_log_streak" in payload and previous.get("updated"):
                payload["event_log_updated"] = previous["updated"]
        STATE.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="drain the ticket inbox onto tasks.yaml (single-writer record-keeper)")
    ap.add_argument("--check", action="store_true", help="report pending ticket count; never mutate")
    ap.add_argument("--dry-run", action="store_true", help="report what would be applied; no writes")
    args = ap.parse_args(argv)

    if not ENABLED:
        print("tabularius: LIMEN_TABVLARIVS=0 — record-keeper disabled; leaving inbox as-is")
        return 0

    if args.check:
        n = pending_count(BOARD)
        print(f"tabularius: {n} ticket(s) pending in inbox" if n else "tabularius: inbox empty")
        _stamp(pending=n, mode="check")
        return 0

    result = drain_once(BOARD, dry_run=args.dry_run)

    if result.deferred:
        print(f"tabularius: queue lock held; {result.pending} ticket(s) deferred to next beat")
        _stamp(pending=result.pending, deferred=True)
        return 0

    if result.pending == 0:
        print("tabularius: OK — inbox empty (no-op)")
        _stamp(pending=0, applied=0, rejected=0)
        return 0

    proof: dict[str, object] = {}
    if not args.dry_run and result.wrote:
        proof = _event_log_proof()

    verb = "WOULD apply" if args.dry_run else "sealed"
    parts = [f"tabularius: {verb} {result.applied} ticket(s)"]
    if result.rejected:
        parts.append(f"quarantined {result.rejected}")
    if not args.dry_run and result.wrote:
        parts.append(f"board resealed ({BOARD.name})")
    if proof.get("event_log_cache_verified"):
        parts.append(f"event-log proof ok (streak {proof.get('event_log_streak')})")
    elif proof:
        parts.append("event-log proof failed-open")
    print("; ".join(parts))
    _stamp(
        pending=result.pending,
        applied=result.applied,
        rejected=result.rejected,
        wrote=result.wrote,
        dry_run=args.dry_run,
        **proof,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
