#!/usr/bin/env python3
"""HORREVM custody — the granary's shipping lane: arca-sealed ciphertext to the cloud rails.

The strategic-use half of HORREVM (the doctor is scripts/cloud-storage-doctor.py). Drives rclone
in HEADLESS API mode (no File Provider desktop apps — the pre-2026-06-15 breakage vector) against
two remotes whose binary, config, rail identities, budgets, and source roots are
fixed by root-owned Domus configuration:

  gdrive:   second-vendor offsite for a newly sealed snapshot of ~/.arca-vault,
            a sealed session-corpus inventory, and the sealed continuity kernel.
            Covers the "GitHub lost AND Mac lost" correlated failure.
  dropbox:  break-glass grab bag — RECOVERY-CARD.md (plaintext, ZERO secrets) + the sealed kernel,
            reachable from any borrowed browser.

Egress law: ONLY ciphertext plus the one non-secret recovery card ever leaves the machine
(L-CLOUD-EGRESS-CONSENT). Every remote or local mutation requires explicit ``--apply``, the
``LIMEN_HORREVM_APPLY=1`` safety valve, and a fresh OpenSSH-signed
``limen.horrevm.apply_receipt.v1`` receipt. The signature is verified under a dedicated namespace
against the fixed Domus owner trust root and replay registry. The executing caller cannot substitute
those surfaces through an argument, environment variable, or checkout edit. The signed payload binds one
action, exact source-manifest and content hashes, exact remote destinations, one expiry, and one
non-replayable attempt id. A flag or self-asserted JSON document is never authorization by itself.
Objects land in one immutable, attempt-hashed set. Probe deletion is restricted
to that set, every remote effect is journaled in owner custody, and
``manifest-current.json`` is copied only after every payload object verifies.
Preview and status spawn no subprocess.

Verbs:
  --push             zero-write push plan; apply requires receipt and owner signature
  --probe            zero-write probe plan; apply requires receipt and owner signature
  --check/default    zero-write push plan with receipt-ready hashes
  --status           zero-write freshness predicate
  --doctor           deployed owner-config and cryptographic-tool hash parity — no rclone
"""

from __future__ import annotations

import sys

# Preview/check/status are literal zero-write contracts, including incidental local bytecode.
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
DOMUS_AUTHORITY_ROOT = Path("/Library/Application Support/org.organvm.domus/limen/authority")
OWNER_PATH_ANCHOR = Path("/")
LOG = DOMUS_AUTHORITY_ROOT / "state" / "horrevm.json"
ARCA = DOMUS_AUTHORITY_ROOT / "bin" / "arca"
RCLONE = DOMUS_AUTHORITY_ROOT / "bin" / "rclone"
RCLONE_CONF = DOMUS_AUTHORITY_ROOT / "config" / "rclone.conf"
OWNER_CONFIG = DOMUS_AUTHORITY_ROOT / "config" / "horrevm.json"
OWNER_APPLY_TMP = DOMUS_AUTHORITY_ROOT / "tmp" / "horrevm"
OWNER_WORKDIR = DOMUS_AUTHORITY_ROOT / "run"
CUSTODY_DIR = "limen-custody"
LEVER = "L-CLOUD-EGRESS-CONSENT"
MIN_PUSH_INTERVAL_H = 20  # MAT-pattern self-throttle: probes every beat, pushes ~daily
RECEIPT_SCHEMA = "limen.horrevm.apply_receipt.v1"
SIGNED_RECEIPT_NAMESPACE = RECEIPT_SCHEMA
OWNER_ALLOWED_SIGNERS = DOMUS_AUTHORITY_ROOT / "trust" / "horrevm-apply.allowed-signers"
OWNER_CONSUMED_DIR = DOMUS_AUTHORITY_ROOT / "consumed" / "horrevm"
OWNER_EFFECTOR = DOMUS_AUTHORITY_ROOT / "bin" / "horrevm-custody"
OWNER_UID = 0
SSH_KEYGEN = Path("/usr/bin/ssh-keygen")
PLAN_SCHEMA = "limen.horrevm.payload_plan.v1"
STATE_SCHEMA = "limen.horrevm.state.v2"
CONFIG_SCHEMA = "limen.horrevm.owner_config.v1"
REMOTE_WRITE_VERBS = frozenset({"copy", "copyto", "delete", "deletefile", "move", "moveto", "sync"})
STATE_RAIL_IDS = {"gdrive": "googledrive", "dropbox": "dropbox"}
MAX_RECEIPT_BYTES = 64 * 1024
MAX_TRUST_FILE_BYTES = 64 * 1024
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_CONFIG_BYTES = 64 * 1024
MAX_RECEIPT_LIFETIME = timedelta(hours=4)
AUTHORIZED_PRINCIPAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@:+-]{0,127}")
ACTIVE_CONFIG: dict[str, Any] | None = None
VERIFIED_CIPHERTEXT_MANIFESTS: dict[str, dict[str, Any]] = {}

# The approved egress list (mirrors the lever text; edit BOTH or neither).
# type seal:   snapshot, tar, and seal via `arca.sh seal` before egress.
# type kernel: the continuity kernel — sealed bundle of the files below + RECOVERY-CARD.md.
PAYLOADS: dict[str, list[dict]] = {
    "gdrive": [
        # The vault also contains a plaintext manifest and Git metadata; seal the whole
        # snapshot again instead of trusting a directory name as a ciphertext proof.
        {"name": "arca-vault", "type": "seal", "src": "~/.arca-vault"},
        {"name": "corpus-inventory", "type": "seal", "src": "~/.limen-private/session-corpus/inventory"},
        {"name": "kernel", "type": "kernel"},
    ],
    "dropbox": [
        {"name": "kernel", "type": "kernel"},
    ],
}
KERNEL_CANDIDATES: list[str] = []


def now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mask(s: str) -> str:
    import re

    return re.sub(r"[\w.+-]+@[\w.-]+", "<account>", s)


def say(msg: str) -> None:
    print(_mask(msg))


def run(cmd: list[str], timeout: int = 120) -> tuple[int | None, str]:
    if not cmd or not Path(cmd[0]).is_absolute():
        raise EffectRefused("apply subprocess executable must be an absolute owner-selected path")
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "HOME": "/var/empty",
                "TMPDIR": str(OWNER_APPLY_TMP),
                "LC_ALL": "C",
                "PYTHONNOUSERSITE": "1",
                "PYTHONSAFEPATH": "1",
            },
            cwd=str(OWNER_WORKDIR),
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None, ""


class ReceiptError(ValueError):
    """A receipt that cannot authorize any effect."""


class EffectRefused(RuntimeError):
    """A mutating command reached the command boundary without authorization."""


class ApplyReceipt(NamedTuple):
    action: str
    target: str
    payload_hash: str
    source_manifest_hash: str
    content_hashes: dict[str, str]
    destinations: tuple[str, ...]
    expires_at: datetime
    attempt_id: str
    receipt_hash: str
    signer: str
    trust_root_hash: str
    remote: str
    config_hash: str
    rail_id: str
    tool_hashes: dict[str, str]
    root_bindings: dict[str, Any]
    object_set: str


def _require_apply_valve(effect: str) -> None:
    if os.environ.get("LIMEN_HORREVM_APPLY") != "1":
        raise EffectRefused(f"{effect} requires LIMEN_HORREVM_APPLY=1")


def _require_receipt(receipt: ApplyReceipt | None, effect: str) -> ApplyReceipt:
    _require_apply_valve(effect)
    if receipt is None:
        raise EffectRefused(f"{effect} requires an apply receipt")
    if receipt.expires_at <= now():
        raise EffectRefused(f"{effect} refused because the apply receipt expired")
    return receipt


def rclone(args: list[str], *, receipt: ApplyReceipt | None = None, timeout: int = 120) -> tuple[int | None, str]:
    """Single rclone boundary: known mutating verbs fail closed without a validated receipt."""

    if not args:
        raise ValueError("rclone command is empty")
    if args[0] in REMOTE_WRITE_VERBS:
        receipt = _require_receipt(receipt, f"rclone {args[0]}")
        if args[0] not in {"copyto", "deletefile"}:
            raise EffectRefused(f"rclone {args[0]} is not an authorized HORREVM operation")
        remote_arguments = [value for value in args[1:] if isinstance(value, str) and ":" in value]
        if len(remote_arguments) != 1:
            raise EffectRefused(f"rclone {args[0]} requires one exact signed remote object")
        refused = [value for value in remote_arguments if value not in receipt.destinations]
        if refused:
            raise EffectRefused(f"rclone {args[0]} destination is outside the signed receipt")
        if args[0] == "deletefile" and any(
            not value.startswith(f"{receipt.remote}:{receipt.object_set}/probes/")
            for value in remote_arguments
        ):
            raise EffectRefused("rclone deletefile is restricted to the signed probe object")
        if args[0] == "copyto" and len(args) >= 3 and ":" in args[2]:
            required = {"--immutable", "--checksum", "--stats-one-line-json"}
            if not required.issubset(args):
                raise EffectRefused("remote creation requires rclone immutable, checksum, and transfer-result semantics")
    return run([str(RCLONE), "--config", str(RCLONE_CONF), *args], timeout)


def _state_parent_fd(*, create: bool) -> tuple[int, str]:
    """Open the pre-provisioned Domus state parent without following links."""

    del create  # Authority directories are installed by Domus, never by this effector.
    try:
        relative = LOG.relative_to(DOMUS_AUTHORITY_ROOT)
    except ValueError as exc:
        raise ReceiptError("custody state path escapes the fixed Domus authority root") from exc
    if len(relative.parts) < 2 or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReceiptError("custody state path is unsafe")
    parent = LOG.parent
    _assert_domus_owner_chain(parent, "Domus custody-state registry", leaf_directory=True)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(
        os, "O_CLOEXEC", 0
    )
    try:
        current = os.open(parent, flags)
    except OSError as exc:
        raise ReceiptError(f"Domus custody-state registry is unsafe: {type(exc).__name__}") from exc
    try:
        metadata = os.fstat(current)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != OWNER_UID
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ReceiptError("Domus custody-state registry lost owner custody")
        return current, LOG.name
    except Exception:
        os.close(current)
        raise


