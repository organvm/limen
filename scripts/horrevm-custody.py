#!/usr/bin/env python3
"""HORREVM custody — the granary's shipping lane: arca-sealed ciphertext to the cloud rails.

The strategic-use half of HORREVM (the doctor is scripts/cloud-storage-doctor.py). Drives rclone
in HEADLESS API mode (no File Provider desktop apps — the pre-2026-06-15 breakage vector) against
two remotes whose entire rclone.conf is one op:// item hydrated by the credential organ:

  gdrive:   second-vendor offsite for crown-jewel CIPHERTEXT — the ~/.arca-vault mirror (already
            AES-256-CBC sealed by arca.sh), a sealed session-corpus inventory, and the sealed
            continuity kernel. Covers the "GitHub lost AND Mac lost" correlated failure.
  dropbox:  break-glass grab bag — RECOVERY-CARD.md (plaintext, ZERO secrets) + the sealed kernel,
            reachable from any borrowed browser.

Egress law: ONLY ciphertext plus the one non-secret recovery card ever leaves the machine
(L-CLOUD-EGRESS-CONSENT). Every remote or local mutation requires explicit ``--apply``, the
``LIMEN_HORREVM_APPLY=1`` safety valve, and a fresh OpenSSH-signed
``limen.horrevm.apply_receipt.v1`` receipt. The signature is verified under a dedicated namespace
against the repository-pinned Domus owner trust root. The executing caller cannot substitute that
trust root through an argument or environment variable. The signed payload binds one
action, exact source-manifest and content hashes, exact remote destinations, one expiry, and one
non-replayable attempt id. A flag or self-asserted JSON document is never authorization by itself.
Remote deletion is restricted to the exact receipt-attempt object below ``limen-custody/.probe/``.
All other modes are literal zero-write previews.

Verbs:
  --push             zero-write push plan; apply requires receipt and owner signature
  --probe            zero-write probe plan; apply requires receipt and owner signature
  --check/default    zero-write push plan with receipt-ready hashes
  --status           zero-write freshness predicate
  --doctor           deterministic config parity (paths, payload spec, arca verbs) — no rclone
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
LOG = ROOT / "logs" / "horrevm.json"
ARCA = ROOT / "scripts" / "arca.sh"
RCLONE_CONF = Path.home() / ".config" / "rclone" / "rclone.conf"
CUSTODY_DIR = "limen-custody"
PROBE_NS = f"{CUSTODY_DIR}/.probe"
LEVER = "L-CLOUD-EGRESS-CONSENT"
MIN_PUSH_INTERVAL_H = 20  # MAT-pattern self-throttle: probes every beat, pushes ~daily
RECEIPT_SCHEMA = "limen.horrevm.apply_receipt.v1"
SIGNED_RECEIPT_NAMESPACE = RECEIPT_SCHEMA
OWNER_ALLOWED_SIGNERS = ROOT / "docs" / "keys" / "horrevm-apply.allowed-signers"
PLAN_SCHEMA = "limen.horrevm.payload_plan.v1"
STATE_SCHEMA = "limen.horrevm.state.v2"
REMOTE_WRITE_VERBS = frozenset({"copy", "copyto", "delete", "deletefile", "move", "moveto", "sync"})
STATE_RAIL_IDS = {"gdrive": "googledrive", "dropbox": "dropbox"}
MAX_RECEIPT_BYTES = 64 * 1024
MAX_TRUST_FILE_BYTES = 64 * 1024
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_LIFETIME = timedelta(hours=4)
AUTHORIZED_PRINCIPAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@:+-]{0,127}")

MAX_AGE_DAYS = int(os.environ.get("LIMEN_HORREVM_MAX_AGE_DAYS", "7"))
BUDGET_GB = {
    "gdrive": float(os.environ.get("LIMEN_HORREVM_DRIVE_BUDGET_GB", "5")),
    "dropbox": float(os.environ.get("LIMEN_HORREVM_DROPBOX_BUDGET_GB", "1")),
}

# The approved egress list (mirrors the lever text; edit BOTH or neither).
# type dir-mirror: source is ALREADY ciphertext — copied as-is.
# type seal:       tarred + sealed via `arca.sh seal` (one envelope, one Keychain key) first.
# type kernel:     the continuity kernel — sealed bundle of the files below + RECOVERY-CARD.md.
PAYLOADS: dict[str, list[dict]] = {
    "gdrive": [
        {"name": "arca-vault", "type": "dir-mirror", "src": "~/.arca-vault"},
        {"name": "corpus-inventory", "type": "seal", "src": "~/.limen-private/session-corpus/inventory"},
        {"name": "kernel", "type": "kernel"},
    ],
    "dropbox": [
        {"name": "kernel", "type": "kernel"},
    ],
}
KERNEL_CANDIDATES = [
    "~/Workspace/limen/FLAME.md",
    "~/Workspace/limen/his-hand-levers.json",
    "~/Workspace/limen/cloud-routines.json",
    "~/Workspace/limen/logs/obligations-ledger.json",
    "~/.arca-vault/manifest.json",
]


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
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
        if args[0] not in {"copy", "copyto", "deletefile"}:
            raise EffectRefused(f"rclone {args[0]} is not an authorized HORREVM operation")
        remote_arguments = [value for value in args[1:] if isinstance(value, str) and ":" in value]
        if len(remote_arguments) != 1:
            raise EffectRefused(f"rclone {args[0]} requires one exact signed remote object")
        refused = [value for value in remote_arguments if value not in receipt.destinations]
        if refused:
            raise EffectRefused(f"rclone {args[0]} destination is outside the signed receipt")
        if args[0] == "deletefile" and any(
            not value.startswith(f"{receipt.remote}:{PROBE_NS}/") for value in remote_arguments
        ):
            raise EffectRefused("rclone deletefile is restricted to the signed probe object")
    return run(["rclone", *args], timeout)


def _state_parent_fd(*, create: bool) -> tuple[int, str]:
    """Open the state parent beneath the real Limen root without following links."""

    try:
        relative = LOG.relative_to(ROOT)
    except ValueError as exc:
        raise ReceiptError("custody state path escapes the Limen root") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReceiptError("custody state path is unsafe")

    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        root_meta = ROOT.lstat()
        if not stat.S_ISDIR(root_meta.st_mode) or stat.S_ISLNK(root_meta.st_mode):
            raise ReceiptError("Limen root must be a real directory")
        current = os.open(ROOT, flags)
    except ReceiptError:
        raise
    except OSError as exc:
        raise ReceiptError(f"Limen root is unsafe: {type(exc).__name__}") from exc

    try:
        opened_root = os.fstat(current)
        if (opened_root.st_dev, opened_root.st_ino) != (root_meta.st_dev, root_meta.st_ino):
            raise ReceiptError("Limen root changed while opening custody state")
        for component in relative.parts[:-1]:
            try:
                child = os.open(component, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, 0o700, dir_fd=current)
                os.fsync(current)
                child = os.open(component, flags, dir_fd=current)
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode) or metadata.st_dev != opened_root.st_dev:
                os.close(child)
                raise ReceiptError("custody state parent escapes the Limen root filesystem")
            os.close(current)
            current = child
        return current, relative.name
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
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ReceiptError("custody state must be a single-link regular file")
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
    if not RCLONE_CONF.exists():
        return True
    rc, out = rclone(["listremotes"], timeout=15)
    configured = {f"{remote}:" for remote in PAYLOADS}
    return rc != 0 or not configured & set(out.split())


def gate_a(remote: str) -> dict:
    """Token + quota (rclone about)."""
    rc, out = rclone(["about", f"{remote}:", "--json"], timeout=60)
    if rc != 0:
        return {"token_ok": False}
    try:
        about = json.loads(out)
        return {"token_ok": True, "quota_total": about.get("total"), "quota_free": about.get("free")}
    except ValueError:
        return {"token_ok": True}


def _attempt_slug(attempt_id: str) -> str:
    return hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()[:24]


def _attempt_key(attempt_id: str) -> str:
    return "sha256:" + hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()


def _target(remote: str) -> str:
    return f"{remote}:{CUSTODY_DIR}"


def _probe_payload(remote: str, attempt_id: str) -> bytes:
    value = {
        "schema": "limen.horrevm.probe_payload.v1",
        "attempt_id": attempt_id,
        "target": _target(remote),
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def gate_b(remote: str, workdir: Path, receipt: ApplyReceipt) -> bool:
    """Receipt-bound exact-object roundtrip; no namespace-wide cleanup is permitted."""

    _require_receipt(receipt, "receipt-bound roundtrip staging")
    if receipt.remote != remote or receipt.target != _target(remote):
        raise EffectRefused("roundtrip target does not match the apply receipt")
    payload = _probe_payload(remote, receipt.attempt_id)
    local = workdir / "roundtrip-probe.txt"
    local.write_bytes(payload)
    probe_path = f"{remote}:{PROBE_NS}/{_attempt_slug(receipt.attempt_id)}-roundtrip.txt"
    if not probe_path.startswith(f"{remote}:{PROBE_NS}/"):
        raise EffectRefused("probe escaped the approved namespace")

    rc, _ = rclone(["copyto", str(local), probe_path], receipt=receipt, timeout=90)
    if rc != 0:
        # A failed copy may still have materialized a partial object. Cleanup remains exact-target.
        rclone(["deletefile", probe_path], receipt=receipt, timeout=60)
        return False
    rc, out = rclone(["cat", probe_path], timeout=60)
    delete_rc, _ = rclone(["deletefile", probe_path], receipt=receipt, timeout=60)
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
    destinations = [f"{remote}:{PROBE_NS}/{_attempt_slug(attempt_id)}-roundtrip.txt"]
    if action == "probe":
        return destinations
    destinations.append(f"{remote}:{PROBE_NS}/{_attempt_slug(attempt_id)}-kernel.tar.enc")
    for payload in payloads:
        name = payload.get("name")
        payload_type = payload.get("type")
        if not isinstance(name, str) or not name:
            continue
        if payload_type == "dir-mirror":
            destinations.append(f"{remote}:{CUSTODY_DIR}/{name}")
        elif payload_type == "seal":
            destinations.append(f"{remote}:{CUSTODY_DIR}/{name}.tar.enc")
        elif payload_type == "kernel":
            destinations.extend(
                [
                    f"{remote}:{CUSTODY_DIR}/kernel.tar.enc",
                    f"{remote}:{CUSTODY_DIR}/RECOVERY-CARD.md",
                ]
            )
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
        if not stat.S_ISREG(source_stat.st_mode):
            raise EffectRefused("receipt-bound source is no longer a regular file")
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


def _safe_manifest_relative(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise EffectRefused("receipt manifest contains an invalid relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        raise EffectRefused("receipt manifest relative path escaped private staging")
    return relative


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
    if kind == "file":
        expected_content = {key: manifest.get(key) for key in ("kind", "size", "sha256")}
        staged_content = {key: staged_manifest.get(key) for key in ("kind", "size", "sha256")}
    else:
        expected_content = {"kind": "dir", "entries": manifest.get("entries")}
        staged_content = {"kind": staged_manifest.get("kind"), "entries": staged_manifest.get("entries")}
    if staged_content != expected_content:
        raise EffectRefused("private staging does not match the apply receipt manifest")
    return destination


def _path_manifest(path: Path) -> tuple[dict[str, Any], list[str]]:
    """Hash a source without following symlinks; errors make an apply plan ineligible."""

    problems: list[str] = []
    display = str(path)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return {"path": display, "kind": "missing"}, problems
    except OSError as exc:
        return {"path": display, "kind": "unreadable"}, [f"{display}: {type(exc).__name__}"]

    if stat.S_ISLNK(mode):
        return {"path": display, "kind": "symlink"}, [f"{display}: symlink sources are refused"]
    if stat.S_ISREG(mode):
        try:
            return {
                "path": display,
                "kind": "file",
                "size": path.stat().st_size,
                "sha256": _file_hash(path),
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
                entries.append({"path": relative, "kind": "dir"})
            elif stat.S_ISREG(child_mode):
                entries.append(
                    {
                        "path": relative,
                        "kind": "file",
                        "size": child.stat().st_size,
                        "sha256": _file_hash(child),
                    }
                )
            else:
                entries.append({"path": relative, "kind": "special"})
                problems.append(f"{display}/{relative}: special sources are refused")
        except OSError as exc:
            entries.append({"path": relative, "kind": "unreadable"})
            problems.append(f"{display}/{relative}: {type(exc).__name__}")
    return {"path": display, "kind": "dir", "entries": entries}, problems


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
    return manifests, included, problems


def _recovery_card(attempt_id: str, included: list[str]) -> str:
    return _mask(
        "# LIMEN Recovery Card (plaintext by design — contains ZERO secrets)\n\n"
        f"Custody attempt: `{attempt_id}`. Generated deterministically by scripts/horrevm-custody.py.\n\n"
        "## What exists where\n"
        "- GitHub org `organvm` — all repos incl. private `organvm/arca` (sealed private estate).\n"
        "- Backblaze — offsite backup of the Mac `/` and `/Volumes/Archive4T`.\n"
        "- Archive4T + T7Recovery — local archive SSOT + second copy.\n"
        "- Google Drive `limen-custody/` — arca-vault mirror + sealed inventories + this kernel.\n"
        "- Dropbox `limen-custody/` — this kernel + this card.\n\n"
        "## Restore order\n"
        "1. New machine: sign into GitHub; clone organvm/limen; read CLAUDE.md + his-hand-levers.json.\n"
        "2. ARCA key: macOS Keychain item `limen-arca-vault` (escrow per lever L-ARCA-KEY-ESCROW).\n"
        "3. `bash scripts/arca.sh unseal kernel.tar.enc <dest>` recovers this kernel's bundle.\n"
        "4. Backblaze restore for bulk; Drive `limen-custody/arca-vault/` for the sealed private estate.\n\n"
        "## Kernel bundle contents\n- " + "\n- ".join(included or ["(none present at build time)"]) + "\n"
    )


def action_plan(action: str, remote: str, attempt_id: str) -> dict[str, Any]:
    """Create the deterministic, receipt-bindable plan without writing local or remote state."""

    if remote not in PAYLOADS:
        raise ReceiptError(f"unknown custody remote: {remote}")
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
    if remote not in BUDGET_GB:
        problems.append(f"no payload budget is configured for {remote}")
    for spec in PAYLOADS[remote]:
        row: dict[str, Any] = {"name": spec.get("name"), "type": spec.get("type")}
        if spec.get("type") in {"dir-mirror", "seal"}:
            source_value = spec.get("src")
            if not isinstance(source_value, str) or not source_value:
                problems.append(f"payload source is missing: {spec!r}")
            else:
                source, found = _path_manifest(Path(os.path.expanduser(source_value)))
                row["source"] = source
                problems.extend(found)
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
    return {
        **manifest,
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


def _open_trusted_input(path: Path, label: str, *, max_bytes: int) -> tuple[int, bytes]:
    """Open one authority input without following links and retain the fd across verification."""

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
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise ReceiptError(f"{label} must be owned by the effective user")
        raw = os.pread(fd, max_bytes + 1, 0)
        if len(raw) != metadata.st_size:
            raise ReceiptError(f"{label} changed while it was read")
        return fd, raw
    except Exception:
        os.close(fd)
        raise


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
        OWNER_ALLOWED_SIGNERS, "pinned allowed-signers owner", max_bytes=MAX_TRUST_FILE_BYTES
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
                    "ssh-keygen",
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
    )
    return receipt, plan


def _consume_receipt(path: Path, receipt: ApplyReceipt) -> None:
    """Persist an owner-adjacent one-shot marker before any apply subprocess."""

    _require_receipt(receipt, "receipt consumption")
    digest = receipt.receipt_hash.removeprefix("sha256:")
    marker = path.with_name(f".{path.name}.{digest}.consumed")
    payload = {
        "schema": "limen.horrevm.consumed_receipt.v1",
        "receipt_hash": receipt.receipt_hash,
        "attempt_id_hash": _attempt_key(receipt.attempt_id),
        "action": receipt.action,
        "target": receipt.target,
        "payload_hash": receipt.payload_hash,
        "source_manifest_hash": receipt.source_manifest_hash,
        "trust_root_hash": receipt.trust_root_hash,
        "consumed_at": _iso(now()),
    }
    encoded = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(marker, flags, 0o600)
    except FileExistsError as exc:
        raise ReceiptError("exact apply receipt was already consumed") from exc
    except OSError as exc:
        raise ReceiptError(f"receipt replay marker could not be created: {type(exc).__name__}") from exc
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    except OSError as exc:
        raise ReceiptError(f"receipt replay marker could not be made durable: {type(exc).__name__}") from exc
    finally:
        os.close(fd)
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        parent_fd = os.open(marker.parent, directory_flags)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise ReceiptError(f"receipt replay marker parent is unsafe: {type(exc).__name__}") from exc


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


def seal(src: Path, out_enc: Path, receipt: ApplyReceipt | None = None) -> bool:
    _require_receipt(receipt, "local sealing")
    rc, out = run(["bash", str(ARCA), "seal", str(src), str(out_enc)], 300)
    if rc != 0:
        say(f"  seal failed for {src.name}: {out.strip()[-120:]}")
    return rc == 0


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
        if spec["type"] == "dir-mirror":
            source_manifest = planned.get("source")
            if not isinstance(source_manifest, dict):
                raise EffectRefused("directory mirror omitted its receipt-bound source manifest")
            snapshot = _snapshot_manifest_source(source_manifest, snapshots / spec["name"], receipt)
            if snapshot is not None:
                if not snapshot.is_dir():
                    raise EffectRefused("directory mirror source is not a directory")
                staged.append((snapshot, spec["name"]))
        elif spec["type"] == "seal":
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
    probe_path = f"{remote}:{PROBE_NS}/{_attempt_slug(receipt.attempt_id)}-kernel.tar.enc"
    if not probe_path.startswith(f"{remote}:{PROBE_NS}/"):
        raise EffectRefused("restore probe escaped the approved namespace")
    pulled = workdir / "pulled-kernel.tar.enc"
    upload_attempted = False
    uploaded = False
    copy_ok = unseal_ok = False
    delete_rc: int | None = None
    try:
        upload_attempted = True
        rc, _ = rclone(["copyto", str(kernel), probe_path], receipt=receipt, timeout=600)
        uploaded = rc == 0
        if not uploaded:
            return False
        rc, _ = rclone(["copyto", probe_path, str(pulled)], receipt=receipt, timeout=600)
        copy_ok = rc == 0 and pulled.is_file() and _file_hash(pulled) == _file_hash(kernel)
        if copy_ok:
            out_dir = workdir / "restore-check"
            rc, _ = run(["bash", str(ARCA), "unseal", str(pulled), str(out_dir)], 300)
            unseal_ok = rc == 0 and out_dir.exists() and any(out_dir.rglob("*"))
    finally:
        if upload_attempted:
            delete_rc, _ = rclone(["deletefile", probe_path], receipt=receipt, timeout=60)
    ok = copy_ok and unseal_ok and delete_rc == 0
    say(f"  {remote}: restore-proof {'PASSED' if ok else 'FAILED'}")
    return ok


def _copy_payloads(remote: str, staged: list[tuple[Path, str]], receipt: ApplyReceipt) -> bool:
    for local, subpath in staged:
        destination = f"{remote}:{CUSTODY_DIR}/{subpath}"
        verb = "copy" if local.is_dir() else "copyto"
        rc, _ = rclone([verb, str(local), destination], receipt=receipt, timeout=1800)
        ok = rc == 0
        if ok:
            rc, _ = rclone(["check", str(local), destination, "--one-way"], timeout=600)
            ok = rc == 0
        say(f"  {remote}: {local.name} {'shipped+verified' if ok else 'FAILED'}")
        if not ok:
            return False
    return bool(staged)


def apply_action(
    action: str,
    receipt_path: Path,
    signature_path: Path,
    *,
    expected_attempt_id: str | None = None,
) -> int:
    try:
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
        _consume_receipt(receipt_path, receipt)
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
        with tempfile.TemporaryDirectory(prefix="horrevm-") as td:
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
            cap = BUDGET_GB[receipt.remote] * 1e9
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
    if parked():
        say(f"status: PARKED on {LEVER} (dark by design) — exit 0")
        return 0
    armed = os.environ.get("LIMEN_HORREVM_APPLY", "0") == "1"
    stale = []
    for remote in PAYLOADS:
        rail = _rail(state, remote)
        last = rail.get("last_verified_push")
        if not last:
            stale.append(f"{remote}: never verified")
        else:
            try:
                parsed = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            except ValueError:
                stale.append(f"{remote}: invalid freshness receipt")
            else:
                if now() - parsed > timedelta(days=MAX_AGE_DAYS):
                    stale.append(f"{remote}: last verified {last}")
    if not armed:
        say(
            f"status: consented-but-unarmed dry-run (set LIMEN_HORREVM_APPLY=1); {len(stale)} rail(s) unproven — exit 0"
        )
        return 0
    if stale:
        say("status: STALE — " + "; ".join(stale))
        return 1
    say("status: fresh — every custody rail verified within bounds")
    return 0


def doctor() -> int:
    problems = []
    if not ARCA.exists():
        problems.append("scripts/arca.sh missing")
    elif "cmd_seal" not in ARCA.read_text(encoding="utf-8"):
        problems.append("arca.sh lacks seal/unseal verbs")
    for remote, payloads in PAYLOADS.items():
        if remote not in BUDGET_GB:
            problems.append(f"no budget for {remote}")
        for spec in payloads:
            if spec["type"] not in ("dir-mirror", "seal", "kernel"):
                problems.append(f"unknown payload type {spec}")
            if spec["type"] != "kernel" and "src" not in spec:
                problems.append(f"payload missing src: {spec}")
    for p in problems:
        say(f"  DOCTOR: {p}")
    say(f"HORREVM custody --doctor: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("OS_ACTIVITY_MODE", "disable")  # fork/os_log SIGSEGV mitigation (#831)
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
