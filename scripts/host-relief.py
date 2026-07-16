#!/usr/bin/env python3
"""host-relief — read-only pressure census for co-equal peer keepers.

The 2026-07-16 incident proved the swap/RSS visibility gap, but it did not grant one
keeper authority to restart another keeper's process. This heartbeat-safe sensor
therefore reports over-ceiling ``com.limen.*`` processes and root-owned pressure
without signalling, restarting, notifying, or writing state. Self-bounds belong in
the process that owns its own lifecycle; an external owner may act only through its
own explicit receipt-bound effector.

``--check`` is the only mode. It performs two bounded reads (``ps`` and
``launchctl list``) and emits a report. ``--apply`` is accepted only to fail closed,
which prevents an older sensor registry or operator command from silently restoring
the unsafe broad-kickstart behavior.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "cli" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from limen.vigilia import params, vitals  # noqa: E402

AGENT_PREFIX = "com.limen."


def parse_ps(text: str) -> list[dict]:
    """Parse the pressure census without retaining process arguments.

    Command-line arguments can contain credentials or private paths.  PID, owner, RSS,
    and the executable basename are enough to route a finding to its real owner.
    """
    rows = []
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[0].isdigit() or not parts[2].isdigit():
            continue
        executable = Path(parts[3].split(None, 1)[0]).name or "unknown"
        rows.append(
            {
                "pid": int(parts[0]),
                "user": parts[1],
                "rss_mb": round(int(parts[2]) / 1024, 1),  # ps rss is KiB
                "executable": executable[:80],
            }
        )
    return rows


def parse_launchctl(text: str) -> dict[str, int]:
    """``launchctl list`` → {label: pid} for running com.limen.* agents."""
    agents: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit() and parts[2].startswith(AGENT_PREFIX):
            agents[parts[2]] = int(parts[0])
    return agents


def plan_relief(
    gate_action: str,
    procs: list[dict],
    agents: dict[str, int],
    ceiling_mb: float,
    root_hog_mb: float,
) -> dict:
    """Pure, actionless classification for owner-routed pressure findings."""
    by_pid = {p["pid"]: p for p in procs}
    over_ceiling = []
    for label, pid in sorted(agents.items()):
        proc = by_pid.get(pid)
        if proc and proc["rss_mb"] > ceiling_mb:
            over_ceiling.append({"label": label, "pid": pid, "rss_mb": proc["rss_mb"]})
    agent_pids = set(agents.values())
    root_hogs = [
        {
            "pid": p["pid"],
            "user": p["user"],
            "rss_mb": p["rss_mb"],
            "executable": p["executable"],
        }
        for p in procs
        if p["user"] == "root" and p["rss_mb"] > root_hog_mb and p["pid"] not in agent_pids and p["pid"] > 1
    ]
    return {
        "gate_action": gate_action,
        "pressure_active": gate_action != vitals.OK,
        "over_ceiling": over_ceiling,
        "root_hogs": root_hogs if gate_action != vitals.OK else [],
        "peer_control": "prohibited",
        "actions": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only (default action)")
    parser.add_argument("--apply", action="store_true", help="fail closed; peer process mutation is prohibited")
    parser.add_argument("--json", action="store_true", help="emit the full JSON report")
    parser.add_argument("--gate-action", default=None, help="override for tests (ok|throttle|shed)")
    parser.add_argument("--ps-fixture", default=None, help="ps output file — override for tests")
    parser.add_argument("--launchctl-fixture", default=None, help="launchctl list output file — override for tests")
    args = parser.parse_args(argv)

    if args.apply:
        print(
            "host-relief: BLOCKED — broad peer-process mutation is prohibited; "
            "use the process owner's receipt-bound self-effector",
            file=sys.stderr,
        )
        return 2
    if args.gate_action:
        gate_action = args.gate_action
    else:
        try:
            gate_action = vitals.beat_gate(shed=False).get("action", vitals.OK)
        except Exception:
            gate_action = vitals.OK  # fail-open: relief never invents pressure

    try:
        ps_text = (
            Path(args.ps_fixture).read_text()
            if args.ps_fixture
            else subprocess.run(
                ["ps", "-axo", "pid=,user=,rss=,command="], capture_output=True, text=True, timeout=15
            ).stdout
        )
        lc_text = (
            Path(args.launchctl_fixture).read_text()
            if args.launchctl_fixture
            else subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=15).stdout
        )
    except Exception as exc:
        print(f"host-relief: unknown — census failed ({str(exc)[:120]}); fail-open")
        return 0

    ceiling_mb = params.get("VITALS_RSS_CEILING_MB", 1024, cast=float)
    root_hog_mb = params.get("VITALS_ROOT_HOG_MB", 4096, cast=float)
    report = plan_relief(gate_action, parse_ps(ps_text), parse_launchctl(lc_text), ceiling_mb, root_hog_mb)
    report["ceiling_mb"] = ceiling_mb
    report["root_hog_mb"] = root_hog_mb

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"host-relief: gate={gate_action} over-ceiling={len(report['over_ceiling'])} "
            f"root-hogs={len(report['root_hogs'])} actions=0 peer-control=prohibited"
        )
        for item in report["over_ceiling"]:
            print(
                f"  - {item['label']} pid {item['pid']} rss {item['rss_mb']:.0f} MB "
                f"(ceiling {ceiling_mb:.0f}); owner route required"
            )
        for hog in report["root_hogs"]:
            print(f"  ! {hog['executable']} pid {hog['pid']} rss {hog['rss_mb']:.0f} MB; human gate required")

    return 0


if __name__ == "__main__":
    sys.exit(main())
