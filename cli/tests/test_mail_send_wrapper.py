"""Authority-bound tests for the Limen-to-UMA mail wrapper."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "mail-send"


def _load():
    loader = importlib.machinery.SourceFileLoader("mail_send_wrapper_uut", str(WRAPPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture
def wrapper(monkeypatch, tmp_path: Path):
    module = _load()
    owner_root = tmp_path / "domus mail owner"
    delegate = owner_root / "bin" / "mail-send"
    delegate.parent.mkdir(parents=True)
    delegate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    delegate.chmod(0o700)
    contract = owner_root / "config" / "mail-send-delegate-contract.json"
    contract.parent.mkdir(parents=True)
    contract.write_text(
        json.dumps(
            {
                "schema": module.CONTRACT_SCHEMA,
                "protocol": module.REQUEST_PROTOCOL,
                "request_flag": module.REQUEST_FLAG,
                "delegate_sha256": "sha256:" + hashlib.sha256(delegate.read_bytes()).hexdigest(),
                "returns_before": [
                    "credential_resolution",
                    "default_file_resolution",
                    "imap",
                    "smtp",
                    "mutation",
                ],
                "owner_predicate": "python -m pytest tests/test_authorization_request.py",
                "owner_receipt_sha256": "sha256:" + "a" * 64,
                "uma_commit": "1" * 40,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    source_receipts = owner_root / "state" / "mail-source-receipts"
    source_snapshots = owner_root / "state" / "mail-source-snapshots"
    owner_home = owner_root / "home"
    owner_tmp = owner_root / "tmp"
    owner_workdir = owner_root / "run"
    for directory in (source_receipts, source_snapshots, owner_home, owner_tmp, owner_workdir):
        directory.mkdir(parents=True)
    monkeypatch.setattr(module, "DOMUS_MAIL_ROOT", owner_root)
    monkeypatch.setattr(module, "DOMUS_MAIL_DELEGATE", delegate)
    monkeypatch.setattr(module, "OWNER_DELEGATE_CONTRACT", contract)
    monkeypatch.setattr(module, "OWNER_SOURCE_RECEIPTS", source_receipts)
    monkeypatch.setattr(module, "OWNER_SOURCE_SNAPSHOTS", source_snapshots)
    monkeypatch.setattr(module, "OWNER_HOME", owner_home)
    monkeypatch.setattr(module, "OWNER_TMPDIR", owner_tmp)
    monkeypatch.setattr(module, "OWNER_WORKDIR", owner_workdir)
    monkeypatch.setattr(module, "OWNER_PATH_ANCHOR", owner_root)
    monkeypatch.setattr(module, "OWNER_UID", os.geteuid())
    return module, owner_root, delegate


def test_preview_uses_only_pinned_pure_request_with_no_credentials(wrapper, tmp_path: Path) -> None:
    module, _owner_root, delegate = wrapper
    home = tmp_path / "home"
    credential = home / ".config" / "mail_automation" / "credentials.env"
    credential.parent.mkdir(parents=True)
    credential.write_text("GMAIL_APP_PASSWORD=$(touch should-never-run)\n", encoding="utf-8")
    credential.chmod(0o600)
    invocation, environment = module.build_invocation(
        ["--self-test", "--attempt-id", "attempt-fixture-001"],
        {
            "HOME": str(home),
            "PATH": str(tmp_path / "attacker-bin"),
            "PYTHONPATH": str(tmp_path / "attacker-modules"),
            "LIMEN_UMA_ROOT": str(tmp_path / "attacker-uma"),
            "UMA_ROOT": str(tmp_path / "legacy-attacker-uma"),
            "GMAIL_APP_PASSWORD": "must-not-propagate",
        },
    )

    assert invocation == [
        str(delegate),
        module.REQUEST_FLAG,
        "--dry-run",
        "--self-test",
        "--attempt-id",
        "attempt-fixture-001",
    ]
    assert str(credential) not in invocation
    assert environment == {
        "HOME": str(module.OWNER_HOME),
        "TMPDIR": str(module.OWNER_TMPDIR),
        "PATH": module.SAFE_PATH,
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "LC_ALL": "C",
    }


def test_explicit_preview_remains_credential_free(wrapper, tmp_path: Path) -> None:
    module, _owner_root, delegate = wrapper
    home = tmp_path / "home"
    home.mkdir()

    invocation, _environment = module.build_invocation(
        ["--dry-run", "--attempt-id", "attempt-fixture-002", "--self-test"],
        {"HOME": str(home)},
    )

    assert invocation == [
        str(delegate),
        module.REQUEST_FLAG,
        "--dry-run",
        "--attempt-id",
        "attempt-fixture-002",
        "--self-test",
    ]
    assert "--credentials-file" not in invocation


def test_apply_is_refused_before_delegate_or_credentials(wrapper) -> None:
    module, _owner_root, _delegate = wrapper
    with pytest.raises(module.DelegateError, match="caller-selected --apply"):
        module.build_invocation(["--apply", "--attempt-id", "attempt-fixture-003"], {})


@pytest.mark.parametrize(
    "flag",
    [
        "--credentials-file",
        "--credentials-file=/tmp/attacker",
        "--authorization-key-file",
        "--authorization-key-file=/tmp/attacker",
        "--attempt-store",
        "--attempt-store=/tmp/attacker",
        "--from-draft",
        "--from-draft=123",
        "--reply-to-search",
        "--reply-to-search=from:sender",
    ],
)
def test_caller_selected_authority_or_credentials_are_refused(wrapper, flag: str) -> None:
    module, _owner_root, _delegate = wrapper
    with pytest.raises(module.DelegateError, match="caller-selected"):
        module.build_invocation(["--dry-run", flag], {"HOME": "/tmp"})


def test_missing_contract_refuses_before_delegate_execution(wrapper, monkeypatch) -> None:
    module, _owner_root, _delegate = wrapper
    module.OWNER_DELEGATE_CONTRACT.unlink()
    monkeypatch.setattr(
        module.os,
        "execve",
        lambda *_args: (_ for _ in ()).throw(AssertionError("delegate executed")),
    )
    assert module.main(["--dry-run", "--self-test"]) == 4


def test_missing_fixed_delegate_fails_closed_despite_caller_discovery_inputs(
    wrapper,
    monkeypatch,
    tmp_path: Path,
) -> None:
    module, _owner_root, delegate = wrapper
    delegate.unlink()
    monkeypatch.setenv("LIMEN_UMA_ROOT", str(tmp_path / "attacker"))
    monkeypatch.setenv("UMA_ROOT", str(tmp_path / "attacker-legacy"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "attacker-modules"))

    assert module.main(["--dry-run", "--self-test"]) == 4


def test_group_writable_delegate_is_refused(wrapper) -> None:
    module, _owner_root, delegate = wrapper
    delegate.chmod(0o720)
    with pytest.raises(module.DelegateError, match="group/world writable"):
        module.build_invocation(["--dry-run"], {"HOME": "/tmp"})


def test_delegate_hash_drift_is_refused(wrapper) -> None:
    module, _owner_root, delegate = wrapper
    delegate.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    with pytest.raises(module.DelegateError, match="bytes do not match"):
        module.build_invocation(["--dry-run"], {})


def test_main_execs_exact_fixed_delegate_with_sanitized_environment(wrapper, monkeypatch, tmp_path: Path) -> None:
    module, _owner_root, delegate = wrapper
    captured = {}

    def execve(path, argv, environment):
        captured.update({"path": path, "argv": argv, "environment": environment})
        raise RuntimeError("stop before replacement")

    monkeypatch.setattr(module.os, "execve", execve)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "attacker"))

    previous_cwd = Path.cwd()
    try:
        with pytest.raises(RuntimeError, match="stop before replacement"):
            module.main(["--self-test", "--attempt-id", "attempt-fixture-006"])
        assert Path.cwd() == module.OWNER_WORKDIR
    finally:
        os.chdir(previous_cwd)

    assert captured["path"] == str(delegate)
    assert captured["argv"][0] == str(delegate)
    assert captured["argv"][1] == module.REQUEST_FLAG
    assert "--dry-run" in captured["argv"]
    assert "PYTHONPATH" not in captured["environment"]
    assert captured["environment"]["PYTHONSAFEPATH"] == "1"


def test_owner_snapshot_receipt_is_verified_and_live_sources_remain_refused(wrapper) -> None:
    module, _owner_root, _delegate = wrapper
    snapshot = module.OWNER_SOURCE_SNAPSHOTS / "draft-001.json"
    snapshot.write_text('{"body":"owner-produced snapshot"}\n', encoding="utf-8")
    contract_hash = "sha256:" + hashlib.sha256(module.OWNER_DELEGATE_CONTRACT.read_bytes()).hexdigest()
    receipt = module.OWNER_SOURCE_RECEIPTS / "draft-001.receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": module.SNAPSHOT_RECEIPT_SCHEMA,
                "contract_hash": contract_hash,
                "source_kind": "draft",
                "snapshot_name": snapshot.name,
                "snapshot_sha256": "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "snapshot_size": snapshot.stat().st_size,
            }
        ),
        encoding="utf-8",
    )

    invocation, _environment = module.build_invocation(
        ["--source-snapshot-receipt", receipt.name, "--attempt-id", "snapshot-request"],
        {},
    )
    assert invocation[:5] == [
        str(module.DOMUS_MAIL_DELEGATE),
        module.REQUEST_FLAG,
        "--dry-run",
        "--source-snapshot-receipt",
        str(receipt),
    ]
    with pytest.raises(module.DelegateError, match="caller-selected --from-draft"):
        module.build_invocation(["--from-draft", "123"], {})


def test_wrapper_delegate_integration_is_pure_before_sensitive_resolution(wrapper) -> None:
    module, _owner_root, delegate = wrapper
    delegate.write_text(
        """#!/usr/bin/python3
