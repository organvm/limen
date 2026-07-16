"""Tests for the read-only host-pressure census (IF-HOST-PRESSURE form 4).

Hermetic ps/launchctl fixtures prove that provider-wide peer control is unavailable
and the check path leaves no state behind.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "host-relief.py"

# The 2026-07-16 incident, as a ps fixture (rss column is KiB):
#   overnight-watch at 3.1 GiB (over the 1024 MB ceiling), bztransmit at 8.6 GiB (root hog),
#   heartbeat healthy, a big non-root browser that must NOT be flagged.
PS_FIXTURE = """\
28017 4jp 3267776 /opt/homebrew/bin/python3 /Users/4jp/Workspace/limen/scripts/overnight-watch.py
10899 root 9000000 /Library/Backblaze.bzpkg/bztransmit -updatebackupstats --token=fixture-secret-argv
32082 4jp 20480 /bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh
40001 4jp 5300000 /Applications/Chrome.app/Contents/MacOS/Chrome
1 root 13824 /sbin/launchd
"""

LAUNCHCTL_FIXTURE = """\
28017\t1\tcom.limen.overnight-watch
32082\t0\tcom.limen.heartbeat
-\t0\tcom.limen.creds-hydrate
598\t0\tcom.apple.WindowServer
"""


def run_relief(tmp_path: Path, *extra: str):
    ps = tmp_path / "ps.txt"
    lc = tmp_path / "launchctl.txt"
    if not ps.exists():
        ps.write_text(PS_FIXTURE)
        lc.write_text(LAUNCHCTL_FIXTURE)
    env = os.environ.copy()
    env["LIMEN_ROOT"] = str(tmp_path)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--ps-fixture",
            str(ps),
            "--launchctl-fixture",
            str(lc),
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def test_shed_reports_over_ceiling_peer_without_action(tmp_path):
    proc = run_relief(tmp_path, "--gate-action", "shed", "--check")
    report = json.loads(proc.stdout)
    assert proc.returncode == 0, proc.stdout
    assert report["pressure_active"] is True
    labels = [item["label"] for item in report["over_ceiling"]]
    assert labels == ["com.limen.overnight-watch"]  # 3.1 GiB > 1024 MB; heartbeat at 20 MB untouched
    assert report["actions"] == []
    assert report["peer_control"] == "prohibited"


def test_root_hog_is_reported_without_manufacturing_kill_authorization(tmp_path):
    proc = run_relief(tmp_path, "--gate-action", "shed", "--check")
    report = json.loads(proc.stdout)
    hogs = report["root_hogs"]
    assert [h["pid"] for h in hogs] == [10899]  # bztransmit; launchd (pid 1) and non-root Chrome excluded
    assert hogs[0]["executable"] == "bztransmit"
    assert "one_liner" not in hogs[0]
    assert "-updatebackupstats" not in proc.stdout
    assert "fixture-secret-argv" not in proc.stdout
    assert report["actions"] == []


def test_apply_fails_closed_instead_of_controlling_peer_processes(tmp_path):
    proc = run_relief(tmp_path, "--gate-action", "shed", "--apply")
    assert proc.returncode == 2
    assert "peer-process mutation is prohibited" in proc.stderr


def test_ok_gate_stands_by_without_state(tmp_path):
    ok = json.loads(run_relief(tmp_path, "--gate-action", "ok", "--check").stdout)
    assert ok["pressure_active"] is False
    assert ok["root_hogs"] == []  # gate ok — hogs are not escalated outside pressure
    assert ok["actions"] == []
    assert not (tmp_path / "logs").exists()


def test_throttle_reports_but_does_not_relieve(tmp_path):
    report = json.loads(run_relief(tmp_path, "--gate-action", "throttle", "--check").stdout)
    assert report["pressure_active"] is True
    assert report["actions"] == []
    # visibility is preserved: the over-ceiling census still names the bloated agent
    assert [i["label"] for i in report["over_ceiling"]] == ["com.limen.overnight-watch"]
    # and a root hog under pressure (gate != ok) is still visible for owner routing
    assert [h["pid"] for h in report["root_hogs"]] == [10899]


def test_check_path_is_zero_write(tmp_path):
    run_relief(tmp_path, "--gate-action", "shed", "--check")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["launchctl.txt", "ps.txt"]


def test_deployed_heartbeat_source_is_check_only():
    registry = yaml.safe_load((ROOT / "institutio" / "governance" / "sensors.yaml").read_text())
    sensor = registry["sensors"]["host-relief"]

    assert "heartbeat" in sensor["source"]
    assert len(sensor["steps"]) == 1
    step = sensor["steps"][0]
    assert step["command"] == "python3 scripts/host-relief.py --check"
    assert step["severity"] == "advisory"
    assert "args_when" not in step
