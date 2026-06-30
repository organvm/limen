#!/usr/bin/env python3
"""Capture a lane-capacity fill snapshot for Agy capacity packets.

This script is intentionally small and read-only with respect to queue state:
it reports current dispatcher reachability and writes two tracked receipts:

- docs/capacity-fill.md: the current packet surface for all paid lanes.
- docs/lane-checkups/agy/<packet>.md: a focused Agy lane receipt with blocker evidence
  when Agy is not currently routable.

Call:
python3 scripts/capacity-fill-ledger.py --write
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))

from limen.capacity import capacity_census
from limen.dispatch import _down_lanes
from limen.io import load_limen_file

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
DOC_PATH = ROOT / "docs" / "capacity-fill.md"
PACKET_DIR = ROOT / "docs" / "lane-checkups" / "agy"
HEALTH_DOC = ROOT / "docs" / "dispatch-health.md"


def _packet_id() -> str:
    """Preferred packet id is explicit env, else derived from dispatch-health date.

    Existing runbook packets in this repo use date-based ids (for example, 20260629-16),
    so we mirror that shape by default to keep this packet compatible with the lane surface.
    """
    explicit = os.environ.get("CAPFILL_ID") or os.environ.get("LIMEN_CAPFILL_ID")
    if explicit:
        return explicit

    date_token = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    try:
        text = HEALTH_DOC.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"Generated: `([^`]+)`", text)
        if match:
            prefix = match.group(1).split("T", 1)[0]
            date_token = prefix.replace("-", "")
    except OSError:
        pass

    return f"{date_token}-16"


def _as_ascii(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def _build_capacity_lines(rows: list[dict]) -> list[str]:
    lines: list[str] = ["| lane | state | remaining | limit | detail |", "|---|---|---|---|---|"]
    for row in rows:
        lines.append(
            f"| {row['agent']} | {'up' if row['reachable'] else 'down'} | {row['remaining']} "
            f"| {row['limit']} | {_as_ascii(str(row['detail']))} |"
        )
    return lines


def _find_agent_row(rows: list[dict], agent: str) -> dict[str, object] | None:
    for row in rows:
        if row.get("agent") == agent:
            return row
    return None


def _load_rows() -> list[dict]:
    board = load_limen_file(TASKS)
    return capacity_census(board)


def _write_markdown(packet_id: str, rows: list[dict], down_lanes: set[str]) -> tuple[Path, Path]:
    agy_row = _find_agent_row(rows, "agy")
    if agy_row is None:
        agy_row = {
            "agent": "agy",
            "reachable": False,
            "remaining": "n/a",
            "limit": "n/a",
            "detail": "no agy row in capacity census",
        }

    blocker = False
    if not bool(agy_row.get("reachable")):
        blocker = True
    if "agy" in down_lanes:
        blocker = True

    packet_path = PACKET_DIR / f"{packet_id}.md"
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    capacity_lines = [
        "# Capacity Fill Ledger",
        "",
        f"Generated: `{generated}`",
        f"Packet: `{packet_id}`",
        "",
        "## Scope",
        "",
        "- target lane: `agy`",
        "- objective: close one lane-fill gap check for Agy productivity",
        "",
        "## Capacity Census",
        "",
        *_build_capacity_lines(rows),
        "",
        "## Down Lanes",
        "",
        f"{', '.join(sorted(down_lanes)) or 'none'}",
        "",
        "## Commands",
        "",
        "- `python3 scripts/dispatch-health.py --write --probe-async`",
        "- `python3 scripts/capacity-fill-ledger.py --write`",
        "",
    ]

    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text("\n".join(capacity_lines) + "\n", encoding="utf-8")

    agy_detail = _as_ascii(str(agy_row.get("detail", "")))
    agy_remaining = agy_row.get("remaining")
    agy_limit = agy_row.get("limit")
    agy_reachable = bool(agy_row.get("reachable"))

    receipt_lines = [
        f"# CAPFILL-agy-{packet_id}",
        "",
        f"Generated: `{generated}`",
        "",
        "## Agy Capacity Check",
        "",
        f"- reachable: `{agy_reachable}`",
        f"- remaining: `{agy_remaining}` / `{agy_limit}`",
        f"- detail: `{agy_detail}`",
        "",
        "## Down / Blocked Lanes",
        "",
    ]

    if down_lanes:
        for lane in sorted(down_lanes):
            receipt_lines.append(f"- {lane}")
    else:
        receipt_lines.append("- none")

    receipt_lines += [
        "",
    ]

    if blocker:
        receipt_lines += [
            "## Human-Gated Blocker",
            "",
            "Agy did not become dispatch-ready in this packet.",
            "",
            "- Exact blocker check command:",
            "  - `python3 - <<'PY'`",
            "  - `from limen.dispatch import _down_lanes`",
            "  - `print(sorted(_down_lanes()))`",
            "  - `PY`",
            "",
            "- Evidence captured when generating this receipt:",
            f"  - Agy appears in down-lanes set: `{'agy' in down_lanes}`",
            f"  - Agy capacity row reachable: `{agy_reachable}`",
            "",
            "## Next Human Path",
            "",
            "1) if network reachability is expected, re-run this command after DNS/network is stable.",
            "2) if running intentionally on a dark network segment, keep `LIMEN_OAUTH_PREFLIGHT=0` for this",
            "   run only after operator approval and local policy review.",
            "",
        ]
    else:
        receipt_lines += [
            "## Status",
            "",
            "- Agy was reachable and not in the down-lane set at packet write time.",
            "- Packet is ready for dispatch-fill follow-up.",
            "",
        ]

    receipt_lines += [
        "## Commands",
        "",
        "- `python3 scripts/dispatch-health.py --write --probe-async`",
        "- `python3 scripts/capacity-fill-ledger.py --write`",
        "",
    ]

    PACKET_DIR.mkdir(parents=True, exist_ok=True)
    packet_path.write_text("\n".join(receipt_lines) + "\n", encoding="utf-8")
    return DOC_PATH, packet_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Agy capacity-fill receipts.")
    parser.add_argument("--write", action="store_true", help="write docs/capacity-fill.md and packet receipt")
    args = parser.parse_args()

    rows = _load_rows()
    down_lanes = _down_lanes()

    if not args.write:
        # Keep CLI cheap for focused checks.
        print(f"Capacity rows: {len(rows)}")
        print(f"Down lanes: {sorted(down_lanes)}")
        return 0

    packet_id = _packet_id()
    doc_path, receipt_path = _write_markdown(packet_id, rows, down_lanes)
    print(f"wrote {doc_path}")
    print(f"wrote {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
