#!/usr/bin/env python3
"""Generate a focused capacity ledger for lane-fill operations.

This ledger stays lightweight:
- prints the current capacity census (reused from limen.capacity);
- highlights the current OpenCode slot visibility/reachability;
- optionally writes ``docs/capacity-fill.md`` and an ignored JSON snapshot.

It is intentionally local and non-invasive: no task-state writes and no side
effects outside docs/logs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
if not os.access(ROOT / "docs", os.W_OK):
    ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import capacity_census, format_capacity_census  # noqa: E402
from limen.io import load_limen_file  # noqa: E402

TASKS_PATH = ROOT / "tasks.yaml"
DISPATCH_HEALTH_DOC = ROOT / "docs" / "dispatch-health.md"
DOC_PATH = ROOT / "docs" / "capacity-fill.md"
JSON_PATH = ROOT / "logs" / "capacity-fill-ledger.json"


def _dispatch_health_status() -> str:
    if not DISPATCH_HEALTH_DOC.exists():
        return "missing"
    text = DISPATCH_HEALTH_DOC.read_text(errors="replace")
    match = re.search(r"^Status:\s*`([^`]+)`", text, flags=re.M)
    return match.group(1).strip() if match else "unknown"


def _to_dict(board: Any) -> Mapping[str, Any] | Any:
    if isinstance(board, dict):
        return board
    if hasattr(board, "model_dump"):
        try:
            return board.model_dump(mode="json", exclude_none=True)
        except Exception:
            pass
    if hasattr(board, "dict"):
        try:
            return board.dict(exclude_none=True)
        except Exception:
            pass
    return board


def build_ledger(board: Any) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    payload = _to_dict(board)
    census = capacity_census(payload)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dispatch_health = _dispatch_health_status()
    up = [row["agent"] for row in census if row["reachable"]]
    down = [row["agent"] for row in census if not row["reachable"]]
    opencode = next((row for row in census if row["agent"] == "opencode"), {})
    lines = [
        "# Capacity Fill Ledger",
        "",
        f"Generated: `{timestamp}`",
        f"Dispatch health status: `{dispatch_health}`",
        "",
        "## Summary",
        f"- up: {', '.join(up) if up else 'none'}",
        f"- down: {', '.join(down) if down else 'none'}",
        "",
        "## OpenCode slot",
        f"- reachable: {'yes' if bool(opencode.get('reachable')) else 'no'}",
        f"- remaining: {opencode.get('remaining', 'unlimited')}/{opencode.get('limit', 'unlimited')}",
        f"- detail: {opencode.get('detail', '-')}",
        "",
        "## Capacity census",
        "```",
        format_capacity_census(census),
        "```",
        "",
        "## Commands",
        "- Re-run this ledger: `python3 scripts/capacity-fill-ledger.py --write`",
        "- Re-check routing pressure: `PYTHONPATH=cli/src python3 scripts/route.py --tasks tasks.yaml`",
    ]
    json_payload = {
        "generated_at": timestamp,
        "dispatch_health": dispatch_health,
        "up": up,
        "down": down,
        "opencode": dict(opencode),
        "census": census,
    }
    return "\n".join(lines), census, json_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tasks", default=str(TASKS_PATH), help="Path to tasks.yaml (or equivalent tasks file)"
    )
    parser.add_argument("--write", action="store_true", help="Write docs and logs payloads")
    args = parser.parse_args()

    try:
        board = load_limen_file(Path(args.tasks))
    except Exception as exc:
        print(f"error: failed to load {args.tasks}: {exc}")
        return 1

    text, census, snapshot = build_ledger(board)
    print(text)

    if args.write:
        DOC_PATH.write_text(text + "\n", encoding="utf-8")
        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
        print(f"wrote {DOC_PATH}")
        print(f"wrote {JSON_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