import json, os, sys
pure = sys.argv[1] == "--authorization-request-only"
print(json.dumps({
  "pure_request": pure,
  "credential_resolution": False,
  "default_file_resolution": False,
  "smtp": False,
  "imap": False,
  "mutation": False,
  "secret_env_present": any(k in os.environ for k in ("GMAIL_APP_PASSWORD", "PYTHONPATH", "UMA_ROOT")),
}))
""",
        encoding="utf-8",
    )
    delegate.chmod(0o700)
    contract = json.loads(module.OWNER_DELEGATE_CONTRACT.read_text(encoding="utf-8"))
    contract["delegate_sha256"] = "sha256:" + hashlib.sha256(delegate.read_bytes()).hexdigest()
    module.OWNER_DELEGATE_CONTRACT.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
    invocation, environment = module.build_invocation(["--self-test"], {"GMAIL_APP_PASSWORD": "never"})
    result = subprocess.run(
        invocation,
        cwd=module.OWNER_WORKDIR,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    evidence = json.loads(result.stdout)
    assert evidence == {
        "pure_request": True,
        "credential_resolution": False,
        "default_file_resolution": False,
        "smtp": False,
        "imap": False,
        "mutation": False,
        "secret_env_present": False,
    }


def test_unsafe_absolute_owner_ancestor_is_refused(wrapper):
    module, owner_root, _delegate = wrapper
    unsafe_parent = owner_root.parent
    unsafe_parent.chmod(0o777)
    module.OWNER_PATH_ANCHOR = unsafe_parent
    try:
        with pytest.raises(module.DelegateError, match="group/world writable"):
            module.build_invocation(["--dry-run"], {})
    finally:
        unsafe_parent.chmod(0o700)


def test_deployed_checkout_mail_wrapper_fails_closed_before_network():
    result = subprocess.run(
        [str(WRAPPER), "--dry-run", "--self-test"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": "/var/empty"},
    )
    assert result.returncode == 4
    assert "REFUSED" in result.stderr
