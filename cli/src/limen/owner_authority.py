"""Owner-custodied signature verification for privileged Limen receipts.

The executing checkout is deliberately not a trust root.  Production authority
is provisioned by Domus under a fixed OS-account path and uses OpenSSH signatures;
the private signing key is never read by Limen or an executor session.  A fresh
checkout therefore ships *unprovisioned* and every privileged receipt fails
closed until the owner installs a sealed ``allowed_signers`` file.

This module is stdlib-only so the installed Claude validator can use it before a
project virtualenv exists.
"""

from __future__ import annotations

import json
import os
import pwd
import shlex
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ATTESTATION_SCHEMA = "limen.owner_attestation.v1"
OWNER_PRINCIPAL = "limen-owner-authority"
_ATTESTATION_FIELD = "owner_attestation"


class OwnerAuthorityError(ValueError):
    """Owner authority is absent, malformed, or cryptographically invalid."""


def os_account_home() -> Path:
    """Return the login database home, ignoring caller-controlled ``HOME``."""

    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    except (KeyError, OSError) as exc:
        raise OwnerAuthorityError("owner-account-home-unavailable") from exc


def authority_root() -> Path:
    """Return the sole production trust root.

    No environment variable, repository path, current directory, or task
    worktree participates in this resolution.
    """

    return os_account_home() / "Library" / "Application Support" / "org.organvm.limen" / "authority"


def receipt_path(name: str) -> Path:
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise OwnerAuthorityError("owner-receipt-name-invalid")
    return authority_root() / "receipts" / name


def runtime_path(name: str) -> Path:
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise OwnerAuthorityError("owner-runtime-name-invalid")
    return authority_root() / "runtime" / name


def canonical_payload(receipt: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in receipt.items() if key != _ATTESTATION_FIELD}
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _sealed_regular_file(path: Path, *, executable: bool = False) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise OwnerAuthorityError("owner-trust-root-unprovisioned") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise OwnerAuthorityError("owner-trust-root-unsealed")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise OwnerAuthorityError("owner-trust-root-unsealed")
    # The executor runs as the login user. A same-user file is therefore not
    # independent custody: even UF_IMMUTABLE can be removed by its owner.
    # Production trust material and launchers must be installed by root.
    if metadata.st_uid != 0:
        raise OwnerAuthorityError("owner-trust-root-unsealed")
    if executable and not metadata.st_mode & stat.S_IXUSR:
        raise OwnerAuthorityError("owner-runtime-not-executable")
    return metadata


def require_sealed_runtime(name: str) -> Path:
    path = runtime_path(name)
    _sealed_regular_file(path, executable=True)
    return path


def require_canonical_orchestrator_parent() -> Path:
    """Prove this validator was reached through the installed preservation runner.

    The validator is a child of the Claude shim; the shim's parent must therefore
    be the sealed Domus ``limen-preservation-dispatch`` process.  Caller
    environment markers and claimed PIDs are intentionally not inputs.
    """

    expected = require_sealed_runtime("limen-preservation-dispatch").resolve()
    shim_pid = os.getppid()
    try:
        parent = subprocess.run(
            ["/bin/ps", "-o", "ppid=", "-p", str(shim_pid)],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        dispatcher_pid = int(parent.stdout.strip())
        command = subprocess.run(
            ["/bin/ps", "-o", "command=", "-p", str(dispatcher_pid)],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        argv = shlex.split(command.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise OwnerAuthorityError("fable-orchestrator-parent-unavailable") from exc
    if parent.returncode != 0 or command.returncode != 0 or not argv:
        raise OwnerAuthorityError("fable-orchestrator-parent-unavailable")
    try:
        actual = Path(argv[0]).resolve(strict=True)
    except OSError as exc:
        raise OwnerAuthorityError("fable-orchestrator-parent-unavailable") from exc
    if actual != expected:
        raise OwnerAuthorityError("fable-direct-launch-prohibited")
    return expected


def _attestation(receipt: Any, *, namespace: str) -> tuple[dict[str, Any], str]:
    if not isinstance(receipt, dict):
        raise OwnerAuthorityError("owner-receipt-not-object")
    value = receipt.get(_ATTESTATION_FIELD)
    if not isinstance(value, dict) or value.get("schema") != ATTESTATION_SCHEMA:
        raise OwnerAuthorityError("owner-attestation-missing")
    if value.get("principal") != OWNER_PRINCIPAL:
        raise OwnerAuthorityError("owner-attestation-principal-invalid")
    if value.get("namespace") != namespace:
        raise OwnerAuthorityError("owner-attestation-namespace-invalid")
    signature = value.get("signature")
    if (
        not isinstance(signature, str)
        or not signature.startswith("-----BEGIN SSH SIGNATURE-----")
        or "-----END SSH SIGNATURE-----" not in signature
    ):
        raise OwnerAuthorityError("owner-attestation-signature-invalid")
    return value, signature


def verify_receipt(
    receipt: Any,
    *,
    namespace: str,
    _trust_root: Path | None = None,
    _require_sealed: bool = True,
) -> dict[str, Any]:
    """Verify one owner-signed receipt.

    Underscored overrides exist only for hermetic unit fixtures.  Production
    callers never expose them and always use the fixed sealed owner root.
    """

    _value, signature = _attestation(receipt, namespace=namespace)
    root = _trust_root if _trust_root is not None else authority_root()
    signers = root / "allowed_signers"
    if _require_sealed:
        _sealed_regular_file(signers)
    else:
        try:
            metadata = signers.lstat()
        except OSError as exc:
            raise OwnerAuthorityError("owner-trust-root-unprovisioned") from exc
        if signers.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise OwnerAuthorityError("owner-trust-root-unsealed")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="limen-owner-", suffix=".sig") as handle:
        handle.write(signature)
        if not signature.endswith("\n"):
            handle.write("\n")
        handle.flush()
        try:
            result = subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(signers),
                    "-I",
                    OWNER_PRINCIPAL,
                    "-n",
                    namespace,
                    "-s",
                    handle.name,
                ],
                input=canonical_payload(receipt),
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise OwnerAuthorityError("owner-attestation-verifier-unavailable") from exc
    if result.returncode != 0:
        raise OwnerAuthorityError("owner-attestation-signature-invalid")
    return dict(receipt)
