#!/usr/bin/env python3
"""Build a Claude lane capacity-fill ledger.

This is a focused helper for CAPFILL packets: it reads the task board and the
current dispatch-health receipt, then writes a lane-level markdown status surface.
It never edits credentials, launchd, task state, or emits external effects.
"""
from __future__ import annotations

import argparse
import datetime as dt
from collections import Counter
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "capacity-fill.md"
DISPATCH_HEALTH_DOC = ROOT / "docs" / "dispatch-health.md"
TASKS_PATH = ROOT / "tasks.yaml"
RECEIPT_DIR = ROOT / "docs" / "lane-checkups" / "claude"
RECEIPT_PATH = RECEIPT_DIR / "20260629-03.md"


def load_yaml_tasks() -> tuple[list[dict], dict, dict]:
    data: dict = {}
    with TASKS_PATH.open("r", encoding="utf-8", errors="replace") as handle:
        data = yaml.safe_load(handle) or {}
    tasks = data.get("tasks", []) if isinstance(data, dict) else []
    return (
        [task for task in tasks if isinstance(task, dict)],
        data.get("portal", {}) if isinstance(data, dict) else {},
        data,
    )


def claude_task_filter(task: dict[str, object]) -> bool:
    return (str(task.get("target_agent") or "").lower() in {"claude", "any"})


def claude_task_counts(tasks: list[dict[str, object]]) -> tuple[int, dict[str, int], list[tuple[str, str, str, int]]]:
    lane_tasks = [task for task in tasks if claude_task_filter(task)]
    by_status = Counter(str(task.get("status", "")) for task in lane_tasks)
    top_open = [
        (
            str(task.get("id") or ""),
            str(task.get("title") or ""),
            str(task.get("priority") or ""),
            int(task.get("budget_cost") or 0),
        )
        for task in lane_tasks
        if str(task.get("status") or "") == "open"
    ]
    top_open = sorted(top_open, key=lambda item: (item[2], item[0]))[:20]
    return len(lane_tasks), dict(by_status), top_open


def load_dispatch_health() -> tuple[str, list[tuple[str, str]]]:
    if not DISPATCH_HEALTH_DOC.exists():
        return "unknown", [("capacity-fill-script", "docs/dispatch-health.md missing")]

    text = DISPATCH_HEALTH_DOC.read_text(encoding="utf-8", errors="replace")
    status_match = re.search(r"^Status:\s*`([^`]+)`", text, re.M)
    status = status_match.group(1).strip() if status_match else "unknown"
    blockers: list[tuple[str, str]] = []
    in_blockers = False
    for line in text.splitlines():
        if line.startswith("## Blockers"):
            in_blockers = True
            continue
        if in_blockers:
            if line.startswith("## "):
                break
            m = re.match(r"- `([^`]+)`: (.+)", line.strip())
            if m:
                blockers.append((m.group(1), m.group(2)))
    if not blockers and status != "healthy":
        blockers.append(("dispatch-health", f"blocked with status {status} but no blockers rendered"))
    return status, blockers


def portal_line(portal: dict) -> str:
    budget = portal.get("budget", {})
    daily = int(budget.get("daily") or 0)
    track = budget.get("track", {})
    used_by_claude = int((track.get("per_agent") or {}).get("claude", 0))
    return (
        f"- Daily cap: `{daily}`\n"
        f"- Claude daily consumed: `{used_by_claude}`\n"
        f"- Remaining slot room (lane-local): `{max(daily - used_by_claude, 0)}`\n"
    )


def render_markdown(now: dt.datetime, portal: dict, status: str, blockers: list[tuple[str, str]],
                   lane_count: int, by_status: dict[str, int],
                   top_open: list[tuple[str, str, str, int]]) -> str:
    blocked = status.lower() != "healthy"
    state = "blocked" if blocked else "ready"
    blocker_lines = [f"- `{code}`: {evidence}" for code, evidence in blockers] if blockers else ["- none"]
    top_rows = "\n".join(f"- `{task_id}` ({priority}, {budget}) {title}" for task_id, title, priority, budget in top_open)
    if not top_rows:
        top_rows = "- none"
    return f"""# Claude Capacity Fill

Generated: `{now.isoformat(timespec='seconds')}`

## Lane State

- Status: `{state}`
- Dispatch health: `{status}`

## Capacity Snapshot

{portal_line(portal)}

## Claude Scope

- Total Claude-targeted tasks: `{lane_count}`
- Status counts: `{', '.join(f'{key}={value}' for key, value in sorted(by_status.items())) or 'no tasks'}`

## Open Queue (top 20)

{top_rows}

## Dispatch Blockers

{chr(10).join(blocker_lines)}

## Next Step

- If status is `ready`, continue dispatch for the top open IDs.
- If status is `blocked`, run the human-gated lane checkup in `docs/lane-checkups/claude/20260629-03.md`.

## Commands

- Refresh this ledger: `python3 scripts/capacity-fill-ledger.py --write`
- Re-check dispatch-health freshness: `python3 scripts/dispatch-health.py --write --probe-async`
"""


def write_lane_checkup(blockers: list[tuple[str, str]], status: str) -> None:
    if status.lower() == "healthy" and not blockers:
        if RECEIPT_PATH.exists():
            RECEIPT_PATH.unlink(missing_ok=True)
        return
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    top = "\n".join(f"- `{bid}`: {evidence}" for bid, evidence in blockers)
    text = f"""# Claude Lane Checkup — 2026-06-29 (packet 03)

Generated: `{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}`

Status: `blocked`

## Blocking items (from docs/dispatch-health.md)

{top or '- none'}

## Human-path evidence

- `python3 scripts/live-root-gate.py --write`
- `git -C ~/Workspace/limen status --branch --short`
- `git -C ~/Workspace/limen cherry origin/main HEAD`

## Gate check command

Run in sequence and stop on first mismatch:

```bash
python3 scripts/dispatch-health.py --write --probe-async
python3 scripts/live-root-gate.py --write
```
"""
    RECEIPT_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a Claude capacity-fill ledger doc.")
    parser.add_argument("--write", action="store_true", help="write docs/capacity-fill.md and any lane checkup receipt")
    args = parser.parse_args()

    tasks, portal, _ = load_yaml_tasks()
    lane_count, by_status, top_open = claude_task_counts(tasks)
    health_status, blockers = load_dispatch_health()

    now = dt.datetime.now(dt.timezone.utc)
    markdown = render_markdown(now, portal, health_status, blockers, lane_count, by_status, top_open)

    if args.write:
        DOC_PATH.write_text(markdown, encoding="utf-8")
        write_lane_checkup(blockers, health_status)
        print(f"capacity-fill-ledger: wrote {DOC_PATH}")
        if health_status.lower() != "healthy":
            print(f"capacity-fill-ledger: blocked; wrote {RECEIPT_PATH}")
        return 0
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
