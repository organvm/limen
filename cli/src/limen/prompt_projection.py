"""Compact, digest-bound prompt projection chunks.

The prompt journals remain the canonical private corpus.  This module builds a
small public manifest plus private, day-addressable redacted chunks so bounded
consumers do not need to read either the full public projection or the raw
event journal.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

MANIFEST_SCHEMA = "limen.prompt_atom_chunk_manifest.v1"
CHUNK_SCHEMA = "limen.prompt_atom_projection_chunk.v1"
PROJECTION_FORM = "chunk_manifest"
AUTHORITY_SEAL_SCHEMA = "limen.prompt-authority-seal.v1"
AUTHORITY_SEAL_SCHEMA_VERSION = 1
_CHUNK_NAME = re.compile(r"^(?:day-\d{4}-\d{2}-\d{2}|unknown)\.json$")
_UTC = dt.timezone.utc


def canonical_json_bytes(value: Any) -> bytes:
    """Return the compact canonical representation used for chunk hashes."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_authority_seal_binding(
    seal: dict[str, Any],
    projection: dict[str, Any],
    *,
    require_ready: bool,
) -> list[str]:
    """Validate the bounded seal's identity and exact projection binding."""

    errors: list[str] = []
    if seal.get("schema") != AUTHORITY_SEAL_SCHEMA:
        errors.append("prompt authority seal schema is invalid")
    if seal.get("schema_version") != AUTHORITY_SEAL_SCHEMA_VERSION:
        errors.append("prompt authority seal version is stale")
    content_hash = str(seal.get("content_hash") or "")
    material = {key: value for key, value in seal.items() if key != "content_hash"}
    if not content_hash or digest(material) != content_hash:
        errors.append("prompt authority seal digest is invalid")
    if seal.get("public_projection_digest") != projection.get("projection_digest"):
        errors.append("prompt authority seal projection binding is stale")
    if require_ready and seal.get("authority_ready") is not True:
        errors.append("prompt authority seal is not authority-ready")
    return errors


