#!/usr/bin/env python3
"""Receipt-bound disk-capacity reclaimer.

This effector is intentionally separate from ``disk-capacity.py``.  The deployed
heartbeat calls only that observation sensor; it never appends ``--apply`` and it
never reaches this file.

The default/``--check``/``--dry-run`` path computes and prints an exact reclaim
plan without writing anything.  Mutation requires both ``--apply`` and a fresh
``limen.disk_capacity.apply_receipt.v1`` JSON receipt bound to the current plan,
root, expiry, and a non-replayable attempt id.  A consumed-attempt result is
reserved before the first effect and retained even if a later effect fails.

The bounded effect surface is deliberately narrow:

* quarantine, verify, then unlink single-link regular, git-ignored
  ``.heal-probe-*.yaml`` files under an opened ``LIMEN_ROOT``;
* truncate the single-link regular ``logs/heartbeat.err.log`` through no-follow
  directory descriptors only when its exact receipt-bound contents exceed
  ``LIMEN_DISK_LOG_CAP_MB``.

Usage:
  python3 scripts/disk-capacity-reclaim.py --check
  python3 scripts/disk-capacity-reclaim.py --check --attempt-id <unique-id>
  python3 scripts/disk-capacity-reclaim.py --apply --receipt /private/path/receipt.json
"""

from __future__ import annotations

import sys

# Preview/check must not create incidental bytecode.
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))
HEARTBEAT_ERR_LOG = ROOT / "logs" / "heartbeat.err.log"
RESULTS_DIR = ROOT / "logs" / "disk-capacity-results"
DEFAULT_LOG_CAP_MB = 50
MAX_RECEIPT_BYTES = 64 * 1024
MAX_PROBE_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_LIFETIME = timedelta(minutes=15)
PLAN_SCHEMA = "limen.disk_capacity.reclaim_plan.v1"
RECEIPT_SCHEMA = "limen.disk_capacity.apply_receipt.v1"
RESULT_SCHEMA = "limen.disk_capacity.apply_result.v1"
ACTION = "reclaim_disk_capacity"
HASH_RX = re.compile(r"sha256:[0-9a-f]{64}")


class ReceiptError(ValueError):
    """The supplied apply receipt is absent, stale, unsafe, or mismatched."""


class EffectAppliedError(ReceiptError):
    """An effect happened (or remains quarantined) even though the step failed."""

    def __init__(self, message: str, effect: dict[str, Any]):
        super().__init__(message)
        self.effect = effect


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_fd(fd: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    return "sha256:" + digest.hexdigest(), total


def _close_quietly(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


def _open_root_dir() -> int:
    """Open the real Limen root once and bind subsequent path walks to that fd."""

    try:
        path_meta = ROOT.lstat()
    except OSError as exc:
        raise ReceiptError(f"LIMEN_ROOT is unreadable ({type(exc).__name__})") from exc
    if not stat.S_ISDIR(path_meta.st_mode) or stat.S_ISLNK(path_meta.st_mode):
        raise ReceiptError("LIMEN_ROOT must be a real non-symlink directory")
    try:
        fd = os.open(ROOT, _directory_flags())
    except OSError as exc:
        raise ReceiptError(f"LIMEN_ROOT could not be opened safely ({type(exc).__name__})") from exc
    opened = os.fstat(fd)
    if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
        path_meta.st_dev,
        path_meta.st_ino,
    ):
        os.close(fd)
        raise ReceiptError("LIMEN_ROOT changed while it was being opened")
    return fd


def _root_id(root_fd: int) -> str:
    opened = os.fstat(root_fd)
    identity = {
        "resolved_path": str(ROOT.resolve()),
        "device": opened.st_dev,
        "inode": opened.st_ino,
    }
    return _sha256_bytes(_canonical_bytes(identity))


def _safe_relative(raw: str) -> Path | None:
    path = Path(raw)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def _open_parent_dir(root_fd: int, relative_path: str) -> tuple[int, str]:
    """Resolve a relative parent beneath *root_fd* without following symlinks.

    Every directory component must remain on the root filesystem.  Returning an
    opened parent descriptor means later renames of a pathname cannot redirect an
    effect through a replacement symlink.
    """

    relative = _safe_relative(relative_path)
    if relative is None:
        raise ReceiptError(f"unsafe relative path {relative_path!r}")
    root_meta = os.fstat(root_fd)
    current = os.dup(root_fd)
    try:
        for component in relative.parts[:-1]:
            try:
                child = os.open(component, _directory_flags(), dir_fd=current)
            except OSError as exc:
                raise ReceiptError(
                    f"{relative_path}: unsafe parent component {component!r} ({type(exc).__name__})"
                ) from exc
            child_meta = os.fstat(child)
            if not stat.S_ISDIR(child_meta.st_mode) or child_meta.st_dev != root_meta.st_dev:
                os.close(child)
                raise ReceiptError(f"{relative_path}: parent escapes the Limen root filesystem")
            os.close(current)
            current = child
        return current, relative.name
    except Exception:
        os.close(current)
        raise


def _fingerprint_fd(fd: int, *, kind: str, relative_path: str) -> tuple[dict[str, Any] | None, str | None]:
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode):
        return None, f"{relative_path}: opened target is not regular"
    if opened.st_nlink != 1:
        return None, f"{relative_path}: target must have exactly one hard link"
    if kind == "unlink" and opened.st_size > MAX_PROBE_BYTES:
        return None, f"{relative_path}: heal probe exceeds {MAX_PROBE_BYTES} bytes"
    digest, size = _sha256_fd(fd)
    return {
        "kind": kind,
        "relative_path": relative_path,
        "size_bytes": size,
        "sha256": digest,
        "device": opened.st_dev,
        "inode": opened.st_ino,
        "link_count": opened.st_nlink,
    }, None


