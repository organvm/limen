"""Exact-target authorization receipts for pull-request merge effects.

The OpenSSH-signed receipt authorizes one bounded *attempt* to merge one exact
PR head. It is not an acceptance predicate: callers must still re-run the live
exact-head review gate and merge policy immediately before the GitHub merge effect.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


SCHEMA = "limen.merge_authorization.v1"
ACTION = "merge"
REVIEW_GATE_CONTEXT = "limen.pr_review_gate.v1"
MAX_WINDOW = dt.timedelta(minutes=15)
MAX_CLOCK_SKEW = dt.timedelta(seconds=30)
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_HEAD_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_PRINCIPAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+:/-]{0,127}$")
_REQUIRED_FIELDS = {
    "schema",
    "authorization_id",
    "action",
    "repository",
    "pull_request",
    "head_sha",
    "issued_at",
    "expires_at",
    "review_gate_context",
    "signer_principal",
    "signature",
}


class AuthorizationError(ValueError):
    """A merge authorization is missing, unsafe, stale, or malformed."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build one JSON object while rejecting ambiguous duplicate member names."""

    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AuthorizationError(f"authorization receipt contains duplicate JSON member: {key}")
        value[key] = item
    return value


@dataclass(frozen=True)
class MergeAuthorization:
    authorization_id: str
    repository: str
    pull_request: int
    head_sha: str
    issued_at: dt.datetime
    expires_at: dt.datetime
    source: Path
    receipt_sha256: str
    signer_principal: str
    allowed_signers: Path
    allowed_signers_sha256: str
    allowed_signers_bytes: bytes

    def permits(self, repository: str, pull_request: int, head_sha: str) -> bool:
        """Return whether this receipt binds the exact requested merge target."""

        return self.repository == repository and self.pull_request == pull_request and self.head_sha == head_sha


