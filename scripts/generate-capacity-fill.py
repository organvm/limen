#!/usr/bin/env python3
"""Generate daily capacity-fill packets for underfed paid lanes.

The capacity-fill receipt detects the leak. This generator gives the scheduler
real open work to feed to each underfilled lane, with stable per-day ids so the
heartbeat can run it repeatedly without flooding the board.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import capacity_fill_snapshot  # noqa: E402
from limen.dispatch import _down_lanes  # noqa: E402
from limen.io import load_limen_file, queue_lock, save_limen_file  # noqa: E402
from limen.models import Task  # noqa: E402

ACTIVE = {"open", "dispatched", "in_progress", "needs_human"}


def _agent_label(agent: str) -> str:
    return {
        "agy": "Agy",
        "jules": "Jules",
        "opencode": "OpenCode",
        "gemini": "Gemini",
        "claude": "Claude",
        "codex": "Codex",
        "copilot": "Copilot",
    }.get(agent, agent)


def _existing_daily(tasks: list[Task], agent: str, stamp: str, target_agent: str) -> set[str]:
    prefix = f"CAPFILL-{agent}-{stamp.replace('-', '')}-"
    return {
        task.id
        for task in tasks
        if task.status in ACTIVE
        and task.id.startswith(prefix)
        and f"lane:{agent}" in (task.labels or [])
        and task.target_agent == target_agent
    }


def _packet_target(row: dict[str, object]) -> str:
    agent = str(row["agent"])
    if row.get("status") == "blocked" or not bool(row.get("reachable")):
        return "any"
    return agent


def plan_capacity_fill_tasks(lf, *, max_new: int, per_lane_cap: int) -> tuple[list[Task], dict[str, object]]:
    stamp = date.today().isoformat()
    compact = stamp.replace("-", "")
    snapshot = capacity_fill_snapshot(lf, down_lanes=_down_lanes())
    planned: list[Task] = []
    existing_ids = {task.id for task in lf.tasks}
    info: dict[str, object] = {"snapshot_status": snapshot["status"], "lanes": []}
    demands: list[dict[str, object]] = []

    for row in snapshot["rows"]:
        agent = row["agent"]
        if row["status"] in {"healthy", "depleted"}:
            continue
        deficit = max(0, int(row["expected_now"]) - int(row["productive"]))
        if deficit <= 0:
            continue
        target_agent = _packet_target(row)
        existing = _existing_daily(lf.tasks, agent, stamp, target_agent)
        desired_active = min(deficit, per_lane_cap)
        need = max(0, desired_active - len(existing))
        info["lanes"].append(
            {
                "agent": agent,
                "deficit": deficit,
                "existing": len(existing),
                "need": need,
                "target_agent": target_agent,
                "status": row["status"],
            }
        )
        if need > 0:
            demands.append({"agent": agent, "need": need, "existing": existing, "target_agent": target_agent})

    for slot in range(1, 1000):
        for demand in demands:
            if len(planned) >= max_new:
                break
            if int(demand["need"]) <= 0:
                continue
            agent = str(demand["agent"])
            target_agent = str(demand["target_agent"])
            tid = f"CAPFILL-{agent}-{compact}-{slot:02d}"
            existing = demand["existing"]
            if tid in existing_ids or tid in existing:
                continue
            existing_ids.add(tid)
            demand["need"] = int(demand["need"]) - 1
            label = _agent_label(agent)
            planned.append(
                Task(
                    id=tid,
                    title=f"{label} daily capacity-fill packet {slot:02d}",
                    repo="organvm/limen",
                    type="code",
                    target_agent=target_agent,
                    priority="high",
                    budget_cost=1,
                    status="open",
                    labels=["capacity-fill", f"lane:{agent}", "daily-checkup", "generated"],
                    context=(
                        f"Close one concrete {label} lane-fill gap for {stamp}. Start from "
                        "docs/capacity-fill.md and docs/dispatch-health.md. Make the smallest "
                        "local, test-backed improvement that helps this lane become productive, "
                        "or, if the next step is human-gated, write a lane-specific receipt under "
                        f"docs/lane-checkups/{agent}/{compact}-{slot:02d}.md with the blocker and "
                        "the exact command/evidence. Do not change credentials, launchd state, "
                        "task states, GitHub settings, or push. Verification: run the focused "
                        "predicate for the touched surface and `python3 scripts/capacity-fill-ledger.py --write`."
                    ),
                    created=stamp,
                    dispatch_log=[],
                )
            )
    return planned, info


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate paid-lane capacity fill packets.")
    parser.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    parser.add_argument("--max-new", type=int, default=int(os.environ.get("LIMEN_CAPACITY_FILL_MAX_NEW", "40")))
    parser.add_argument("--per-lane-cap", type=int, default=int(os.environ.get("LIMEN_CAPACITY_FILL_PER_LANE", "15")))
    parser.add_argument("--apply", action="store_true", help="append generated tasks to tasks.yaml")
    args = parser.parse_args()

    tasks_path = Path(args.tasks)
    lf = load_limen_file(tasks_path)
    planned, info = plan_capacity_fill_tasks(lf, max_new=args.max_new, per_lane_cap=args.per_lane_cap)
    print(
        f"capacity-fill-generator: status={info['snapshot_status']} planned={len(planned)} "
        f"lanes={info['lanes']}"
    )
    for task in planned:
        print(f"  {task.id} -> {task.target_agent}: {task.title}")
    if not args.apply or not planned:
        return 0

    with queue_lock(tasks_path) as got:
        if not got:
            print("queue busy - skipped applying capacity-fill tasks this pass")
            return 0
        fresh = load_limen_file(tasks_path)
        fresh_planned, _ = plan_capacity_fill_tasks(fresh, max_new=args.max_new, per_lane_cap=args.per_lane_cap)
        fresh.tasks.extend(fresh_planned)
        save_limen_file(tasks_path, fresh)
        print(f"applied {len(fresh_planned)} capacity-fill tasks -> {tasks_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
