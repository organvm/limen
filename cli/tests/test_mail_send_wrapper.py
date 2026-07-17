"""Authority-bound tests for the Limen-to-UMA mail wrapper."""

from __future__ import annotations

import importlib.machinery
import importlib.util
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
    credential = owner_root / "credentials" / "mail.env"
    credential.parent.mkdir(parents=True)
    credential.write_text("GMAIL_USER=fixture@example.invalid\n", encoding="utf-8")
    credential.chmod(0o600)
    attempt_store = owner_root / "state" / "mail-attempts"
    owner_home = owner_root / "home"
    owner_tmp = owner_root / "tmp"
    owner_workdir = owner_root / "run"
    for directory in (attempt_store, owner_home, owner_tmp, owner_workdir):
        directory.mkdir(parents=True)
    monkeypatch.setattr(module, "DOMUS_MAIL_ROOT", owner_root)
    monkeypatch.setattr(module, "DOMUS_MAIL_DELEGATE", delegate)
    monkeypatch.setattr(module, "OWNER_CREDENTIALS", credential)
    monkeypatch.setattr(module, "OWNER_ATTEMPT_STORE", attempt_store)
    monkeypatch.setattr(module, "OWNER_HOME", owner_home)
    monkeypatch.setattr(module, "OWNER_TMPDIR", owner_tmp)
    monkeypatch.setattr(module, "OWNER_WORKDIR", owner_workdir)
    monkeypatch.setattr(module, "OWNER_PATH_ANCHOR", owner_root)
    monkeypatch.setattr(module, "OWNER_UID", os.geteuid())
    return module, owner_root, delegate


def test_preview_uses_only_fixed_delegate_with_dry_run_and_no_credentials(wrapper, tmp_path: Path) -> None:
    module, _owner_root, delegate = wrapper
    home = tmp_path / "home"
    credential = home / ".config" / "mail_automation" / "credentials.env"
    credential.parent.mkdir(parents=True)
    credential.write_text("GMAIL_APP_PASSWORD=$(touch should-never-run)\n", encoding="utf-8")
    credential.chmod(0o600)
    module._credential_file = lambda *_args: (_ for _ in ()).throw(AssertionError("preview resolved credentials"))

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
        "--dry-run",
        "--attempt-id",
        "attempt-fixture-002",
        "--self-test",
    ]
    assert "--credentials-file" not in invocation


def test_apply_passes_fixed_private_credential_only_after_complete_receipt_shape(
    wrapper,
    tmp_path: Path,
) -> None:
    module, _owner_root, delegate = wrapper
    args = [
        "--apply",
        "--attempt-id",
        "attempt-fixture-003",
        "--authorization-receipt",
        str(tmp_path / "receipt.json"),
        "--authorization-signature",
        str(tmp_path / "receipt.json.sig"),
        "--self-test",
    ]

    invocation, environment = module.build_invocation(args, {"HOME": "/attacker", "SECRET": "drop-me"})

    assert invocation == [
        str(delegate),
        "--credentials-file",
        str(module.OWNER_CREDENTIALS),
        "--attempt-store",
        str(module.OWNER_ATTEMPT_STORE),
        *args,
    ]
    assert "--dry-run" not in invocation
    assert "SECRET" not in environment


@pytest.mark.parametrize(
    "flag",
    [
        "--credentials-file",
        "--credentials-file=/tmp/attacker",
        "--authorization-key-file",
        "--authorization-key-file=/tmp/attacker",
        "--attempt-store",
        "--attempt-store=/tmp/attacker",
    ],
)
def test_caller_selected_authority_or_credentials_are_refused(wrapper, flag: str) -> None:
    module, _owner_root, _delegate = wrapper
    with pytest.raises(module.DelegateError, match="caller-selected"):
        module.build_invocation(["--dry-run", flag], {"HOME": "/tmp"})


def test_apply_requires_signature_before_delegate_or_credentials_are_read(wrapper, tmp_path: Path) -> None:
    module, _owner_root, _delegate = wrapper
    with pytest.raises(module.DelegateError, match="authorization-signature"):
        module.build_invocation(
            [
                "--apply",
                "--attempt-id",
                "attempt-fixture-004",
                "--authorization-receipt",
                str(tmp_path / "receipt.json"),
            ],
            {"HOME": str(tmp_path / "home")},
        )


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


def test_insecure_credential_file_is_refused_on_apply(wrapper, tmp_path: Path) -> None:
    module, _owner_root, _delegate = wrapper
    module.OWNER_CREDENTIALS.chmod(0o644)

    with pytest.raises(module.DelegateError, match="mode-0400/0600"):
        module.build_invocation(
            [
                "--apply",
                "--attempt-id",
                "attempt-fixture-005",
                "--authorization-receipt",
                str(tmp_path / "receipt.json"),
                "--authorization-signature",
                str(tmp_path / "receipt.json.sig"),
            ],
            {"HOME": "/attacker"},
        )


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
    assert "--dry-run" in captured["argv"]
    assert "PYTHONPATH" not in captured["environment"]
    assert captured["environment"]["PYTHONSAFEPATH"] == "1"


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
