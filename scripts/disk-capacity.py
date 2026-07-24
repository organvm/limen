#!/usr/bin/env python3
"""disk-capacity.py — zero-write beat sensor for the disk-full root cause.

The gap this closes: disk-full was a silent failure mode — worktrees and artifacts
accumulated until the host ran out of space, stalling the fleet with zero beat-visible
signal. This sensor makes disk usage a continuous-runtime invariant: green ⟺
/System/Volumes/Data capacity is below threshold; red ⟺ the beat surfaces the escalation.

``--check`` is an observation-only advisory gate: it exits 1 when capacity is at
or above the 1..100 threshold in the fixed root-owned Domus config. Caller
arguments and environment variables cannot change that threshold. It never removes
files, truncates logs, or writes a receipt. Remediation is deliberately owned by
the separate ``disk-capacity-reclaim.py`` effector.

Exit codes: 0 = observed healthy or unsupported non-macOS host; 1 = threshold
breached; 2 = the production macOS volume could not be observed.

Usage:
  python3 scripts/disk-capacity.py --check
"""

from __future__ import annotations

import sys

# The deployed heartbeat's observation path must not create incidental bytecode.
sys.dont_write_bytecode = True

import argparse
import json
import os
import platform
import stat
import subprocess
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
VOLUME = "/System/Volumes/Data"
DF = Path("/bin/df")
OWNER_UID = 0
DOMUS_AUTHORITY_ROOT = Path("/Library/Application Support/org.organvm.domus/limen/authority")
OWNER_CONFIG = DOMUS_AUTHORITY_ROOT / "config" / "disk-capacity.json"
OWNER_PATH_ANCHOR = Path("/")
CONFIG_SCHEMA = "limen.disk_capacity.owner_config.v1"
MAX_CONFIG_BYTES = 16 * 1024


class SensorConfigError(ValueError):
    """The deployed owner configuration cannot be trusted."""


def _assert_owner_chain(path: Path, *, leaf_directory: bool = False) -> None:
    try:
        path.relative_to(OWNER_PATH_ANCHOR)
    except ValueError as exc:
        raise SensorConfigError("owner config is outside the fixed absolute authority anchor") from exc
    relative = path.relative_to(OWNER_PATH_ANCHOR)
    components = [
        OWNER_PATH_ANCHOR,
        *(
            OWNER_PATH_ANCHOR.joinpath(*relative.parts[:index])
            for index in range(1, len(relative.parts) + 1)
        ),
    ]
    for index, candidate in enumerate(components):
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise SensorConfigError(f"owner config path is unavailable ({type(exc).__name__})") from exc
        is_leaf = index == len(components) - 1
        expected_directory = not is_leaf or leaf_directory
        if stat.S_ISLNK(metadata.st_mode):
            raise SensorConfigError("owner config path must not contain symlinks")
        if expected_directory and not stat.S_ISDIR(metadata.st_mode):
            raise SensorConfigError("owner config ancestor is not a directory")
        if not expected_directory and not stat.S_ISREG(metadata.st_mode):
            raise SensorConfigError("owner config is not a regular file")
        if metadata.st_uid != OWNER_UID:
            raise SensorConfigError("owner config path is not owner-custodied")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise SensorConfigError("owner config path is group/world writable")


def _load_threshold() -> int:
    _assert_owner_chain(OWNER_CONFIG)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(OWNER_CONFIG, flags)
    except OSError as exc:
        raise SensorConfigError(f"owner config is unreadable ({type(exc).__name__})") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise SensorConfigError("owner config must be a single-link regular file")
        if not 1 <= metadata.st_size <= MAX_CONFIG_BYTES:
            raise SensorConfigError("owner config size is outside 1..16384 bytes")
        raw = os.pread(fd, MAX_CONFIG_BYTES + 1, 0)
        if len(raw) != metadata.st_size:
            raise SensorConfigError("owner config changed while read")
    finally:
        os.close(fd)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SensorConfigError("owner config is not valid JSON") from exc
    if not isinstance(value, dict) or set(value) != {"schema", "threshold_percent"}:
        raise SensorConfigError("owner config fields do not match the sensor schema")
    if value.get("schema") != CONFIG_SCHEMA:
        raise SensorConfigError(f"owner config schema must be {CONFIG_SCHEMA}")
    threshold = value.get("threshold_percent")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 100:
        raise SensorConfigError("owner threshold_percent must be an integer in 1..100")
    return threshold


def _capacity_pct(volume: str = VOLUME) -> float | None:
    """Return percent-used for *volume* via `df`.

    Uses df(1) so it measures the filesystem the volume actually lives on, not a
    statvfs() call which APFS inflates with purgeable space.  Returns None if the
    volume is not mounted or df fails.
    """
    try:
        result = subprocess.run(
            [str(DF), "-P", volume],
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "HOME": "/var/empty",
                "TMPDIR": "/tmp",
                "LC_ALL": "C",
            },
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
        host = platform.system()
        if host != "Darwin":
            print(f"disk-capacity: unsupported host {host!r} — macOS volume check not applicable")
            return 0
        print(f"disk-capacity: UNKNOWN — production volume {VOLUME!r} could not be observed")
        return 2
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
    ap.parse_args(argv)
    try:
        threshold = _load_threshold()
    except SensorConfigError as exc:
        print(f"disk-capacity: UNKNOWN — {exc}")
        return 2
    return check(threshold)


if __name__ == "__main__":
    sys.exit(main())
