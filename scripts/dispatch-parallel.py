#!/usr/bin/env python3
"""dispatch-parallel.py — one call that dispatches ALL lanes concurrently (reserve→run→commit).
Replaces the heartbeat's serial per-lane for-loop. Safe: tasks.yaml written twice under this
single process; slow agent runs happen in a thread pool; git plumbing is lock-guarded.

  python3 scripts/dispatch-parallel.py --lanes codex,opencode,agy,claude,gemini,jules,copilot,github_actions,warp,oz \
      --per-lane 3 --workers 8 [--dry-run]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file  # noqa: E402
from limen.dispatch import dispatch_parallel, _down_lanes  # noqa: E402


def _parse_lanes(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for lane in raw.split(","):
        lane = lane.strip()
        if not lane or lane in seen:
            continue
        out.append(lane)
        seen.add(lane)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS"))
    ap.add_argument(
        "--lanes",
        default="codex,opencode,agy,claude,gemini,jules,copilot,github_actions,warp,oz",
    )
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
    lanes = [x for x in _parse_lanes(args.lanes) if x not in down]
    if down:
        print(f"── skipping down lanes: {sorted(down)}")
    path = Path(args.tasks)
    lf = load_limen_file(path)
    dispatch_parallel(lf, path, lanes, per_agent_limit=args.per_lane,
                      max_workers=args.workers, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
