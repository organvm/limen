#!/usr/bin/env python3
"""Build the OpenCode daily capacity-fill packet surface.

This is the missing focused surface for CAPFILL packets:
it writes a compact capacity ledger and records the evidence that gates OpenCode
productivity for the day.

Run:
  python3 scripts/capacity-fill-ledger.py --write
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

def detect_root() -> Path:
    fallback = Path(__file__).resolve().parents[1]
    cwd = Path.cwd().resolve()
    env_root = Path(os.environ.get("LIMEN_ROOT", str(fallback)))
    candidates = [cwd, env_root, fallback]
    for candidate in candidates:
        if (candidate / "tasks.yaml").exists() and candidate.is_dir():
            return candidate
    return fallback


ROOT = detect_root()
DOC_PATH = ROOT / "docs" / "capacity-fill.md"
DISPATCH_HEALTH_DOC = ROOT / "docs" / "dispatch-health.md"
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "capacity-fill-ledger.json"
RECEIPT_DIR = ROOT / "docs" / "lane-checkups" / "opencode"
RECEIPT_PATH = RECEIPT_DIR / "20260629-12.md"

# Ensure local module import remains stable when run from a detached worktree.
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.capacity import CapacityRow, capacity_census, format_capacity_census  # noqa: E402
from limen.io import load_limen_file  # noqa: E402


def parse_dispatch_health(path: Path) -> dict[str, Any]:
    """Extract the dispatch-health status and blocker list, preserving human-readable evidence."""
    if not path.exists():
        return {"status": "missing", "blockers": []}

    text = path.read_text(encoding="utf-8", errors="replace")
    status_match = re.search(r"^Status: `([^`]+)`", text, re.MULTILINE)
    status = status_match.group(1) if status_match else "unknown"

    blockers: list[str] = []
    in_blockers = False
    for line in text.splitlines():
        if line.startswith("## Blockers"):
            in_blockers = True
            continue
        if in_blockers:
            if line.startswith("## "):
                break
            if line.startswith("- "):
                blockers.append(line[2:].strip())
    return {"status": status, "blockers": blockers}


def load_board() -> object | None:
    board_path = ROOT / "tasks.yaml"
    if not board_path.exists():
        print(f"capacity-fill-ledger: missing {board_path}, proceeding without board context")
        return None
    try:
        return load_limen_file(board_path)
    except Exception as exc:
        print(f"capacity-fill-ledger: could not load {board_path}: {exc}")
        return None


def write_capacity_receipt(rows: list[CapacityRow], opencode: CapacityRow, health: dict[str, Any], generated: str) -> str:
    lines = [
        "# Capacity Fill",
        "",
        f"Generated: `{generated}`",
        "",
        "## Opencode Lens",
        "",
        f"- Status: `{'up' if opencode['reachable'] else 'down'}`",
        f"- Capacity remaining: `{opencode['remaining']}/{opencode['limit']}`",
        f"- Detail: `{opencode['detail']}`",
        f"- Dispatch-health status: `{health['status']}`",
        "",
        "## Capacity census",
        "",
        "```text",
        format_capacity_census(rows),
        "```",
        "",
        "## Commands",
        "",
        "- Refresh this receipt: `python3 scripts/capacity-fill-ledger.py --write`",
        "- Check async proof: `python3 scripts/dispatch-health.py --write --probe-async`",
        "- Verify async dispatch: `pytest -q cli/tests/test_async_dispatch.py`",
        "",
        "## Human Gates",
        "",
        "- No implicit gate changes are made by this script.",
    ]

    if health["blockers"]:
        lines += ["", "## Dispatch-Health Blockers", ""] + [f"- {line}" for line in health["blockers"]]
    else:
        lines.append("")
        lines.append("- Dispatch-health reported no blockers.")
    return "\n".join(lines) + "\n"


def write_human_receipt(opencode: CapacityRow, health: dict[str, Any], generated: str) -> None:
    """Record a lane-specific blocker so the operator has one durable next action."""
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    blocks = [line for line in health.get("blockers", []) if any(k in line for k in ("live-root", "heartbeat", "async"))]
    if not blocks:
        blocks = [f"OpenCode not reachable: {opencode['detail']}"]

    lines = [
        "# Opencode CAPFILL lane checkup — 20260629-12",
        "",
        f"Generated: `{generated}`",
        "",
        "## Status",
        "",
        "- Lane: `opencode`",
        "- Condition: `blocked`",
        "",
        "## Blocker",
        "",
    ] + [f"- {line}" for line in blocks] + [
        "",
        "## Exact evidence command",
        "",
        "- `python3 scripts/dispatch-health.py --write --probe-async`",
        "",
        "## Human decision",
        "",
        "- This packet is waiting on live-root / dispatch substrate alignment before OpenCode can be scheduled predictably.",
    ]
    RECEIPT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_index(rows: list[CapacityRow], health: dict[str, Any], generated: str) -> dict[str, Any]:
    opencode = next((row for row in rows if row["agent"] == "opencode"), None)
    return {
        "generated": generated,
        "opencode": opencode,
        "health": health,
        "capacity_rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write capacity-fill ledger for the OpenCode packet.")
    parser.add_argument("--write", action="store_true", help="Write docs/capacity-fill.md and cache index")
    args = parser.parse_args()

    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = capacity_census(load_board())
    opencode = next((row for row in rows if row["agent"] == "opencode"), None)
    health = parse_dispatch_health(DISPATCH_HEALTH_DOC)

    if args.write:
        if not opencode:
            print("capacity-fill-ledger: no opencode row in capacity census")
            return 1

        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOC_PATH.write_text(
            write_capacity_receipt(rows, opencode, health, generated),
            encoding="utf-8",
        )

        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
        index = build_index(rows, health, generated)
        index_path = PRIVATE_INDEX
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")

        if not opencode["reachable"] or health["status"] != "healthy":
            write_human_receipt(opencode, health, generated)
        print(f"capacity-fill-ledger: wrote {DOC_PATH} and {index_path}")
        return 0

    for row in rows:
        print(f"{row['agent']} reachable={row['reachable']} remaining={row['remaining']}/{row['limit']}")
    print(f"dispatch-health: {health['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
