#!/usr/bin/env python3
"""Write the paid-lane capacity fill receipt.

Read-only on tasks.yaml; this records how well each paid lane is fed and how much
productive work was actually completed in the current day.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
import sys

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import (  # type: ignore
    canonical_agent,
    capacity_census,
)  # noqa: E402
from limen.io import load_limen_file  # noqa: E402

DOC_PATH = ROOT / "docs" / "capacity-fill.md"
PRIVATE_INDEX = ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "capacity-fill.json"


def _int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _get(value: object, key: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            pass
    try:
        return getattr(value, key)
    except AttributeError:
        return default


def _load_usage(root: Path | None = None) -> dict[str, Any]:
    usage_path = (root or ROOT) / "logs" / "usage.json"
    try:
        return json.loads(usage_path.read_text())
    except (OSError, ValueError):
        return {}


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _window_hours_from_usage(agent: str, usage: dict[str, Any]) -> float:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    if isinstance(info, dict):
        hours = info.get("window_hours")
        if isinstance(hours, (int, float)) and hours > 0:
            return float(hours)
        window = str(info.get("window") or "")
    else:
        window = ""
    match = re.search(r"(\\d+(?:\\.\\d+)?)\\s*h", window)
    if match:
        return float(match.group(1))
    if "today" in window or "day" in window or "24" in window:
        return 24.0
    return 24.0


def _progress_from_usage(agent: str, usage: dict[str, Any], reset_at: datetime | None, now: datetime) -> float:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    if isinstance(info, dict):
        time_left = info.get("time_left_frac")
        if isinstance(time_left, (int, float)):
            return max(0.0, min(1.0, 1.0 - float(time_left)))
    if reset_at is None:
        return 1.0
    hours = _window_hours_from_usage(agent, usage)
    elapsed = max(0.0, (now - reset_at).total_seconds() / 3600.0)
    return max(0.0, min(1.0, elapsed / hours))


def _task_status(task: object) -> str:
    return str(_get(task, "status", "") or "")


def _task_agent(task: object) -> str:
    return canonical_agent(str(_get(task, "target_agent", "") or ""))


def _task_cost_int(task: object) -> int:
    return _int(_get(task, "budget_cost", 1), 1)


def _dispatch_event_attempts(board: object, agent: str, day: str) -> int:
    tasks = _get(board, "tasks", []) or []
    if not isinstance(tasks, list):
        return 0
    touched: set[str] = set()
    for task in tasks:
        task_id = str(_get(task, "id", "") or "")
        log = _get(task, "dispatch_log", []) or []
        if not isinstance(log, list):
            continue
        for event in log:
            event_agent = canonical_agent(str(_get(event, "agent", "") or ""))
            if event_agent != agent:
                continue
            timestamp = _get(event, "timestamp")
            if day and not str(timestamp).startswith(day):
                continue
            status = str(_get(event, "status", "") or "")
            if status == "open":
                continue
            if task_id:
                touched.add(task_id)
    return len(touched)


def _usage_consumed_runs(agent: str, usage: dict[str, Any]) -> int:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    if not isinstance(info, dict):
        return 0
    signal = str(info.get("signal") or "")
    if signal in {"count", "dispatch-count", "runs"}:
        return _int(info.get("consumed"), 0)
    return 0


def _usage_health(agent: str, usage: dict[str, Any]) -> str:
    vendors = usage.get("vendors") if isinstance(usage, dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else {}
    return str(info.get("health") or "") if isinstance(info, dict) else ""


def _lane_work_counts(board: object, agent: str) -> tuple[int, int]:
    tasks = _get(board, "tasks", []) or []
    if not isinstance(tasks, list):
        return 0, 0
    open_work = 0
    active_work = 0
    for task in tasks:
        status = _task_status(task)
        task_agent = _task_agent(task)
        cost = _task_cost_int(task)
        if status == "open" and task_agent in {agent, "any"}:
            open_work += cost
        elif status in {"dispatched", "in_progress"} and task_agent == agent:
            active_work += cost
    return open_work, active_work


def _daily_task_target(agent: str, board: object) -> int:
    env_name = f"LIMEN_{agent.upper()}_DAILY_TASKS"
    if os.environ.get(env_name):
        return _int(os.environ.get(env_name), 0)
    if agent == "claude":
        return 15
    budget = _get(board, "portal", {})
    per_agent = _get(budget, "budget", {})
    caps = _get(per_agent, "per_agent", {}) or {}
    if isinstance(caps, dict):
        return _int(caps.get(agent), 0)
    return 0


def _load_down_lanes() -> set[str]:
    try:
        from limen.dispatch import _down_lanes as active_down_lanes  # noqa: PLC0415

        return active_down_lanes()
    except Exception:
        return set()


def _compat_capacity_fill_snapshot(
    board: object,
    *,
    now: datetime | None = None,
    usage: dict[str, Any] | None = None,
    down_lanes: set[str] | None = None,
    agents: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    from limen.capacity import capacity_census

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    usage = usage if usage is not None else _load_usage()
    down_lanes = down_lanes or set()
    agents = agents or ("jules", "claude", "opencode", "agy", "gemini", "codex")
    portal = _get(board, "portal", {})
    budget = _get(portal, "budget", {})
    track = _get(budget, "track", {})
    progress_day = str(_get(track, "date", "") or now.date().isoformat())
    per_agent_spent = _get(track, "per_agent", {})
    if not isinstance(per_agent_spent, dict):
        per_agent_spent = {}
    per_agent_reset = _get(track, "per_agent_reset", {}) or {}
    if not isinstance(per_agent_reset, dict):
        per_agent_reset = {}
    census = {row["agent"]: row for row in capacity_census(board)}
    rows = []
    blockers = []
    bad_usage_health = {"exhausted", "rate-limited", "low", "throttle"}
    for agent in agents:
        target = _daily_task_target(agent, board)
        if target <= 0:
            continue
        reset_at = _parse_dt(per_agent_reset.get(agent))
        expected_progress = _progress_from_usage(agent, usage, reset_at, now)
        expected_now = min(target, int(round(target * expected_progress)))
        if expected_progress > 0 and expected_now == 0:
            expected_now = 1
        productive = _int(per_agent_spent.get(agent), 0)
        attempts = max(_dispatch_event_attempts(board, agent, progress_day), _usage_consumed_runs(agent, usage))
        observed = max(productive, attempts)
        open_work, active_work = _lane_work_counts(board, agent)
        remaining = max(0, target - productive)
        row_census = census.get(agent)
        reachable = bool(row_census and row_census["reachable"]) and agent not in down_lanes
        usage_health = _usage_health(agent, usage)

        if agent in down_lanes:
            status = "blocked"
            evidence = "lane is down by the live dispatch gate"
            action = "clear the lane-down/auth/rate-limit gate, then route and dispatch this lane"
        elif usage_health in bad_usage_health and observed > 0:
            status = "depleted"
            evidence = f"usage meter health={usage_health}; observed={observed}, productive={productive}"
            action = "wait for this lane's meter to refresh or fail over before feeding it again"
        elif expected_now > 0 and productive < expected_now:
            if attempts >= expected_now:
                status = "unproductive"
                evidence = f"attempted {attempts}/{expected_now}, but productive board spend is {productive}/{expected_now}"
                action = "heal failed/rerouted dispatches so attempts become done/dispatched work"
            elif reachable and open_work > 0:
                status = "underfilled"
                evidence = f"productive {productive}/{expected_now}; attempts {attempts}/{expected_now}"
                action = "route open work to this lane and dispatch before the window resets"
            elif open_work <= 0:
                status = "no_work"
                evidence = f"productive {productive}/{expected_now}, but no open/any work is available"
                action = "generate or route appropriate open work for this lane"
            else:
                status = "blocked"
                evidence = f"productive {productive}/{expected_now}, but the lane is not reachable"
                action = "fix lane reachability/auth/budget before routing more work"
        else:
            status = "healthy"
            evidence = f"productive {productive}/{expected_now}; attempts {attempts}/{expected_now}"
            action = "keep pacing normally"

        row = {
            "agent": agent,
            "target": target,
            "expected_now": expected_now,
            "productive": productive,
            "attempts": attempts,
            "observed": observed,
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

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "status": "healthy" if not blockers else "blocked",
        "rows": rows,
        "blockers": blockers,
    }


def _compat_format_capacity_fill(snapshot: dict[str, Any]) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the paid-lane capacity fill receipt.")
    parser.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    args = parser.parse_args()

    board = load_limen_file(Path(args.tasks))
    try:
        from limen.capacity import capacity_fill_snapshot, format_capacity_fill  # type: ignore
    except (ImportError, AttributeError):
        snapshot_fn = _compat_capacity_fill_snapshot
        format_fn = _compat_format_capacity_fill
    else:
        snapshot_fn = capacity_fill_snapshot
        format_fn = format_capacity_fill

    try:
        from limen.dispatch import _down_lanes
        down_lanes = _down_lanes()
    except Exception:
        down_lanes = _load_down_lanes()

    snapshot = snapshot_fn(board, down_lanes=down_lanes)
    markdown = format_fn(snapshot)
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