def _fingerprint_name(
    parent_fd: int,
    name: str,
    *,
    kind: str,
    relative_path: str,
) -> tuple[dict[str, Any] | None, str | None]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        return None, f"{relative_path}: could not open safely ({type(exc).__name__})"
    try:
        return _fingerprint_fd(fd, kind=kind, relative_path=relative_path)
    finally:
        os.close(fd)


def _fingerprint_regular_at(
    root_fd: int,
    *,
    kind: str,
    relative_path: str,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parent_fd, name = _open_parent_dir(root_fd, relative_path)
    except ReceiptError as exc:
        return None, str(exc)
    try:
        return _fingerprint_name(parent_fd, name, kind=kind, relative_path=relative_path)
    finally:
        os.close(parent_fd)


def _ignored_heal_probes() -> tuple[list[str], list[str]]:
    # Git's read-only plumbing can still write trace files when the parent
    # process exports GIT_TRACE* variables.  A literal zero-write preview owns
    # the subprocess environment as well as this Python process.
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_TRACE")}
    git_env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            env=git_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], [f"git ignored-candidate discovery failed ({type(exc).__name__})"]
    if result.returncode != 0:
        return [], ["git ignored-candidate discovery failed"]

    candidates: list[str] = []
    problems: list[str] = []
    for raw in result.stdout.split("\0"):
        if not raw:
            continue
        relative = _safe_relative(raw)
        if relative is None:
            problems.append("git returned an unsafe ignored path")
            continue
        if relative.name.startswith(".heal-probe-") and relative.name.endswith(".yaml"):
            candidates.append(relative.as_posix())
    return sorted(set(candidates)), problems


def build_plan(log_cap_mb: int) -> dict[str, Any]:
    """Compute the exact, deterministic mutation plan without writing anything."""

    cap_bytes = log_cap_mb * 1024 * 1024
    targets: list[dict[str, Any]] = []
    try:
        root_fd = _open_root_dir()
    except ReceiptError as exc:
        root_fd = None
        problems = [str(exc)]
        root_id = _sha256_bytes(str(ROOT.absolute()).encode("utf-8"))
    else:
        problems = []
        root_id = _root_id(root_fd)
        try:
            candidates, discovery_problems = _ignored_heal_probes()
            problems.extend(discovery_problems)
            for relative in candidates:
                fingerprint, problem = _fingerprint_regular_at(
                    root_fd,
                    kind="unlink",
                    relative_path=relative,
                )
                if problem:
                    problems.append(problem)
                elif fingerprint:
                    targets.append(fingerprint)

            log_relative = "logs/heartbeat.err.log"
            try:
                log_meta = HEARTBEAT_ERR_LOG.lstat()
            except FileNotFoundError:
                log_meta = None
            except OSError as exc:
                log_meta = None
                problems.append(f"{log_relative}: unreadable ({type(exc).__name__})")
            if log_meta is not None and log_meta.st_size > cap_bytes:
                fingerprint, problem = _fingerprint_regular_at(
                    root_fd,
                    kind="truncate",
                    relative_path=log_relative,
                )
                if problem:
                    problems.append(problem)
                elif fingerprint:
                    targets.append(fingerprint)
        finally:
            os.close(root_fd)

    targets.sort(key=lambda row: (str(row["relative_path"]), str(row["kind"])))
    unsigned = {
        "schema": PLAN_SCHEMA,
        "action": ACTION,
        "root_id": root_id,
        "log_cap_bytes": cap_bytes,
        "targets": targets,
        "problems": sorted(set(problems)),
    }
    return {**unsigned, "plan_hash": _sha256_bytes(_canonical_bytes(unsigned))}


