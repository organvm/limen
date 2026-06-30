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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import capacity as capacity_module  # noqa: E402
from limen.dispatch import _down_lanes  # noqa: E402
from limen.io import load_limen_file  # noqa: E402

DEFAULT_DAILY_TASK_TARGETS: dict[str, int] = {
    "jules": 100,
    "claude": 15,
    "opencode": 100,
    "agy": 100,
    "gemini": 10,
    "codex": 100,
    "copilot": 100,
    "warp": 10,
    "oz": 10,
    "github_actions": 10,
}


def _int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _task_value(task: object, key: str, default: object | None = None) -> object | None:
    if isinstance(task, dict):
        return task.get(key, default)
    return getattr(task, key, default)


def _board_value(board: object, key: str, default: object | None = None) -> object | None:
    if isinstance(board, dict):
        return board.get(key, default)
    return getattr(board, key, default)


def _task_status(task: object) -> str:
    return str(_task_value(task, "status", "") or "")


def _task_agent(task: object) -> str:
    return str(_task_value(task, "target_agent", "") or "")


def _task_cost(task: object) -> int:
    return _int(_task_value(task, "budget_cost", 1), 1)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _dispatch_event_attempts(board: object, agent: str, day: str) -> int:
    tasks = _board_value(board, "tasks", []) or []
    if not isinstance(tasks, list):
        return 0
    touched: set[str] = set()
    for task in tasks:
        task_id = str(_task_value(task, "id", "") or "")
        for event in _task_value(task, "dispatch_log", []) or []:
            if not isinstance(event, dict):
                continue
            if capacity_module.canonical_agent(str(_task_value(event, "agent", "") or "")) != agent:
                continue
            if not str(_task_value(event, "timestamp", "")).startswith(day):
                continue
            if str(_task_value(event, "status", "") or "") == "open":
                continue
            if task_id:
                touched.add(task_id)
    return len(touched)


def _lane_work_counts(board: object, agent: str) -> tuple[int, int]:
    tasks = _board_value(board, "tasks", []) or []
    if not isinstance(tasks, list):
        return 0, 0
    open_work = 0
    active_work = 0
    for task in tasks:
        status = _task_status(task)
        task_agent = capacity_module.canonical_agent(_task_agent(task))
        cost = _task_cost(task)
        if status == "open" and task_agent in {agent, "any"}:
            open_work += cost
        elif status in {"dispatched", "in_progress"} and task_agent == agent:
            active_work += cost
    return open_work, active_work


def _daily_task_target(agent: str, board: object) -> int:
    env_name = f"LIMEN_{agent.upper()}_DAILY_TASKS"
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return _int(env_value, 0)
    if agent in DEFAULT_DAILY_TASK_TARGETS:
        return DEFAULT_DAILY_TASK_TARGETS[agent]
    portal = _board_value(board, "portal", {}) or {}
    budget = _board_value(portal, "budget", {}) if isinstance(portal, dict) else {}
    if isinstance(budget, dict) and isinstance(budget.get("per_agent", {}), dict):
        return _int((budget.get("per_agent", {}) or {}).get(agent), 0)
    return 0


def _fallback_capacity_fill_snapshot(board: object, *, down_lanes: set[str] | None = None, **_) -> dict[str, object]:
    census_rows = capacity_module.capacity_census(board)
    by_agent = {row["agent"]: row for row in census_rows}
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    track = _board_value(_board_value(board, "portal", {}) or {}, "budget", {}) or {}
    per_agent_spent = _board_value(track, "track", {}) or {}
    per_agent_spent = _board_value(per_agent_spent, "per_agent", {}) if isinstance(per_agent_spent, dict) else {}
    if not isinstance(per_agent_spent, dict):
        per_agent_spent = {}

    rows: list[dict[str, object]] = []
    blockers: list[dict[str, str]] = []
    down_lanes = down_lanes or set()

    for agent in capacity_module.PAID_AGENT_ORDER:
        target = _daily_task_target(agent, board)
        if target <= 0:
            continue
        productive = _int(per_agent_spent.get(agent), 0)
        attempts = max(
            _dispatch_event_attempts(board, agent, day),
            productive,
        )
        open_work, active_work = _lane_work_counts(board, agent)
        expected_now = target
        remaining = max(0, target - productive)
        census = by_agent.get(agent, {})
        reachable = bool(census.get("reachable", False)) and agent not in down_lanes

        if agent in down_lanes:
            status = "blocked"
            evidence = "lane is down by the live dispatch gate"
            action = "clear gate/dispatch issues, then route and dispatch work"
        elif productive >= expected_now:
            status = "healthy"
            evidence = f"productive {productive}/{expected_now}; attempts {attempts}/{expected_now}"
            action = "keep dispatch pace normal"
        elif attempts >= expected_now:
            status = "unproductive"
            evidence = (
                f"attempted {attempts}/{expected_now}, but productive board spend is "
                f"{productive}/{expected_now}"
            )
            action = "heal failed/rerouted dispatches so attempts become done/dispatched work"
        elif not reachable:
            status = "blocked"
            evidence = f"productive {productive}/{expected_now}, but the lane is not reachable"
            action = "fix lane reachability/auth/budget before feeding work"
        elif open_work > 0:
            status = "underfilled"
            evidence = f"productive {productive}/{expected_now}; attempts {attempts}/{expected_now}"
            action = "route open work and dispatch before the window resets"
        else:
            status = "no_work"
            evidence = f"productive {productive}/{expected_now}, but no open/any work is available"
            action = "generate or route open work for this lane"

        row = {
            "agent": agent,
            "target": target,
            "expected_now": expected_now,
            "productive": productive,
            "attempts": attempts,
            "observed": max(productive, attempts),
            "open_work": open_work,
            "active_work": active_work,
            "remaining": remaining,
            "reachable": reachable,
            "status": status,
            "evidence": evidence,
            "action": action,
        }
        rows.append(row)
        if status in {"underfilled", "unproductive", "blocked", "no_work"}:
            blockers.append({"id": f"lane-fill-{agent}", "evidence": f"{agent}: {evidence}"})

    overall = "healthy" if not blockers else "blocked"
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "status": overall,
        "rows": rows,
        "blockers": blockers,
    }


def _fallback_format_capacity_fill(snapshot: dict[str, object]) -> str:
    lines = [
        "# Capacity Fill",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        f"Status: `{snapshot['status']}`",
        "",
        "| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in snapshot["rows"]:
        lines.append(
            "| "
            f"`{row['agent']}` | `{row['status']}` | {row['productive']} | {row['attempts']} | "
            f"{row['expected_now']} | {row['target']} | {row['open_work']} | {row['active_work']} | "
            f"{row['action']} |"
        )
    lines.extend(["", "## Evidence", ""])
    for row in snapshot["rows"]:
        lines.append(f"- `{row['agent']}`: {row['evidence']}")
    return "\n".join(lines) + "\n"


capacity_fill_snapshot = getattr(capacity_module, "capacity_fill_snapshot", _fallback_capacity_fill_snapshot)
format_capacity_fill = getattr(capacity_module, "format_capacity_fill", _fallback_format_capacity_fill)

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
