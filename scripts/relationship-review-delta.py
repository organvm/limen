#!/usr/bin/env python3
"""PII-clean, zero-write relationship review-due observation.

Limen is only a consumer.  The private relationship owner produces an immutable
Messages snapshot and a coherent review adapter, preserves that bundle in durable
content-addressed custody, and atomically hydrates a private local handoff.  This
script refuses raw database/registry paths and consumes only that verified handoff.

The observation never hydrates, checkpoints, copies, notifies, or writes state.  It
prints only aggregate counts.  Missing, stale, mutable, or locally orphaned custody
is explicit unavailable coverage, never a zero-due result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HANDOFF_SCHEMA = "limen.relationship_review_handoff.v1"
SNAPSHOT_SCHEMA = "relationship.review_snapshot.v1"
ADAPTER_SCHEMA = "relationship.review_adapter.v1"
ARTIFACT_KEYS = frozenset({"adapter", "messages"})
THRESHOLD = 20
MAX_SNAPSHOT_AGE_SECONDS = 8 * 24 * 60 * 60
FUTURE_SKEW_SECONDS = 300
APPLE_EPOCH_OFFSET = 978307200


class HandoffError(ValueError):
    """The private owner handoff is absent, stale, mutable, or unbound."""


def _log_clean(message: str) -> None:
    """Print one PII-clean line suitable for the public heartbeat log."""

    print(f"relationship-review-delta: {message}")


def _coverage_unavailable(*, as_json: bool, threshold: int | None, reason: str) -> int:
    """Report unknown coverage explicitly; unavailable never means zero due."""

    if as_json:
        print(
            json.dumps(
                {
                    "available": False,
                    "checked": 0,
                    "review_due": None,
                    "threshold": threshold,
                    "reason": reason,
                }
            )
        )
    else:
        _log_clean(f"coverage unavailable ({reason}); review-due state is unknown")
    return 0


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"{field} is missing")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HandoffError(f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise HandoffError(f"{field} lacks a timezone")
    return parsed.astimezone(timezone.utc)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_private_path(root: Path, relative: Any, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise HandoffError(f"{label} path is missing")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise HandoffError(f"{label} path is not a safe relative path")

    root = root.resolve(strict=True)
    current = root
    for part in candidate.parts:
        current = current / part
        try:
            current_stat = current.lstat()
        except OSError as exc:
            raise HandoffError(f"{label} is unavailable") from exc
        if stat.S_ISLNK(current_stat.st_mode):
            raise HandoffError(f"{label} path contains a symlink")

    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise HandoffError(f"{label} escapes private handoff custody") from exc
    return resolved


def _private_file_state(path: Path, *, label: str) -> tuple[int, int, int, int]:
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise HandoffError(f"{label} is unavailable") from exc
    if not stat.S_ISREG(file_stat.st_mode) or stat.S_ISLNK(file_stat.st_mode):
        raise HandoffError(f"{label} is not a regular file")
    if file_stat.st_uid != os.geteuid():
        raise HandoffError(f"{label} has the wrong owner")
    if stat.S_IMODE(file_stat.st_mode) & 0o077:
        raise HandoffError(f"{label} is not private")
    if file_stat.st_nlink != 1:
        raise HandoffError(f"{label} is not an isolated hydrated copy")
    return (file_stat.st_dev, file_stat.st_ino, file_stat.st_size, file_stat.st_mtime_ns)


def _read_private_json(path: Path, *, label: str) -> tuple[dict[str, Any], tuple[int, int, int, int], bytes]:
    before = _private_file_state(path, label=label)
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"{label} is not an object")
    if _private_file_state(path, label=label) != before:
        raise HandoffError(f"{label} changed while reading")
    return value, before, payload


def _remote_immutable_uri(value: Any, immutable_ref: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise HandoffError(f"{field} is missing")
    parsed = urlparse(value)
    if not parsed.scheme or parsed.scheme.lower() == "file" or not parsed.netloc:
        raise HandoffError(f"{field} lacks durable remote custody")
    if (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}:
        raise HandoffError(f"{field} points back to the local host")
    if immutable_ref not in value:
        raise HandoffError(f"{field} is not content-addressed")
    return value


def _artifact_contract(value: Any, *, label: str) -> tuple[str, int, str]:
    if not isinstance(value, dict):
        raise HandoffError(f"{label} artifact contract is missing")
    path = value.get("path")
    digest = value.get("sha256")
    size = value.get("bytes")
    if not isinstance(path, str) or not path:
        raise HandoffError(f"{label} artifact path is missing")
    if not isinstance(digest, str) or len(digest) != 64:
        raise HandoffError(f"{label} artifact digest is invalid")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise HandoffError(f"{label} artifact digest is invalid") from exc
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise HandoffError(f"{label} artifact size is invalid")
    return path, size, digest.lower()


def _snapshot_id(artifacts: dict[str, Any]) -> str:
    frozen: dict[str, dict[str, Any]] = {}
    for key in sorted(ARTIFACT_KEYS):
        _path, size, digest = _artifact_contract(artifacts.get(key), label=key)
        frozen[key] = {"bytes": size, "sha256": digest}
    canonical = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{_sha256_bytes(canonical)}"


def _load_handoff(
    handoff_path: Path,
    *,
    now: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    """Validate owner custody and return only exact, private hydrated artifact paths."""

    expanded_handoff = handoff_path.expanduser()
    try:
        _private_file_state(expanded_handoff, label="handoff")
        handoff_path = expanded_handoff.resolve(strict=True)
    except (OSError, HandoffError) as exc:
        raise HandoffError("handoff is unavailable") from exc
    root = handoff_path.parent
    handoff, handoff_state, _handoff_bytes = _read_private_json(handoff_path, label="handoff")
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise HandoffError("handoff schema is invalid")

    source = handoff.get("snapshot_receipt")
    if not isinstance(source, dict):
        raise HandoffError("snapshot receipt binding is missing")
    receipt_path = _safe_private_path(root, source.get("path"), label="snapshot receipt")
    receipt, receipt_state, receipt_bytes = _read_private_json(receipt_path, label="snapshot receipt")
    expected_receipt_digest = source.get("sha256")
    if not isinstance(expected_receipt_digest, str) or _sha256_bytes(receipt_bytes) != expected_receipt_digest:
        raise HandoffError("snapshot receipt digest does not match hydration handoff")

    if receipt.get("schema") != SNAPSHOT_SCHEMA:
        raise HandoffError("snapshot receipt schema is invalid")
    produced_at = _utc_timestamp(receipt.get("produced_at"), "produced_at")
    expires_at = _utc_timestamp(receipt.get("expires_at"), "expires_at")
    hydrated_at = _utc_timestamp(handoff.get("hydrated_at"), "hydrated_at")
    custody = receipt.get("custody")
    if not isinstance(custody, dict) or handoff.get("custody_verification") != "verified":
        raise HandoffError("durable owner custody is unverified")
    custody_verified_at = _utc_timestamp(handoff.get("custody_verified_at"), "custody_verified_at")
    skew = timedelta(seconds=FUTURE_SKEW_SECONDS)
    max_age = timedelta(seconds=max_age_seconds)
    if produced_at > now + skew or custody_verified_at > now + skew or hydrated_at > now + skew:
        raise HandoffError("snapshot custody timestamp is in the future")
    if custody_verified_at + skew < produced_at or hydrated_at + skew < custody_verified_at:
        raise HandoffError("custody and hydration timestamps are out of order")
    if expires_at <= produced_at or now >= expires_at:
        raise HandoffError("snapshot custody is expired")
    if now - produced_at > max_age or now - custody_verified_at > max_age or now - hydrated_at > max_age:
        raise HandoffError("snapshot custody is stale")

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != ARTIFACT_KEYS:
        raise HandoffError("snapshot artifacts are incomplete")
    snapshot_id = _snapshot_id(artifacts)
    if receipt.get("snapshot_id") != snapshot_id or handoff.get("snapshot_id") != snapshot_id:
        raise HandoffError("snapshot identity is unbound")

    if custody.get("immutable_ref") != snapshot_id:
        raise HandoffError("durable owner custody is unbound")
    snapshot_uri = _remote_immutable_uri(custody.get("snapshot_uri"), snapshot_id, field="snapshot_uri")
    receipt_uri = _remote_immutable_uri(custody.get("receipt_uri"), snapshot_id, field="receipt_uri")
    if handoff.get("source_snapshot_uri") != snapshot_uri or handoff.get("source_receipt_uri") != receipt_uri:
        raise HandoffError("hydration source does not match owner custody")

    paths: dict[str, Path] = {}
    states: dict[str, tuple[int, int, int, int]] = {}
    for key in sorted(ARTIFACT_KEYS):
        relative, size, digest = _artifact_contract(artifacts[key], label=key)
        path = _safe_private_path(root, relative, label=key)
        file_state = _private_file_state(path, label=key)
        if file_state[2] != size or _sha256_file(path) != digest:
            raise HandoffError(f"{key} artifact does not match owner receipt")
        if _private_file_state(path, label=key) != file_state:
            raise HandoffError(f"{key} artifact changed while hashing")
        paths[key] = path
        states[key] = file_state

    if _private_file_state(handoff_path, label="handoff") != handoff_state:
        raise HandoffError("handoff changed during validation")
    if _private_file_state(receipt_path, label="snapshot receipt") != receipt_state:
        raise HandoffError("snapshot receipt changed during validation")

    return {
        "paths": paths,
        "states": states,
        "control_paths": {"handoff": handoff_path, "receipt": receipt_path},
        "control_states": {"handoff": handoff_state, "receipt": receipt_state},
    }


def _review_subjects(adapter: Path) -> list[tuple[str, list[str], str]]:
    value, _state, _payload = _read_private_json(adapter, label="adapter")
    if value.get("schema") != ADAPTER_SCHEMA or not isinstance(value.get("people"), list):
        raise HandoffError("adapter schema is invalid")

    out: list[tuple[str, list[str], str]] = []
    seen: set[str] = set()
    for person in value["people"]:
        if not isinstance(person, dict):
            raise HandoffError("adapter person is invalid")
        slug = person.get("slug")
        handles = person.get("handles")
        last_review = person.get("last_review")
        if not isinstance(slug, str) or not slug or Path(slug).name != slug or slug in {".", ".."} or slug in seen:
            raise HandoffError("adapter person identity is invalid")
        if (
            not isinstance(handles, list)
            or not handles
            or any(not isinstance(item, str) or not item for item in handles)
        ):
            raise HandoffError("adapter handles are invalid")
        if not isinstance(last_review, str) or not last_review:
            raise HandoffError("adapter review cursor is invalid")
        seen.add(slug)
        out.append((slug, list(dict.fromkeys(handles)), last_review))
    return out


def _apple_ns_since(cursor: str) -> int:
    """Convert an owner cursor to the Apple Core Data nanosecond boundary."""

    parsed = datetime.fromisoformat(cursor)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return int((parsed.timestamp() - APPLE_EPOCH_OFFSET) * 1_000_000_000)


def _sqlite_companions(chat_db: Path) -> tuple[Path, ...]:
    return tuple(chat_db.with_name(f"{chat_db.name}{suffix}") for suffix in ("-wal", "-shm", "-journal"))


def _open_chat_db(chat_db: Path) -> sqlite3.Connection:
    """Open only a stable owner snapshot; never participate in a live WAL protocol."""

    if any(path.exists() for path in _sqlite_companions(chat_db)):
        raise sqlite3.OperationalError("immutable snapshot has mutable SQLite companions")
    uri = f"{chat_db.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only = ON")
        state = connection.execute("PRAGMA query_only").fetchone()
        if not state or int(state[0]) != 1:
            raise sqlite3.OperationalError("query_only could not be enabled")
    except Exception:
        connection.close()
        raise
    return connection


def _count_new_inbound(chat_db: Path, handles: list[str], since_ns: int) -> int:
    connection = _open_chat_db(chat_db)
    try:
        placeholders = ",".join("?" for _ in handles)
        sql = (
            f"SELECT COUNT(*) FROM message m JOIN handle h ON m.handle_id = h.ROWID "
            f"WHERE h.id IN ({placeholders}) AND m.is_from_me = 0 AND m.date > ?"
        )
        row = connection.execute(sql, [*handles, since_ns]).fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def _unchanged(bundle: dict[str, Any]) -> bool:
    for key, path in bundle["paths"].items():
        if _private_file_state(path, label=key) != bundle["states"][key]:
            return False
    for key, path in bundle["control_paths"].items():
        if _private_file_state(path, label=key) != bundle["control_states"][key]:
            return False
    if any(path.exists() for path in _sqlite_companions(bundle["paths"]["messages"])):
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Relationship review-due observation (zero-write consumer).")
    parser.add_argument("--json", action="store_true", help="print a machine-readable count-only summary")
    parser.add_argument(
        "--handoff",
        type=Path,
        default=None,
        help="private owner hydration handoff (or LIMEN_RELATIONSHIP_REVIEW_HANDOFF)",
    )
    args = parser.parse_args(argv)

    threshold: int | None = None
    try:
        threshold = _positive_int_env("LIMEN_RELATIONSHIP_REVIEW_THRESHOLD", THRESHOLD)
        max_age_seconds = _positive_int_env(
            "LIMEN_RELATIONSHIP_REVIEW_MAX_SNAPSHOT_AGE_SECONDS",
            MAX_SNAPSHOT_AGE_SECONDS,
        )
        handoff_raw = args.handoff or os.environ.get("LIMEN_RELATIONSHIP_REVIEW_HANDOFF")
        if not handoff_raw:
            return _coverage_unavailable(as_json=args.json, threshold=threshold, reason="handoff_missing")

        bundle = _load_handoff(
            Path(handoff_raw),
            now=datetime.now(timezone.utc),
            max_age_seconds=max_age_seconds,
        )
        subjects = _review_subjects(bundle["paths"]["adapter"])
        results: list[bool] = []
        for _slug, handles, cursor in subjects:
            count = _count_new_inbound(bundle["paths"]["messages"], handles, _apple_ns_since(cursor))
            results.append(count >= threshold)
        if not _unchanged(bundle):
            raise HandoffError("snapshot changed during observation")

        due = sum(results)
        if args.json:
            print(
                json.dumps(
                    {
                        "available": True,
                        "checked": len(results),
                        "review_due": due,
                        "threshold": threshold,
                    }
                )
            )
        else:
            _log_clean(f"{due}/{len(results)} people review-due (>= {threshold} new inbound since last review)")
        return 0
    except (HandoffError, sqlite3.Error):
        return _coverage_unavailable(as_json=args.json, threshold=threshold, reason="snapshot_unavailable")
    except Exception as exc:  # noqa: BLE001 - heartbeat safety; never print private exception text
        return _coverage_unavailable(
            as_json=args.json,
            threshold=threshold,
            reason=f"internal_{type(exc).__name__.lower()}",
        )


if __name__ == "__main__":
    sys.exit(main())