def _parse_timestamp(raw: Any, field: str) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ReceiptError(f"receipt {field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReceiptError(f"receipt {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ReceiptError(f"receipt {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_receipt_window(value: dict[str, Any]) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    issued_at = _parse_timestamp(value.get("issued_at"), "issued_at")
    expires_at = _parse_timestamp(value.get("expires_at"), "expires_at")
    if issued_at > now:
        raise ReceiptError("receipt was issued in the future")
    if expires_at <= now:
        raise ReceiptError("receipt has expired")
    if expires_at <= issued_at:
        raise ReceiptError("receipt expires before it was issued")
    if expires_at - issued_at > MAX_RECEIPT_LIFETIME:
        raise ReceiptError("receipt lifetime exceeds 15 minutes")
    return issued_at, expires_at


def _require_receipt_current(receipt: dict[str, Any]) -> None:
    """Fail closed when a once-valid receipt expires before a write boundary."""

    expires_at = _parse_timestamp(receipt.get("expires_at"), "expires_at")
    if expires_at <= datetime.now(timezone.utc):
        raise ReceiptError("receipt expired before the next write boundary")


def load_receipt(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Read once and validate all receipt bindings before reserving an attempt."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReceiptError(f"receipt is unreadable ({type(exc).__name__})") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ReceiptError("receipt must be a regular non-symlink file")
        if metadata.st_size > MAX_RECEIPT_BYTES:
            raise ReceiptError(f"receipt exceeds {MAX_RECEIPT_BYTES} bytes")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ReceiptError("receipt must not be group/world writable")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
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
            raise ReceiptError(f"receipt exceeds {MAX_RECEIPT_BYTES} bytes")
        value = json.loads(raw)
    except ReceiptError:
        raise
    except (OSError, ValueError) as exc:
        raise ReceiptError(f"receipt is unreadable ({type(exc).__name__})") from exc
    finally:
        os.close(fd)
    if not isinstance(value, dict) or value.get("schema") != RECEIPT_SCHEMA:
        raise ReceiptError(f"receipt schema must be {RECEIPT_SCHEMA}")
    if value.get("action") != ACTION:
        raise ReceiptError(f"receipt action must be {ACTION}")
    if value.get("authorized") is not True:
        raise ReceiptError("receipt must explicitly set authorized=true")
    authorized_by = value.get("authorized_by")
    if not isinstance(authorized_by, str) or not authorized_by.strip():
        raise ReceiptError("receipt must name authorized_by")
    if value.get("root_id") != plan["root_id"]:
        raise ReceiptError("receipt root_id does not match this Limen root")
    plan_hash = value.get("plan_hash")
    if not isinstance(plan_hash, str) or not HASH_RX.fullmatch(plan_hash):
        raise ReceiptError("receipt plan_hash must be sha256:<64 lowercase hex>")
    if plan_hash != plan["plan_hash"]:
        raise ReceiptError("receipt plan_hash does not match the current reclaim plan")
    attempt_id = value.get("attempt_id")
    if not isinstance(attempt_id, str) or not 1 <= len(attempt_id) <= 256:
        raise ReceiptError("receipt attempt_id must be 1..256 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in attempt_id):
        raise ReceiptError("receipt attempt_id contains control characters")
    issued_at, expires_at = _validate_receipt_window(value)
    return {
        "attempt_id": attempt_id,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "receipt_hash": _sha256_bytes(raw),
    }


def _consume_receipt(receipt_path: Path, receipt: dict[str, Any], plan: dict[str, Any]) -> None:
    """Publish an owner-adjacent one-shot marker before the first target effect."""

    _require_receipt_current(receipt)
    receipt_digest = str(receipt["receipt_hash"]).removeprefix("sha256:")
    marker = receipt_path.with_name(f".{receipt_path.name}.{receipt_digest}.consumed")
    payload = {
        "schema": "limen.disk_capacity.consumed_receipt.v1",
        "receipt_hash": receipt["receipt_hash"],
        "plan_hash": plan["plan_hash"],
        "attempt_id_hash": _sha256_bytes(receipt["attempt_id"].encode("utf-8")),
        "consumed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(marker, flags, 0o600)
    except FileExistsError as exc:
        raise ReceiptError("exact apply receipt was already consumed") from exc
    except OSError as exc:
        raise ReceiptError(f"receipt replay marker could not be created ({type(exc).__name__})") from exc
    try:
        _write_fd(fd, payload)
    except OSError as exc:
        raise ReceiptError(f"receipt replay marker could not be made durable ({type(exc).__name__})") from exc
    finally:
        os.close(fd)
    try:
        parent_fd = os.open(marker.parent, _directory_flags())
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise ReceiptError(f"receipt replay marker parent could not be made durable ({type(exc).__name__})") from exc


def _result_path(attempt_id: str) -> Path:
    name = hashlib.sha256(attempt_id.encode("utf-8")).hexdigest() + ".json"
    return RESULTS_DIR / name


def _write_fd(fd: int, value: dict[str, Any]) -> None:
    payload = json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        view = view[written:]
    os.fsync(fd)


def _open_or_create_child_dir(parent_fd: int, name: str, *, mode: int, private: bool) -> int:
    created = False
    try:
        os.mkdir(name, mode=mode, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise ReceiptError(f"could not create directory {name!r} ({type(exc).__name__})") from exc
    try:
        child_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise ReceiptError(f"directory {name!r} could not be opened safely ({type(exc).__name__})") from exc
    metadata = os.fstat(child_fd)
    parent_meta = os.fstat(parent_fd)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_dev != parent_meta.st_dev:
        os.close(child_fd)
        raise ReceiptError(f"directory {name!r} escapes the Limen root filesystem")
    if private:
        effective_uid = os.geteuid() if hasattr(os, "geteuid") else metadata.st_uid
        if metadata.st_uid != effective_uid or metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            os.close(child_fd)
            raise ReceiptError(f"directory {name!r} must be private to the effective user")
    if created:
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            os.close(child_fd)
            raise ReceiptError(f"directory {name!r} could not be made durable") from exc
    return child_fd


def _reserve_attempt(
    receipt: dict[str, Any],
    plan: dict[str, Any],
    root_fd: int,
) -> tuple[int, Path, int]:
    _require_receipt_current(receipt)
    if _root_id(root_fd) != plan["root_id"]:
        raise ReceiptError("LIMEN_ROOT changed after receipt validation")
    logs_fd = _open_or_create_child_dir(root_fd, "logs", mode=0o700, private=False)
    try:
        results_fd = _open_or_create_child_dir(logs_fd, "disk-capacity-results", mode=0o700, private=True)
    finally:
        os.close(logs_fd)
    try:
        quarantine_fd = _open_or_create_child_dir(results_fd, ".quarantine", mode=0o700, private=True)
        path = _result_path(receipt["attempt_id"])
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(path.name, flags, 0o600, dir_fd=results_fd)
        except FileExistsError as exc:
            os.close(quarantine_fd)
            raise ReceiptError("receipt attempt_id was already consumed") from exc
        except OSError:
            os.close(quarantine_fd)
            raise
        reserved = {
            "schema": RESULT_SCHEMA,
            "status": "reserved",
            "attempt_id_hash": _sha256_bytes(receipt["attempt_id"].encode("utf-8")),
            "receipt_hash": receipt["receipt_hash"],
            "plan_hash": plan["plan_hash"],
            "root_id": plan["root_id"],
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "effects": [],
        }
        try:
            _write_fd(fd, reserved)
            os.fsync(results_fd)
        except Exception:
            os.close(fd)
            os.close(quarantine_fd)
            raise
        return fd, path, quarantine_fd
    finally:
        os.close(results_fd)


def _matches(target: dict[str, Any], fingerprint: dict[str, Any]) -> bool:
    return all(
        fingerprint.get(key) == target.get(key)
        for key in ("kind", "relative_path", "size_bytes", "sha256", "device", "inode", "link_count")
    )


def _restore_quarantined(
    quarantine_fd: int,
    quarantine_name: str,
    parent_fd: int,
    original_name: str,
) -> tuple[bool, bool, str]:
    """Restore without overwriting a concurrently-created original path."""

    try:
        os.link(
            quarantine_name,
            original_name,
            src_dir_fd=quarantine_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except FileExistsError:
        return False, True, "original path is occupied; mismatched candidate retained in quarantine"
    except OSError as exc:
        return (
            False,
            True,
            f"restore link failed ({type(exc).__name__}); mismatched candidate retained in quarantine",
        )
    try:
        os.unlink(quarantine_name, dir_fd=quarantine_fd)
    except OSError as exc:
        return True, True, f"original restored but quarantine copy remains ({type(exc).__name__})"
    try:
        os.fsync(parent_fd)
        os.fsync(quarantine_fd)
    except OSError as exc:
        return True, False, f"original restored but durability confirmation failed ({type(exc).__name__})"
    return True, False, "original restored"


def _quarantine_effect(
    target: dict[str, Any],
    quarantine_name: str,
    *,
    restored: bool,
    quarantine_retained: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "kind": "quarantine",
        "relative_path": target["relative_path"],
        "size_bytes_before": target["size_bytes"],
        "mutation_observed": True,
        "deleted": False,
        "restored": restored,
        "quarantine_retained": quarantine_retained,
        "quarantine_path": f"logs/disk-capacity-results/.quarantine/{quarantine_name}",
        "detail": detail,
    }


def _unlink_exact(
    target: dict[str, Any],
    root_fd: int,
    quarantine_fd: int,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    relative = str(target["relative_path"])
    parent_fd, name = _open_parent_dir(root_fd, relative)
    quarantine_name = f"{hashlib.sha256(relative.encode('utf-8')).hexdigest()[:16]}-{uuid.uuid4().hex}.candidate"
    moved = False
    deleted = False
    try:
        fingerprint, problem = _fingerprint_name(parent_fd, name, kind="unlink", relative_path=relative)
        if problem or fingerprint is None or not _matches(target, fingerprint):
            raise ReceiptError(f"{relative}: target changed after receipt validation")
        _require_receipt_current(receipt)
        try:
            os.rename(name, quarantine_name, src_dir_fd=parent_fd, dst_dir_fd=quarantine_fd)
            moved = True
        except OSError as exc:
            raise ReceiptError(f"{relative}: quarantine move failed ({type(exc).__name__})") from exc

        moved_fingerprint, moved_problem = _fingerprint_name(
            quarantine_fd,
            quarantine_name,
            kind="unlink",
            relative_path=relative,
        )
        if moved_problem or moved_fingerprint is None or not _matches(target, moved_fingerprint):
            reason = moved_problem or "moved inode/content no longer matches the receipt"
            restored, retained, detail = _restore_quarantined(quarantine_fd, quarantine_name, parent_fd, name)
            if restored and not retained:
                raise ReceiptError(f"{relative}: candidate changed during quarantine; {detail}")
            effect = _quarantine_effect(
                target,
                quarantine_name,
                restored=restored,
                quarantine_retained=retained,
                detail=detail,
            )
            raise EffectAppliedError(f"{relative}: {reason}; {detail}", effect)

        try:
            os.unlink(quarantine_name, dir_fd=quarantine_fd)
            deleted = True
            effect = {
                "kind": "unlink",
                "relative_path": relative,
                "size_bytes_before": target["size_bytes"],
                "mutation_observed": True,
                "deleted": True,
                "durability_confirmed": False,
            }
            os.fsync(quarantine_fd)
            os.fsync(parent_fd)
            effect["durability_confirmed"] = True
            return effect
        except OSError as exc:
            if deleted:
                raise EffectAppliedError(f"{relative}: deleted but durability confirmation failed", effect) from exc
            restored, retained, detail = _restore_quarantined(quarantine_fd, quarantine_name, parent_fd, name)
            if restored and not retained:
                raise ReceiptError(f"{relative}: delete failed; {detail}") from exc
            effect = _quarantine_effect(
                target,
                quarantine_name,
                restored=restored,
                quarantine_retained=retained,
                detail=detail,
            )
            raise EffectAppliedError(f"{relative}: delete failed; {detail}", effect) from exc
    except EffectAppliedError:
        raise
    except ReceiptError:
        raise
    except OSError as exc:
        if moved and not deleted:
            restored, retained, detail = _restore_quarantined(quarantine_fd, quarantine_name, parent_fd, name)
            if restored and not retained:
                raise ReceiptError(f"{relative}: effect failed; {detail}") from exc
            effect = _quarantine_effect(
                target,
                quarantine_name,
                restored=restored,
                quarantine_retained=retained,
                detail=detail,
            )
            raise EffectAppliedError(f"{relative}: effect failed; {detail}", effect) from exc
        raise ReceiptError(f"{relative}: effect failed ({type(exc).__name__})") from exc
    finally:
        _close_quietly(parent_fd)


def _truncate_exact(target: dict[str, Any], root_fd: int, receipt: dict[str, Any]) -> dict[str, Any]:
    relative = str(target["relative_path"])
    parent_fd, name = _open_parent_dir(root_fd, relative)
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    effect: dict[str, Any] | None = None
    try:
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ReceiptError(f"{relative}: could not open safely ({type(exc).__name__})") from exc
        try:
            fingerprint, problem = _fingerprint_fd(fd, kind="truncate", relative_path=relative)
            if problem or fingerprint is None or not _matches(target, fingerprint):
                raise ReceiptError(f"{relative}: target changed after receipt validation")
            latest = os.fstat(fd)
            if latest.st_nlink != 1 or (latest.st_dev, latest.st_ino) != (
                target["device"],
                target["inode"],
            ):
                raise ReceiptError(f"{relative}: target link identity changed before truncation")
            _require_receipt_current(receipt)
            os.ftruncate(fd, 0)
            effect = {
                "kind": "truncate",
                "relative_path": relative,
                "size_bytes_before": target["size_bytes"],
                "mutation_observed": True,
                "durability_confirmed": False,
            }
            try:
                os.fsync(fd)
            except OSError as exc:
                raise EffectAppliedError(
                    f"{relative}: truncated but durability confirmation failed",
                    effect,
                ) from exc
            effect["durability_confirmed"] = True
            return effect
        finally:
            pending_error = sys.exc_info()[0] is not None
            try:
                os.close(fd)
            except OSError as exc:
                if not pending_error and effect is not None:
                    raise EffectAppliedError(f"{relative}: truncated but close reporting failed", effect) from exc
                if not pending_error:
                    raise ReceiptError(f"{relative}: target close failed") from exc
    finally:
        _close_quietly(parent_fd)


def apply(receipt_path: Path, log_cap_mb: int) -> int:
    plan = build_plan(log_cap_mb)
    if plan["problems"]:
        print("disk-capacity reclaim REFUSED: unsafe plan: " + "; ".join(plan["problems"]))
        return 2
    root_fd: int | None = None
    quarantine_fd: int | None = None
    result_fd: int | None = None
    try:
        receipt = load_receipt(receipt_path, plan)
        root_fd = _open_root_dir()
        _consume_receipt(receipt_path, receipt, plan)
        result_fd, result_path, quarantine_fd = _reserve_attempt(receipt, plan, root_fd)
    except ReceiptError as exc:
        _close_quietly(root_fd)
        print(f"disk-capacity reclaim REFUSED: {exc}")
        return 2
    except OSError as exc:
        _close_quietly(root_fd)
        print(f"disk-capacity reclaim REFUSED: attempt reservation failed ({type(exc).__name__})")
        return 2

    effects: list[dict[str, Any]] = []
    status = "applied"
    error: str | None = None
    try:
        for target in plan["targets"]:
            _require_receipt_current(receipt)
            if target["kind"] == "unlink":
                effect = _unlink_exact(target, root_fd, quarantine_fd, receipt)
            elif target["kind"] == "truncate":
                effect = _truncate_exact(target, root_fd, receipt)
            else:
                raise ReceiptError(f"unsupported target kind {target['kind']!r}")
            effects.append(effect)
    except EffectAppliedError as exc:
        effects.append(exc.effect)
        status = "failed_after_effects"
        error = str(exc)
    except (OSError, ReceiptError) as exc:
        status = "failed_after_effects" if effects else "failed_before_effects"
        error = str(exc)

    result = {
        "schema": RESULT_SCHEMA,
        "status": status,
        "attempt_id_hash": _sha256_bytes(receipt["attempt_id"].encode("utf-8")),
        "receipt_hash": receipt["receipt_hash"],
        "plan_hash": plan["plan_hash"],
        "root_id": plan["root_id"],
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "effects": effects,
        "error": error,
    }
    publication_error: str | None = None
    try:
        _write_fd(result_fd, result)
    except Exception as exc:
        publication_error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            os.close(result_fd)
        except OSError as exc:
            publication_error = publication_error or f"{type(exc).__name__}: {exc}"
        _close_quietly(quarantine_fd)
        _close_quietly(root_fd)

    relative_result = result_path.relative_to(ROOT)
    if publication_error:
        emergency = {
            **result,
            "status": "result_publication_failed_after_effects"
            if effects
            else "result_publication_failed_before_effects",
            "result_path": str(relative_result),
            "publication_error": publication_error,
        }
        print("disk-capacity reclaim RESULT PUBLICATION FAILED: " + json.dumps(emergency, sort_keys=True))
        return 1
    print(f"disk-capacity reclaim: {status}; effects={len(effects)}; result={relative_result}")
    return 0 if status == "applied" else 1


def preview(log_cap_mb: int, *, attempt_id: str | None = None, receipt_path: Path | None = None) -> int:
    plan = build_plan(log_cap_mb)
    chosen = attempt_id or f"disk-reclaim-{uuid.uuid4().hex}"
    receipt_status: dict[str, Any]
    if receipt_path is None:
        receipt_status = {
            "schema": RECEIPT_SCHEMA,
            "action": ACTION,
            "root_id": plan["root_id"],
            "plan_hash": plan["plan_hash"],
            "attempt_id": chosen,
            "authorized": False,
            "authorized_by": "",
            "issued_at": "<ISO-8601 UTC issue time>",
            "expires_at": "<ISO-8601 UTC expiry>",
        }
    else:
        try:
            receipt = load_receipt(receipt_path, plan)
        except ReceiptError as exc:
            print(json.dumps({"mode": "preview", "zero_write": True, "receipt_valid": False, "error": str(exc)}))
            return 2
        receipt_status = {
            "receipt_valid": True,
            "attempt_id_hash": _sha256_bytes(receipt["attempt_id"].encode("utf-8")),
            "expires_at": receipt["expires_at"],
        }
    print(
        json.dumps(
            {
                "mode": "preview",
                "zero_write": True,
                "plan": plan,
                "apply_receipt": receipt_status,
            },
            sort_keys=True,
        )
    )
    return 1 if plan["problems"] else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="receipt-bound disk-capacity reclaimer")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="print the exact zero-write reclaim plan")
    modes.add_argument("--apply", action="store_true", help="apply one exact plan; requires --receipt")
    ap.add_argument("--dry-run", action="store_true", help="explicit alias for the zero-write default")
    ap.add_argument("--receipt", type=Path, help=f"{RECEIPT_SCHEMA} JSON receipt")
    ap.add_argument("--attempt-id", help="choose a receipt-template attempt id for preview")
    ap.add_argument(
        "--log-cap-mb",
        type=int,
        default=int(os.environ.get("LIMEN_DISK_LOG_CAP_MB", DEFAULT_LOG_CAP_MB)),
        help=f"truncate heartbeat.err.log above this many MiB (default {DEFAULT_LOG_CAP_MB})",
    )
    args = ap.parse_args(argv)
    if args.log_cap_mb <= 0:
        ap.error("--log-cap-mb must be positive")
    if args.apply and args.dry_run:
        ap.error("--apply and --dry-run are mutually exclusive")
    if args.apply and args.attempt_id:
        ap.error("--attempt-id is preview-only; apply uses the receipt binding")
    if args.apply:
        if args.receipt is None:
            print("disk-capacity reclaim REFUSED: --apply requires --receipt PATH")
            return 2
        return apply(args.receipt, args.log_cap_mb)
    return preview(args.log_cap_mb, attempt_id=args.attempt_id, receipt_path=args.receipt)


if __name__ == "__main__":
    sys.exit(main())
