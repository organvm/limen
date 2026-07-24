import json
import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _env_without_reclaim_settings(**overrides):
    env = dict(os.environ)
    env.pop("LIMEN_RECLAIM", None)
    env.pop("LIMEN_RECLAIM_APPLY", None)
    env.update(overrides)
    return env


def _run_reclaim_census(tmp_path, **settings):
    limen = tmp_path / "limen"
    home = tmp_path / "home"
    limen.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "drain.sh"), "--census"],
        capture_output=True,
        text=True,
        env=_env_without_reclaim_settings(
            LIMEN_ROOT=str(limen),
            LIMEN_TASKS=str(limen / "tasks.yaml"),
            HOME=str(home),
            **settings,
        ),
        check=True,
    )
    return json.loads(proc.stdout)


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
        env=_env_without_reclaim_settings(
            LIMEN_ROOT=str(limen),
            LIMEN_TASKS=str(tasks),
            HOME=str(home),
        ),
        check=True,
    )
    census = json.loads(proc.stdout)
    encoded = json.dumps(census, sort_keys=True)

    assert census["tasks_present"] is True
    assert census["task_status_counts"] == {"done": 1, "open": 1}
    assert census["reclaim_enabled"] is False
    assert census["reclaim_apply_enabled"] is False
    assert "private task title" not in encoded
    assert "PRIVATE-OPEN" not in encoded


def test_drain_census_reports_effective_reclaim_apply_arming(tmp_path):
    apply_only = _run_reclaim_census(tmp_path, LIMEN_RECLAIM_APPLY="1")
    assert apply_only["reclaim_enabled"] is False
    assert apply_only["reclaim_apply_enabled"] is False

    preview = _run_reclaim_census(tmp_path, LIMEN_RECLAIM="1")
    assert preview["reclaim_enabled"] is True
    assert preview["reclaim_apply_enabled"] is False

    armed = _run_reclaim_census(tmp_path, LIMEN_RECLAIM="1", LIMEN_RECLAIM_APPLY="1")
    assert armed["reclaim_enabled"] is True
    assert armed["reclaim_apply_enabled"] is True


def test_reclaim_parameter_defaults_match_preview_posture():
    panel = yaml.safe_load((ROOT / "institutio" / "governance" / "parameters.yaml").read_text(encoding="utf-8"))
    parameters = panel["parameters"]
    assert parameters["LIMEN_RECLAIM"]["default"] == "0"
    assert parameters["LIMEN_RECLAIM_APPLY"]["default"] == "0"


def test_drain_reclaim_preview_is_zero_write_and_never_passes_apply(tmp_path):
    limen = tmp_path / "limen"
    home = tmp_path / "home"
    stub = tmp_path / "bin"
    trace = tmp_path / "python-invocations"
    effect = tmp_path / "apply-effect"
    limen.mkdir()
    home.mkdir()
    stub.mkdir()
    python = stub / "python3"
    python.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$LIMEN_TEST_TRACE"\n'
        'case " $* " in\n'
        '  *" --apply "*) touch "$LIMEN_TEST_EFFECT" ;;\n'
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    python.chmod(0o755)

    subprocess.run(
        ["bash", str(ROOT / "scripts" / "drain.sh")],
        capture_output=True,
        text=True,
        env=_env_without_reclaim_settings(
            PATH=f"{stub}:{os.environ['PATH']}",
            LIMEN_ROOT=str(limen),
            LIMEN_TASKS=str(limen / "tasks.yaml"),
            HOME=str(home),
            LIMEN_JULES_LAND="0",
            LIMEN_MERGE_DRAIN="0",
            LIMEN_SELF_HEAL="0",
            LIMEN_CONVERGE="0",
            LIMEN_RECLAIM="1",
            LIMEN_RECLAIM_APPLY="0",
            LIMEN_QUEUE_LOCK_HELD="0",
            LIMEN_TEST_TRACE=str(trace),
            LIMEN_TEST_EFFECT=str(effect),
        ),
        check=True,
    )

    reclaim_calls = [line for line in trace.read_text(encoding="utf-8").splitlines() if "reclaim-worktrees.py" in line]
    assert len(reclaim_calls) == 2
    assert all("--apply" not in line for line in reclaim_calls)
    assert not effect.exists()
    assert list(limen.rglob("*")) == []


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
