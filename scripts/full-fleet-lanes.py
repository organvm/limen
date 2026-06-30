#!/usr/bin/env python3
"""Resolve and classify the full Limen fleet lane set.

This is the operator-facing lane resolver for overnight runs:

  python3 scripts/full-fleet-lanes.py --format shell
  python3 scripts/full-fleet-lanes.py --lanes all --format table
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import classify_lanes, resolve_lane_selector  # noqa: E402
from limen.dispatch import _down_lanes  # noqa: E402
from limen.io import load_limen_file  # noqa: E402


def _load_board(tasks: Path):
    try:
        return load_limen_file(tasks)
    except Exception:
        return None


def _csv(items: list[str] | tuple[str, ...]) -> str:
    return ",".join(items)


def build_snapshot(args: argparse.Namespace) -> dict[str, object]:
    tasks = Path(args.tasks)
    board = _load_board(tasks)
    down = _down_lanes()
    selected = resolve_lane_selector(args.lanes, board=board, down_lanes=down)
    classified = classify_lanes(board, down_lanes=down)
    by_status: dict[str, list[str]] = {"active": [], "down": [], "depleted": [], "human-gated": []}
    for row in classified:
        by_status.setdefault(str(row["status"]), []).append(str(row["agent"]))
    return {
        "selector": args.lanes,
        "tasks": str(tasks),
        "selected": list(selected),
        "active": by_status.get("active", []),
        "down": by_status.get("down", []),
        "depleted": by_status.get("depleted", []),
        "human_gated": by_status.get("human-gated", []),
        "classification": classified,
    }


def emit_shell(snapshot: dict[str, object]) -> None:
    values = {
        "FLEET_SELECTOR": str(snapshot["selector"]),
        "LIMEN_LANES": _csv(snapshot["selected"]),
        "FLEET_LANES_ACTIVE": _csv(snapshot["active"]),
        "FLEET_LANES_DOWN": _csv(snapshot["down"]),
        "FLEET_LANES_DEPLETED": _csv(snapshot["depleted"]),
        "FLEET_LANES_HUMAN_GATED": _csv(snapshot["human_gated"]),
    }
    for key, value in values.items():
        print(f"{key}={shlex.quote(value)}")


def emit_table(snapshot: dict[str, object]) -> None:
    print("| Lane | Kind | Status | Detail |")
    print("|---|---|---|---|")
    for row in snapshot["classification"]:
        detail = str(row.get("detail") or "").replace("|", "\\|")
        print(f"| `{row['agent']}` | `{row['kind']}` | `{row['status']}` | {detail} |")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and classify Limen full-fleet lanes.")
    parser.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    parser.add_argument("--lanes", default=os.environ.get("LIMEN_LANES", "auto"))
    parser.add_argument("--format", choices=("shell", "json", "table", "csv"), default="table")
    args = parser.parse_args()
    try:
        snapshot = build_snapshot(args)
    except ValueError as exc:
        print(f"full-fleet-lanes: {exc}", file=sys.stderr)
        return 2
    if args.format == "shell":
        emit_shell(snapshot)
    elif args.format == "json":
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    elif args.format == "csv":
        print(_csv(snapshot["selected"]))
    else:
        emit_table(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
