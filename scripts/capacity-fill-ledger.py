#!/usr/bin/env python3
"""Write the paid-lane capacity fill receipt.

Read-only on tasks.yaml. This records whether each paid lane is actually being
fed productively against its own reset window, instead of relying on the operator
to remember which subscriptions should have been used today.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import capacity_fill_snapshot, format_capacity_fill  # noqa: E402
from limen.dispatch import _down_lanes  # noqa: E402
from limen.io import load_limen_file  # noqa: E402

DOC_PATH = ROOT / "docs" / "capacity-fill.md"
PRIVATE_INDEX = ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "capacity-fill.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the paid-lane capacity fill receipt.")
    parser.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    args = parser.parse_args()

    board = load_limen_file(Path(args.tasks))
    snapshot = capacity_fill_snapshot(board, down_lanes=_down_lanes())
    markdown = format_capacity_fill(snapshot)
    if args.write:
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOC_PATH.write_text(markdown, encoding="utf-8")
        PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
        PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(markdown, end="")

    msg = f"capacity-fill: {snapshot['status']} with {len(snapshot['blockers'])} blockers"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
