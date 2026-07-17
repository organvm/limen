"""Production-path and zero-write tests for the disk-capacity sensor/effector split."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SENSOR = ROOT / "scripts" / "disk-capacity.py"
EFFECTOR = ROOT / "scripts" / "disk-capacity-reclaim.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_test_authority(module, directory: Path) -> None:
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        pytest.skip("ssh-keygen is required for signed receipt fixtures")
    signing_key = directory / f"{module.__name__}-authority"
    subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(signing_key)],
        check=True,
        capture_output=True,
    )
    public_key = signing_key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed_signers = directory / f"{module.__name__}-allowed-signers"
    allowed_signers.write_text(
        f"human:test-authority {public_key[0]} {public_key[1]}\n",
        encoding="utf-8",
    )
    module.OWNER_ALLOWED_SIGNERS = allowed_signers
    module._TEST_SIGNING_KEY = signing_key


def _repo(tmp_path: Path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".heal-probe-*.yaml\nlogs/\n", encoding="utf-8")
    probe = tmp_path / ".heal-probe-example.yaml"
    probe.write_text("ephemeral: true\n", encoding="utf-8")
    log = tmp_path / "logs" / "heartbeat.err.log"
    log.parent.mkdir(parents=True)
    log.write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    module = _load(EFFECTOR, f"disk_capacity_reclaim_{tmp_path.name}")
    _install_test_authority(module, tmp_path.parent)
    return module, probe, log


def _receipt(module, path: Path, plan: dict, *, attempt_id: str = "attempt-one") -> Path:
    now = datetime.now(timezone.utc)
    value = {
        "schema": module.RECEIPT_SCHEMA,
        "action": module.ACTION,
        "authorized": True,
        "authorized_by": "human:test-authority",
        "root_id": plan["root_id"],
        "plan_hash": plan["plan_hash"],
        "attempt_id": attempt_id,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    _resign(module, path)
    return path


def _signature(path: Path) -> Path:
    return Path(f"{path}.sig")


def _signed_args(path: Path) -> list[str]:
    return ["--receipt", str(path), "--signature", str(_signature(path))]


def _resign(module, path: Path) -> None:
    _signature(path).unlink(missing_ok=True)
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(module._TEST_SIGNING_KEY),
            "-n",
            module.SIGNED_RECEIPT_NAMESPACE,
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_deployed_sensor_is_observation_only(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    module = _load(SENSOR, "disk_capacity_sensor_observation_only")
    monkeypatch.setattr(module, "_capacity_pct", lambda: 91.0)

    assert module.main(["--check", "--threshold", "80"]) == 1
    assert "separate explicit receipt-bound action" in capsys.readouterr().out
    assert not hasattr(module, "apply")
    with pytest.raises(SystemExit) as exc:
        module.main(["--check", "--apply"])
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_reclaim_preview_is_literal_zero_write(tmp_path, monkeypatch, capsys):
    module, probe, log = _repo(tmp_path, monkeypatch)
    before_probe = probe.read_bytes()
    before_log = log.read_bytes()
    trace_path = tmp_path.parent / f"{tmp_path.name}-git-trace.json"
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace_path))
    commands: list[list[str]] = []
    real_run = module.subprocess.run

    def command_spy(command, *args, **kwargs):
        commands.append(list(command))
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", command_spy)

    assert module.main(["--check", "--log-cap-mb", "1", "--attempt-id", "preview-one"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["mode"] == "preview"
    assert output["zero_write"] is True
    assert output["plan"]["problems"] == []
    assert {row["kind"] for row in output["plan"]["targets"]} == {"unlink", "truncate"}
    assert probe.read_bytes() == before_probe
    assert log.read_bytes() == before_log
    assert not module.RESULTS_DIR.exists()
    assert not trace_path.exists()
    assert commands and all(command[:2] == ["git", "ls-files"] for command in commands)
    assert not any(
        command[0] in {"b2", "backblaze", "launchctl", "mv", "rclone", "rsync", "sendmail"} for command in commands
    )


def test_receipt_requires_explicit_authority_and_bounded_freshness(tmp_path, monkeypatch):
    module, probe, log = _repo(tmp_path, monkeypatch)
    plan = module.build_plan(1)
    path = _receipt(module, tmp_path / "apply-receipt.json", plan)
    value = json.loads(path.read_text(encoding="utf-8"))

    value["authorized"] = False
    path.write_text(json.dumps(value), encoding="utf-8")
    _resign(module, path)
    assert module.main(["--apply", *_signed_args(path), "--log-cap-mb", "1"]) == 2
    assert probe.exists() and log.stat().st_size > 0

    value["authorized"] = True
    value["issued_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    value["expires_at"] = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    path.write_text(json.dumps(value), encoding="utf-8")
    _resign(module, path)
    assert module.main(["--apply", *_signed_args(path), "--log-cap-mb", "1"]) == 2
    assert probe.exists() and log.stat().st_size > 0


def test_caller_cannot_substitute_an_untrusted_signer(tmp_path, monkeypatch):
    module, probe, log = _repo(tmp_path, monkeypatch)
    plan = module.build_plan(1)
    receipt = _receipt(module, tmp_path / "untrusted.json", plan, attempt_id="untrusted-signer")
    attacker_key = tmp_path.parent / f"{tmp_path.name}-attacker"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(attacker_key)],
        check=True,
        capture_output=True,
    )
    _signature(receipt).unlink()
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(attacker_key),
            "-n",
            module.SIGNED_RECEIPT_NAMESPACE,
            str(receipt),
        ],
        check=True,
        capture_output=True,
    )
    before = (probe.read_bytes(), log.read_bytes())

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "1"]) == 2
    assert (probe.read_bytes(), log.read_bytes()) == before
    assert not module.RESULTS_DIR.exists()


def test_missing_pinned_trust_root_ignores_caller_env(tmp_path, monkeypatch):
    module, probe, log = _repo(tmp_path, monkeypatch)
    plan = module.build_plan(1)
    receipt = _receipt(module, tmp_path / "missing-trust.json", plan, attempt_id="missing-trust-root")
    valid_but_caller_selected = module.OWNER_ALLOWED_SIGNERS
    monkeypatch.setattr(module, "OWNER_ALLOWED_SIGNERS", tmp_path / "missing-owner-root")
    monkeypatch.setenv("LIMEN_DISK_CAPACITY_ALLOWED_SIGNERS", str(valid_but_caller_selected))
    before = (probe.read_bytes(), log.read_bytes())

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "1"]) == 2
    assert (probe.read_bytes(), log.read_bytes()) == before
    assert not module.RESULTS_DIR.exists()


def test_owner_adjacent_marker_blocks_replay_after_local_result_loss(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("logs/\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    module = _load(EFFECTOR, "disk_capacity_external_replay")
    _install_test_authority(module, tmp_path.parent)
    plan = module.build_plan(10)
    receipt = _receipt(module, tmp_path / "empty-plan-receipt.json", plan, attempt_id="external-replay")

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "10"]) == 0
    markers = list(tmp_path.glob(".empty-plan-receipt.json.*.consumed"))
    assert len(markers) == 1
    shutil.rmtree(module.RESULTS_DIR)

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "10"]) == 2
    assert len(list(tmp_path.glob(".empty-plan-receipt.json.*.consumed"))) == 1


def test_apply_without_receipt_refuses_without_writes(tmp_path, monkeypatch, capsys):
    module, probe, log = _repo(tmp_path, monkeypatch)
    before = (probe.read_bytes(), log.read_bytes())

    assert module.main(["--apply", "--log-cap-mb", "1"]) == 2

    assert "requires --receipt" in capsys.readouterr().out
    assert (probe.read_bytes(), log.read_bytes()) == before
    assert not module.RESULTS_DIR.exists()


def test_exact_receipt_applies_once_and_publishes_result(tmp_path, monkeypatch):
    module, probe, log = _repo(tmp_path, monkeypatch)
    plan = module.build_plan(1)
    receipt = _receipt(module, tmp_path / "apply-receipt.json", plan)

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "1"]) == 0

    assert not probe.exists()
    assert log.read_bytes() == b""
    results = list(module.RESULTS_DIR.glob("*.json"))
    assert len(results) == 1
    result = json.loads(results[0].read_text(encoding="utf-8"))
    assert result["schema"] == module.RESULT_SCHEMA
    assert result["status"] == "applied"
    assert {row["kind"] for row in result["effects"]} == {"unlink", "truncate"}

    # The same exact receipt cannot authorize the now-different plan or a second result.
    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "1"]) == 2
    assert len(list(module.RESULTS_DIR.glob("*.json"))) == 1


def test_changed_target_invalidates_receipt_before_any_effect(tmp_path, monkeypatch):
    module, probe, log = _repo(tmp_path, monkeypatch)
    plan = module.build_plan(1)
    receipt = _receipt(module, tmp_path / "apply-receipt.json", plan, attempt_id="changed-target")
    probe.write_text("changed after receipt\n", encoding="utf-8")
    before = (probe.read_bytes(), log.read_bytes())

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "1"]) == 2

    assert (probe.read_bytes(), log.read_bytes()) == before
    assert not module.RESULTS_DIR.exists()


def test_expired_receipt_and_receipt_preview_are_zero_write(tmp_path, monkeypatch, capsys):
    module, probe, log = _repo(tmp_path, monkeypatch)
    plan = module.build_plan(1)
    receipt = _receipt(module, tmp_path / "expired.json", plan, attempt_id="expired")
    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    receipt.write_text(json.dumps(value), encoding="utf-8")
    receipt.chmod(0o600)
    _resign(module, receipt)
    before = (probe.read_bytes(), log.read_bytes())

    assert module.main(["--check", *_signed_args(receipt), "--log-cap-mb", "1"]) == 2

    output = json.loads(capsys.readouterr().out)
    assert output["zero_write"] is True
    assert output["receipt_valid"] is False
    assert "expired" in output["error"]
    assert (probe.read_bytes(), log.read_bytes()) == before
    assert not module.RESULTS_DIR.exists()


def test_receipt_expiry_between_reservation_and_effect_refuses_target_writes(tmp_path, monkeypatch):
    module, probe, log = _repo(tmp_path, monkeypatch)
    plan = module.build_plan(1)
    receipt = _receipt(module, tmp_path / "boundary-expiry.json", plan, attempt_id="boundary-expiry")
    before = (probe.read_bytes(), log.read_bytes())
    real_require_current = module._require_receipt_current
    checks = 0

    def expire_after_reservation(receipt_value):
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise module.ReceiptError("receipt expired before the next write boundary")
        return real_require_current(receipt_value)

    monkeypatch.setattr(module, "_require_receipt_current", expire_after_reservation)

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "1"]) == 1

    assert checks == 3
    assert (probe.read_bytes(), log.read_bytes()) == before
    result = json.loads(next(module.RESULTS_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert result["status"] == "failed_before_effects"
    assert result["effects"] == []
    assert "expired before the next write boundary" in result["error"]


def test_hard_linked_truncate_target_is_rejected_without_effect(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text("logs/\n", encoding="utf-8")
    logs = root / "logs"
    logs.mkdir()
    outside = tmp_path / "outside-root.bin"
    outside.write_bytes(b"v" * (1024 * 1024 + 1))
    os.link(outside, logs / "heartbeat.err.log")
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    module = _load(EFFECTOR, "disk_capacity_hard_link")

    plan = module.build_plan(1)

    assert "target must have exactly one hard link" in "; ".join(plan["problems"])
    assert outside.stat().st_size == 1024 * 1024 + 1
    assert not module.RESULTS_DIR.exists()


def test_parent_symlink_replacement_cannot_redirect_truncate(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text("logs/\n", encoding="utf-8")
    logs = root / "logs"
    logs.mkdir()
    authorized_log = logs / "heartbeat.err.log"
    authorized_log.write_bytes(b"a" * (1024 * 1024 + 1))
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    escaped_log = outside_dir / "heartbeat.err.log"
    escaped_log.write_bytes(authorized_log.read_bytes())
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    module = _load(EFFECTOR, "disk_capacity_parent_replacement")
    _install_test_authority(module, tmp_path)
    plan = module.build_plan(1)
    receipt = _receipt(module, tmp_path / "parent-replacement.json", plan, attempt_id="parent-replacement")
    reserve = module._reserve_attempt

    def reserve_then_replace_parent(receipt_value, current_plan, root_fd):
        result = reserve(receipt_value, current_plan, root_fd)
        logs.rename(root / "logs-authorized")
        logs.symlink_to(outside_dir, target_is_directory=True)
        return result

    monkeypatch.setattr(module, "_reserve_attempt", reserve_then_replace_parent)

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "1"]) == 1

    assert (root / "logs-authorized" / "heartbeat.err.log").stat().st_size == 1024 * 1024 + 1
    assert escaped_log.stat().st_size == 1024 * 1024 + 1
    result = json.loads(next((root / "logs-authorized" / "disk-capacity-results").glob("*.json")).read_text())
    assert result["status"] == "failed_before_effects"
    assert result["effects"] == []


def test_replaced_unlink_candidate_is_restored_from_quarantine(tmp_path, monkeypatch):
    module, probe, _log = _repo(tmp_path, monkeypatch)
    replacement = tmp_path / "valuable-replacement.txt"
    replacement.write_text("must survive\n", encoding="utf-8")
    plan = module.build_plan(10)
    receipt = _receipt(module, tmp_path / "candidate-replacement.json", plan, attempt_id="candidate-replacement")
    real_rename = module.os.rename
    replaced = False

    def replace_before_quarantine(source, destination, *args, **kwargs):
        nonlocal replaced
        if not replaced and source == probe.name:
            replaced = True
            probe.unlink()
            replacement.replace(probe)
        return real_rename(source, destination, *args, **kwargs)

    monkeypatch.setattr(module.os, "rename", replace_before_quarantine)

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "10"]) == 1

    assert probe.read_text(encoding="utf-8") == "must survive\n"
    assert not replacement.exists()
    assert list((module.RESULTS_DIR / ".quarantine").iterdir()) == []
    result = json.loads(next(module.RESULTS_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert result["status"] == "failed_before_effects"
    assert result["effects"] == []
    assert "original restored" in result["error"]


def test_post_truncate_fsync_failure_reports_the_effect(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text("logs/\n", encoding="utf-8")
    log = root / "logs" / "heartbeat.err.log"
    log.parent.mkdir()
    log.write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    module = _load(EFFECTOR, "disk_capacity_post_truncate")
    _install_test_authority(module, tmp_path)
    plan = module.build_plan(1)
    receipt = _receipt(module, tmp_path / "post-truncate.json", plan, attempt_id="post-truncate")
    target_identity = (log.stat().st_dev, log.stat().st_ino)
    real_fsync = module.os.fsync
    failed = False

    def fail_target_fsync(fd):
        nonlocal failed
        metadata = os.fstat(fd)
        if not failed and (metadata.st_dev, metadata.st_ino) == target_identity:
            failed = True
            raise OSError("synthetic post-truncate durability failure")
        return real_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", fail_target_fsync)

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "1"]) == 1

    assert log.stat().st_size == 0
    result = json.loads(next(module.RESULTS_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert result["status"] == "failed_after_effects"
    assert result["effects"] == [
        {
            "kind": "truncate",
            "relative_path": "logs/heartbeat.err.log",
            "size_bytes_before": 1024 * 1024 + 1,
            "mutation_observed": True,
            "durability_confirmed": False,
        }
    ]
    assert "truncated but durability confirmation failed" in result["error"]


def test_result_finalization_failure_reports_completed_effects(tmp_path, monkeypatch, capsys):
    module, probe, _log = _repo(tmp_path, monkeypatch)
    plan = module.build_plan(10)
    receipt = _receipt(module, tmp_path / "result-failure.json", plan, attempt_id="result-failure")
    real_write = module._write_fd

    def fail_final_write(fd, value):
        if value.get("schema") == module.RESULT_SCHEMA and value.get("status") != "reserved":
            raise OSError("synthetic result finalization failure")
        return real_write(fd, value)

    monkeypatch.setattr(module, "_write_fd", fail_final_write)

    assert module.main(["--apply", *_signed_args(receipt), "--log-cap-mb", "10"]) == 1

    assert not probe.exists()
    output = capsys.readouterr().out
    prefix = "disk-capacity reclaim RESULT PUBLICATION FAILED: "
    emergency = json.loads(next(line.removeprefix(prefix) for line in output.splitlines() if line.startswith(prefix)))
    assert emergency["status"] == "result_publication_failed_after_effects"
    assert emergency["effects"][0]["kind"] == "unlink"
    assert emergency["effects"][0]["mutation_observed"] is True
    reserved = json.loads(next(module.RESULTS_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert reserved["status"] == "reserved"
