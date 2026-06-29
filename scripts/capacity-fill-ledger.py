#!/usr/bin/env python3
"""Track the one-lane capacity-fill pulse for this packet.

This is intentionally small and read-only by default. With ``--write`` it refreshes:

* ``docs/capacity-fill.md`` — human-readable daily pulse for lane operators.
* ``logs/capacity-fill-ledger.json`` — structured evidence for automation.

The current packet focus is **agy** productivity, so the receipt always includes:

* current AGY capacity census line (including remaining quota);
* AGY hard blockers from dispatch's down-lane derivation (manual lane-marking, usage dead-ness,
  and OAuth preflight).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))

from limen.capacity import capacity_census  # noqa: E402
from limen.dispatch import _down_lanes  # noqa: E402
from limen.io import load_limen_file  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
DOC_PATH = ROOT / "docs" / "capacity-fill.md"
LEDGER_PATH = ROOT / "logs" / "capacity-fill-ledger.json"
TASKS_PATH = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(Path.home()))
    except (OSError, ValueError):
        return str(path)


def capacity_snapshot() -> tuple[list[dict[str, Any]], set[str]]:
    """Build a capacity census from the tracked board, and read dispatch's current down-lane set."""
    rows: list[dict[str, Any]] = []
    board: dict[str, Any] | None = None
    try:
        board = load_limen_file(TASKS_PATH).model_dump(mode="json", exclude_none=True)
    except Exception:
        board = None

    try:
        rows = capacity_census(board)
    except Exception as exc:
        rows = []
        print(f"WARN capacity_census failed: {exc}")

    try:
        dead = _down_lanes()
    except Exception as exc:
        print(f"WARN _down_lanes unavailable: {exc}")
        dead = set()

    return rows, set(dead)


def build_markdown(snapshot: dict[str, Any]) -> str:
    generated = snapshot.get("generated_at")
    status = snapshot.get("status")
    agy = snapshot.get("agy", {})
    up = snapshot.get("up", [])
    down = snapshot.get("down", [])
    down_reason = snapshot.get("agy_down_reason")

    lines = [
        "# Capacity Fill Ledger",
        "",
        f"Generated: `{generated}`",
        "",
        f"Status: `{status}`",
        "",
        "## Agy lane",
        "",
        f"- Reachable: `{agy.get('reachable', False)}`",
        f"- Detail: `{agy.get('detail', 'unknown')}`",
        f"- Remaining: `{agy.get('remaining', 'unknown')}` / `{agy.get('limit', 'unknown')}`",
        f"- Down reason: `{down_reason or 'none'}`",
        "",
        "## Capacity snapshot",
        "",
        "- Up lanes:",
    ]
    for lane in sorted(up):
        lines.append(f"  - `{lane}`")
    if not up:
        lines.append("  - none")
    lines.append("")
    lines.append("- Down lanes:")
    for lane in sorted(down):
        lines.append(f"  - `{lane}`")
    if not down:
        lines.append("  - none")

    lines += [
        "",
        "## Focus",
        "",
        "- If Agy remains `down` for multiple beats, run:",
        "  - `python3 scripts/dispatch-health.py --write --probe-async`",
        "  - `python3 scripts/capacity-fill-ledger.py --write`",
        "  - and check manual entries in `logs/lanes-down.txt` if present.",
        "",
    ]
    return "\n".join(lines)


def build_snapshot() -> dict[str, Any]:
    rows, dead = capacity_snapshot()
    by_agent = {row.get("agent"): row for row in rows}
    up = [row["agent"] for row in rows if row.get("reachable") and row.get("agent") not in dead]
    down = [
        row["agent"]
        for row in rows
        if (not row.get("reachable") or row.get("agent") in dead)
    ]
    agy_row = by_agent.get("agy") or {}
    blocker = []
    if agy_row.get("agent") is not None and not agy_row.get("reachable", False):
        blocker.append(f"agy unreachable: {agy_row.get('detail')}")
    if "agy" in dead:
        blocker.append("agy currently marked down by dispatch derivation")
    status = "up" if agy_row and agy_row.get("reachable") and "agy" not in dead else "down"
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tasks_path": str(TASKS_PATH),
        "status": "healthy" if status == "up" else "blocked",
        "rows": rows,
        "up": sorted(set(up)),
        "down": sorted(set(down)),
        "down_raw": sorted(dead),
        "agy": agy_row,
        "agy_down_reason": "; ".join(blocker) or None,
        "commands": [
            "python3 scripts/capacity-fill-ledger.py --write",
            "python3 scripts/dispatch-health.py --write --probe-async",
            "python3 scripts/route.py --tasks tasks.yaml --workdir ~/Workspace --apply",
        ],
    }


def write_outputs(snapshot: dict[str, Any]) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(build_markdown(snapshot), encoding="utf-8")
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="refresh markdown and ledger outputs")
    args = parser.parse_args()

    snapshot = build_snapshot()
    if args.write:
        write_outputs(snapshot)
        print(f"capacity-fill-ledger: wrote {DOC_PATH} and {LEDGER_PATH}")
        return 0

    print(build_markdown(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
