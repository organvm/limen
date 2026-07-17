"""The Limen mail shim discovers UMA without executing credential files."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "mail-send"


def _python_stub(path: Path) -> Path:
    stub = path / "python3"
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "${1:-}" = "-c" ]; then exit "${MODULE_DISCOVERY_RC:-1}"; fi\n'
        'if [ "${1:-}" = "--help" ] || [ "${2:-}" = "--help" ] || [ "${3:-}" = "--help" ]; then '
        "printf '%s\\n' \"${MAIL_SEND_HELP:-}\"; exit 0; fi\n"
        'printf \'%s\\n\' "$@" > "$MAIL_SEND_ARGV_LOG"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def test_wrapper_prefers_registered_uma_root_and_never_sources_credentials(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config = home / ".config" / "mail_automation"
    config.mkdir(parents=True)
    marker = tmp_path / "credential-file-executed"
    credential_file = config / "credentials.env"
    credential_file.write_text(
        f"GMAIL_USER=me@example.com\nGMAIL_APP_PASSWORD=$(touch {marker})\ntouch {marker}\n",
        encoding="utf-8",
    )
    registered = tmp_path / "registered-uma"
    legacy = tmp_path / "legacy-uma"
    registered.mkdir()
    legacy.mkdir()
    (registered / "mail_send.py").write_text("# fixture\n", encoding="utf-8")
    (legacy / "mail_send.py").write_text("# wrong fixture\n", encoding="utf-8")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    _python_stub(binary_dir)
    argv_log = tmp_path / "argv.log"

    proc = subprocess.run(
        [str(WRAPPER), "--self-test", "--attempt-id", "attempt-fixture-001"],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{binary_dir}:{os.environ['PATH']}",
            "LIMEN_UMA_ROOT": str(registered),
            "UMA_ROOT": str(legacy),
            "MAIL_SEND_ARGV_LOG": str(argv_log),
        },
        check=True,
    )

    assert proc.stdout == ""
    assert argv_log.read_text(encoding="utf-8").splitlines() == [
        str(registered / "mail_send.py"),
        "--credentials-file",
        str(credential_file),
        "--dry-run",
        "--self-test",
        "--attempt-id",
        "attempt-fixture-001",
    ]
    assert not marker.exists()


def test_wrapper_falls_back_to_installed_module_without_inventing_apply(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    _python_stub(binary_dir)
    argv_log = tmp_path / "argv.log"

    subprocess.run(
        [str(WRAPPER), "--attempt-id", "attempt-fixture-002", "--self-test"],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{binary_dir}:{os.environ['PATH']}",
            "LIMEN_UMA_ROOT": str(tmp_path / "absent-uma"),
            "MAIL_SEND_ARGV_LOG": str(argv_log),
            "MODULE_DISCOVERY_RC": "0",
        },
        check=True,
    )

    args = argv_log.read_text(encoding="utf-8").splitlines()
    assert args == ["-m", "mail_send", "--dry-run", "--attempt-id", "attempt-fixture-002", "--self-test"]
    assert "--apply" not in args


def test_wrapper_refuses_apply_when_deployed_delegate_lacks_receipt_contract(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uma = tmp_path / "uma"
    uma.mkdir()
    (uma / "mail_send.py").write_text("# legacy fixture\n", encoding="utf-8")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    _python_stub(binary_dir)
    argv_log = tmp_path / "argv.log"

    proc = subprocess.run(
        [
            str(WRAPPER),
            "--apply",
            "--attempt-id",
            "attempt-fixture-003",
            "--authorization-receipt",
            str(tmp_path / "receipt.json"),
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{binary_dir}:{os.environ['PATH']}",
            "LIMEN_UMA_ROOT": str(uma),
            "MAIL_SEND_ARGV_LOG": str(argv_log),
            "MAIL_SEND_HELP": "--self-test --dry-run",
        },
    )

    assert proc.returncode == 4
    assert "lacks required contract flag --apply" in proc.stderr
    assert not argv_log.exists()


def test_wrapper_refuses_caller_selected_hmac_key_contract(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uma = tmp_path / "uma"
    uma.mkdir()
    (uma / "mail_send.py").write_text("# receipt-bound fixture\n", encoding="utf-8")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    _python_stub(binary_dir)
    argv_log = tmp_path / "argv.log"
    receipt = tmp_path / "receipt.json"
    key = tmp_path / "authorization.key"

    proc = subprocess.run(
        [
            str(WRAPPER),
            "--apply",
            "--attempt-id",
            "attempt-fixture-004",
            "--authorization-receipt",
            str(receipt),
            "--authorization-key-file",
            str(key),
            "--self-test",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{binary_dir}:{os.environ['PATH']}",
            "LIMEN_UMA_ROOT": str(uma),
            "MAIL_SEND_ARGV_LOG": str(argv_log),
            "MAIL_SEND_HELP": (
                "--apply --attempt-id --authorization-receipt --authorization-key-file --credentials-file"
            ),
        },
    )

    assert proc.returncode == 4
    assert "caller-selected authorization key" in proc.stderr
    assert not argv_log.exists()


def test_wrapper_passes_apply_only_after_pinned_signature_contract_probe(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    uma = tmp_path / "uma"
    uma.mkdir()
    (uma / "mail_send.py").write_text("# owner-signature fixture\n", encoding="utf-8")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    _python_stub(binary_dir)
    argv_log = tmp_path / "argv.log"
    receipt = tmp_path / "receipt.json"
    signature = tmp_path / "receipt.json.sig"

    subprocess.run(
        [
            str(WRAPPER),
            "--apply",
            "--attempt-id",
            "attempt-fixture-005",
            "--authorization-receipt",
            str(receipt),
            "--authorization-signature",
            str(signature),
            "--self-test",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{binary_dir}:{os.environ['PATH']}",
            "LIMEN_UMA_ROOT": str(uma),
            "MAIL_SEND_ARGV_LOG": str(argv_log),
            "MAIL_SEND_HELP": (
                "--apply --attempt-id --authorization-receipt --authorization-signature --credentials-file"
            ),
        },
        check=True,
    )

    args = argv_log.read_text(encoding="utf-8").splitlines()
    assert args == [
        str(uma / "mail_send.py"),
        "--apply",
        "--attempt-id",
        "attempt-fixture-005",
        "--authorization-receipt",
        str(receipt),
        "--authorization-signature",
        str(signature),
        "--self-test",
    ]
    assert "--dry-run" not in args