def parse_timestamp(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(_UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bucket(timestamp: Any) -> tuple[str, str | None]:
    parsed = parse_timestamp(timestamp)
    if parsed is None:
        return "unknown", None
    normalized = iso_z(parsed)
    return f"day-{normalized[:10]}", normalized


def redacted_atom_row(atom: dict[str, Any]) -> dict[str, Any]:
    """Return only fields required for bounded review joins.

    Prompt text, evidence coordinates, raw hashes, dependency prose, and local
    paths are deliberately absent.
    """

    outcome = atom.get("outcome")
    outcome = outcome if isinstance(outcome, dict) else {}
    _bucket_name, timestamp = _bucket(atom.get("timestamp"))
    return {
        "atom_id": str(atom.get("atom_id") or ""),
        "occurrence_id": str(atom.get("occurrence_id") or ""),
        "kind": str(atom.get("kind") or "prompt atom"),
        "source": str(atom.get("source") or ""),
        "timestamp": timestamp,
        "owner": atom.get("owner"),
        "owner_route": atom.get("owner_route"),
        "session_ref_hash": str(atom.get("session_ref_hash") or ""),
        "disposition": str(outcome.get("disposition") or "unassessed"),
        "is_current_intent": atom.get("is_current_intent") is True,
    }


def build_chunks(
    atoms: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    """Build deterministic descriptors and payloads keyed by UTC day."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        row = redacted_atom_row(atom)
        if not row["atom_id"]:
            continue
        bucket, _timestamp = _bucket(atom.get("timestamp"))
        grouped[bucket].append(row)

    descriptors: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for bucket in sorted(grouped):
        rows = sorted(
            grouped[bucket],
            key=lambda row: (
                row.get("timestamp") is None,
                str(row.get("timestamp") or ""),
                str(row.get("atom_id") or ""),
            ),
        )
        filename = f"{bucket}.json"
        payload = {
            "schema": CHUNK_SCHEMA,
            "bucket": bucket,
            "rows": rows,
        }
        encoded = canonical_json_bytes(payload)
        timestamps = [str(row["timestamp"]) for row in rows if row.get("timestamp")]
        descriptors.append(
            {
                "bucket": bucket,
                "file": filename,
                "sha256": sha256_bytes(encoded),
                "bytes": len(encoded),
                "row_count": len(rows),
                "current_unresolved_count": sum(
                    1
                    for row in rows
                    if row.get("is_current_intent") and row.get("disposition") not in {"done", "superseded"}
                ),
                "start": min(timestamps) if timestamps else None,
                "end": max(timestamps) if timestamps else None,
            }
        )
        payloads[filename] = encoded
    return descriptors, payloads


def apply_manifest(
    public_header: dict[str, Any],
    descriptors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Turn the normal public header into a compact chunk manifest."""

    manifest = dict(public_header)
    manifest["schema"] = MANIFEST_SCHEMA
    manifest["projection_form"] = PROJECTION_FORM
    manifest["chunk_schema"] = CHUNK_SCHEMA
    manifest["chunks"] = descriptors
    manifest["chunk_count"] = len(descriptors)
    manifest["atom_rows_indexed"] = sum(int(row["row_count"]) for row in descriptors)
    manifest["current_unresolved_atoms_indexed"] = sum(int(row["current_unresolved_count"]) for row in descriptors)
    # These legacy fields remain shape-compatible.  Zero means no rows were
    # dropped: the complete queue lives in the digest-bound chunks.
    manifest["unresolved_atoms"] = []
    manifest["unresolved_atoms_truncated"] = 0
    manifest.pop("projection_digest", None)
    return manifest


def descriptor_files_present(
    manifest: dict[str, Any],
    chunk_root: Path,
) -> bool:
    """Cheap no-content probe used only by the idempotent writer fast path."""

    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        return False
    for descriptor in chunks:
        if not isinstance(descriptor, dict):
            return False
        filename = str(descriptor.get("file") or "")
        if not _CHUNK_NAME.fullmatch(filename):
            return False
        path = chunk_root / filename
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size != descriptor.get("bytes"):
            return False
    return True


def validate_manifest(
    manifest: dict[str, Any],
    chunk_root: Path,
    *,
    verify_content: bool = True,
) -> list[str]:
    """Validate shape, aggregate counts, file boundaries, and chunk digests."""

    errors: list[str] = []
    if manifest.get("schema") != MANIFEST_SCHEMA:
        errors.append("prompt chunk manifest schema is invalid")
    if manifest.get("projection_form") != PROJECTION_FORM:
        errors.append("prompt projection form is not chunk_manifest")
    if manifest.get("chunk_schema") != CHUNK_SCHEMA:
        errors.append("prompt chunk schema is invalid")
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        return [*errors, "prompt chunk descriptors are missing"]
    if manifest.get("chunk_count") != len(chunks):
        errors.append("prompt chunk count does not match descriptors")

    seen_files: set[str] = set()
    row_count = 0
    unresolved_count = 0
    for descriptor in chunks:
        if not isinstance(descriptor, dict):
            errors.append("prompt chunk descriptor is malformed")
            continue
        filename = str(descriptor.get("file") or "")
        if not _CHUNK_NAME.fullmatch(filename) or filename in seen_files:
            errors.append("prompt chunk filename is unsafe or duplicated")
            continue
        seen_files.add(filename)
        path = chunk_root / filename
        try:
            encoded = path.read_bytes() if verify_content else b""
            size = len(encoded) if verify_content else path.stat().st_size
        except OSError:
            errors.append(f"prompt chunk is missing: {filename}")
            continue
        if size != descriptor.get("bytes"):
            errors.append(f"prompt chunk byte count mismatch: {filename}")
        if verify_content:
            if sha256_bytes(encoded) != descriptor.get("sha256"):
                errors.append(f"prompt chunk digest mismatch: {filename}")
                continue
            try:
                payload = json.loads(encoded)
            except (UnicodeDecodeError, json.JSONDecodeError):
                errors.append(f"prompt chunk is malformed: {filename}")
                continue
            rows = payload.get("rows") if isinstance(payload, dict) else None
            if (
                payload.get("schema") != CHUNK_SCHEMA
                or payload.get("bucket") != descriptor.get("bucket")
                or not isinstance(rows, list)
            ):
                errors.append(f"prompt chunk contract mismatch: {filename}")
                continue
            if len(rows) != descriptor.get("row_count"):
                errors.append(f"prompt chunk row count mismatch: {filename}")
        row_count += int(descriptor.get("row_count") or 0)
        unresolved_count += int(descriptor.get("current_unresolved_count") or 0)
    if row_count != manifest.get("atom_rows_indexed"):
        errors.append("prompt manifest atom row total does not reconcile")
    if unresolved_count != manifest.get("current_unresolved_atoms_indexed"):
        errors.append("prompt manifest unresolved row total does not reconcile")
    return errors


def load_window_rows(
    manifest: dict[str, Any],
    chunk_root: Path,
    *,
    start: dt.datetime,
    end: dt.datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Load and verify only chunks intersecting the half-open UTC window."""

    errors = validate_manifest(manifest, chunk_root, verify_content=False)
    if errors:
        return [], errors
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for descriptor in manifest["chunks"]:
        chunk_start = parse_timestamp(descriptor.get("start"))
        chunk_end = parse_timestamp(descriptor.get("end"))
        if chunk_start is not None and chunk_end is not None:
            if chunk_end < start or chunk_start >= end:
                continue
        filename = str(descriptor["file"])
        path = chunk_root / filename
        try:
            encoded = path.read_bytes()
        except OSError:
            errors.append(f"prompt chunk is missing: {filename}")
            continue
        if len(encoded) != descriptor.get("bytes") or sha256_bytes(encoded) != descriptor.get("sha256"):
            errors.append(f"prompt chunk digest mismatch: {filename}")
            continue
        try:
            payload = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"prompt chunk is malformed: {filename}")
            continue
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != CHUNK_SCHEMA
            or payload.get("bucket") != descriptor.get("bucket")
            or not isinstance(payload.get("rows"), list)
        ):
            errors.append(f"prompt chunk contract mismatch: {filename}")
            continue
        for row in payload["rows"]:
            if not isinstance(row, dict):
                errors.append(f"prompt chunk row is malformed: {filename}")
                continue
            timestamp = parse_timestamp(row.get("timestamp"))
            if timestamp is None or not start <= timestamp < end:
                continue
            atom_id = str(row.get("atom_id") or "")
            if not atom_id or atom_id in seen:
                errors.append("prompt chunk atom id is missing or duplicated")
                continue
            seen.add(atom_id)
            rows.append(row)
    rows.sort(key=lambda row: (str(row.get("timestamp") or ""), str(row.get("atom_id") or "")))
    return rows, errors
