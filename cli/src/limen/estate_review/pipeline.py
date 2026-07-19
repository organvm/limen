"""End-to-end canonical estate review command."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .config import ReviewConfig
from .model import iso_z
from .reconcile import reconcile_snapshot
from .render import (
    build_artifact,
    build_seal,
    build_validation,
    stable_json,
    validate_artifact_contract,
)
from .sources import NativeCollectors, collect_prompt_atoms

DEFAULT_SNAPSHOT = "2026-07-19T15:11:00Z"
DEFAULT_OUTPUT = Path("docs/reviews/seven-agent-whole-estate-2026-07-19")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def _implementation_digest(root: Path) -> str:
    package = root / "cli" / "src" / "limen" / "estate_review"
    digest = hashlib.sha256()
    paths = list(package.glob("*.py"))
    paths.extend(
        root / relative
        for relative in (
            "cli/src/limen/cli.py",
            "cli/src/limen/execution_contract.py",
            "cli/src/limen/models.py",
            "cli/src/limen/progress.py",
            "cli/src/limen/tabularius.py",
            "scripts/prompt-estate-reconcile.py",
            "scripts/lib/workstream-capsule.sh",
        )
    )
    for path in sorted((path for path in paths if path.is_file()), key=str):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _receipt_links(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Load only explicit owner-link content bindings and proof tuples."""

    path = root / "docs" / "estate-session-review-owner-links.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, list[dict[str, Any]]] = {}
    for row in payload.get("links") or []:
        ask_id = str(row.get("review_ask_id") or row.get("prompt_atom_id") or "")
        receipts: list[str] = []
        if row.get("receipt"):
            receipts.append(str(row["receipt"]))
        if row.get("receipt_target"):
            target = str(row["receipt_target"])
            if target.startswith("https://github.com/") and "/pull/" in target:
                receipts.append(target)
        if ask_id and receipts:
            result[ask_id] = [
                {
                    "url": receipt,
                    "predicate_result": row.get("predicate_result"),
                    "predicate_checked_at": row.get("predicate_checked_at"),
                    "receipt_head_sha": row.get("receipt_head_sha"),
                }
                for receipt in sorted(set(receipts))
            ]
    return result


def _owner_link_summary(
    root: Path,
    asks: list[dict[str, Any]],
    prompt_coverage: dict[str, Any],
) -> dict[str, Any]:
    path = root / "docs" / "estate-session-review-owner-links.json"
    ask_ids = {str(row.get("ask") or "") for row in asks if row.get("ask")}
    scope = prompt_coverage.get("source_scope") or {}
    prompt_exact = bool(
        prompt_coverage.get("available") is True
        and prompt_coverage.get("coverage") != "coverage_unknown"
        and scope.get("scope") == "all"
        and scope.get("target_scope") == "all"
        and scope.get("all_baseline_complete") is True
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "state": "pending",
            "prompt_authority_exact": prompt_exact,
            "asks": len(ask_ids),
            "links": 0,
            "missing": len(ask_ids),
            "duplicates": 0,
            "unknown": 0,
        }
    rows = payload.get("links") if isinstance(payload, dict) else None
    if payload.get("schema") != "limen.estate_session_review_owner_links.v1" or not isinstance(rows, list):
        rows = []
    ids = [str(row.get("prompt_atom_id") or row.get("review_ask_id") or "") for row in rows if isinstance(row, dict)]
    counts = collections.Counter(ids)
    linked = set(ids)
    missing = ask_ids - linked
    unknown = linked - ask_ids
    duplicates = sum(value - 1 for value in counts.values() if value > 1)
    state = "complete" if prompt_exact and not missing and not unknown and not duplicates else "pending"
    return {
        "state": state,
        "prompt_authority_exact": prompt_exact,
        "asks": len(ask_ids),
        "links": len(rows),
        "missing": len(missing),
        "duplicates": duplicates,
        "unknown": len(unknown),
    }


