#!/usr/bin/env python3
"""tabularius-organ.py — outbound compatibility relay to the conduct keeper.

Each beat it drains the lock-free ticket inbox (``logs/tickets/inbox``) by submitting bounded
packets to the authenticated remote owner. ``tasks.yaml`` is a read-only hot projection. A ticket
is archived only after the remote GitHub-backed projection receipt is acknowledged; broker
unavailability leaves the unacknowledged suffix pending.

Idempotent and beat-safe: an empty inbox is an instant no-op (no lock, no board I/O), so it is
harmless to fire every beat while no producers exist yet. If the queue lock is held by a legacy
writer mid-migration, it defers to the next beat rather than blocking.

  python3 scripts/tabularius-organ.py            # relay the inbox, else no-op (exit 0)
  python3 scripts/tabularius-organ.py --check    # report pending count only; never mutate
  python3 scripts/tabularius-organ.py --dry-run  # report what WOULD be applied; make no writes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.tabularius import drain_once, pending_count  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
BOARD = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
ENABLED = os.environ.get("LIMEN_TABVLARIVS", "1") != "0"
STATE = ROOT / "logs" / "tabularius-organ-state.json"


def _stamp(**fields: object) -> None:
    """Write the counts-only liveness stamp organ-health.py probes (no task content — PII-clean)."""
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(), **fields}, indent=2))
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="relay the ticket inbox to the authenticated conduct keeper")
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
        print(f"tabularius: {result.pending} ticket(s) deferred ({result.note})")
        _stamp(pending=result.pending, applied=result.applied, rejected=result.rejected, deferred=True)
        return 0

    if result.pending == 0:
        print("tabularius: OK — inbox empty (no-op)")
        _stamp(
            pending=0,
            applied=0,
            rejected=0,
        )
        return 0

    verb = "WOULD relay" if args.dry_run else "broker acknowledged"
    parts = [f"tabularius: {verb} {result.applied} ticket(s)"]
    if result.rejected:
        parts.append(f"quarantined {result.rejected}")
    print("; ".join(parts))
    _stamp(
        pending=result.pending,
        applied=result.applied,
        rejected=result.rejected,
        wrote=result.wrote,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