def _timestamp(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise AuthorizationError(f"{field} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AuthorizationError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorizationError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _stable_source(path: Path) -> Path:
    """Bind later revalidation to the lexical path used for this load."""

    return Path(os.path.abspath(os.fspath(path)))


def _validate_file_metadata(metadata: os.stat_result, *, label: str) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise AuthorizationError(f"{label} must be a non-symlink regular file")
    if metadata.st_uid != os.getuid():
        raise AuthorizationError(f"{label} must be owned by the executing user")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise AuthorizationError(f"{label} must not be group- or world-writable")


def _version(metadata: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    """Return metadata that changes when an opened regular file is rewritten."""

    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_owned_bytes(path: Path, *, label: str) -> tuple[Path, bytes]:
    """Read one bounded owner file through a no-follow descriptor snapshot."""

    source = _stable_source(path)
    try:
        metadata = source.lstat()
    except OSError as exc:
        raise AuthorizationError(f"cannot inspect {label}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise AuthorizationError(f"{label} must be a non-symlink regular file")
    _validate_file_metadata(metadata, label=label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise AuthorizationError(f"cannot safely open {label}: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise AuthorizationError(f"{label} changed while it was opened")
        _validate_file_metadata(opened, label=label)
        if opened.st_size > 64 * 1024:
            raise AuthorizationError(f"{label} exceeds the 64 KiB bound")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, 8192)
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > 64 * 1024:
                raise AuthorizationError(f"{label} exceeds the 64 KiB bound")
        closed_snapshot = os.fstat(descriptor)
        if _version(opened) != _version(closed_snapshot):
            raise AuthorizationError(f"{label} changed while it was read")
    except OSError as exc:
        raise AuthorizationError(f"cannot read {label}: {exc}") from exc
    finally:
        os.close(descriptor)
    return source, bytes(payload)


def _read_object(path: Path) -> tuple[Path, dict[str, Any], str]:
    source, payload = _read_owned_bytes(path, label="authorization receipt")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    except UnicodeDecodeError as exc:
        raise AuthorizationError("authorization receipt is not UTF-8") from exc
    except AuthorizationError:
        raise
    except ValueError as exc:
        raise AuthorizationError("authorization receipt is not valid JSON") from exc
    if not isinstance(value, dict):
        raise AuthorizationError("authorization receipt root must be an object")
    return source, value, hashlib.sha256(payload).hexdigest()


def _read_allowed_signers(path: Path) -> tuple[Path, bytes, str]:
    source, payload = _read_owned_bytes(path, label="allowed-signers owner")
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise AuthorizationError("allowed-signers owner is not UTF-8") from exc
    if not any(line.strip() and not line.lstrip().startswith("#") for line in lines):
        raise AuthorizationError("allowed-signers owner contains no signer principals")
    return source, payload, hashlib.sha256(payload).hexdigest()


@contextmanager
def materialize_allowed_signers(authorization: MergeAuthorization) -> Iterator[Path]:
    """Expose only the authorization's immutable trust snapshot to child predicates."""

    payload = authorization.allowed_signers_bytes
    if hashlib.sha256(payload).hexdigest() != authorization.allowed_signers_sha256:
        raise AuthorizationError("allowed-signers snapshot digest is inconsistent")
    try:
        with tempfile.NamedTemporaryFile(prefix="limen-merge-signers-") as signer_file:
            signer_file.write(payload)
            signer_file.flush()
            os.fchmod(signer_file.fileno(), stat.S_IRUSR)
            yield Path(signer_file.name)
    except OSError as exc:
        raise AuthorizationError(f"cannot materialize allowed-signers snapshot: {exc}") from exc


def _canonical_payload(value: dict[str, Any]) -> bytes:
    payload = {key: item for key, item in value.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _verify_signature(
    value: dict[str, Any],
    *,
    signer_principal: str,
    allowed_signers: bytes,
) -> None:
    signature = value.get("signature")
    if not isinstance(signature, str) or not signature.startswith("-----BEGIN SSH SIGNATURE-----\n"):
        raise AuthorizationError("signature must be an armored OpenSSH signature")
    try:
        with (
            tempfile.NamedTemporaryFile(prefix="limen-merge-signers-") as signer_file,
            tempfile.NamedTemporaryFile(prefix="limen-merge-", suffix=".sig") as signature_file,
        ):
            signer_file.write(allowed_signers)
            signer_file.flush()
            os.fchmod(signer_file.fileno(), stat.S_IRUSR)
            signature_file.write(signature.encode("ascii"))
            signature_file.flush()
            result = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    signer_file.name,
                    "-I",
                    signer_principal,
                    "-n",
                    SCHEMA,
                    "-s",
                    signature_file.name,
                ],
                input=_canonical_payload(value),
                capture_output=True,
                timeout=10,
                check=False,
            )
    except (OSError, UnicodeEncodeError, subprocess.SubprocessError) as exc:
        raise AuthorizationError(f"cannot verify authorization signature: {exc}") from exc
    if result.returncode != 0:
        raise AuthorizationError("authorization signature is invalid or signer is not allowed")


def load_authorization(
    path: Path,
    *,
    allowed_signers: Path,
    now: dt.datetime | None = None,
) -> MergeAuthorization:
    """Load and validate one short-lived exact-head merge authorization."""

    source, value, receipt_sha256 = _read_object(path)
    if set(value) != _REQUIRED_FIELDS:
        raise AuthorizationError("authorization receipt fields do not match the v1 schema")
    if value.get("schema") != SCHEMA:
        raise AuthorizationError(f"schema must be {SCHEMA}")
    if value.get("action") != ACTION:
        raise AuthorizationError(f"action must be {ACTION}")
    if value.get("review_gate_context") != REVIEW_GATE_CONTEXT:
        raise AuthorizationError(f"review_gate_context must be {REVIEW_GATE_CONTEXT}")

    authorization_id = value.get("authorization_id")
    repository = value.get("repository")
    pull_request = value.get("pull_request")
    head_sha = value.get("head_sha")
    signer_principal = value.get("signer_principal")
    if not isinstance(authorization_id, str) or not _ID_RE.fullmatch(authorization_id):
        raise AuthorizationError("authorization_id must be a stable 8-128 character identifier")
    if not isinstance(repository, str) or not _REPO_RE.fullmatch(repository):
        raise AuthorizationError("repository must be OWNER/NAME")
    if isinstance(pull_request, bool) or not isinstance(pull_request, int) or pull_request <= 0:
        raise AuthorizationError("pull_request must be a positive integer")
    if not isinstance(head_sha, str) or not _HEAD_RE.fullmatch(head_sha):
        raise AuthorizationError("head_sha must be a full 40-character Git commit SHA")
    if not isinstance(signer_principal, str) or not _PRINCIPAL_RE.fullmatch(signer_principal):
        raise AuthorizationError("signer_principal is invalid")

    issued_at = _timestamp(value.get("issued_at"), "issued_at")
    expires_at = _timestamp(value.get("expires_at"), "expires_at")
    observed_now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    if expires_at <= issued_at:
        raise AuthorizationError("expires_at must be later than issued_at")
    if expires_at - issued_at > MAX_WINDOW:
        raise AuthorizationError("authorization window must not exceed 15 minutes")
    if issued_at > observed_now + MAX_CLOCK_SKEW:
        raise AuthorizationError("authorization receipt is issued in the future")
    if observed_now >= expires_at:
        raise AuthorizationError("authorization receipt is expired")

    trusted_signers, trusted_signers_bytes, trusted_signers_sha256 = _read_allowed_signers(allowed_signers)
    _verify_signature(
        value,
        signer_principal=signer_principal,
        allowed_signers=trusted_signers_bytes,
    )

    return MergeAuthorization(
        authorization_id=authorization_id,
        repository=repository,
        pull_request=pull_request,
        head_sha=head_sha,
        issued_at=issued_at,
        expires_at=expires_at,
        source=source,
        receipt_sha256=receipt_sha256,
        signer_principal=signer_principal,
        allowed_signers=trusted_signers,
        allowed_signers_sha256=trusted_signers_sha256,
        allowed_signers_bytes=trusted_signers_bytes,
    )
