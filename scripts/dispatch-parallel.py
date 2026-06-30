#!/usr/bin/env python3
"""dispatch-parallel.py — one call that dispatches ALL lanes concurrently (reserve→run→commit).
Replaces the heartbeat's serial per-lane for-loop. Safe: tasks.yaml written twice under this
single process; slow agent runs happen in a thread pool; git plumbing is lock-guarded.

  python3 scripts/dispatch-parallel.py --lanes auto \
      --per-lane 3 --workers 8 [--dry-run]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import PAID_AGENT_ORDER, canonical_agent, capacity_census, format_capacity_census  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.dispatch import dispatch_parallel, _down_lanes  # noqa: E402


def resolve_lanes(selector: str, down: set[str], census=None) -> list[str]:
    raw = (selector or "auto").strip()
    if raw == "all":
        return [agent for agent in PAID_AGENT_ORDER if agent not in down]
    if raw == "auto":
        rows = census
        if rows is None:
            return []
        lanes = [
            str(row.get("agent"))
            for row in rows
            if row.get("reachable") and str(row.get("agent")) not in down
        ]
        return lanes or [agent for agent in ("codex",) if agent not in down]
    lanes: list[str] = []
    for item in raw.split(","):
        agent = canonical_agent(item.strip())
        if agent and agent in PAID_AGENT_ORDER and agent not in down and agent not in lanes:
            lanes.append(agent)
    return lanes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS"))
    ap.add_argument("--lanes", default="auto")
    ap.add_argument("--per-lane", type=int, default=int(os.environ.get("LIMEN_LOCAL_LIMIT", "3")))
    ap.add_argument("--workers", type=int, default=int(os.environ.get("LIMEN_WORKERS", "8")))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
    policy_path = root / "logs" / "autonomy-policy.json"
    if not args.dry_run and os.environ.get("LIMEN_FORCE_AUTONOMY") != "1":
        try:
            policy = json.loads(policy_path.read_text())
        except Exception:
            policy = {"mode": "observe", "dispatch_enabled": False}
        if policy.get("mode") != "dispatch" or not policy.get("dispatch_enabled"):
            print(
                "dispatch-parallel skipped: autonomy policy is not dispatch-enabled "
                f"({policy_path})"
            )
            return 0
    down = _down_lanes()   # skip lanes that can't produce (e.g. gemini ratelimited) — no wasted slots
    path = Path(args.tasks)
    lf = load_limen_file(path)
    census = capacity_census(lf)
    print(format_capacity_census(census))
    lanes = resolve_lanes(args.lanes, down, census)
    if down:
        print(f"── skipping down lanes: {sorted(down)}")
    dispatch_parallel(lf, path, lanes, per_agent_limit=args.per_lane,
                      max_workers=args.workers, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
