#!/usr/bin/env python3
"""Check whether TABVLARIVS has enough live event-log proof to flip SSOT.

This is deliberately read-only. It inspects the counts-only stamp written by
``scripts/tabularius-organ.py`` after real keeper seals and answers one question:
has the standing event log both matched and regenerated the live board cache for
enough consecutive keeper beats to consider the final source-of-truth flip?
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
DEFAULT_STATE = ROOT / "logs" / "tabularius-organ-state.json"
DEFAULT_MIN_STREAK = 3
DEFAULT_MAX_AGE_MINUTES = 24 * 60


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _positive_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def check_state(path: Path, *, min_streak: int, max_age_minutes: int) -> dict[str, object]:
    errors: list[str] = []
    if not path.exists():
        return {
            "ok": False,
            "state": str(path),
            "errors": [f"event proof state missing: {path}"],
            "streak": 0,
            "required_streak": min_streak,
        }

    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "state": str(path),
            "errors": [f"event proof state unreadable: {exc}"],
            "streak": 0,
            "required_streak": min_streak,
        }
    if not isinstance(data, dict):
        return {
            "ok": False,
            "state": str(path),
            "errors": ["event proof state must be a JSON object"],
            "streak": 0,
            "required_streak": min_streak,
        }

    proof_updated_raw = data.get("event_log_updated") or data.get("updated")
    updated = _parse_timestamp(proof_updated_raw)
    if updated is None:
        errors.append("event proof state missing parseable proof timestamp")
        age_minutes = None
    else:
        age_minutes = (datetime.now(timezone.utc) - updated).total_seconds() / 60
        if max_age_minutes > 0 and age_minutes > max_age_minutes:
            errors.append(
                f"event proof state is stale: {age_minutes:.1f} minutes old "
                f"(max {max_age_minutes})"
            )

    if data.get("event_log_verified") is not True:
        errors.append("event_log_verified is not true")
    if data.get("event_log_cache_verified") is not True:
        errors.append("event_log_cache_verified is not true")

    streak = _positive_int(data.get("event_log_streak"))
    if streak < min_streak:
        errors.append(f"event_log_streak {streak} is below required {min_streak}")

    events = _positive_int(data.get("event_log_events"))
    if events <= 0:
        errors.append("event_log_events is missing or zero")

    return {
        "ok": not errors,
        "state": str(path),
        "errors": errors,
        "streak": streak,
        "required_streak": min_streak,
        "events": events,
        "archive_tickets": _positive_int(data.get("event_log_archive_tickets")),
        "archive_replay_tickets": _positive_int(data.get("event_log_archive_replay_tickets")),
        "updated": proof_updated_raw,
        "liveness_updated": data.get("updated"),
        "age_minutes": age_minutes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument(
        "--min-streak",
        type=int,
        default=int(os.environ.get("LIMEN_TABULARIUS_EVENT_PROOF_MIN_STREAK", DEFAULT_MIN_STREAK)),
        help=f"Required consecutive keeper proof streak (default {DEFAULT_MIN_STREAK}).",
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=int(os.environ.get("LIMEN_TABULARIUS_EVENT_PROOF_MAX_AGE_MINUTES", DEFAULT_MAX_AGE_MINUTES)),
        help=f"Maximum proof age in minutes; <=0 disables freshness check (default {DEFAULT_MAX_AGE_MINUTES}).",
    )
    parser.add_argument("--json-output", action="store_true", help="Emit machine-readable proof result.")
    args = parser.parse_args(argv)

    result = check_state(args.state, min_streak=max(1, args.min_streak), max_age_minutes=args.max_age_minutes)
    if args.json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            "tabularius-event-proof: pass "
            f"streak={result['streak']}/{result['required_streak']} "
            f"events={result['events']} state={result['state']}"
        )
    else:
        print(
            "tabularius-event-proof: blocked "
            f"streak={result['streak']}/{result['required_streak']} state={result['state']}",
            file=sys.stderr,
        )
        for error in result["errors"]:
            print(f"  - {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
