#!/usr/bin/env python3
"""handoff-relay.py — session-end packet for cross-vendor warm resume.

This organ closes the walk-away loop by writing a durable summary of the current
board state (open lanes, in-flight claims, blockers, and budget). The packet is
read at session-start to avoid cold-starts after a vendor seam transition.
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

from limen.watch import snapshot
from limen.dispatch import _down_lanes

HANDOFF_PATH = ROOT / "logs" / "handoff-relay.json"

def write_handoff() -> None:
    try:
        limen, board, per_lane, working, procs, budget = snapshot()
    except Exception as e:
        print(f"Failed to read board state: {e}", file=sys.stderr)
        return

    # In-flight claims
    in_flight = []
    for lane, tasks in working.items():
        for tid, repo, title in tasks:
            in_flight.append({
                "id": tid,
                "lane": lane,
                "repo": repo,
                "title": title
            })

    # Available lanes
    down_lanes = list(_down_lanes())
    active_lanes = [l for l in per_lane.keys() if l not in down_lanes]

    packet = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "budget": {
            "spent": budget.track.spent,
            "daily": budget.daily,
            "per_agent": budget.track.per_agent
        },
        "active_lanes": active_lanes,
        "down_lanes": down_lanes,
        "in_flight": in_flight,
        "board_summary": dict(board)
    }

    HANDOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HANDOFF_PATH, "w") as f:
        json.dump(packet, f, indent=2)

    print(f"Handoff packet written to {HANDOFF_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    
    write_handoff()
    return 0

if __name__ == "__main__":
    sys.exit(main())