def load_state() -> dict:
    parent_fd: int | None = None
    state_fd: int | None = None
    try:
        parent_fd, name = _state_parent_fd(create=False)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        state_fd = os.open(name, flags, dir_fd=parent_fd)
        metadata = os.fstat(state_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != OWNER_UID
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ReceiptError("custody state must remain an owner-custodied single-link regular file")
        if metadata.st_size > MAX_STATE_BYTES:
            raise ReceiptError("custody state exceeds its bounded size")
        chunks: list[bytes] = []
        remaining = MAX_STATE_BYTES + 1
        while remaining:
            chunk = os.read(state_fd, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_STATE_BYTES:
            raise ReceiptError("custody state exceeds its bounded size")
        value = json.loads(raw)
    except FileNotFoundError:
        return {"rails": {}}
    except (OSError, ReceiptError, ValueError) as exc:
        return {"rails": {}, "_state_error": f"custody state unreadable: {type(exc).__name__}"}
    finally:
        if state_fd is not None:
            os.close(state_fd)
        if parent_fd is not None:
            os.close(parent_fd)
    if not isinstance(value, dict) or not isinstance(value.get("rails", {}), dict):
        return {"rails": {}, "_state_error": "custody state schema is invalid"}
    return value


def save_state(state: dict, receipt: ApplyReceipt | None = None) -> bool:
    """Atomically publish apply state through a root-anchored no-follow path."""

    _require_receipt(receipt, "custody state publication")
    state["schema"] = STATE_SCHEMA
    state["generated_at"] = _iso(now())
    state.setdefault("rails", {}).setdefault("icloud", {"status": "delegated-to-existing-organs"})
    state["rails"].setdefault("onedrive", {"status": "dormant-by-design"})
    parent_fd: int | None = None
    tmp_name = ""
    try:
        parent_fd, name = _state_parent_fd(create=True)
        try:
            existing = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1):
            raise ReceiptError("custody state destination is not a single-link regular file")

        tmp_name = f".horrevm-state-{uuid.uuid4().hex}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        fd = os.open(tmp_name, flags, 0o600, dir_fd=parent_fd)
        payload = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8")
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write while publishing custody state")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        tmp_name = ""
        os.fsync(parent_fd)
        return True
    except (OSError, ReceiptError) as exc:
        say(f"state log unwritable ({exc})")
        return False
    finally:
        if parent_fd is not None and tmp_name:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except OSError:
                pass
        if parent_fd is not None:
            os.close(parent_fd)


def _state_rail_id(remote: str) -> str:
    return STATE_RAIL_IDS.get(remote, remote)


def _rail(state: dict, remote: str, *, create: bool = False) -> dict:
    rails = state.setdefault("rails", {}) if create else state.get("rails", {})
    key = _state_rail_id(remote)
    if create:
        if key not in rails and remote != key and isinstance(rails.get(remote), dict):
            rails[key] = dict(rails[remote])
        return rails.setdefault(key, {})
    value = rails.get(key)
    if not isinstance(value, dict) and remote != key:
        value = rails.get(remote)
    return value if isinstance(value, dict) else {}


def parked() -> bool:
    """Pure owner-config predicate; status/preview must never spawn rclone."""

    return ACTIVE_CONFIG is None


def gate_a(remote: str) -> dict:
    """Token + quota (rclone about)."""
    rc, out = rclone(["about", f"{remote}:", "--json"], timeout=60)
    if rc != 0:
        return {"token_ok": False}
    try:
        about = json.loads(out)
    except ValueError:
        return {"token_ok": False, "reason": "quota response was not valid JSON"}
    if not isinstance(about, dict):
        return {"token_ok": False, "reason": "quota response was not an object"}
    total = about.get("total")
    free = about.get("free")
    if (
        isinstance(total, bool)
        or isinstance(free, bool)
        or not isinstance(total, (int, float))
        or not isinstance(free, (int, float))
        or not 0 <= free <= total <= 10**18
    ):
        return {"token_ok": False, "reason": "quota values were outside 0 <= free <= total <= 1e18"}
    return {"token_ok": True, "quota_total": total, "quota_free": free}


def _attempt_slug(attempt_id: str) -> str:
    return hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()[:24]


def _attempt_key(attempt_id: str) -> str:
    return "sha256:" + hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()


def _target(remote: str) -> str:
    return f"{remote}:{CUSTODY_DIR}"


def _object_set(attempt_id: str) -> str:
    return f"{CUSTODY_DIR}/sets/{_attempt_slug(attempt_id)}"


def _probe_payload(remote: str, attempt_id: str) -> bytes:
    value = {
        "schema": "limen.horrevm.probe_payload.v1",
        "attempt_id_hash": _attempt_key(attempt_id),
        "target": _target(remote),
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _remote_object_stat(destination: str) -> tuple[str, dict[str, Any] | None]:
    """Return absent/present/unknown without mutating the remote."""

    rc, out = rclone(["lsjson", destination, "--stat", "--hash"], timeout=90)
    if rc == 3:
        return "absent", None
    if rc != 0:
        return "unknown", None
    try:
        value = json.loads(out)
    except ValueError:
        return "unknown", None
    if not isinstance(value, dict) or value.get("IsDir") is True:
        return "unknown", None
    identity = value.get("ID") or value.get("OrigID")
    if not isinstance(identity, str) or not identity:
        return "unknown", None
    return "present", value


def _copy_result_proves_one_create(output: str) -> bool:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        transfers = value.get("transfers")
        errors = value.get("errors")
        return (
            isinstance(transfers, int)
            and not isinstance(transfers, bool)
            and transfers == 1
            and isinstance(errors, int)
            and not isinstance(errors, bool)
            and errors == 0
        )
    return False


def _remote_identity(value: dict[str, Any]) -> tuple[str, int] | None:
    identity = value.get("ID") or value.get("OrigID")
    size = value.get("Size")
    if (
        not isinstance(identity, str)
        or not identity
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        return None
    return identity, size


def _immutable_remote_create(
    local: Path,
    destination: str,
    receipt: ApplyReceipt,
    *,
    phase_prefix: str,
    timeout: int,
) -> bool:
    """Create one absent object exactly once and prove its post-readback identity."""

    digest, size = _safe_regular_hash(local)
    preflight, _before = _remote_object_stat(destination)
    if preflight == "present":
        raise EffectRefused(f"{destination}: immutable destination already exists")
    if preflight != "absent":
        raise EffectRefused(f"{destination}: immutable destination absence is not provable")
    _append_effect_journal(
        receipt,
        {
            "phase": f"{phase_prefix}-copy-planned",
            "object": destination,
            "sha256": digest,
            "size_bytes": size,
            "preflight": "absent",
        },
    )
    try:
        rc, out = rclone(
            [
                "copyto",
                str(local),
                destination,
                "--immutable",
                "--checksum",
                "--stats-one-line-json",
                "--stats",
                "1s",
            ],
            receipt=receipt,
            timeout=timeout,
        )
    except Exception as exc:
        _append_effect_journal(
            receipt,
            {
                "phase": f"{phase_prefix}-copy-returned",
                "object": destination,
                "command_rc": None,
                "ambiguity": True,
                "boundary_error": type(exc).__name__,
            },
        )
        raise
    _append_effect_journal(
        receipt,
        {
            "phase": f"{phase_prefix}-copy-returned",
            "object": destination,
            "command_rc": rc,
            "output_sha256": _sha256_bytes(out.encode("utf-8")),
            "ambiguity": True,
        },
    )
    created_once = rc == 0 and _copy_result_proves_one_create(out)
    first_state, first = _remote_object_stat(destination)
    first_identity = _remote_identity(first) if first_state == "present" and first is not None else None
    readback_rc: int | None = None
    second_identity: tuple[str, int] | None = None
    if created_once and first_identity is not None and first_identity[1] == size:
        readback_rc, _ = rclone(
            ["check", str(local), destination, "--one-way", "--download"],
            timeout=max(600, timeout),
        )
        second_state, second = _remote_object_stat(destination)
        if second_state == "present" and second is not None:
            second_identity = _remote_identity(second)
    ok = (
        created_once
        and first_identity is not None
        and first_identity[1] == size
        and readback_rc == 0
        and second_identity == first_identity
    )
    _append_effect_journal(
        receipt,
        {
            "phase": f"{phase_prefix}-verified" if ok else f"{phase_prefix}-unverified",
            "object": destination,
            "sha256": digest,
            "readback_rc": readback_rc,
            "remote_identity_hash": (
                _sha256_bytes(first_identity[0].encode("utf-8")) if first_identity is not None else None
            ),
            "ambiguity": not ok,
        },
    )
    return ok


def _journaled_probe_delete(
    destination: str,
    receipt: ApplyReceipt,
    *,
    phase_prefix: str,
) -> int | None:
    _append_effect_journal(
        receipt,
        {"phase": f"{phase_prefix}-cleanup-planned", "object": destination},
    )
    try:
        rc, out = rclone(["deletefile", destination], receipt=receipt, timeout=60)
    except Exception as exc:
        _append_effect_journal(
            receipt,
            {
                "phase": f"{phase_prefix}-cleanup-returned",
                "object": destination,
                "command_rc": None,
                "ambiguity": True,
                "boundary_error": type(exc).__name__,
            },
        )
        raise
    _append_effect_journal(
        receipt,
        {
            "phase": f"{phase_prefix}-cleanup-returned",
            "object": destination,
            "command_rc": rc,
            "output_sha256": _sha256_bytes(out.encode("utf-8")),
            "ambiguity": rc != 0,
        },
    )
    return rc


def gate_b(remote: str, workdir: Path, receipt: ApplyReceipt) -> bool:
    """Receipt-bound exact-object roundtrip; no namespace-wide cleanup is permitted."""

    _require_receipt(receipt, "receipt-bound roundtrip staging")
    if receipt.remote != remote or receipt.target != _target(remote):
        raise EffectRefused("roundtrip target does not match the apply receipt")
    payload = _probe_payload(remote, receipt.attempt_id)
    local = workdir / "roundtrip-probe.txt"
    local.write_bytes(payload)
    probe_path = f"{remote}:{receipt.object_set}/probes/roundtrip.txt"
    if not probe_path.startswith(f"{remote}:{receipt.object_set}/probes/"):
        raise EffectRefused("probe escaped the approved namespace")

    if not _immutable_remote_create(local, probe_path, receipt, phase_prefix="probe", timeout=90):
        # A failed create is ambiguous. Never retry or delete an object we did not exactly prove.
        return False
    rc, out = rclone(["cat", probe_path], timeout=60)
    delete_rc = _journaled_probe_delete(probe_path, receipt, phase_prefix="probe")
    return rc == 0 and out.encode("utf-8") == payload and delete_rc == 0


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _content_hash_bindings(value: Any, *, prefix: str = "source") -> dict[str, str]:
    """Return deterministic logical-name -> SHA-256 bindings from a source manifest."""

    bindings: dict[str, str] = {}

    def visit(current: Any, logical_name: str) -> None:
        if isinstance(current, dict):
            digest = current.get("sha256")
            if isinstance(digest, str):
                bindings[logical_name] = digest
            for key in sorted(current):
                child = current[key]
                if key.endswith("_sha256") and isinstance(child, str):
                    bindings[f"{logical_name}.{key}"] = child
                elif key != "sha256":
                    visit(child, f"{logical_name}.{key}")
        elif isinstance(current, list):
            for index, child in enumerate(current):
                visit(child, f"{logical_name}[{index}]")

    visit(value, prefix)
    return dict(sorted(bindings.items()))


def _plan_destinations(action: str, remote: str, attempt_id: str, payloads: list[dict[str, Any]]) -> list[str]:
    object_set = _object_set(attempt_id)
    destinations = [f"{remote}:{object_set}/probes/roundtrip.txt"]
    if action == "probe":
        return destinations
    destinations.append(f"{remote}:{object_set}/probes/kernel.tar.enc")
    for payload in payloads:
        name = payload.get("name")
        payload_type = payload.get("type")
        if not isinstance(name, str) or not name:
            continue
        if payload_type == "seal":
            destinations.append(f"{remote}:{object_set}/objects/{name}.tar.enc")
        elif payload_type == "kernel":
            destinations.extend(
                [
                    f"{remote}:{object_set}/objects/kernel.tar.enc",
                    f"{remote}:{object_set}/objects/RECOVERY-CARD.md",
                ]
            )
    destinations.append(f"{remote}:{object_set}/manifest-current.json")
    return list(dict.fromkeys(destinations))


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _copy_bound_file(source: Path, destination: Path, expected: dict[str, Any], receipt: ApplyReceipt) -> None:
    """Stream one no-follow source into private staging and prove its receipt-bound bytes."""

    _require_receipt(receipt, "receipt-bound file staging")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    destination_flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        source_fd = os.open(source, source_flags)
    except OSError as exc:
        raise EffectRefused(f"receipt-bound source became unsafe: {type(exc).__name__}") from exc
    destination_fd: int | None = None
    digest = hashlib.sha256()
    size = 0
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_nlink != 1:
            raise EffectRefused("receipt-bound source is no longer a single-link regular file")
        if (
            expected.get("device"),
            expected.get("inode"),
            expected.get("link_count"),
        ) != (source_stat.st_dev, source_stat.st_ino, source_stat.st_nlink):
            raise EffectRefused("receipt-bound source identity changed")
        destination_fd = os.open(destination, destination_flags, 0o400)
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                view = view[written:]
        os.fsync(destination_fd)
    except Exception:
        if destination_fd is not None:
            destination.unlink(missing_ok=True)
        raise
    finally:
        os.close(source_fd)
        if destination_fd is not None:
            os.close(destination_fd)

    actual_digest = "sha256:" + digest.hexdigest()
    if expected.get("kind") != "file" or expected.get("size") != size or expected.get("sha256") != actual_digest:
        destination.unlink(missing_ok=True)
        raise EffectRefused("staged source bytes do not match the apply receipt manifest")
    staged_meta = destination.lstat()
    if not stat.S_ISREG(staged_meta.st_mode) or staged_meta.st_nlink != 1:
        destination.unlink(missing_ok=True)
        raise EffectRefused("private staging is not a single-link regular file")


def _safe_manifest_relative(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise EffectRefused("receipt manifest contains an invalid relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        raise EffectRefused("receipt manifest relative path escaped private staging")
    return relative


def _content_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    kind = manifest.get("kind")
    if kind == "file":
        return {
            "kind": "file",
            "size": manifest.get("size"),
            "sha256": manifest.get("sha256"),
        }
    if kind == "dir":
        rows = []
        for entry in manifest.get("entries", []):
            if not isinstance(entry, dict):
                raise EffectRefused("manifest contains a malformed entry")
            row = {"path": entry.get("path"), "kind": entry.get("kind")}
            if entry.get("kind") == "file":
                row.update({"size": entry.get("size"), "sha256": entry.get("sha256")})
            rows.append(row)
        return {"kind": "dir", "entries": rows}
    return {"kind": kind}


def _snapshot_manifest_source(
    manifest: dict[str, Any],
    destination: Path,
    receipt: ApplyReceipt,
) -> Path | None:
    """Materialize only bytes named by a validated plan, then detach egress from live sources."""

    _require_receipt(receipt, "receipt-bound source snapshot")
    kind = manifest.get("kind")
    if kind == "missing":
        return None
    raw_source = manifest.get("path")
    if not isinstance(raw_source, str) or not raw_source:
        raise EffectRefused("receipt manifest omitted its source path")
    source = Path(raw_source)

    if kind == "file":
        _copy_bound_file(source, destination, manifest, receipt)
    elif kind == "dir":
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise EffectRefused("receipt directory manifest is malformed")
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        for entry in entries:
            if not isinstance(entry, dict):
                raise EffectRefused("receipt directory manifest contains a malformed entry")
            relative = _safe_manifest_relative(entry.get("path"))
            staged_path = destination.joinpath(*relative.parts)
            entry_kind = entry.get("kind")
            if entry_kind == "dir":
                staged_path.mkdir(parents=True, exist_ok=True, mode=0o700)
            elif entry_kind == "file":
                _copy_bound_file(source.joinpath(*relative.parts), staged_path, entry, receipt)
            else:
                raise EffectRefused("receipt manifest contains a refused source kind")
    else:
        raise EffectRefused("receipt manifest source is not snapshot-eligible")

    current, problems = _path_manifest(source)
    if problems or current != manifest:
        raise EffectRefused("live source changed while its receipt-bound snapshot was staged")
    staged_manifest, staged_problems = _path_manifest(destination)
    if staged_problems:
        raise EffectRefused("private staging produced an unsafe payload")
    expected_content = _content_manifest(manifest)
    staged_content = _content_manifest(staged_manifest)
    if staged_content != expected_content:
        raise EffectRefused("private staging does not match the apply receipt manifest")
    return destination


def _path_manifest(path: Path) -> tuple[dict[str, Any], list[str]]:
    """Hash a source without following symlinks; errors make an apply plan ineligible."""

    problems: list[str] = []
    display = str(path)
    try:
        metadata = path.lstat()
        mode = metadata.st_mode
    except FileNotFoundError:
        return {"path": display, "kind": "missing"}, problems
    except OSError as exc:
        return {"path": display, "kind": "unreadable"}, [f"{display}: {type(exc).__name__}"]

    if stat.S_ISLNK(mode):
        return {"path": display, "kind": "symlink"}, [f"{display}: symlink sources are refused"]
    if stat.S_ISREG(mode):
        if metadata.st_nlink != 1:
            return {
                "path": display,
                "kind": "hardlink",
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "link_count": metadata.st_nlink,
            }, [f"{display}: source must have exactly one hard link"]
        try:
            return {
                "path": display,
                "kind": "file",
                "size": metadata.st_size,
                "sha256": _file_hash(path),
                "device": metadata.st_dev,
                "inode": metadata.st_ino,
                "link_count": metadata.st_nlink,
            }, problems
        except OSError as exc:
            return {"path": display, "kind": "unreadable"}, [f"{display}: {type(exc).__name__}"]
    if not stat.S_ISDIR(mode):
        return {"path": display, "kind": "special"}, [f"{display}: special sources are refused"]

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(path.rglob("*"), key=lambda child: child.relative_to(path).as_posix())
    except OSError as exc:
        return {"path": display, "kind": "unreadable"}, [f"{display}: {type(exc).__name__}"]
    for child in children:
        relative = child.relative_to(path).as_posix()
        try:
            child_mode = child.lstat().st_mode
            if stat.S_ISLNK(child_mode):
                entries.append({"path": relative, "kind": "symlink"})
                problems.append(f"{display}/{relative}: symlink sources are refused")
            elif stat.S_ISDIR(child_mode):
                entries.append(
                    {
                        "path": relative,
                        "kind": "dir",
                        "device": child.lstat().st_dev,
                        "inode": child.lstat().st_ino,
                    }
                )
            elif stat.S_ISREG(child_mode):
                child_meta = child.lstat()
                if child_meta.st_nlink != 1:
                    entries.append(
                        {
                            "path": relative,
                            "kind": "hardlink",
                            "link_count": child_meta.st_nlink,
                        }
                    )
                    problems.append(f"{display}/{relative}: source must have exactly one hard link")
                    continue
                entries.append(
                    {
                        "path": relative,
                        "kind": "file",
                        "size": child_meta.st_size,
                        "sha256": _file_hash(child),
                        "device": child_meta.st_dev,
                        "inode": child_meta.st_ino,
                        "link_count": child_meta.st_nlink,
                    }
                )
            else:
                entries.append({"path": relative, "kind": "special"})
                problems.append(f"{display}/{relative}: special sources are refused")
        except OSError as exc:
            entries.append({"path": relative, "kind": "unreadable"})
            problems.append(f"{display}/{relative}: {type(exc).__name__}")
    return {
        "path": display,
        "kind": "dir",
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "entries": entries,
    }, problems


def _kernel_sources() -> tuple[list[dict[str, Any]], list[str], list[str]]:
    manifests: list[dict[str, Any]] = []
    included: list[str] = []
    problems: list[str] = []
    for candidate in KERNEL_CANDIDATES:
        path = Path(os.path.expanduser(candidate))
        manifest, found = _path_manifest(path)
        manifests.append(manifest)
        problems.extend(found)
        if manifest.get("kind") == "file":
            included.append(path.name)
        elif manifest.get("kind") == "missing":
            problems.append(f"{path}: required kernel source is missing")
    return manifests, included, problems


def _recovery_card(attempt_id: str, included: list[str]) -> str:
    return _mask(
        "# LIMEN Recovery Card (plaintext by design — contains ZERO secrets)\n\n"
        f"Custody attempt digest: `{_attempt_key(attempt_id)}`. "
        "Generated deterministically by the owner-installed HORREVM effector.\n\n"
        "## What exists where\n"
        "- GitHub org `organvm` — all repos incl. private `organvm/arca` (sealed private estate).\n"
        "- Backblaze — offsite backup of the Mac `/` and `/Volumes/Archive4T`.\n"
        "- Archive4T + T7Recovery — local archive SSOT + second copy.\n"
        "- Google Drive `limen-custody/` — sealed arca-vault snapshot + sealed inventories + this kernel.\n"
        "- Dropbox `limen-custody/` — this kernel + this card.\n\n"
        "## Restore order\n"
        "1. New machine: sign into GitHub; clone organvm/limen; read CLAUDE.md + his-hand-levers.json.\n"
        "2. ARCA key: macOS Keychain item `limen-arca-vault` (escrow per lever L-ARCA-KEY-ESCROW).\n"
        "3. `bash scripts/arca.sh unseal kernel.tar.enc <dest>` recovers this kernel's bundle.\n"
        "4. Backblaze restore for bulk; Drive `limen-custody/arca-vault.tar.enc` for the sealed private estate.\n\n"
        "## Kernel bundle contents\n- " + "\n- ".join(included or ["(none present at build time)"]) + "\n"
    )


def action_plan(action: str, remote: str, attempt_id: str) -> dict[str, Any]:
    """Create the deterministic, receipt-bindable plan without writing local or remote state."""

    config = _owner_config()
    if remote not in PAYLOADS:
        raise ReceiptError(f"unknown custody remote: {remote}")
    rail = config["rails"][remote]
    common = {
        "config_hash": config["config_hash"],
        "rail_id": rail["rail_id"],
        "tool_hashes": dict(config["tool_hashes"]),
        "object_set": _object_set(attempt_id),
    }
    if action == "probe":
        payload = _probe_payload(remote, attempt_id)
        source_manifest = {
            "kind": "generated-probe",
            "sha256": _sha256_bytes(payload),
            "size": len(payload),
        }
        return {
            "schema": PLAN_SCHEMA,
            "action": action,
            "target": _target(remote),
            "destination": _target(remote),
            "destinations": _plan_destinations(action, remote, attempt_id, []),
            "attempt_id": attempt_id,
            **common,
            "root_bindings": {},
            "payload_hash": _sha256_bytes(payload),
            "source_manifest_hash": _canonical_hash(source_manifest),
            "content_hashes": _content_hash_bindings(source_manifest),
            "hash_kind": "sha256-exact-probe-bytes",
            "problems": [],
        }
    if action != "push":
        raise ReceiptError(f"unsupported custody action: {action}")

    payloads: list[dict[str, Any]] = []
    problems: list[str] = []
    for spec in PAYLOADS[remote]:
        row: dict[str, Any] = {"name": spec.get("name"), "type": spec.get("type")}
        if spec.get("type") == "seal":
            source_value = spec.get("src")
            if not isinstance(source_value, str) or not source_value:
                problems.append(f"payload source is missing: {spec!r}")
            else:
                source, found = _path_manifest(Path(os.path.expanduser(source_value)))
                row["source"] = source
                problems.extend(found)
                if source.get("kind") == "missing":
                    problems.append(f"required payload source is missing: {spec['name']}")
        elif spec.get("type") == "kernel":
            sources, included, found = _kernel_sources()
            card = _recovery_card(attempt_id, included).encode("utf-8")
            row.update({"sources": sources, "recovery_card_sha256": _sha256_bytes(card)})
            problems.extend(found)
        else:
            problems.append(f"unknown payload spec: {spec!r}")
        payloads.append(row)

    manifest = {
        "schema": PLAN_SCHEMA,
        "action": action,
        "target": _target(remote),
        "attempt_id": attempt_id,
        "probe_payload_hash": _sha256_bytes(_probe_payload(remote, attempt_id)),
        "payloads": payloads,
    }
    probe_payload = _probe_payload(remote, attempt_id)
    source_manifest = {
        "probe": {"kind": "generated-probe", "sha256": _sha256_bytes(probe_payload), "size": len(probe_payload)},
        "payloads": payloads,
    }
    root_bindings = {
        str(row.get("name")): row.get("source")
        if row.get("type") == "seal"
        else row.get("sources")
        for row in payloads
    }
    return {
        **manifest,
        **common,
        "root_bindings": root_bindings,
        "destination": _target(remote),
        "destinations": _plan_destinations(action, remote, attempt_id, payloads),
        "payload_hash": _canonical_hash(manifest),
        "source_manifest_hash": _canonical_hash(source_manifest),
        "content_hashes": _content_hash_bindings(source_manifest),
        "hash_kind": "sha256-canonical-source-manifest",
        "problems": problems,
    }


def _parse_receipt_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ReceiptError(f"receipt {field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptError(f"receipt {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ReceiptError(f"receipt {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_receipt_window(value: dict[str, Any]) -> tuple[datetime, datetime]:
    current = now()
    issued_at = _parse_receipt_timestamp(value.get("issued_at"), "issued_at")
    expires_at = _parse_receipt_timestamp(value.get("expires_at"), "expires_at")
    if issued_at > current:
        raise ReceiptError("receipt was issued in the future")
    if expires_at <= current:
        raise ReceiptError("receipt has expired")
    if expires_at <= issued_at:
        raise ReceiptError("receipt expires before it was issued")
    if expires_at - issued_at > MAX_RECEIPT_LIFETIME:
        raise ReceiptError("receipt lifetime exceeds four hours")
    return issued_at, expires_at


def _assert_domus_owner_chain(path: Path, label: str, *, leaf_directory: bool = False) -> None:
    """Require every absolute authority component to remain in owner-only custody."""

    try:
        relative = path.relative_to(OWNER_PATH_ANCHOR)
    except ValueError as exc:
        raise ReceiptError(f"{label} is outside the fixed absolute authority anchor") from exc
    components = [
        OWNER_PATH_ANCHOR,
        *(
            OWNER_PATH_ANCHOR.joinpath(*relative.parts[:index])
            for index in range(1, len(relative.parts) + 1)
        ),
    ]
    for index, candidate in enumerate(components):
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise ReceiptError(f"{label} owner path is unavailable: {type(exc).__name__}") from exc
        is_leaf = index == len(components) - 1
        expected_directory = not is_leaf or leaf_directory
        if stat.S_ISLNK(metadata.st_mode):
            raise ReceiptError(f"{label} owner path must not contain symlinks")
        if expected_directory and not stat.S_ISDIR(metadata.st_mode):
            raise ReceiptError(f"{label} owner path component is not a directory")
        if not expected_directory and not stat.S_ISREG(metadata.st_mode):
            raise ReceiptError(f"{label} must be a regular file")
        if metadata.st_uid != OWNER_UID:
            raise ReceiptError(f"{label} must be owned by the Domus authority uid")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ReceiptError(f"{label} owner path must not be group/world writable")


def _open_trusted_input(
    path: Path,
    label: str,
    *,
    max_bytes: int,
    domus_custodied: bool = False,
) -> tuple[int, bytes]:
    """Open one authority input without following links and retain the fd across verification."""

    if domus_custodied:
        _assert_domus_owner_chain(path, label)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReceiptError(f"{label} is unreadable: {type(exc).__name__}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ReceiptError(f"{label} must be a single-link regular non-symlink file")
        if metadata.st_size <= 0 or metadata.st_size > max_bytes:
            raise ReceiptError(f"{label} must contain 1..{max_bytes} bytes")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ReceiptError(f"{label} must not be group/world writable")
        expected_uid = OWNER_UID if domus_custodied else (
            os.geteuid() if hasattr(os, "geteuid") else metadata.st_uid
        )
        if metadata.st_uid != expected_uid:
            custody = "Domus authority" if domus_custodied else "effective user"
            raise ReceiptError(f"{label} must be owned by the {custody}")
        raw = os.pread(fd, max_bytes + 1, 0)
        if len(raw) != metadata.st_size:
            raise ReceiptError(f"{label} changed while it was read")
        return fd, raw
    except Exception:
        os.close(fd)
        raise


def _trusted_file_hash(path: Path, label: str, *, max_bytes: int = 128 * 1024 * 1024) -> str:
    _assert_domus_owner_chain(path, label)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReceiptError(f"{label} is unreadable: {type(exc).__name__}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ReceiptError(f"{label} must be a single-link regular file")
        if not 1 <= metadata.st_size <= max_bytes:
            raise ReceiptError(f"{label} size is outside the owner bound")
        digest = hashlib.sha256()
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 1024 * 1024))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
        if remaining == 0:
            raise ReceiptError(f"{label} exceeds its owner size bound")
        return "sha256:" + digest.hexdigest()
    finally:
        os.close(fd)


def _load_owner_config() -> dict[str, Any]:
    fd, raw = _open_trusted_input(
        OWNER_CONFIG,
        "Domus HORREVM owner config",
        max_bytes=MAX_CONFIG_BYTES,
        domus_custodied=True,
    )
    os.close(fd)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReceiptError("Domus HORREVM owner config is not valid JSON") from exc
    expected = {
        "schema",
        "rclone_binary",
        "rclone_config",
        "arca_binary",
        "max_age_days",
        "rails",
        "sources",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ReceiptError("Domus HORREVM owner config fields do not match the schema")
    if value.get("schema") != CONFIG_SCHEMA:
        raise ReceiptError(f"Domus HORREVM owner config schema must be {CONFIG_SCHEMA}")

    for field, fixed in (
        ("rclone_binary", RCLONE),
        ("rclone_config", RCLONE_CONF),
        ("arca_binary", ARCA),
    ):
        raw_path = value.get(field)
        if not isinstance(raw_path, str) or Path(raw_path) != fixed:
            raise ReceiptError(f"Domus HORREVM {field} must equal the fixed deployed path")
    max_age = value.get("max_age_days")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or not 1 <= max_age <= 365:
        raise ReceiptError("Domus HORREVM max_age_days must be an integer in 1..365")
    rails = value.get("rails")
    if not isinstance(rails, dict) or set(rails) != set(PAYLOADS):
        raise ReceiptError("Domus HORREVM owner config must define every and only the fixed custody rails")
    normalized_rails: dict[str, dict[str, Any]] = {}
    for remote in sorted(PAYLOADS):
        row = rails.get(remote)
        if not isinstance(row, dict) or set(row) != {"rail_id", "budget_bytes"}:
            raise ReceiptError(f"Domus HORREVM rail {remote} fields are invalid")
        rail_id = row.get("rail_id")
        budget = row.get("budget_bytes")
        if not isinstance(rail_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", rail_id):
            raise ReceiptError(f"Domus HORREVM rail {remote} rail_id must be a sha256 identity")
        if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 100 * 10**9:
            raise ReceiptError(f"Domus HORREVM rail {remote} budget_bytes is outside 1..100GB")
        normalized_rails[remote] = {"rail_id": rail_id, "budget_bytes": budget}
    sources = value.get("sources")
    if not isinstance(sources, dict) or set(sources) != {"arca-vault", "corpus-inventory", "kernel"}:
        raise ReceiptError("Domus HORREVM sources must define arca-vault, corpus-inventory, and kernel")
    normalized_sources: dict[str, Any] = {}
    for name in ("arca-vault", "corpus-inventory"):
        raw_path = sources.get(name)
        if not isinstance(raw_path, str) or not raw_path.startswith("/"):
            raise ReceiptError(f"Domus HORREVM source {name} must be an absolute path")
        path = Path(raw_path)
        if path != path.resolve():
            raise ReceiptError(f"Domus HORREVM source {name} must be canonical")
        normalized_sources[name] = str(path)
    kernel = sources.get("kernel")
    if not isinstance(kernel, list) or not kernel:
        raise ReceiptError("Domus HORREVM kernel sources must be a non-empty list")
    normalized_kernel: list[str] = []
    for raw_path in kernel:
        if not isinstance(raw_path, str) or not raw_path.startswith("/"):
            raise ReceiptError("Domus HORREVM kernel source paths must be absolute")
        path = Path(raw_path)
        if path != path.resolve():
            raise ReceiptError("Domus HORREVM kernel source paths must be canonical")
        normalized_kernel.append(str(path))
    if len(normalized_kernel) != len(set(normalized_kernel)):
        raise ReceiptError("Domus HORREVM kernel source paths must be unique")
    normalized_sources["kernel"] = normalized_kernel
    return {
        "schema": CONFIG_SCHEMA,
        "config_hash": _sha256_bytes(raw),
        "max_age_days": max_age,
        "rails": normalized_rails,
        "sources": normalized_sources,
        "tool_hashes": {
            "rclone": _trusted_file_hash(RCLONE, "Domus rclone binary"),
            "rclone_config": _trusted_file_hash(RCLONE_CONF, "Domus rclone config", max_bytes=MAX_CONFIG_BYTES),
            "arca": _trusted_file_hash(ARCA, "Domus ARCA effector"),
        },
    }


def _activate_owner_config() -> dict[str, Any]:
    global ACTIVE_CONFIG, KERNEL_CANDIDATES
    ACTIVE_CONFIG = _load_owner_config()
    KERNEL_CANDIDATES = list(ACTIVE_CONFIG["sources"]["kernel"])
    for remote, payloads in PAYLOADS.items():
        for spec in payloads:
            if spec.get("type") == "seal":
                spec["src"] = ACTIVE_CONFIG["sources"][spec["name"]]
    return ACTIVE_CONFIG


def _owner_config() -> dict[str, Any]:
    if ACTIVE_CONFIG is None:
        raise ReceiptError("fixed Domus HORREVM owner config is not activated")
    return ACTIVE_CONFIG


def _verify_authority_signature(
    receipt_raw: bytes,
    *,
    signer: str,
    signature_path: Path,
) -> str:
    """Verify exact receipt bytes against the pinned Domus trust root without temp files."""

    if not AUTHORIZED_PRINCIPAL.fullmatch(signer):
        raise ReceiptError("receipt authorized_by is not a safe OpenSSH principal")
    allowed_fd, allowed_raw = _open_trusted_input(
        OWNER_ALLOWED_SIGNERS,
        "pinned allowed-signers owner",
        max_bytes=MAX_TRUST_FILE_BYTES,
        domus_custodied=True,
    )
    signature_fd: int | None = None
    try:
        try:
            allowed_text = allowed_raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReceiptError("allowed-signers owner is not UTF-8") from exc
        if not any(line.strip() and not line.lstrip().startswith("#") for line in allowed_text.splitlines()):
            raise ReceiptError("allowed-signers owner contains no principals")
        signature_fd, signature_raw = _open_trusted_input(
            signature_path, "receipt signature", max_bytes=MAX_TRUST_FILE_BYTES
        )
        if not signature_raw.startswith(b"-----BEGIN SSH SIGNATURE-----\n"):
            raise ReceiptError("receipt signature is not an OpenSSH signature")
        try:
            verified = subprocess.run(
                [
                    str(SSH_KEYGEN),
                    "-Y",
                    "verify",
                    "-f",
                    f"/dev/fd/{allowed_fd}",
                    "-I",
                    signer,
                    "-n",
                    SIGNED_RECEIPT_NAMESPACE,
                    "-s",
                    f"/dev/fd/{signature_fd}",
                ],
                input=receipt_raw,
                capture_output=True,
                timeout=10,
                pass_fds=(allowed_fd, signature_fd),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ReceiptError("OpenSSH receipt verification is unavailable") from exc
        if verified.returncode != 0:
            raise ReceiptError("receipt signature is forged, mismatched, or untrusted")
        return _sha256_bytes(allowed_raw)
    finally:
        os.close(allowed_fd)
        if signature_fd is not None:
            os.close(signature_fd)


def load_apply_receipt(
    path: Path,
    signature_path: Path,
    expected_action: str,
    *,
    expected_attempt_id: str | None = None,
) -> tuple[ApplyReceipt, dict[str, Any]]:
    """Read once and validate the signed authority plus every binding before any mutation."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReceiptError(f"receipt is unreadable: {type(exc).__name__}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ReceiptError("receipt must be a single-link regular non-symlink file")
        if metadata.st_size > MAX_RECEIPT_BYTES:
            raise ReceiptError("receipt exceeds 64 KiB")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ReceiptError("receipt must not be group/world writable")
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise ReceiptError("receipt must be owned by the effective user")
        chunks: list[bytes] = []
        remaining = MAX_RECEIPT_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 8192))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_RECEIPT_BYTES:
            raise ReceiptError("receipt exceeds 64 KiB")
        value = json.loads(raw)
    except ReceiptError:
        raise
    except (OSError, ValueError) as exc:
        raise ReceiptError(f"receipt is unreadable: {type(exc).__name__}") from exc
    finally:
        os.close(fd)
    if not isinstance(value, dict) or value.get("schema") != RECEIPT_SCHEMA:
        raise ReceiptError(f"receipt schema must be {RECEIPT_SCHEMA}")
    if value.get("authorized") is not True:
        raise ReceiptError("receipt must explicitly set authorized=true")
    authorized_by = value.get("authorized_by")
    if not isinstance(authorized_by, str) or not authorized_by.strip():
        raise ReceiptError("receipt must name authorized_by")
    expected_fields = {
        "schema",
        "authorized",
        "authorized_by",
        "action",
        "destination",
        "destinations",
        "source_manifest_hash",
        "content_hashes",
        "payload_hash",
        "config_hash",
        "rail_id",
        "tool_hashes",
        "root_bindings",
        "object_set",
        "issued_at",
        "expires_at",
        "attempt_id",
    }
    if set(value) != expected_fields:
        raise ReceiptError("receipt fields do not match the signed authority schema")
    trust_root_hash = _verify_authority_signature(
        raw,
        signer=authorized_by,
        signature_path=signature_path,
    )

    action = value.get("action")
    target = value.get("destination")
    destinations = value.get("destinations")
    source_manifest_hash = value.get("source_manifest_hash")
    content_hashes = value.get("content_hashes")
    payload_hash = value.get("payload_hash")
    config_hash = value.get("config_hash")
    rail_id = value.get("rail_id")
    tool_hashes = value.get("tool_hashes")
    root_bindings = value.get("root_bindings")
    object_set = value.get("object_set")
    attempt_id = value.get("attempt_id")
    if action != expected_action:
        raise ReceiptError(f"receipt action {action!r} does not match {expected_action!r}")
    if not isinstance(target, str):
        raise ReceiptError("receipt target must be a string")
    remotes = {f"{remote}:{CUSTODY_DIR}": remote for remote in PAYLOADS}
    remote = remotes.get(target)
    if not remote:
        raise ReceiptError("receipt target is not one exact configured custody rail")
    if not isinstance(attempt_id, str) or not attempt_id or len(attempt_id) > 256:
        raise ReceiptError("receipt attempt_id must be 1..256 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in attempt_id):
        raise ReceiptError("receipt attempt_id contains control characters")
    if expected_attempt_id is not None and attempt_id != expected_attempt_id:
        raise ReceiptError("receipt attempt_id does not match --attempt-id")
    if not isinstance(payload_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", payload_hash):
        raise ReceiptError("receipt payload_hash must be sha256:<64 lowercase hex>")
    if not isinstance(source_manifest_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", source_manifest_hash):
        raise ReceiptError("receipt source_manifest_hash must be sha256:<64 lowercase hex>")
    if not isinstance(content_hashes, dict) or not all(
        isinstance(name, str) and name and isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        for name, digest in content_hashes.items()
    ):
        raise ReceiptError("receipt content_hashes must map logical names to sha256 digests")
    if not isinstance(config_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", config_hash):
        raise ReceiptError("receipt config_hash must be a sha256 digest")
    if not isinstance(rail_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", rail_id):
        raise ReceiptError("receipt rail_id must be a sha256 identity")
    if not isinstance(tool_hashes, dict) or not all(
        isinstance(name, str)
        and isinstance(digest, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        for name, digest in tool_hashes.items()
    ):
        raise ReceiptError("receipt tool_hashes must bind every deployed tool")
    if not isinstance(root_bindings, dict):
        raise ReceiptError("receipt root_bindings must be an object")
    if not isinstance(object_set, str) or object_set != _object_set(attempt_id):
        raise ReceiptError("receipt object_set must be the immutable attempt-scoped set")
    if (
        not isinstance(destinations, list)
        or not destinations
        or not all(isinstance(destination, str) and destination for destination in destinations)
    ):
        raise ReceiptError("receipt destinations must name exact remote objects")
    _issued_at, expires_at = _validate_receipt_window(value)

    plan = action_plan(action, remote, attempt_id)
    if plan["problems"]:
        raise ReceiptError("payload plan is unsafe: " + "; ".join(plan["problems"]))
    if payload_hash != plan["payload_hash"]:
        raise ReceiptError("receipt payload_hash does not match the current payload plan")
    if source_manifest_hash != plan["source_manifest_hash"]:
        raise ReceiptError("receipt source_manifest_hash does not match the current sources")
    if content_hashes != plan["content_hashes"]:
        raise ReceiptError("receipt content_hashes do not match the current source bytes")
    if destinations != plan["destinations"]:
        raise ReceiptError("receipt destinations do not match the exact custody objects")
    for field, supplied in (
        ("config_hash", config_hash),
        ("rail_id", rail_id),
        ("tool_hashes", tool_hashes),
        ("root_bindings", root_bindings),
        ("object_set", object_set),
    ):
        if supplied != plan[field]:
            raise ReceiptError(f"receipt {field} does not match fixed owner evidence")
    receipt = ApplyReceipt(
        action=action,
        target=target,
        payload_hash=payload_hash,
        source_manifest_hash=source_manifest_hash,
        content_hashes=dict(content_hashes),
        destinations=tuple(destinations),
        expires_at=expires_at,
        attempt_id=attempt_id,
        receipt_hash=_sha256_bytes(raw),
        signer=authorized_by,
        trust_root_hash=trust_root_hash,
        remote=remote,
        config_hash=config_hash,
        rail_id=rail_id,
        tool_hashes=dict(tool_hashes),
        root_bindings=dict(root_bindings),
        object_set=object_set,
    )
    return receipt, plan


def _require_domus_installed_effector() -> None:
    actual = Path(__file__).resolve()
    if actual != OWNER_EFFECTOR:
        raise ReceiptError("apply is available only from the fixed Domus-installed effector")
    _assert_domus_owner_chain(actual, "Domus HORREVM effector")


def _consume_receipt(receipt: ApplyReceipt) -> None:
    """Reserve the signed receipt in fixed Domus custody before any apply subprocess."""

    _require_receipt(receipt, "receipt consumption")
    if hasattr(os, "geteuid") and os.geteuid() != OWNER_UID:
        raise ReceiptError("receipt consumption requires the Domus authority execution identity")
    _assert_domus_owner_chain(
        OWNER_CONSUMED_DIR,
        "Domus receipt-consumption registry",
        leaf_directory=True,
    )
    digest = _attempt_key(receipt.attempt_id).removeprefix("sha256:")
    marker_name = f"{digest}.json"
    payload = {
        "schema": "limen.horrevm.consumed_receipt.v1",
        "receipt_hash": receipt.receipt_hash,
        "attempt_id_hash": _attempt_key(receipt.attempt_id),
        "action": receipt.action,
        "target": receipt.target,
        "payload_hash": receipt.payload_hash,
        "source_manifest_hash": receipt.source_manifest_hash,
        "config_hash": receipt.config_hash,
        "rail_id": receipt.rail_id,
        "tool_hashes": receipt.tool_hashes,
        "root_bindings_hash": _canonical_hash(receipt.root_bindings),
        "object_set": receipt.object_set,
        "trust_root_hash": receipt.trust_root_hash,
        "consumed_at": _iso(now()),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    directory_fd: int | None = None
    marker_fd: int | None = None
    try:
        try:
            directory_flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            directory_fd = os.open(OWNER_CONSUMED_DIR, directory_flags)
            directory_metadata = os.fstat(directory_fd)
            if directory_metadata.st_uid != OWNER_UID or directory_metadata.st_mode & (
                stat.S_IWGRP | stat.S_IWOTH
            ):
                raise ReceiptError("Domus receipt-consumption registry lost owner custody")
            marker_fd = os.open(marker_name, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError as exc:
            raise ReceiptError("receipt attempt_id was already consumed") from exc
        except OSError as exc:
            raise ReceiptError(f"receipt replay marker could not be created: {type(exc).__name__}") from exc
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(marker_fd, view)
                view = view[written:]
            os.fsync(marker_fd)
            os.fsync(directory_fd)
        except OSError as exc:
            raise ReceiptError(f"receipt replay marker could not be made durable: {type(exc).__name__}") from exc
    finally:
        if marker_fd is not None:
            os.close(marker_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _attempt_journal_name(receipt: ApplyReceipt) -> str:
    return _attempt_key(receipt.attempt_id).removeprefix("sha256:") + ".json"


def _append_effect_journal(receipt: ApplyReceipt, event: dict[str, Any]) -> None:
    """Append one durable owner-custodied effect fact before/after every remote mutation."""

    _require_receipt(receipt, "effect journal publication")
    _assert_domus_owner_chain(
        OWNER_CONSUMED_DIR,
        "Domus HORREVM effect journal registry",
        leaf_directory=True,
    )
    directory_fd = os.open(
        OWNER_CONSUMED_DIR,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    journal_fd: int | None = None
    try:
        flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        journal_fd = os.open(_attempt_journal_name(receipt), flags, dir_fd=directory_fd)
        metadata = os.fstat(journal_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != OWNER_UID
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ReceiptError("HORREVM effect journal lost owner custody")
        payload = {
            "schema": "limen.horrevm.effect_event.v1",
            "attempt_id_hash": _attempt_key(receipt.attempt_id),
            "receipt_hash": receipt.receipt_hash,
            "recorded_at": _iso(now()),
            **event,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        view = memoryview(encoded)
        while view:
            written = os.write(journal_fd, view)
            if written <= 0:
                raise OSError("short write to effect journal")
            view = view[written:]
        os.fsync(journal_fd)
        os.fsync(directory_fd)
    finally:
        if journal_fd is not None:
            os.close(journal_fd)
        os.close(directory_fd)


def _acquire_state_lock() -> tuple[int, int]:
    """Serialize state publication across distinct owner-authorized attempts."""

    _assert_domus_owner_chain(
        OWNER_CONSUMED_DIR,
        "Domus HORREVM apply lock registry",
        leaf_directory=True,
    )
    directory_fd = os.open(
        OWNER_CONSUMED_DIR,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        lock_fd = os.open(".active-apply.lock", flags, 0o600, dir_fd=directory_fd)
    except FileExistsError as exc:
        os.close(directory_fd)
        raise ReceiptError("another HORREVM apply owns the durable state lock") from exc
    os.write(lock_fd, f"{os.getpid()}\n".encode("ascii"))
    os.fsync(lock_fd)
    os.fsync(directory_fd)
    return directory_fd, lock_fd


def _release_state_lock(directory_fd: int, lock_fd: int) -> None:
    os.close(lock_fd)
    try:
        os.unlink(".active-apply.lock", dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def payload_bytes(paths: list[Path]) -> int:
    total = 0
    for p in paths:
        if p.is_file():
            total += p.stat().st_size
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
    return total


def _ciphertext_hash(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EffectRefused(f"ciphertext could not be opened safely: {type(exc).__name__}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise EffectRefused("ciphertext must be a single-link regular non-symlink file")
        if metadata.st_size < 16:
            raise EffectRefused("ciphertext is too short to contain an ARCA envelope")
        header = os.pread(fd, 8, 0)
        if header != b"Salted__":
            raise EffectRefused("ciphertext lacks the ARCA OpenSSL salted envelope header")
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
        return "sha256:" + digest.hexdigest()
    finally:
        os.close(fd)


def _verify_unsealed_manifest(
    ciphertext: Path,
    *,
    expected_name: str,
    expected_manifest: dict[str, Any],
    verification_root: Path,
) -> None:
    _ciphertext_hash(ciphertext)
    verification_root.mkdir(mode=0o700)
    rc, _ = run(
        ["/bin/bash", str(ARCA), "unseal", str(ciphertext), str(verification_root)],
        300,
    )
    if rc != 0:
        raise EffectRefused("ARCA unseal verification failed")
    children = list(verification_root.iterdir())
    if [child.name for child in children] != [expected_name]:
        raise EffectRefused("ARCA unseal produced an unexpected root set")
    actual, problems = _path_manifest(verification_root / expected_name)
    if problems or _content_manifest(actual) != _content_manifest(expected_manifest):
        raise EffectRefused("ARCA unseal manifest does not match the receipt-bound plaintext")


def seal(src: Path, out_enc: Path, receipt: ApplyReceipt | None = None) -> bool:
    _require_receipt(receipt, "local sealing")
    _assert_domus_owner_chain(ARCA, "Domus ARCA effector")
    source_manifest, source_problems = _path_manifest(src)
    if source_problems or source_manifest.get("kind") not in {"file", "dir"}:
        raise EffectRefused("receipt-bound plaintext became unsafe before sealing")
    rc, output = run(["/bin/bash", str(ARCA), "seal", str(src), str(out_enc)], 300)
    if rc != 0:
        say(f"  seal failed for {src.name}: {output.strip()[-120:]}")
        return False
    verify_root = out_enc.parent / f".verify-{out_enc.name}-{uuid.uuid4().hex}"
    try:
        _verify_unsealed_manifest(
            out_enc,
            expected_name=src.name,
            expected_manifest=source_manifest,
            verification_root=verify_root,
        )
        VERIFIED_CIPHERTEXT_MANIFESTS[str(out_enc.resolve())] = {
            "expected_name": src.name,
            "manifest": _content_manifest(source_manifest),
            "ciphertext_sha256": _ciphertext_hash(out_enc),
        }
        return True
    except EffectRefused as exc:
        out_enc.unlink(missing_ok=True)
        say(f"  seal verification failed for {src.name}: {exc}")
        return False


def build_kernel(
    workdir: Path,
    receipt: ApplyReceipt | None = None,
    source_manifests: list[dict[str, Any]] | None = None,
) -> Path | None:
    """Assemble the continuity kernel: recovery card (plaintext, zero secrets) + sealed bundle."""
    receipt = _require_receipt(receipt, "kernel staging")
    if source_manifests is None:
        source_manifests, _included, problems = _kernel_sources()
        if problems:
            raise EffectRefused("kernel source plan is unsafe")
    bundle = workdir / "kernel-src"
    bundle.mkdir(parents=True, exist_ok=True)
    included: list[str] = []
    for manifest in source_manifests:
        if not isinstance(manifest, dict):
            raise EffectRefused("kernel source manifest is malformed")
        if manifest.get("kind") == "missing":
            continue
        raw_source = manifest.get("path")
        if not isinstance(raw_source, str) or not raw_source:
            raise EffectRefused("kernel source manifest omitted its path")
        name = Path(raw_source).name
        if not name or name in included:
            raise EffectRefused("kernel source names are empty or collide")
        _snapshot_manifest_source(manifest, bundle / name, receipt)
        included.append(name)
    card = workdir / "RECOVERY-CARD.md"
    _require_receipt(receipt, "recovery-card staging")
    card.write_text(_recovery_card(receipt.attempt_id, included), encoding="utf-8")
    out_enc = workdir / "kernel.tar.enc"
    if not seal(bundle, out_enc, receipt):
        return None
    return workdir


def _begin_attempt(state: dict, receipt: ApplyReceipt) -> bool:
    attempts = state.setdefault("attempts", {})
    key = _attempt_key(receipt.attempt_id)
    if not isinstance(attempts, dict) or key in attempts or receipt.attempt_id in attempts:
        return False
    attempts[key] = {
        "attempt_id_hash": key,
        "action": receipt.action,
        "target": receipt.target,
        "payload_hash": receipt.payload_hash,
        "receipt_hash": receipt.receipt_hash,
        "expires_at": _iso(receipt.expires_at),
        "started_at": _iso(now()),
        "status": "started",
    }
    if save_state(state, receipt):
        return True
    attempts.pop(key, None)
    return False


def _finish_attempt(state: dict, receipt: ApplyReceipt, status_value: str) -> bool:
    attempts = state.get("attempts", {})
    row = attempts.get(_attempt_key(receipt.attempt_id)) if isinstance(attempts, dict) else None
    if not isinstance(row, dict):
        return False
    row.update({"status": status_value, "completed_at": _iso(now())})
    return save_state(state, receipt)


def _stage_payloads(
    remote: str,
    workdir: Path,
    receipt: ApplyReceipt | None = None,
    plan: dict[str, Any] | None = None,
) -> tuple[list[tuple[Path, str]], Path | None]:
    receipt = _require_receipt(receipt, "payload staging")
    plan = plan or action_plan("push", remote, receipt.attempt_id)
    if plan.get("problems") or plan.get("payload_hash") != receipt.payload_hash:
        raise EffectRefused("payload staging plan does not match the apply receipt")
    planned_payloads = plan.get("payloads")
    if not isinstance(planned_payloads, list) or len(planned_payloads) != len(PAYLOADS[remote]):
        raise EffectRefused("payload staging plan shape is invalid")
    staged: list[tuple[Path, str]] = []
    kernel_dir: Path | None = None
    snapshots = workdir / "receipt-bound-snapshots"
    snapshots.mkdir(mode=0o700)
    for spec, planned in zip(PAYLOADS[remote], planned_payloads, strict=True):
        if (
            not isinstance(planned, dict)
            or planned.get("name") != spec.get("name")
            or planned.get("type") != spec.get("type")
        ):
            raise EffectRefused("payload staging plan no longer matches the configured payload")
        if spec["type"] == "seal":
            source_manifest = planned.get("source")
            if not isinstance(source_manifest, dict):
                raise EffectRefused("sealed payload omitted its receipt-bound source manifest")
            snapshot = _snapshot_manifest_source(source_manifest, snapshots / spec["name"], receipt)
            if snapshot is not None:
                enc = workdir / f"{spec['name']}.tar.enc"
                if not seal(snapshot, enc, receipt):
                    return [], None
                staged.append((enc, enc.name))
        elif spec["type"] == "kernel":
            source_manifests = planned.get("sources")
            if not isinstance(source_manifests, list):
                raise EffectRefused("kernel omitted its receipt-bound source manifests")
            kernel_dir = kernel_dir or build_kernel(workdir, receipt, source_manifests)
            if not kernel_dir:
                return [], None
            expected_card_hash = planned.get("recovery_card_sha256")
            if expected_card_hash != _file_hash(kernel_dir / "RECOVERY-CARD.md"):
                raise EffectRefused("recovery card does not match the apply receipt")
            staged.append((kernel_dir / "kernel.tar.enc", "kernel.tar.enc"))
            staged.append((kernel_dir / "RECOVERY-CARD.md", "RECOVERY-CARD.md"))
    return staged, (kernel_dir / "kernel.tar.enc" if kernel_dir else None)


def restore_test(
    remote: str,
    workdir: Path,
    kernel: Path | None,
    receipt: ApplyReceipt,
) -> bool:
    """Preflight Gate D in the receipt namespace; failure occurs before final payload copy."""

    _require_receipt(receipt, "restore-proof staging")
    if not kernel or not kernel.is_file():
        return False
    probe_path = f"{remote}:{receipt.object_set}/probes/kernel.tar.enc"
    if not probe_path.startswith(f"{remote}:{receipt.object_set}/probes/"):
        raise EffectRefused("restore probe escaped the approved namespace")
    pulled = workdir / "pulled-kernel.tar.enc"
    uploaded = False
    copy_ok = unseal_ok = False
    delete_rc: int | None = None
    try:
        _assert_domus_owner_chain(ARCA, "Domus ARCA effector")
        uploaded = _immutable_remote_create(
            kernel,
            probe_path,
            receipt,
            phase_prefix="restore-probe",
            timeout=600,
        )
        if not uploaded:
            return False
        _append_effect_journal(
            receipt,
            {
                "phase": "restore-pull-planned",
                "object": probe_path,
                "local_target_hash": _sha256_bytes(str(pulled).encode("utf-8")),
            },
        )
        try:
            rc, pull_out = rclone(["copyto", probe_path, str(pulled)], receipt=receipt, timeout=600)
        except Exception as exc:
            _append_effect_journal(
                receipt,
                {
                    "phase": "restore-pull-returned",
                    "object": probe_path,
                    "command_rc": None,
                    "ambiguity": True,
                    "boundary_error": type(exc).__name__,
                },
            )
            raise
        _append_effect_journal(
            receipt,
            {
                "phase": "restore-pull-returned",
                "object": probe_path,
                "command_rc": rc,
                "output_sha256": _sha256_bytes(pull_out.encode("utf-8")),
                "ambiguity": rc != 0,
            },
        )
        expected = VERIFIED_CIPHERTEXT_MANIFESTS.get(str(kernel.resolve()))
        copy_ok = (
            rc == 0
            and expected is not None
            and _ciphertext_hash(pulled) == expected["ciphertext_sha256"]
        )
        if copy_ok:
            out_dir = workdir / "restore-check"
            try:
                _verify_unsealed_manifest(
                    pulled,
                    expected_name=str(expected["expected_name"]),
                    expected_manifest=dict(expected["manifest"]),
                    verification_root=out_dir,
                )
                unseal_ok = True
            except EffectRefused:
                unseal_ok = False
    finally:
        if uploaded:
            delete_rc = _journaled_probe_delete(
                probe_path,
                receipt,
                phase_prefix="restore-probe",
            )
    ok = copy_ok and unseal_ok and delete_rc == 0
    say(f"  {remote}: restore-proof {'PASSED' if ok else 'FAILED'}")
    return ok


def _safe_regular_hash(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EffectRefused(f"staged object could not be opened safely: {type(exc).__name__}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise EffectRefused("staged object must be a single-link regular file")
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
        return "sha256:" + digest.hexdigest(), metadata.st_size
    finally:
        os.close(fd)


def _write_exclusive_json(path: Path, value: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o400)
    try:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_payloads(remote: str, staged: list[tuple[Path, str]], receipt: ApplyReceipt) -> bool:
    manifest_objects: list[dict[str, Any]] = []
    for local, subpath in staged:
        if not local.is_file():
            raise EffectRefused("HORREVM final objects must be materialized regular files")
        if subpath.endswith(".enc"):
            digest = _ciphertext_hash(local)
            verified = VERIFIED_CIPHERTEXT_MANIFESTS.get(str(local.resolve()))
            if verified is None or verified.get("ciphertext_sha256") != digest:
                raise EffectRefused("ciphertext lacks an exact local unseal-manifest proof")
            size = local.lstat().st_size
        else:
            digest, size = _safe_regular_hash(local)
        destination = f"{remote}:{receipt.object_set}/objects/{subpath}"
        if destination not in receipt.destinations:
            raise EffectRefused("final object destination is outside the signed immutable set")
        ok = _immutable_remote_create(
            local,
            destination,
            receipt,
            phase_prefix="object",
            timeout=1800,
        )
        say(f"  {remote}: {local.name} {'shipped+verified' if ok else 'FAILED'}")
        if not ok:
            return False
        manifest_objects.append(
            {
                "object": destination,
                "sha256": digest,
                "size_bytes": size,
            }
        )
    if not manifest_objects:
        return False

    manifest_path = staged[0][0].parent / "manifest-current.json"
    manifest = {
        "schema": "limen.horrevm.immutable_object_set.v1",
        "attempt_id_hash": _attempt_key(receipt.attempt_id),
        "object_set": receipt.object_set,
        "config_hash": receipt.config_hash,
        "rail_id": receipt.rail_id,
        "payload_hash": receipt.payload_hash,
        "source_manifest_hash": receipt.source_manifest_hash,
        "objects": manifest_objects,
    }
    _write_exclusive_json(manifest_path, manifest)
    manifest_destination = f"{remote}:{receipt.object_set}/manifest-current.json"
    if manifest_destination not in receipt.destinations:
        raise EffectRefused("manifest-current destination is outside the signed immutable set")
    ok = _immutable_remote_create(
        manifest_path,
        manifest_destination,
        receipt,
        phase_prefix="manifest-current",
        timeout=600,
    )
    return ok


def _apply_action_locked(
    action: str,
    receipt_path: Path,
    signature_path: Path,
    *,
    expected_attempt_id: str | None = None,
) -> int:
    try:
        _require_domus_installed_effector()
        _require_apply_valve("HORREVM apply")
        receipt, plan = load_apply_receipt(
            receipt_path,
            signature_path,
            action,
            expected_attempt_id=expected_attempt_id,
        )
    except (EffectRefused, ReceiptError) as exc:
        say(f"HORREVM custody REFUSED: {exc}")
        return 2

    state = load_state()
    if state.get("_state_error"):
        say(f"HORREVM custody REFUSED: {state['_state_error']}")
        return 2
    attempts = state.get("attempts", {})
    if isinstance(attempts, dict) and (_attempt_key(receipt.attempt_id) in attempts or receipt.attempt_id in attempts):
        say(f"HORREVM custody REFUSED: attempt_id {receipt.attempt_id!r} was already consumed")
        return 2
    rail = _rail(state, receipt.remote, create=True)
    if action == "push":
        last_verified = rail.get("last_verified_push")
        if isinstance(last_verified, str):
            try:
                if now() - datetime.fromisoformat(last_verified.replace("Z", "+00:00")) < timedelta(
                    hours=MIN_PUSH_INTERVAL_H
                ):
                    say(f"self-throttled (<{MIN_PUSH_INTERVAL_H}h since the last verified push); receipt not consumed")
                    return 0
            except ValueError:
                pass

    try:
        _consume_receipt(receipt)
    except (EffectRefused, ReceiptError) as exc:
        say(f"HORREVM custody REFUSED: {exc}")
        return 2
    if parked():
        say(f"HORREVM custody PARKED on {LEVER} — exact receipt consumed; no remote writes")
        return 2

    about = gate_a(receipt.remote)
    if not about.get("token_ok"):
        say(f"  {receipt.remote}: token dead — no attempt or remote write; re-consent via {LEVER}")
        return 1
    rail.update(about)
    if not _begin_attempt(state, receipt):
        say("HORREVM custody REFUSED: could not durably reserve the receipt attempt")
        return 2

    try:
        _assert_domus_owner_chain(OWNER_APPLY_TMP, "Domus HORREVM apply temp root", leaf_directory=True)
        with tempfile.TemporaryDirectory(prefix="horrevm-", dir=str(OWNER_APPLY_TMP)) as td:
            workdir = Path(td)
            rail["probe_roundtrip_ok"] = gate_b(receipt.remote, workdir, receipt)
            if not rail["probe_roundtrip_ok"]:
                rail["verify_ok"] = False
                _finish_attempt(state, receipt, "failed_roundtrip")
                say(f"  {receipt.remote}: roundtrip FAILED — payload copy blocked")
                return 1
            if action == "probe":
                rail["last_probe"] = _iso(now())
                if not _finish_attempt(state, receipt, "probe_verified"):
                    return 1
                return 0

            staged, kernel = _stage_payloads(receipt.remote, workdir, receipt, plan)
            if not staged or not kernel:
                rail["verify_ok"] = False
                _finish_attempt(state, receipt, "failed_staging")
                return 1

            # Close the receipt/source race before any final-destination copy.
            current_plan = action_plan(action, receipt.remote, receipt.attempt_id)
            if current_plan["problems"] or current_plan["payload_hash"] != receipt.payload_hash:
                rail["verify_ok"] = False
                _finish_attempt(state, receipt, "failed_payload_changed")
                say(f"  {receipt.remote}: payload changed after receipt validation — copy blocked")
                return 1

            size = payload_bytes([source for source, _ in staged])
            cap = _owner_config()["rails"][receipt.remote]["budget_bytes"]
            free = rail.get("quota_free")
            if size > cap or (isinstance(free, (int, float)) and free < 2 * size):
                rail["verify_ok"] = False
                _finish_attempt(state, receipt, "failed_budget")
                say(f"  {receipt.remote}: BUDGET REFUSED ({size / 1e9:.2f}GB vs cap {cap / 1e9:.0f}GB, free {free})")
                return 1

            rail["restore_ok"] = restore_test(receipt.remote, workdir, kernel, receipt)
            if not rail["restore_ok"]:
                rail["verify_ok"] = False
                _finish_attempt(state, receipt, "failed_restore")
                say(f"  {receipt.remote}: restore proof FAILED — payload copy blocked")
                return 1

            rail["verify_ok"] = _copy_payloads(receipt.remote, staged, receipt)
            if not rail["verify_ok"]:
                _finish_attempt(state, receipt, "failed_copy_or_integrity")
                return 1

            completed = _iso(now())
            # These are the only freshness stamps, reached only after roundtrip, restore, copy, and
            # integrity proof all pass for this exact receipt-bound attempt.
            rail.update(
                {
                    "last_push": completed,
                    "last_push_attempt": completed,
                    "last_verified_push": completed,
                    "last_restore_test": completed,
                    "last_attempt_id_hash": _attempt_key(receipt.attempt_id),
                    "config_hash": receipt.config_hash,
                    "rail_id": receipt.rail_id,
                    "tool_hashes": receipt.tool_hashes,
                    "object_set": receipt.object_set,
                    "manifest_current_verified": True,
                }
            )
            if not _finish_attempt(state, receipt, "verified"):
                say("HORREVM custody FAILED: remote proof passed but freshness receipt was not published")
                return 1
    except (EffectRefused, OSError, ValueError) as exc:
        _finish_attempt(state, receipt, "failed_effect_boundary")
        say(f"HORREVM custody FAILED closed: {exc}")
        return 1

    say(f"HORREVM custody verified for {receipt.target} ({receipt.attempt_id})")
    return 0


def apply_action(
    action: str,
    receipt_path: Path,
    signature_path: Path,
    *,
    expected_attempt_id: str | None = None,
) -> int:
    try:
        directory_fd, lock_fd = _acquire_state_lock()
    except ReceiptError as exc:
        say(f"HORREVM custody REFUSED: {exc}")
        return 2
    try:
        return _apply_action_locked(
            action,
            receipt_path,
            signature_path,
            expected_attempt_id=expected_attempt_id,
        )
    finally:
        _release_state_lock(directory_fd, lock_fd)


def preview(
    action: str,
    *,
    attempt_id: str | None = None,
    receipt_path: Path | None = None,
    signature_path: Path | None = None,
) -> int:
    """Print receipt-ready bindings without rclone writes, staging, temp files, or state writes."""

    if receipt_path is not None:
        if signature_path is None:
            say("HORREVM custody preview REFUSED: signed receipt requires a signature path")
            return 2
        try:
            receipt, plan = load_apply_receipt(
                receipt_path,
                signature_path,
                action,
                expected_attempt_id=attempt_id,
            )
        except ReceiptError as exc:
            say(f"HORREVM custody preview REFUSED: {exc}")
            return 2
        rows = [
            {
                "action": action,
                "target": receipt.target,
                "payload_hash": receipt.payload_hash,
                "source_manifest_hash": receipt.source_manifest_hash,
                "content_hashes": receipt.content_hashes,
                "destinations": list(receipt.destinations),
                "config_hash": receipt.config_hash,
                "rail_id": receipt.rail_id,
                "tool_hashes": receipt.tool_hashes,
                "root_bindings": receipt.root_bindings,
                "object_set": receipt.object_set,
                "attempt_id": receipt.attempt_id,
                "expires_at": _iso(receipt.expires_at),
                "receipt_valid": True,
                "signature_namespace": SIGNED_RECEIPT_NAMESPACE,
                "trust_root_hash": receipt.trust_root_hash,
                "problems": plan["problems"],
            }
        ]
    else:
        chosen = attempt_id or f"horrevm-{uuid.uuid4().hex}"
        rows = []
        for remote in PAYLOADS:
            plan = action_plan(action, remote, chosen)
            rows.append(
                {
                    "receipt_template": {
                        "schema": RECEIPT_SCHEMA,
                        "authorized": False,
                        "authorized_by": "",
                        "action": action,
                        "destination": plan["destination"],
                        "destinations": plan["destinations"],
                        "source_manifest_hash": plan["source_manifest_hash"],
                        "content_hashes": plan["content_hashes"],
                        "payload_hash": plan["payload_hash"],
                        "config_hash": plan["config_hash"],
                        "rail_id": plan["rail_id"],
                        "tool_hashes": plan["tool_hashes"],
                        "root_bindings": plan["root_bindings"],
                        "object_set": plan["object_set"],
                        "issued_at": "<ISO-8601 UTC issue time>",
                        "expires_at": "<ISO-8601 UTC expiry>",
                        "attempt_id": chosen,
                    },
                    "signature_namespace": SIGNED_RECEIPT_NAMESPACE,
                    "problems": plan["problems"],
                }
            )
    say(json.dumps({"mode": "dry-run", "zero_write": True, "bindings": rows}, sort_keys=True))
    return 0 if not any(row["problems"] for row in rows) else 1


def status() -> int:
    state = load_state()
    if state.get("_state_error"):
        say(f"status: UNPROVEN — {state['_state_error']}")
        return 2
    if parked():
        say(f"status: UNPROVEN — PARKED on {LEVER}; no current remote custody evidence")
        return 2
    armed = os.environ.get("LIMEN_HORREVM_APPLY", "0") == "1"
    stale = []
    for remote in PAYLOADS:
        rail = _rail(state, remote)
        config = _owner_config()
        if (
            rail.get("config_hash") != config["config_hash"]
            or rail.get("rail_id") != config["rails"][remote]["rail_id"]
            or rail.get("tool_hashes") != config["tool_hashes"]
            or rail.get("manifest_current_verified") is not True
            or not isinstance(rail.get("object_set"), str)
        ):
            stale.append(f"{remote}: owner bindings or immutable manifest proof are stale")
            continue
        last = rail.get("last_verified_push")
        if not last:
            stale.append(f"{remote}: never verified")
        else:
            try:
                parsed = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            except ValueError:
                stale.append(f"{remote}: invalid freshness receipt")
            else:
                if now() - parsed > timedelta(days=_owner_config()["max_age_days"]):
                    stale.append(f"{remote}: last verified {last}")
    if stale:
        say("status: STALE — " + "; ".join(stale))
        return 1
    if not armed:
        say("status: fresh but apply is currently unarmed — existing owner evidence remains current")
        return 0
    say("status: fresh — every custody rail verified within bounds")
    return 0


def doctor() -> int:
    problems: list[str] = []
    try:
        config = _owner_config()
        _assert_domus_owner_chain(OWNER_APPLY_TMP, "Domus HORREVM apply temp root", leaf_directory=True)
        _assert_domus_owner_chain(OWNER_WORKDIR, "Domus HORREVM workdir", leaf_directory=True)
        for name, current in (
            ("rclone", _trusted_file_hash(RCLONE, "Domus rclone binary")),
            ("rclone_config", _trusted_file_hash(RCLONE_CONF, "Domus rclone config", max_bytes=MAX_CONFIG_BYTES)),
            ("arca", _trusted_file_hash(ARCA, "Domus ARCA effector")),
        ):
            if current != config["tool_hashes"].get(name):
                problems.append(f"deployed {name} hash differs from the owner config")
    except ReceiptError as exc:
        problems.append(str(exc))
    for p in problems:
        say(f"  DOCTOR: {p}")
    say(f"HORREVM custody --doctor: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="HORREVM custody — ciphertext to the cloud rails")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--push", action="store_true")
    modes.add_argument("--probe", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--status", action="store_true")
    modes.add_argument("--doctor", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="explicit alias for the zero-write default")
    ap.add_argument("--apply", action="store_true", help="enable receipt-bound effects for --push/--probe")
    ap.add_argument("--receipt", type=Path, help=f"{RECEIPT_SCHEMA} JSON authorization")
    ap.add_argument("--signature", type=Path, help="detached OpenSSH signature over the exact receipt bytes")
    ap.add_argument("--attempt-id", help="choose/confirm an arbitrary non-replayable attempt id")
    args = ap.parse_args(argv)

    if args.apply and args.dry_run:
        ap.error("--apply and --dry-run are mutually exclusive")
    if args.apply and (args.status or args.doctor or args.check):
        ap.error("--apply is valid only for --push or --probe")
    if args.receipt and (args.status or args.doctor):
        ap.error("--receipt is valid only for push/probe previews or applies")
    if args.signature and args.receipt is None:
        ap.error("--signature requires --receipt")
    if args.apply:
        try:
            _require_domus_installed_effector()
        except ReceiptError as exc:
            say(f"HORREVM custody REFUSED: {exc}")
            return 2
    try:
        if ACTIVE_CONFIG is None:
            _activate_owner_config()
    except ReceiptError as exc:
        say(f"HORREVM custody REFUSED: {exc}")
        return 2
    if args.doctor:
        return doctor()
    if args.status:
        return status()
    action = "probe" if args.probe else "push"
    if args.apply:
        if args.receipt is None:
            say("HORREVM custody REFUSED: --apply requires --receipt PATH")
            return 2
        if args.signature is None:
            say("HORREVM custody REFUSED: --apply requires --signature PATH")
            return 2
        return apply_action(
            action,
            args.receipt,
            args.signature,
            expected_attempt_id=args.attempt_id,
        )
    return preview(
        action,
        attempt_id=args.attempt_id,
        receipt_path=args.receipt,
        signature_path=args.signature,
    )


if __name__ == "__main__":
    sys.exit(main())
