import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_drain_census_is_counts_only(tmp_path):
    limen = tmp_path / "limen"
    home = tmp_path / "home"
    (limen / "logs").mkdir(parents=True)
    home.mkdir()
    tasks = limen / "tasks.yaml"
    tasks.write_text(
        """
tasks:
  - id: PRIVATE-OPEN
    title: private task title
    status: open
  - id: PRIVATE-DONE
    title: private done title
    status: done
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "drain.sh"), "--census"],
        capture_output=True,
        text=True,
        env={**os.environ, "LIMEN_ROOT": str(limen), "LIMEN_TASKS": str(tasks), "HOME": str(home)},
        check=True,
    )
    census = json.loads(proc.stdout)
    encoded = json.dumps(census, sort_keys=True)

    assert census["tasks_present"] is True
    assert census["task_status_counts"] == {"done": 1, "open": 1}
    assert census["reclaim_enabled"] is True
    assert census["reclaim_apply_enabled"] is True
    assert "private task title" not in encoded
    assert "PRIVATE-OPEN" not in encoded


def test_drain_pause_guard_runs_before_every_effector(tmp_path):
    limen = tmp_path / "limen"
    home = tmp_path / "home"
    stub = tmp_path / "bin"
    marker = limen / "logs" / "AUTONOMY_PAUSED"
    marker.parent.mkdir(parents=True)
    marker.write_text("reason: containment\n", encoding="utf-8")
    home.mkdir()
    stub.mkdir()
    called = tmp_path / "effector-called"
    python = stub / "python3"
    python.write_text(f"#!/bin/sh\ntouch '{called}'\nexit 99\n", encoding="utf-8")
    python.chmod(0o755)

    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "drain.sh")],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{stub}:{os.environ['PATH']}",
            "LIMEN_ROOT": str(limen),
            "LIMEN_TASKS": str(limen / "tasks.yaml"),
            "HOME": str(home),
        },
        check=True,
    )

    assert "REFUSED-PAUSED" in proc.stdout
    assert not called.exists()
    assert marker.read_text(encoding="utf-8") == "reason: containment\n"
