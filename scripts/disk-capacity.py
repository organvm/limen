#!/usr/bin/env python3
"""disk-capacity.py — zero-write beat sensor for the disk-full root cause.

The gap this closes: disk-full was a silent failure mode — worktrees and artifacts
accumulated until the host ran out of space, stalling the fleet with zero beat-visible
signal. This sensor makes disk usage a continuous-runtime invariant: green ⟺
/System/Volumes/Data capacity is below threshold; red ⟺ the beat surfaces the escalation.

``--check`` is an observation-only advisory gate: it exits 1 when capacity is at
or above the threshold (default 80%).  It never removes files, truncates logs, or
writes a receipt.  Remediation is deliberately owned by the separate
``disk-capacity-reclaim.py`` effector, whose apply path requires an exact receipt.

Exit codes: 0 = ok or volume unavailable; 1 = threshold breached.

Usage:
  python3 scripts/disk-capacity.py --check
  python3 scripts/disk-capacity.py --check --threshold 90
"""

from __future__ import annotations

import sys

# The deployed heartbeat's observation path must not create incidental bytecode.
sys.dont_write_bytecode = True

import argparse
import os
import subprocess
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))

VOLUME = "/System/Volumes/Data"
DEFAULT_THRESHOLD = 80  # percent-used; override via LIMEN_DISK_CAPACITY_THRESHOLD


def _capacity_pct(volume: str = VOLUME) -> float | None:
    """Return percent-used for *volume* via `df`.

    Uses df(1) so it measures the filesystem the volume actually lives on, not a
    statvfs() call which APFS inflates with purgeable space.  Returns None if the
    volume is not mounted or df fails.
    """
    try:
        result = subprocess.run(
            ["df", "-P", volume],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return None
        # POSIX df -P: Filesystem Blocks Used Available Capacity% Mounted-on
        fields = lines[1].split()
        if len(fields) < 5:
            return None
        cap_str = fields[4].rstrip("%")
        return float(cap_str)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def check(threshold: int) -> int:
    pct = _capacity_pct()
    if pct is None:
        # Volume absent (CI / non-macOS / VM) — fail open.
        print(f"disk-capacity: volume {VOLUME!r} not found — check skipped (fail-open)")
        return 0
    print(f"disk-capacity: {VOLUME} used {pct:.1f}% (threshold {threshold}%)")
    if pct >= threshold:
        print(
            f"  ↑ disk-capacity BREACHED — {pct:.1f}% >= {threshold}% threshold; "
            "inspect the zero-write reclaim plan with "
            "`python3 scripts/disk-capacity-reclaim.py --check`; "
            "application is a separate explicit receipt-bound action"
        )
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="disk-capacity beat sensor — zero-write check only")
    ap.add_argument("--check", action="store_true", help="advisory check: exit 1 when capacity >= threshold")
    ap.add_argument(
        "--threshold",
        type=int,
        default=int(os.environ.get("LIMEN_DISK_CAPACITY_THRESHOLD", DEFAULT_THRESHOLD)),
        help=f"percent-used threshold (default {DEFAULT_THRESHOLD}; env LIMEN_DISK_CAPACITY_THRESHOLD)",
    )
    args = ap.parse_args(argv)

    return check(args.threshold)


if __name__ == "__main__":
    sys.exit(main())
