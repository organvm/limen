#!/usr/bin/env python3
"""Verify and project the cross-repository governance-memory receipts.

Limen is a scheduler and redacted read model in this lane.  It does not parse
raw conversations, decide constitutional authority, or rebuild the lineage
graph.  Those owner artifacts are supplied through parameter-registry paths;
this verifier checks their snapshot coherence, coverage arithmetic, bounded
cadence receipts, and public projection without copying private bodies.

The generated receipt deliberately contains no wall-clock timestamp.  An
unchanged frozen snapshot therefore produces byte-identical output and
``--write`` emits no filesystem change on a fixed-point rerun.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
).expanduser()
PUBLIC_OUT = Path(
    os.environ.get("LIMEN_GOV_READINESS_OUT", ROOT / "logs" / "governance-memory-readiness.json")
).expanduser()
PRIVATE_OUT = PRIVATE_ROOT / "lifecycle" / "governance-memory-readiness.private.json"
DOC_OUT = ROOT / "docs" / "governance-memory-readiness.md"
DEFAULT_MAX_INPUT_BYTES = int(os.environ.get("LIMEN_GOV_INPUT_MAX_BYTES", str(8 * 1024 * 1024)))

CADENCE_STAGES: tuple[str, ...] = (
    "discover",
    "snapshot",
    "parse",
    "classify",
    "reconcile",
    "distill",
    "validate",
    "render",
    "receipt",
)

CLASSIFICATION_STATUSES: tuple[str, ...] = (
    "acquired",
    "parsed",
    "quarantined",
    "inaccessible",
    "missing-expected",
    "owner-blocked",
)

SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$")


@dataclass(frozen=True)
class InputSpec:
    key: str
    env: str
    contract: str
    snapshot_required: bool = False


INPUT_SPECS: tuple[InputSpec, ...] = (
    InputSpec("source_census", "LIMEN_GOV_SOURCE_CENSUS", "source-census.v1", True),
    InputSpec("source_envelopes", "LIMEN_GOV_SOURCE_ENVELOPES", "source-envelope.v1", True),
    InputSpec("lineage_graph", "LIMEN_GOV_LINEAGE_GRAPH", "lineage-graph.v1", True),
    InputSpec("governance_testament", "LIMEN_GOV_TESTAMENT", "governance-testament.v1"),
    InputSpec("assertion_evidence", "LIMEN_GOV_ASSERTION_EVIDENCE", "assertion-evidence.v1"),
    InputSpec("coverage_receipt", "LIMEN_GOV_COVERAGE_RECEIPT", "coverage-receipt.v1", True),
    InputSpec("iceberg_atlas", "LIMEN_GOV_ICEBERG_ATLAS", "iceberg-atlas.v1", True),
    InputSpec("self_images", "LIMEN_GOV_SELF_IMAGES", "node-self-image.v1"),
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_value(value: Any) -> str:
    return digest_bytes(canonical_json(value).encode("utf-8"))


def safe_token(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    if SAFE_TOKEN.fullmatch(text):
        return text
    return f"sha256:{digest_bytes(text.encode('utf-8', errors='replace'))[:20]}"


def nested_get(value: Any, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current = value
        for key in path:
            if not isinstance(current, Mapping) or key not in current:
                break
            current = current[key]
        else:
            return current
    return None


def as_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def configured_inputs(environ: Mapping[str, str] | None = None) -> dict[str, Path | None]:
    source = os.environ if environ is None else environ
    configured: dict[str, Path | None] = {}
    for spec in INPUT_SPECS:
        raw = str(source.get(spec.env, "")).strip()
        configured[spec.key] = Path(os.path.expandvars(raw)).expanduser() if raw else None
    return configured


def decode_document(raw: bytes, path: Path) -> Any:
    text = raw.decode("utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def load_input(path: Path | None, *, max_bytes: int) -> tuple[Any | None, dict[str, Any]]:
    if path is None:
        return None, {"state": "missing-configuration"}
    try:
        stat = path.stat()
    except OSError as exc:
        return None, {"state": "inaccessible", "diagnostic": type(exc).__name__}
    if not path.is_file():
        return None, {"state": "inaccessible", "diagnostic": "not-a-file"}
    if stat.st_size > max_bytes:
        return None, {
            "state": "quarantined",
            "diagnostic": "input-byte-limit-exceeded",
            "size_bytes": stat.st_size,
            "max_bytes": max_bytes,
        }
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, {"state": "inaccessible", "diagnostic": type(exc).__name__}
    try:
        document = decode_document(raw, path)
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return None, {
            "state": "quarantined",
            "diagnostic": type(exc).__name__,
            "sha256": digest_bytes(raw),
            "size_bytes": len(raw),
        }
    if not isinstance(document, (dict, list)):
        return None, {
            "state": "quarantined",
            "diagnostic": "root-must-be-object-or-array",
            "sha256": digest_bytes(raw),
            "size_bytes": len(raw),
        }
    return document, {
        "state": "available",
        "sha256": digest_bytes(raw),
        "size_bytes": len(raw),
    }


def extract_snapshot_ids(document: Any) -> list[str]:
    records = document if isinstance(document, list) else [document]
    values: set[str] = set()
    for record in records:
        value = nested_get(
            record,
            ("snapshot_id",),
            ("frozen_snapshot_id",),
            ("snapshot", "id"),
            ("metadata", "snapshot_id"),
            ("coverage", "snapshot_id"),
            ("custody_snapshot", "snapshot_id"),
        )
        token = safe_token(value)
        if token:
            values.add(token)
    return sorted(values)


def extract_contract_ids(document: Any) -> list[str]:
    records = document if isinstance(document, list) else [document]
    values: set[str] = set()
    for record in records:
        value = nested_get(
            record,
            ("contract_name",),
            ("schema_version",),
            ("contract",),
            ("contract_id",),
            ("schema_id",),
            ("$schema",),
        )
        token = safe_token(value)
        if token:
            values.add(token)
    return sorted(values)


def contract_matches(declared: Iterable[str], expected: str) -> bool:
    values = list(declared)
    if not values:
        return True
    for declared_id in values:
        normalized = declared_id.rstrip("/#")
        if not (
            normalized == expected
            or normalized.endswith(f"/{expected}")
            or normalized.endswith(f"#{expected}")
        ):
            return False
    return True


def normalize_status_counts(document: Any) -> dict[str, int]:
    raw = nested_get(
        document,
        ("counts",),
        ("status_counts",),
        ("coverage", "counts"),
        ("coverage", "status_counts"),
    )
    if not isinstance(raw, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key, value in raw.items():
        normalized = str(key).strip().lower().replace("_", "-")
        number = as_nonnegative_int(value)
        if number is not None:
            counts[normalized] = number
    return counts


def coverage_projection(document: Any) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    counts = normalize_status_counts(document)
    raw_denominator = nested_get(
        document,
        ("denominator",),
        ("dynamic_denominator",),
        ("coverage", "denominator"),
        ("coverage", "dynamic_denominator"),
    )
    if isinstance(raw_denominator, Mapping):
        raw_denominator = raw_denominator.get("count")
    denominator = as_nonnegative_int(raw_denominator)
    assigned = sum(counts.get(status, 0) for status in CLASSIFICATION_STATUSES)
    unassessed = counts.get("unassessed")
    if unassessed is None:
        unassessed = as_nonnegative_int(nested_get(document, ("unassessed",), ("coverage", "unassessed"))) or 0
    duplicate_assignments = as_nonnegative_int(
        nested_get(document, ("duplicate_assignments",), ("coverage", "duplicate_assignments"))
    ) or 0
    sources = document.get("sources") if isinstance(document, Mapping) else None
    if isinstance(sources, list):
        source_ids = [
            item.get("source_id", item.get("unit_id"))
            for item in sources
            if isinstance(item, Mapping)
        ]
        duplicate_assignments += len(source_ids) - len(set(source_ids))
        if denominator is not None and len(sources) != denominator:
            issues.append("coverage-source-count-mismatch")
        expected_counts = Counter(
            str(item.get("status") or "").replace("_", "-")
            for item in sources
            if isinstance(item, Mapping)
        )
        if any(counts.get(status, 0) != expected_counts.get(status, 0) for status in CLASSIFICATION_STATUSES):
            issues.append("coverage-status-counts-mismatch")
    residual_count = sum(counts.get(status, 0) for status in CLASSIFICATION_STATUSES if status != "parsed")
    residuals = document.get("residual_owners") if isinstance(document, Mapping) else None
    routing_complete = isinstance(residuals, list) and len(residuals) == residual_count
    residual_ids: list[Any] = []
    if isinstance(residuals, list):
        for residual in residuals:
            if not isinstance(residual, Mapping):
                routing_complete = False
                continue
            residual_id = residual.get("source_id", residual.get("unit_id"))
            residual_ids.append(residual_id)
            if not all(residual.get(field) for field in ("owner_reference", "failed_predicate", "next_action")):
                routing_complete = False
        if len(residual_ids) != len(set(residual_ids)):
            routing_complete = False
    if isinstance(sources, list):
        expected_residual_ids = {
            item.get("source_id", item.get("unit_id"))
            for item in sources
            if isinstance(item, Mapping) and item.get("status") != "parsed"
        }
        if set(residual_ids) != expected_residual_ids:
            routing_complete = False
    if not routing_complete:
        issues.append("coverage-residual-owner-routing-incomplete")
    computed_exact = (
        denominator is not None
        and assigned == denominator
        and unassessed == 0
        and duplicate_assignments == 0
        and routing_complete
    )
    declared_exact = nested_get(document, ("exact_all",), ("coverage", "exact_all"))
    if not isinstance(declared_exact, bool):
        issues.append("coverage-exact-all-missing")
        declared_exact = False
    if denominator is None:
        issues.append("coverage-denominator-missing")
    elif assigned != denominator:
        issues.append("coverage-denominator-mismatch")
    if unassessed:
        issues.append("coverage-unassessed-nonzero")
    if duplicate_assignments:
        issues.append("coverage-duplicate-classification")
    if declared_exact != computed_exact:
        issues.append("coverage-exact-all-contradicts-counts")
    computed_ready = computed_exact and residual_count == 0
    declared_ready = nested_get(document, ("ready",), ("coverage", "ready"))
    if not isinstance(declared_ready, bool):
        issues.append("coverage-ready-missing")
        declared_ready = False
    if declared_ready != computed_ready:
        issues.append("coverage-ready-contradicts-counts")
    return (
        {
            "denominator": denominator,
            "classified_once": assigned,
            "status_counts": {key: counts[key] for key in sorted(counts)},
            "unassessed": unassessed,
            "duplicate_assignments": duplicate_assignments,
            "exact_all": bool(declared_exact and computed_exact),
            "ready": bool(declared_ready and computed_ready),
            "residual_count": residual_count,
        },
        issues,
    )


def source_census_projection(document: Any) -> tuple[dict[str, Any], list[str]]:
    if isinstance(document, list):
        records = document
    elif isinstance(document, Mapping) and isinstance(document.get("sources"), list):
        records = document["sources"]
    else:
        records = []
    issues: list[str] = []
    ids: list[Any] = []
    statuses: Counter[str] = Counter()
    routed_residuals = 0
    for index, item in enumerate(records):
        if not isinstance(item, Mapping):
            issues.append(f"source-census-invalid-record:{index}")
            continue
        unit_id = item.get("unit_id", item.get("source_id"))
        ids.append(unit_id)
        status = str(item.get("status") or "").replace("_", "-")
        statuses[status] += 1
        if status not in CLASSIFICATION_STATUSES:
            issues.append(f"source-census-invalid-status:{index}")
        if status != "parsed":
            blocker_data = item.get("blocker") if isinstance(item.get("blocker"), Mapping) else item
            if all(blocker_data.get(field) for field in ("owner_reference", "failed_predicate", "next_action")):
                routed_residuals += 1
            else:
                issues.append(f"source-census-unrouted-residual:{index}")
    duplicates = len(ids) - len(set(ids))
    if duplicates:
        issues.append("source-census-duplicate-unit-id")
    return {
        "denominator": len(records),
        "status_counts": {key: statuses[key] for key in sorted(statuses)},
        "duplicate_assignments": duplicates,
        "routed_residuals": routed_residuals,
    }, issues


def iter_records(document: Any, keys: Iterable[str]) -> list[Any]:
    if isinstance(document, list):
        return document
    if not isinstance(document, Mapping):
        return []
    for key in keys:
        value = document.get(key)
        if isinstance(value, list):
            return value
    return []


def collect_stage_receipts(documents: Iterable[Any]) -> dict[str, dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, Mapping):
            continue
        candidates: list[Any] = []
        for key in ("stage_receipts", "stages"):
            value = document.get(key)
            if isinstance(value, list):
                candidates.extend(value)
        cadence = document.get("cadence")
        if isinstance(cadence, Mapping):
            for key in ("stage_receipts", "stages"):
                value = cadence.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
        for item in candidates:
            if not isinstance(item, Mapping):
                continue
            stage = str(item.get("stage") or item.get("phase") or item.get("id") or "").strip().lower()
            if stage in CADENCE_STAGES:
                collected[stage] = dict(item)
    return collected


def cadence_projection(documents: Iterable[Any]) -> tuple[dict[str, Any], list[str]]:
    receipts = collect_stage_receipts(documents)
    issues: list[str] = []
    observed: list[dict[str, Any]] = []
    successful = {"ok", "done", "complete", "completed"}
    for stage in CADENCE_STAGES:
        item = receipts.get(stage)
        if item is None:
            issues.append(f"cadence-stage-missing:{stage}")
            observed.append({"stage": stage, "status": "missing"})
            continue
        status = str(item.get("status") or "unknown").lower()
        cursor = item.get("cursor", item.get("resume_cursor", item.get("output_cursor")))
        limit = item.get("limit", item.get("work_limit", item.get("max_items")))
        receipt_id = item.get("receipt_id", item.get("digest", item.get("sha256")))
        bounded = item.get("bounded") is True or as_nonnegative_int(limit) is not None
        resumable = cursor is not None
        idempotent = receipt_id is not None
        if status not in successful:
            issues.append(f"cadence-stage-not-complete:{stage}")
        if not bounded:
            issues.append(f"cadence-stage-unbounded:{stage}")
        if not resumable:
            issues.append(f"cadence-stage-cursor-missing:{stage}")
        if not idempotent:
            issues.append(f"cadence-stage-receipt-missing:{stage}")
        observed.append(
            {
                "stage": stage,
                "status": safe_token(status, "unknown"),
                "bounded": bounded,
                "resumable": resumable,
                "idempotent": idempotent,
            }
        )
    return {
        "required_order": list(CADENCE_STAGES),
        "observed": observed,
        "complete": not issues,
    }, issues


def assertion_projection(document: Any) -> tuple[dict[str, Any], list[str]]:
    if isinstance(document, Mapping) and document.get("assertion_id"):
        records = [document]
    else:
        records = iter_records(document, ("assertions", "records", "items"))
    issues: list[str] = []
    class_counts: dict[str, int] = {}
    verified = 0
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            issues.append(f"assertion-invalid-record:{index}")
            continue
        assertion_class = str(record.get("assertion_class") or record.get("class") or "unknown")
        class_counts[assertion_class] = class_counts.get(assertion_class, 0) + 1
        state = str(record.get("verification_state") or record.get("state") or "unverified").lower()
        groups = record.get("independence_groups", record.get("evidence_groups", []))
        if not isinstance(groups, list):
            groups = []
        evidence = record.get("evidence_references")
        evidence_types: set[str] = set()
        if isinstance(evidence, list):
            groups = [
                item.get("independence_group")
                for item in evidence
                if isinstance(item, Mapping) and item.get("independence_group")
            ]
            evidence_types = {
                str(item.get("evidence_type"))
                for item in evidence
                if isinstance(item, Mapping) and item.get("evidence_type")
            }
        group_count = len({canonical_json(item) for item in groups})
        if assertion_class in {"external_fact", "external-fact"} and group_count < 2:
            issues.append(f"assertion-independent-evidence-insufficient:{index}")
        if assertion_class in {"operator_directive", "operator-directive"}:
            required = {"immutable_source_event", "ratified_constitutional_record"}
            if not required.issubset(evidence_types):
                issues.append(f"assertion-operator-authority-incomplete:{index}")
        if assertion_class in {"current_state", "current-state"}:
            required = {"owner_record", "fresh_verifier_receipt"}
            freshness = record.get("freshness")
            if not required.issubset(evidence_types) or not (
                isinstance(freshness, Mapping) and freshness.get("status") == "fresh"
            ):
                issues.append(f"assertion-current-state-evidence-incomplete:{index}")
        if state == "verified":
            verified += 1
        elif state not in {"unverified", "blocked", "superseded"}:
            issues.append(f"assertion-verification-state-invalid:{index}")
    return {
        "total": len(records),
        "verified": verified,
        "class_counts": {key: class_counts[key] for key in sorted(class_counts)},
    }, issues


def atlas_projection(document: Any) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        return {
            "status": "missing",
            "zoom_levels": [],
            "timeline_counts": {"operator_intent": 0, "artifact": 0},
            "ideal_forms": [],
            "self_image_count": 0,
        }
    raw_zoom = document.get("zoom_levels", nested_get(document, ("atlas", "zoom_levels")))
    zoom_levels: list[dict[str, Any]] = []
    if isinstance(raw_zoom, list):
        for index, item in enumerate(raw_zoom[:12]):
            if isinstance(item, Mapping):
                level_id = item.get("id", item.get("level", index))
                count = as_nonnegative_int(item.get("node_count", item.get("count"))) or 0
            else:
                level_id = item
                count = 0
            zoom_levels.append({"id": safe_token(level_id, str(index)), "node_count": count})
    timeline_counts = {"operator_intent": 0, "artifact": 0}
    timelines = document.get("timelines")
    if isinstance(timelines, Mapping):
        for public_key, aliases in {
            "operator_intent": ("operator_intent", "operator-intent", "intent"),
            "artifact": ("artifact", "artifacts"),
        }.items():
            for alias in aliases:
                value = timelines.get(alias)
                if isinstance(value, list):
                    timeline_counts[public_key] = len(value)
                    break
                if isinstance(value, Mapping):
                    timeline_counts[public_key] = as_nonnegative_int(value.get("count")) or 0
                    break
                number = as_nonnegative_int(value)
                if number is not None:
                    timeline_counts[public_key] = number
                    break
    ideal_forms: list[dict[str, Any]] = []
    for index, item in enumerate(iter_records(document, ("ideal_forms", "ideals"))[:100]):
        if not isinstance(item, Mapping):
            continue
        distance = item.get("distance_to_ideal", item.get("distance"))
        if isinstance(distance, str):
            distance = safe_token(distance, "unknown")
        elif not isinstance(distance, (int, float)) or isinstance(distance, bool):
            distance = None
        ideal_forms.append(
            {
                "id": safe_token(item.get("id"), f"ideal-{index}"),
                "implementation_state": safe_token(item.get("implementation_state", item.get("state")), "unknown"),
                "distance_to_ideal": distance,
                "citation_debt": as_nonnegative_int(item.get("citation_debt")) or 0,
            }
        )
    raw_self_images = document.get("self_images", document.get("node_self_images"))
    if isinstance(raw_self_images, list):
        self_image_count = len(raw_self_images)
    elif isinstance(raw_self_images, Mapping):
        self_image_count = as_nonnegative_int(raw_self_images.get("count")) or len(raw_self_images)
    else:
        self_image_count = as_nonnegative_int(document.get("self_image_count")) or 0
    return {
        "status": "ok",
        "zoom_levels": zoom_levels,
        "timeline_counts": timeline_counts,
        "ideal_forms": ideal_forms,
        "self_image_count": self_image_count,
    }


def blocker(spec: InputSpec, state: str, diagnostic: str | None = None) -> dict[str, Any]:
    suffix = f":{diagnostic}" if diagnostic else ""
    return {
        "id": f"owner-receipt:{spec.key}:{state}{suffix}",
        "input": spec.key,
        "owner_reference": f"parameter-contract:{spec.env}",
        "failed_predicate": f"{spec.contract} input state is {state}",
        "next_command": f'{spec.env}="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict',
    }


def build_readiness(
    input_paths: Mapping[str, Path | None] | None = None,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = dict(configured_inputs() if input_paths is None else input_paths)
    documents: dict[str, Any] = {}
    public_inputs: dict[str, dict[str, Any]] = {}
    private_paths: dict[str, str | None] = {}
    blockers: list[dict[str, Any]] = []
    violations: list[str] = []
    snapshots: dict[str, str] = {}

    for spec in INPUT_SPECS:
        path = paths.get(spec.key)
        private_paths[spec.key] = str(path) if path is not None else None
        document, metadata = load_input(path, max_bytes=max_input_bytes)
        public_metadata = dict(metadata)
        public_metadata["contract"] = spec.contract
        if document is not None:
            documents[spec.key] = document
            snapshot_ids = extract_snapshot_ids(document)
            declared_contracts = extract_contract_ids(document)
            public_metadata["snapshot_id"] = snapshot_ids[0] if len(snapshot_ids) == 1 else None
            public_metadata["declared_contract"] = declared_contracts[0] if len(declared_contracts) == 1 else declared_contracts
            if len(snapshot_ids) == 1:
                snapshots[spec.key] = snapshot_ids[0]
            elif len(snapshot_ids) > 1:
                violations.append(f"snapshot-id-mismatch:{spec.key}")
            elif spec.snapshot_required:
                violations.append(f"snapshot-id-missing:{spec.key}")
            if not contract_matches(declared_contracts, spec.contract):
                violations.append(f"contract-mismatch:{spec.key}")
        else:
            blockers.append(blocker(spec, str(metadata["state"]), metadata.get("diagnostic")))
        public_inputs[spec.key] = public_metadata

    snapshot_values = sorted(set(snapshots.values()))
    if len(snapshot_values) > 1:
        violations.append("snapshot-id-mismatch")
    snapshot_id = snapshot_values[0] if len(snapshot_values) == 1 else None

    coverage_document = documents.get("coverage_receipt")
    if coverage_document is not None:
        coverage, coverage_issues = coverage_projection(coverage_document)
        violations.extend(coverage_issues)
    else:
        coverage = {
            "denominator": None,
            "classified_once": 0,
            "status_counts": {},
            "unassessed": 0,
            "duplicate_assignments": 0,
            "exact_all": False,
            "ready": False,
            "residual_count": len(blockers),
        }

    census, census_issues = source_census_projection(documents.get("source_census"))
    violations.extend(census_issues)
    if coverage_document is not None and documents.get("source_census") is not None:
        if coverage["denominator"] != census["denominator"]:
            violations.append("source-census-coverage-denominator-mismatch")
        for status in CLASSIFICATION_STATUSES:
            if coverage["status_counts"].get(status, 0) != census["status_counts"].get(status, 0):
                violations.append("source-census-coverage-status-mismatch")
                break

    cadence, cadence_issues = cadence_projection(documents.values())
    violations.extend(cadence_issues)
    assertions, assertion_issues = assertion_projection(documents.get("assertion_evidence"))
    violations.extend(assertion_issues)
    atlas = atlas_projection(documents.get("iceberg_atlas"))

    available_count = sum(1 for item in public_inputs.values() if item["state"] == "available")
    hard_failures = [
        value
        for value in violations
        if value.startswith(
            (
                "snapshot-id-missing",
                "snapshot-id-mismatch",
                "contract-mismatch",
                "coverage-",
                "source-census-",
                "assertion-",
            )
        )
    ]
    if hard_failures:
        status = "blocked"
    elif (
        available_count == len(INPUT_SPECS)
        and coverage["exact_all"]
        and coverage["ready"]
        and cadence["complete"]
    ):
        status = "ready"
    else:
        status = "degraded"

    core: dict[str, Any] = {
        "$schema": "governance-memory-readiness.v1",
        "surface": "redacted-read-model",
        "status": status,
        "snapshot_id": snapshot_id,
        "inputs": public_inputs,
        "coverage": coverage,
        "source_census": census,
        "cadence": cadence,
        "assertions": assertions,
        "atlas": atlas,
        "blockers": sorted(blockers, key=lambda item: item["id"]),
        "violations": sorted(set(violations)),
    }
    input_fingerprint = digest_value({key: value.get("sha256") for key, value in public_inputs.items()})
    core["input_fingerprint"] = input_fingerprint
    core["receipt_id"] = f"sha256:{digest_value(core)}"
    private = {
        **core,
        "privacy": {
            "contains_raw_bodies": False,
            "configured_input_paths": private_paths,
            "public_output": str(PUBLIC_OUT),
        },
    }
    return core, private


def render_markdown(receipt: Mapping[str, Any]) -> str:
    coverage = receipt["coverage"]
    atlas = receipt["atlas"]
    lines = [
        "# Governance Memory Readiness",
        "",
        "> Limen is the bounded scheduler and redacted read model. Constitutional, custody, lineage, and compiler owners remain authoritative for their own receipts.",
        "",
        f"- Status: `{receipt['status']}`",
        f"- Snapshot: `{receipt.get('snapshot_id') or 'not-coherent'}`",
        f"- Receipt: `{receipt['receipt_id']}`",
        f"- Exact classification: `{coverage['exact_all']}` ({coverage['classified_once']} / {coverage.get('denominator')})",
        f"- Operationally ready: `{coverage['ready']}`",
        f"- Visible residuals: `{coverage['residual_count']}`",
        "",
        "## Owner Inputs",
        "",
        "| Input | Contract | State | Snapshot |",
        "|---|---|---|---|",
    ]
    for key, item in receipt["inputs"].items():
        lines.append(
            f"| `{key}` | `{item['contract']}` | `{item['state']}` | `{item.get('snapshot_id') or '—'}` |"
        )
    lines.extend(
        [
            "",
            "## Iceberg Atlas Projection",
            "",
            f"- Operator-intent events: `{atlas['timeline_counts']['operator_intent']}`",
            f"- Artifact events: `{atlas['timeline_counts']['artifact']}`",
            f"- Ideal forms: `{len(atlas['ideal_forms'])}`",
            f"- Node self-images: `{atlas['self_image_count']}`",
            "",
            "## Bounded Cadence",
            "",
            "`discover → snapshot → parse → classify → reconcile → distill → validate → render → receipt`",
            "",
        ]
    )
    if receipt["blockers"]:
        lines.extend(["## Owner Blockers", ""])
        for item in receipt["blockers"]:
            lines.append(
                f"- `{item['id']}` — owner `{item['owner_reference']}`; predicate `{item['failed_predicate']}`; next: `{item['next_command']}`."
            )
        lines.append("")
    if receipt["violations"]:
        lines.extend(["## Validation Debt", ""])
        lines.extend(f"- `{item}`" for item in receipt["violations"])
        lines.append("")
    lines.extend(
        [
            "## Fixed-point Predicate",
            "",
            "Run twice with the same configured owner receipts. The public JSON, private JSON, Markdown, input fingerprint, and receipt ID must remain byte-identical; `--write` reports no changed files on the second run.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_if_changed(path: Path, content: str) -> bool:
    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def write_outputs(public: Mapping[str, Any], private: Mapping[str, Any], markdown: str) -> list[str]:
    changed: list[str] = []
    outputs = (
        (PUBLIC_OUT, json.dumps(public, indent=2, sort_keys=True) + "\n"),
        (PRIVATE_OUT, json.dumps(private, indent=2, sort_keys=True) + "\n"),
        (DOC_OUT, markdown),
    )
    for path, content in outputs:
        if write_if_changed(path, content):
            changed.append(str(path))
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write deterministic public/private receipts")
    parser.add_argument("--json", action="store_true", help="print the redacted receipt")
    parser.add_argument("--strict", action="store_true", help="exit nonzero unless the receipt is ready")
    parser.add_argument(
        "--max-input-bytes",
        type=int,
        default=DEFAULT_MAX_INPUT_BYTES,
        help="finite byte limit applied independently to every owner receipt",
    )
    args = parser.parse_args(argv)
    if args.max_input_bytes <= 0:
        parser.error("--max-input-bytes must be positive")
    public, private = build_readiness(max_input_bytes=args.max_input_bytes)
    markdown = render_markdown(public)
    changed: list[str] = []
    if args.write:
        changed = write_outputs(public, private, markdown)
    if args.json:
        print(json.dumps(public, indent=2, sort_keys=True))
    else:
        print(
            "governance-memory-readiness: "
            f"{public['status']}; snapshot={public.get('snapshot_id') or 'none'}; "
            f"exact_all={public['coverage']['exact_all']}; changed={len(changed)}"
        )
    return 1 if args.strict and public["status"] != "ready" else 0


if __name__ == "__main__":
    raise SystemExit(main())
