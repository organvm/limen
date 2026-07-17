from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vltima-absorb-cadence.py"


def _load(name: str = "vltima_absorb_cadence_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_default_cadence_dry_run_plans_safe_chain() -> None:
    cadence = _load("vltima_absorb_default")

    receipt = cadence.build_receipt(
        execute=False,
        materialize_private=False,
        stop_on_failure=True,
        timeout=10,
    )
    step_ids = [item["id"] for item in receipt["results"]]

    assert receipt["status"] == "planned"
    assert receipt["materialize_private"] is False
    assert "capture" in step_ids
    assert "materialize-private" not in step_ids
    assert step_ids.index("governance-memory-readiness") < step_ids.index("command-center")
    assert step_ids[-2:] == ["prior-excavations", "result-digest"]


def test_configured_governance_cadence_precedes_readiness(
    monkeypatch,
    tmp_path: Path,
) -> None:
    snapshot_id = "gov-snapshot-2026-07-16"
    snapshot_at = "2026-07-16T00:00:00Z"
    config = tmp_path / "private" / "cadence.yaml"
    run_root = tmp_path / "private" / "runs"
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_ID", snapshot_id)
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_AT", snapshot_at)
    monkeypatch.setenv("LIMEN_GOV_CONFIG", str(config))
    monkeypatch.setenv("LIMEN_GOV_RUN_ROOT", str(run_root))
    cadence = _load("vltima_absorb_configured_governance")

    receipt = cadence.build_receipt(
        execute=False,
        materialize_private=False,
        stop_on_failure=True,
        timeout=10,
    )
    step_ids = [item["id"] for item in receipt["results"]]
    governance_index = step_ids.index("governance-memory-cadence")

    assert governance_index + 1 == step_ids.index("governance-memory-readiness")
    command = receipt["results"][governance_index]["command"]
    assert f"--snapshot-id {snapshot_id}" in command
    assert f"--snapshot-at {snapshot_at}" in command
    assert "--config $LIMEN_GOV_CONFIG" in command
    assert f"--run-root $LIMEN_GOV_RUN_ROOT/{snapshot_id}" in command
    assert "--strict --write" in command
    assert str(tmp_path) not in command


def test_configured_governance_receipts_are_derived_for_readiness(
    monkeypatch,
    tmp_path: Path,
) -> None:
    snapshot_id = "gov-snapshot-2026-07-16"
    run_root = tmp_path / "private" / "runs"
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_ID", snapshot_id)
    monkeypatch.setenv("LIMEN_GOV_RUN_ROOT", str(run_root))
    cadence = _load("vltima_absorb_governance_receipts")

    environment = cadence.governance_receipt_environment()
    selected_run = run_root / snapshot_id

    assert environment == {
        "LIMEN_GOV_STAGE_RECEIPTS": str(selected_run / "governance-stage-receipts.v1.json"),
        "LIMEN_GOV_CADENCE_RECEIPT": str(selected_run / "governance-cadence-receipts.v1.json"),
        "LIMEN_GOV_SNAPSHOT_BUNDLE": str(selected_run / "governance-snapshot-bundle.v1.json"),
    }


def test_configured_governance_receipts_preserve_explicit_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_ID", "gov-snapshot-2026-07-16")
    monkeypatch.setenv("LIMEN_GOV_RUN_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("LIMEN_GOV_STAGE_RECEIPTS", "/owner/stage-receipts.json")
    monkeypatch.setenv("LIMEN_GOV_CADENCE_RECEIPT", "/owner/cadence-receipt.json")
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_BUNDLE", "/owner/snapshot-bundle.json")
    cadence = _load("vltima_absorb_governance_receipt_overrides")

    assert cadence.governance_receipt_environment() == {
        "LIMEN_GOV_STAGE_RECEIPTS": "/owner/stage-receipts.json",
        "LIMEN_GOV_CADENCE_RECEIPT": "/owner/cadence-receipt.json",
        "LIMEN_GOV_SNAPSHOT_BUNDLE": "/owner/snapshot-bundle.json",
    }


def test_governance_readiness_subprocess_receives_derived_receipts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    snapshot_id = "gov-snapshot-2026-07-16"
    run_root = tmp_path / "runs"
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_ID", snapshot_id)
    monkeypatch.setenv("LIMEN_GOV_RUN_ROOT", str(run_root))
    cadence = _load("vltima_absorb_governance_receipt_subprocess")
    observed: dict[str, str] = {}

    class Process:
        returncode = 0
        pid = 1

        def communicate(self, *, timeout):
            del timeout
            return "", ""

    def fake_popen(command, **kwargs):
        del command
        observed.update(kwargs["env"])
        return Process()

    monkeypatch.setattr(cadence.subprocess, "Popen", fake_popen)
    step = next(step for step in cadence.BASE_STEPS if step.id == "governance-memory-readiness")

    result = cadence.run_step(step, timeout=10)

    selected_run = run_root / snapshot_id
    assert result["status"] == "ok"
    assert observed["LIMEN_GOV_STAGE_RECEIPTS"] == str(selected_run / "governance-stage-receipts.v1.json")
    assert observed["LIMEN_GOV_CADENCE_RECEIPT"] == str(selected_run / "governance-cadence-receipts.v1.json")
    assert observed["LIMEN_GOV_SNAPSHOT_BUNDLE"] == str(selected_run / "governance-snapshot-bundle.v1.json")


def test_governance_heartbeat_exports_selected_run_receipts() -> None:
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")

    assert (
        'LIMEN_GOV_STAGE_RECEIPTS="${LIMEN_GOV_STAGE_RECEIPTS:-$governance_run_dir/governance-stage-receipts.v1.json}"'
    ) in heartbeat
    assert (
        'LIMEN_GOV_CADENCE_RECEIPT="${LIMEN_GOV_CADENCE_RECEIPT:-'
        '$governance_run_dir/governance-cadence-receipts.v1.json}"'
    ) in heartbeat
    assert (
        'LIMEN_GOV_SNAPSHOT_BUNDLE="${LIMEN_GOV_SNAPSHOT_BUNDLE:-'
        '$governance_run_dir/governance-snapshot-bundle.v1.json}"'
    ) in heartbeat


def test_materialize_private_is_explicit_opt_in() -> None:
    cadence = _load("vltima_absorb_materialize")

    receipt = cadence.build_receipt(
        execute=False,
        materialize_private=True,
        stop_on_failure=True,
        timeout=10,
    )
    materialize = [item for item in receipt["results"] if item["id"] == "materialize-private"]

    assert len(materialize) == 1
    assert "--materialize" in materialize[0]["command"]
    assert receipt["privacy"]["raw_materialization_opt_in"] is True


def test_render_markdown_records_contract_and_commands() -> None:
    cadence = _load("vltima_absorb_markdown")
    receipt = cadence.build_receipt(
        execute=False,
        materialize_private=False,
        stop_on_failure=True,
        timeout=10,
    )

    markdown = cadence.render_markdown(receipt)

    assert "# VLTIMA Absorption Cadence" in markdown
    assert "brainstorms do not become current authority" in markdown
    assert "scripts/session-corpus-ledger.py --write --all" in markdown
    assert "discover → snapshot → parse → classify → reconcile → distill → validate → render → receipt" in markdown
    assert "scripts/governance-memory-readiness.py --strict --write" in markdown
    assert "--materialize-private" in markdown


def test_render_markdown_redacts_absolute_home_paths() -> None:
    cadence = _load("vltima_absorb_public_paths")
    receipt = {
        "generated_at": "2026-07-06T00:00:00+00:00",
        "status": "ok",
        "mode": "write",
        "materialize_private": False,
        "results": [
            {
                "id": "capture",
                "phase": "capture",
                "status": "ok",
                "command": "python3 scripts/session-corpus-ledger.py --write --all",
                "reason": "test",
                "stdout_tail": ["/Users/4jp/Workspace/limen/docs/session-corpus-ledger.md"],
                "stderr_tail": [],
            }
        ],
    }

    markdown = cadence.render_markdown(receipt)

    assert "/Users/4jp" not in markdown
    assert "$LIMEN_ROOT/docs/session-corpus-ledger.md" in markdown


def test_step_timeout_terminates_the_entire_process_group(tmp_path: Path) -> None:
    cadence = _load("vltima_absorb_process_group")
    child_pid_path = tmp_path / "child.pid"
    worker = tmp_path / "spawn-child.py"
    worker.write_text(
        "\n".join(
            (
                "import subprocess",
                "import sys",
                "import time",
                "from pathlib import Path",
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
                "Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')",
                "time.sleep(60)",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    step = cadence.CadenceStep(
        id="timeout-fixture",
        phase="validate",
        command=(sys.executable, str(worker), str(child_pid_path)),
        reason="prove descendant cleanup",
    )

    result = cadence.run_step(step, timeout=1)

    assert result["status"] == "timeout"
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    for _ in range(40):
        state = subprocess.run(
            ("ps", "-p", str(child_pid), "-o", "stat="),
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if not state or state.startswith("Z"):
            break
        time.sleep(0.05)
    else:
        os.kill(child_pid, 9)
        raise AssertionError("timed-out VLTIMA step left a live descendant")


def test_failed_governance_cadence_still_refreshes_strict_readiness(monkeypatch) -> None:
    cadence = _load("vltima_absorb_fail_closed_readiness")
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_ID", "snapshot-fixture")
    monkeypatch.setenv("LIMEN_GOV_SNAPSHOT_AT", "2026-07-16T00:00:00Z")
    monkeypatch.setenv("LIMEN_GOV_CONFIG", "/tmp/config.yaml")
    monkeypatch.setenv("LIMEN_GOV_RUN_ROOT", "/tmp/runs")
    invoked: list[str] = []

    def fake_run(step, *, timeout):
        del timeout
        invoked.append(step.id)
        failed = step.id in {"governance-memory-cadence", "governance-memory-readiness"}
        return {
            "id": step.id,
            "phase": step.phase,
            "command": "fixture",
            "reason": step.reason,
            "optional": step.optional,
            "returncode": 1 if failed else 0,
            "duration_seconds": 0,
            "stdout_tail": [],
            "stderr_tail": [],
            "status": "failed" if failed else "ok",
        }

    monkeypatch.setattr(cadence, "run_step", fake_run)
    receipt = cadence.build_receipt(
        execute=True,
        materialize_private=False,
        stop_on_failure=True,
        timeout=10,
    )

    assert invoked[-2:] == ["governance-memory-cadence", "governance-memory-readiness"]
    assert "command-center" not in invoked
    assert receipt["status"] == "failed"