def collect_snapshot(config: ReviewConfig) -> dict[str, Any]:
    """Collect canonical sessions and exact prompt atoms without remote writes."""

    sessions, coverage = NativeCollectors(config).all()
    asks, prompt_coverage = collect_prompt_atoms(config, sessions)
    coverage["prompt_atoms"] = prompt_coverage
    return {
        "schema": "limen.seven_agent_estate_review.v2",
        "snapshot_at": iso_z(config.snapshot_at),
        "windows": [
            {
                "id": window.id,
                "label": window.label,
                "start": iso_z(window.start),
                "end": iso_z(window.end),
                "half_open": True,
                "timezone": config.timezone,
            }
            for window in config.windows
        ],
        "coverage": coverage,
        "asks": asks,
        "_sessions": sessions,
    }


def build_outputs(config: ReviewConfig) -> dict[str, bytes]:
    """Build every tracked review output in memory before writing."""

    snapshot = reconcile_snapshot(
        collect_snapshot(config),
        config,
        receipt_urls_by_ask=_receipt_links(config.root),
    )
    snapshot["owner_link_index"] = _owner_link_summary(
        config.root,
        snapshot.get("asks") or [],
        (snapshot.get("coverage") or {}).get("prompt_atoms") or {},
    )
    artifact = build_artifact(snapshot)
    validation = build_validation(
        snapshot,
        artifact,
        test_path=config.output_dir / "test_model.py",
    )
    artifact_errors = validate_artifact_contract(artifact)
    if artifact_errors or validation["synthetic_tests_result"] != "passed":
        errors = artifact_errors or [validation["synthetic_tests_detail"]]
        raise ValueError("review validation failed: " + "; ".join(errors))
    files = {
        "snapshot.json": stable_json(snapshot),
        "artifact.json": stable_json(artifact),
        "validation.json": stable_json(validation),
    }
    seal = build_seal(
        snapshot,
        files,
        implementation_digest=_implementation_digest(config.root),
    )
    files["../../../estate-session-review-seal.json"] = stable_json(seal)
    return files


def _output_path(config: ReviewConfig, relative: str) -> Path:
    if relative == "../../../estate-session-review-seal.json":
        return config.root / "docs" / "estate-session-review-seal.json"
    return config.output_dir / relative


def write_outputs(config: ReviewConfig, outputs: dict[str, bytes]) -> list[Path]:
    """Write tracked redacted outputs atomically."""

    written: list[Path] = []
    for relative, content in outputs.items():
        path = _output_path(config, relative)
        _atomic_write(path, content)
        written.append(path)
    return written


def check_outputs(config: ReviewConfig, outputs: dict[str, bytes]) -> list[str]:
    """Return byte-level drift without touching output files."""

    drift: list[str] = []
    for relative, expected in outputs.items():
        path = _output_path(config, relative)
        try:
            actual = path.read_bytes()
        except FileNotFoundError:
            drift.append(f"missing:{path.relative_to(config.root)}")
            continue
        if actual != expected:
            drift.append(f"changed:{path.relative_to(config.root)}")
    return drift


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify the canonical frozen whole-estate agent review.")
    parser.add_argument("--snapshot-at", default=DEFAULT_SNAPSHOT)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    output = args.output_dir
    if not output.is_absolute():
        output = root / output
    config = ReviewConfig.from_values(
        root=root,
        snapshot_at=args.snapshot_at,
        output_dir=output,
    )
    try:
        outputs = build_outputs(config)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"estate-review: FAIL: {exc}")
        return 2
    if args.write:
        paths = write_outputs(config, outputs)
        print(f"estate-review: wrote {len(paths)} tracked outputs")
        return 0
    if args.check:
        drift = check_outputs(config, outputs)
        if drift:
            print("estate-review: FAIL: " + ", ".join(drift))
            return 1
        print("estate-review: PASS: frozen outputs are byte-identical")
        return 0
    print(
        json.dumps(
            {
                "snapshot_at": iso_z(config.snapshot_at),
                "outputs": sorted(outputs),
                "write": False,
            },
            indent=2,
        )
    )
    return 0
