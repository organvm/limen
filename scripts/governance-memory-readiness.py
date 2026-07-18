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
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema
import rfc8785
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
# Body-free owner projections in the real frozen snapshot are each larger than
# 100 MiB. Keep a finite per-artifact ceiling, but do not make the default
# reject the real event/envelope sets while accepting only compact fixtures.
DEFAULT_MAX_INPUT_BYTES = int(os.environ.get("LIMEN_GOV_INPUT_MAX_BYTES", str(256 * 1024 * 1024)))
_SCHEMA_ROOT_ENV = os.environ.get("LIMEN_GOV_SCHEMA_ROOT", "").strip()
SCHEMA_ROOT = Path(_SCHEMA_ROOT_ENV).expanduser() if _SCHEMA_ROOT_ENV else None

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
    collection: bool = False


INPUT_SPECS: tuple[InputSpec, ...] = (
    InputSpec("source_census", "LIMEN_GOV_SOURCE_CENSUS", "source-census.v1", True),
    InputSpec("snapshot_bundle", "LIMEN_GOV_SNAPSHOT_BUNDLE", "governance-snapshot-bundle.v1", True),
    InputSpec("source_envelopes", "LIMEN_GOV_SOURCE_ENVELOPES", "source-envelope.v1", True, True),
    InputSpec("normalized_events", "LIMEN_GOV_NORMALIZED_EVENTS", "normalized-event.v1", True, True),
    InputSpec(
        "normalization_parity",
        "LIMEN_GOV_NORMALIZATION_PARITY",
        "normalization-parity-receipt.v1",
        True,
    ),
    InputSpec("lineage_graph", "LIMEN_GOV_LINEAGE_GRAPH", "lineage-graph.v1", True),
    InputSpec("governance_testament", "LIMEN_GOV_TESTAMENT", "governance-testament.v1"),
    InputSpec(
        "assertion_evidence",
        "LIMEN_GOV_ASSERTION_EVIDENCE",
        "assertion-evidence.v1",
        collection=True,
    ),
    InputSpec("coverage_receipt", "LIMEN_GOV_COVERAGE_RECEIPT", "coverage-receipt.v1", True),
    InputSpec("ideal_forms", "LIMEN_GOV_IDEAL_FORMS", "ideal-form-register.v1", True),
    InputSpec("iceberg_atlas", "LIMEN_GOV_ICEBERG_ATLAS", "iceberg-atlas.v1", True),
    InputSpec("self_images", "LIMEN_GOV_SELF_IMAGES", "node-self-image-set.v1", True),
    InputSpec(
        "stage_receipts",
        "LIMEN_GOV_STAGE_RECEIPTS",
        "governance-stage-receipt.v1",
        True,
        True,
    ),
    InputSpec(
        "cadence_receipt",
        "LIMEN_GOV_CADENCE_RECEIPT",
        "governance-cadence-receipt.v1",
        True,
        True,
    ),
    InputSpec("atlas_receipt", "LIMEN_GOV_ATLAS_RECEIPT", "governance-atlas-receipt.v1", True),
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_value(value: Any) -> str:
    return f"sha256:{digest_bytes(rfc8785.dumps(value))}"


def safe_token(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    if SAFE_TOKEN.fullmatch(text):
        return text
    return f"sha256:{digest_bytes(text.encode('utf-8', errors='replace'))[:20]}"


def reference_resolves(reference: Any, identifiers: set[str]) -> bool:
    value = str(reference or "")
    return value in identifiers or value.partition(":")[2] in identifiers


def resolve_reference(reference: Any, records: Mapping[str, Any]) -> Any | None:
    value = str(reference or "")
    if value in records:
        return records[value]
    suffix = value.partition(":")[2]
    return records.get(suffix)


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


def schema_path(schema_root: Path, contract: str) -> Path:
    filename = f"{contract}.schema.json"
    candidates = (schema_root / "schemas" / filename, schema_root / filename)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def load_schema(schema_root: Path, contract: str) -> tuple[dict[str, Any] | None, str | None]:
    path = schema_path(schema_root, contract)
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__
    if not isinstance(value, dict):
        return None, "schema-root-must-be-object"
    try:
        jsonschema.Draft202012Validator.check_schema(value)
    except jsonschema.SchemaError:
        return None, "invalid-json-schema"
    return value, None


def validation_records(document: Any, spec: InputSpec) -> list[Any]:
    if spec.collection:
        return document if isinstance(document, list) else [document]
    return [document]


def schema_issues(
    document: Any,
    spec: InputSpec,
    schema: Mapping[str, Any],
) -> list[str]:
    records = validation_records(document, spec)
    if spec.collection and not records:
        return [f"semantic-empty:{spec.key}"]
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    issues: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            issues.append(f"schema-invalid:{spec.key}:{index}:root:{type(record).__name__}")
            continue
        errors = sorted(
            validator.iter_errors(record),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
        for error in errors[:25]:
            path = ".".join(str(part) for part in error.absolute_path) or "root"
            issues.append(f"schema-invalid:{spec.key}:{index}:{safe_token(path, 'root')}:{error.validator}")
        if len(errors) > 25:
            issues.append(f"schema-invalid:{spec.key}:{index}:additional-errors")
    return issues


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


def extract_snapshot_digests(document: Any) -> list[str]:
    records = document if isinstance(document, list) else [document]
    values: set[str] = set()
    for record in records:
        value = nested_get(
            record,
            ("snapshot_digest",),
            ("snapshot_hash",),
            ("custody_snapshot", "snapshot_hash"),
        )
        if isinstance(value, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", value):
            values.add(value)
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
        return False
    for declared_id in values:
        normalized = declared_id.rstrip("/#")
        if not (normalized == expected or normalized.endswith(f"/{expected}") or normalized.endswith(f"#{expected}")):
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
    duplicate_assignments = (
        as_nonnegative_int(nested_get(document, ("duplicate_assignments",), ("coverage", "duplicate_assignments"))) or 0
    )
    sources = document.get("sources") if isinstance(document, Mapping) else None
    source_ids: list[Any] = []
    if isinstance(sources, list):
        source_ids = [item.get("source_id", item.get("unit_id")) for item in sources if isinstance(item, Mapping)]
        duplicate_assignments += len(source_ids) - len(set(source_ids))
        if denominator is not None and len(sources) != denominator:
            issues.append("coverage-source-count-mismatch")
        expected_counts = Counter(
            str(item.get("status") or "").replace("_", "-") for item in sources if isinstance(item, Mapping)
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
    debt_clear = True
    for field in READINESS_DEBT_FIELDS:
        value = document.get(field) if isinstance(document, Mapping) else None
        if not isinstance(value, list):
            issues.append(f"coverage-{field.replace('_', '-')}-missing")
            debt_clear = False
        elif value:
            issues.append(f"coverage-{field.replace('_', '-')}-nonzero")
            debt_clear = False
    computed_ready = computed_exact and residual_count == 0 and debt_clear
    declared_ready = nested_get(document, ("ready",), ("coverage", "ready"))
    if not isinstance(declared_ready, bool):
        issues.append("coverage-ready-missing")
        declared_ready = False
    if declared_ready != computed_ready:
        issues.append("coverage-ready-contradicts-counts")
    closure_status = document.get("closure_status") if isinstance(document, Mapping) else None
    if closure_status != ("ready" if computed_ready else "closed_with_owner_routed_debt"):
        issues.append("coverage-closure-status-contradicts-readiness")
    return (
        {
            "denominator": denominator,
            "source_ids": sorted(str(item) for item in source_ids),
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
    records = document.get("raw_units", []) if isinstance(document, Mapping) else []
    roots = document.get("discovery_roots", []) if isinstance(document, Mapping) else []
    expectations = document.get("seed_expectations", []) if isinstance(document, Mapping) else []
    issues: list[str] = []
    root_ids = [str(item.get("root_id") or "") for item in roots if isinstance(item, Mapping)]
    expectation_ids = [str(item.get("expectation_id") or "") for item in expectations if isinstance(item, Mapping)]
    if not roots:
        issues.append("source-census-discovery-roots-empty")
    if len(root_ids) != len(set(root_ids)):
        issues.append("source-census-duplicate-discovery-root")
    if len(expectation_ids) != len(set(expectation_ids)):
        issues.append("source-census-duplicate-expectation")
    known_roots = set(root_ids)
    known_expectations = set(expectation_ids)
    required_expectations = {
        str(item.get("expectation_id"))
        for item in expectations
        if isinstance(item, Mapping) and item.get("required") is True
    }
    expectation_sources = {
        str(item.get("expectation_id")): str(item.get("source_family"))
        for item in expectations
        if isinstance(item, Mapping)
    }
    represented_expectations: set[str] = set()
    ids: list[Any] = []
    statuses: Counter[str] = Counter()
    routed_residuals = 0
    for index, item in enumerate(records):
        if not isinstance(item, Mapping):
            issues.append(f"source-census-invalid-record:{index}")
            continue
        unit_id = item.get("raw_unit_id")
        ids.append(unit_id)
        if item.get("discovery_root_id") not in known_roots:
            issues.append(f"source-census-discovery-root-unresolved:{index}")
        expectation_id = item.get("expectation_id")
        if expectation_id is not None and expectation_id not in known_expectations:
            issues.append(f"source-census-expectation-unresolved:{index}")
        elif expectation_id is not None:
            represented_expectations.add(str(expectation_id))
            if expectation_sources.get(str(expectation_id)) != str(item.get("source_family")):
                issues.append(f"source-census-expectation-source-mismatch:{index}")
        status = str(item.get("acquisition_status") or "").replace("-", "_")
        statuses[status] += 1
        if status not in {"acquired", "inaccessible", "missing_expected", "blocked"}:
            issues.append(f"source-census-invalid-status:{index}")
        if status != "acquired":
            if all(item.get(field) for field in ("owner_reference", "failed_predicate", "next_action")):
                routed_residuals += 1
            else:
                issues.append(f"source-census-unrouted-residual:{index}")
    duplicates = len(ids) - len(set(ids))
    if duplicates:
        issues.append("source-census-duplicate-unit-id")
    if not records:
        issues.append("source-census-empty")
    missing_required = sorted(required_expectations - represented_expectations)
    if missing_required:
        issues.append("source-census-required-expectation-unrepresented")
    return {
        "denominator": len(records),
        "discovery_root_ids": sorted(root_ids),
        "required_expectation_ids": sorted(required_expectations),
        "unrepresented_required_expectation_ids": missing_required,
        "raw_unit_ids": sorted(str(item) for item in ids),
        "status_counts": {key: statuses[key] for key in sorted(statuses)},
        "duplicate_assignments": duplicates,
        "routed_residuals": routed_residuals,
        "ready": bool(records and statuses.get("acquired", 0) == len(records) and not missing_required),
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


def trusted_receipt_bindings(snapshot_bundle: Any) -> dict[str, str]:
    if not isinstance(snapshot_bundle, Mapping):
        return {}
    bindings: dict[str, str] = {}

    def bind(value: Any) -> None:
        if (
            isinstance(value, Mapping)
            and isinstance(value.get("reference"), str)
            and isinstance(value.get("digest"), str)
        ):
            bindings[str(value["reference"])] = str(value["digest"])

    for field in (
        "source_census",
        "lineage_graph",
        "governance_testament",
        "coverage",
        "ideal_form_register",
        "node_self_image_set",
        "iceberg_atlas",
        "normalization_parity_receipt",
        "governance_atlas_receipt",
    ):
        bind(snapshot_bundle.get(field))
    for field in ("governance_stage_receipts", "governance_cadence_receipts"):
        values = snapshot_bundle.get(field)
        if isinstance(values, list):
            for value in values:
                bind(value)
    return bindings


READINESS_DEBT_FIELDS: tuple[str, ...] = (
    "unresolved_blockers",
    "quarantines",
    "missing_requirements",
    "citation_debt",
    "incomplete_predicates",
)


def strict_readiness_issues(document: Any, owner: str) -> list[str]:
    readiness = document.get("readiness") if isinstance(document, Mapping) else None
    if not isinstance(readiness, Mapping):
        return [f"{owner}-readiness-missing"]
    issues: list[str] = []
    if readiness.get("exact_all") is not True:
        issues.append(f"{owner}-exact-all-false")
    for field in READINESS_DEBT_FIELDS:
        value = readiness.get(field)
        if not isinstance(value, list):
            issues.append(f"{owner}-{field.replace('_', '-')}-missing")
        elif value:
            issues.append(f"{owner}-{field.replace('_', '-')}-nonzero")
    if readiness.get("ready") is not True:
        issues.append(f"{owner}-ready-false")
    if readiness.get("status") != "ready":
        issues.append(f"{owner}-status-not-ready")
    return issues


def normalized_event_projection(
    document: Any,
    *,
    envelopes_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    records = document if isinstance(document, list) else []
    issues: list[str] = []
    event_ids: list[str] = []
    role_counts: Counter[str] = Counter()
    authority_counts: Counter[str] = Counter()
    raw_unit_ids: set[str] = set()
    envelope_references: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            issues.append(f"normalized-event-invalid-record:{index}")
            continue
        event_id = str(record.get("event_id") or "")
        event_ids.append(event_id)
        identity_basis = record.get("identity_basis")
        if isinstance(identity_basis, Mapping):
            expected = f"evt_{digest_value(identity_basis).removeprefix('sha256:')}"
            if event_id != expected:
                issues.append(f"normalized-event-identity-mismatch:{index}")
        else:
            issues.append(f"normalized-event-identity-basis-missing:{index}")
        envelope = resolve_reference(record.get("source_envelope_reference"), envelopes_by_id)
        envelope_role = (
            {"user": "operator", "human": "operator"}.get(
                str(envelope.get("role") or "").lower(),
                str(envelope.get("role") or "").lower(),
            )
            if isinstance(envelope, Mapping)
            else ""
        )
        identity_content_hash = identity_basis.get("content_hash") if isinstance(identity_basis, Mapping) else None
        custody = envelope.get("custody_snapshot") if isinstance(envelope, Mapping) else None
        if not isinstance(envelope, Mapping) or (
            record.get("source_family") != envelope.get("source_family")
            or record.get("source_instance") != envelope.get("source_instance")
            or record.get("format_adapter") != envelope.get("format_adapter")
            or record.get("normalized_role") != envelope_role
            or record.get("authority_class") != envelope.get("authority_class")
            or identity_content_hash != envelope.get("body_hash")
            or record.get("raw_unit_content_hash") != envelope.get("raw_unit_content_hash")
            or record.get("occurred_at") != envelope.get("event_timestamp")
            or not isinstance(custody, Mapping)
            or record.get("snapshot_id") != custody.get("snapshot_id")
            or record.get("snapshot_digest") != custody.get("snapshot_hash")
        ):
            issues.append(f"normalized-event-envelope-evidence-mismatch:{index}")
        role_counts[str(record.get("normalized_role") or "unknown")] += 1
        authority_counts[str(record.get("authority_class") or "unknown")] += 1
        raw_unit_ids.add(str(record.get("raw_unit_id") or ""))
        envelope_references.add(str(record.get("source_envelope_reference") or ""))
    if not records:
        issues.append("normalized-events-empty")
    if len(event_ids) != len(set(event_ids)):
        issues.append("normalized-event-duplicate-id")
    return (
        {
            "count": len(records),
            "event_set_digest": digest_value(records),
            "event_ids": sorted(event_ids),
            "raw_unit_ids": sorted(raw_unit_ids),
            "source_envelope_references": sorted(envelope_references),
            "role_counts": dict(sorted(role_counts.items())),
            "authority_counts": dict(sorted(authority_counts.items())),
        },
        issues,
    )


def source_envelope_projection(document: Any) -> tuple[dict[str, Any], list[str]]:
    records = document if isinstance(document, list) else []
    issues: list[str] = []
    source_ids: list[str] = []
    authority_counts: Counter[str] = Counter()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            issues.append(f"source-envelope-invalid-record:{index}")
            continue
        source_ids.append(str(record.get("source_id") or ""))
        authority_class = str(record.get("authority_class") or "unknown")
        authority_counts[authority_class] += 1
        if authority_class == "operator_intent" and record.get("role") != "operator":
            issues.append(f"source-envelope-operator-role-mismatch:{index}")
    if not records:
        issues.append("source-envelopes-empty")
    if len(source_ids) != len(set(source_ids)):
        issues.append("source-envelope-duplicate-id")
    return {
        "count": len(records),
        "source_ids": sorted(source_ids),
        "authority_counts": dict(sorted(authority_counts.items())),
    }, issues


def normalization_parity_projection(
    document: Any,
    *,
    census: Any,
    normalized_events: Mapping[str, Any],
    events_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    promotions = document.get("promotions", []) if isinstance(document, Mapping) else []
    census_hashes = {
        str(item.get("raw_unit_id")): item.get("content_hash")
        for item in (census.get("raw_units", []) if isinstance(census, Mapping) else [])
        if isinstance(item, Mapping)
    }
    census_ids = set(census_hashes)
    promoted_ids: list[str] = []
    promoted_event_ids: set[str] = set()
    disposition_count = 0
    blocking_disposition_count = 0
    for index, promotion in enumerate(promotions):
        if not isinstance(promotion, Mapping):
            issues.append(f"normalization-parity-invalid-promotion:{index}")
            continue
        promoted_ids.append(str(promotion.get("raw_unit_id") or ""))
        raw_unit_id = str(promotion.get("raw_unit_id") or "")
        if raw_unit_id not in census_hashes or promotion.get("raw_unit_content_hash") != census_hashes.get(raw_unit_id):
            issues.append(f"normalization-parity-raw-unit-content-hash-mismatch:{index}")
        event_ids = promotion.get("event_ids")
        if isinstance(event_ids, list):
            promoted_event_ids.update(str(item) for item in event_ids)
            for event_id in event_ids:
                event = events_by_id.get(str(event_id))
                if (
                    not isinstance(event, Mapping)
                    or event.get("raw_unit_id") != promotion.get("raw_unit_id")
                    or event.get("raw_unit_content_hash") != promotion.get("raw_unit_content_hash")
                ):
                    issues.append(f"normalization-parity-leaf-mapping-mismatch:{index}")
        elif isinstance(promotion.get("disposition"), Mapping):
            disposition_count += 1
            if promotion["disposition"].get("type") != "ignored_transport_echo":
                blocking_disposition_count += 1
    if set(promoted_ids) != census_ids or len(promoted_ids) != len(census_ids):
        issues.append("normalization-parity-raw-unit-crosswalk-incomplete")
    if len(promoted_ids) != len(set(promoted_ids)):
        issues.append("normalization-parity-duplicate-raw-unit")
    expected_event_ids = set(normalized_events.get("event_ids", []))
    output_event_ids = set(
        document.get("output_events", {}).get("event_ids", [])
        if isinstance(document, Mapping) and isinstance(document.get("output_events"), Mapping)
        else []
    )
    if promoted_event_ids != expected_event_ids or output_event_ids != expected_event_ids:
        issues.append("normalization-parity-event-crosswalk-incomplete")
    input_ids = set(
        document.get("input_census", {}).get("raw_unit_ids", [])
        if isinstance(document, Mapping) and isinstance(document.get("input_census"), Mapping)
        else []
    )
    if input_ids != census_ids:
        issues.append("normalization-parity-census-binding-mismatch")
    if not set(normalized_events.get("raw_unit_ids", [])).issubset(census_ids):
        issues.append("normalization-parity-event-raw-unit-unresolved")
    input_census = document.get("input_census") if isinstance(document, Mapping) else None
    input_raw_units = input_census.get("raw_units", []) if isinstance(input_census, Mapping) else []
    input_hashes = {
        str(item.get("raw_unit_id")): item.get("content_hash") for item in input_raw_units if isinstance(item, Mapping)
    }
    if len(input_hashes) != len(input_raw_units) or input_hashes != census_hashes:
        issues.append("normalization-parity-census-content-binding-mismatch")
    if not isinstance(input_census, Mapping) or (
        input_census.get("census_id") != (census.get("census_id") if isinstance(census, Mapping) else None)
        or input_census.get("census_digest") != (census.get("census_digest") if isinstance(census, Mapping) else None)
    ):
        issues.append("normalization-parity-census-digest-mismatch")
    output_events = document.get("output_events") if isinstance(document, Mapping) else None
    if not isinstance(output_events, Mapping) or (
        output_events.get("event_set_digest") != normalized_events.get("event_set_digest")
    ):
        issues.append("normalization-parity-event-set-digest-mismatch")
    issues.extend(strict_readiness_issues(document, "normalization-parity"))
    if blocking_disposition_count:
        issues.append("normalization-parity-blocking-dispositions-nonzero")
    return {
        "raw_unit_count": len(census_ids),
        "promotion_count": len(promotions),
        "event_count": len(expected_event_ids),
        "disposition_count": disposition_count,
        "blocking_disposition_count": blocking_disposition_count,
        "exact_all": not any("crosswalk" in item or "duplicate" in item for item in issues),
        "ready": not issues,
    }, issues


def lineage_projection(
    document: Any,
    envelopes_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    nodes = document.get("nodes", []) if isinstance(document, Mapping) else []
    edges = document.get("edges", []) if isinstance(document, Mapping) else []
    issues: list[str] = []
    node_ids: list[str] = []
    lane_counts: Counter[str] = Counter()
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            issues.append(f"lineage-invalid-node:{index}")
            continue
        node_ids.append(str(node.get("node_id") or ""))
        lane_counts[str(node.get("lane") or "unknown")] += 1
        if node.get("review_state") != "reviewed":
            issues.append(f"lineage-node-not-reviewed:{index}")
        if resolve_reference(node.get("source_envelope_id"), envelopes_by_id) is None:
            issues.append(f"lineage-node-envelope-unresolved:{index}")
    known_nodes = set(node_ids)
    for index, edge in enumerate(edges):
        if not isinstance(edge, Mapping):
            issues.append(f"lineage-invalid-edge:{index}")
            continue
        if edge.get("review_state") != "reviewed":
            issues.append(f"lineage-edge-not-reviewed:{index}")
        if edge.get("from_node") not in known_nodes or edge.get("to_node") not in known_nodes:
            issues.append(f"lineage-edge-node-unresolved:{index}")
        spans = edge.get("evidence_spans")
        if not isinstance(spans, list) or not spans:
            issues.append(f"lineage-edge-evidence-empty:{index}")
        else:
            for span_index, span in enumerate(spans):
                envelope = (
                    resolve_reference(span.get("source_envelope_id"), envelopes_by_id)
                    if isinstance(span, Mapping)
                    else None
                )
                if (
                    not isinstance(span, Mapping)
                    or not isinstance(envelope, Mapping)
                    or (span.get("body_hash") != envelope.get("body_hash"))
                ):
                    issues.append(f"lineage-edge-evidence-unresolved:{index}:{span_index}")
    if len(node_ids) != len(set(node_ids)):
        issues.append("lineage-duplicate-node-id")
    if not nodes:
        issues.append("lineage-nodes-empty")
    if not edges:
        issues.append("lineage-edges-empty")
    for lane in ("operator_intent", "artifact"):
        if lane_counts.get(lane, 0) == 0:
            issues.append(f"lineage-lane-empty:{lane}")
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "lane_counts": dict(sorted(lane_counts.items())),
    }, issues


def stage_receipt_projection(document: Any) -> tuple[dict[str, Any], list[str]]:
    receipts = document if isinstance(document, list) else []
    issues: list[str] = []
    observed: list[dict[str, Any]] = []
    predecessor: str | None = None
    run_ids: set[str] = set()
    output_bindings: list[dict[str, Any]] = []
    receipt_records: dict[str, Mapping[str, Any]] = {}
    for index, stage in enumerate(CADENCE_STAGES):
        receipt = receipts[index] if index < len(receipts) and isinstance(receipts[index], Mapping) else None
        if receipt is None or receipt.get("stage") != stage:
            issues.append(f"stage-receipt-missing:{stage}")
            observed.append({"stage": stage, "status": "missing"})
            continue
        run_ids.add(str(receipt.get("run_id") or ""))
        declared, valid = declared_contract_digest(receipt, "receipt_digest")
        if declared is None:
            issues.append(f"stage-receipt-digest-missing:{stage}")
        elif not valid:
            issues.append(f"stage-receipt-digest-mismatch:{stage}")
        if receipt.get("status") != "completed":
            issues.append(f"stage-receipt-not-complete:{stage}")
        if receipt.get("predecessor_receipt_digest") != predecessor:
            issues.append(f"stage-receipt-predecessor-mismatch:{stage}")
        predecessor = str(receipt.get("receipt_digest") or "")
        outputs = receipt.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            issues.append(f"stage-receipt-outputs-empty:{stage}")
            outputs = []
        elif receipt.get("output_digest") != digest_value(outputs):
            issues.append(f"stage-receipt-output-digest-mismatch:{stage}")
        for output_index, output in enumerate(outputs):
            if not isinstance(output, Mapping):
                issues.append(f"stage-receipt-output-invalid:{stage}:{output_index}")
                continue
            output_bindings.append(
                {
                    **dict(output),
                    "stage": stage,
                    "stage_receipt_id": receipt.get("stage_receipt_id"),
                    "stage_receipt_digest": receipt.get("receipt_digest"),
                }
            )
        predicate = receipt.get("predicate")
        if not isinstance(predicate, Mapping) or not predicate.get("predicate_id"):
            issues.append(f"stage-receipt-predicate-missing:{stage}")
        for key in (
            str(receipt.get("stage_receipt_id") or ""),
            str(receipt.get("receipt_target") or ""),
        ):
            if not key:
                continue
            if key in receipt_records and receipt_records[key] is not receipt:
                issues.append(f"stage-receipt-reference-duplicate:{key}")
            receipt_records[key] = receipt
        observed.append(
            {
                "stage": stage,
                "status": safe_token(receipt.get("status"), "unknown"),
                "receipt_digest": safe_token(receipt.get("receipt_digest")),
            }
        )
    if len(receipts) != len(CADENCE_STAGES):
        issues.append("stage-receipt-count-mismatch")
    if len(run_ids) != 1 or "" in run_ids:
        issues.append("stage-receipt-run-id-mismatch")
    output_keys = [
        (
            str(item.get("artifact_id") or ""),
            str(item.get("reference") or ""),
            str(item.get("digest") or ""),
        )
        for item in output_bindings
    ]
    if len(output_keys) != len(set(output_keys)):
        issues.append("stage-receipt-output-binding-duplicate")
    return {
        "required_order": list(CADENCE_STAGES),
        "observed": observed,
        "receipts": receipts,
        "output_bindings": output_bindings,
        "receipt_records": receipt_records,
        "complete": not issues,
    }, issues


def cadence_projection(
    document: Any,
    *,
    stage_receipts: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    observed: list[dict[str, Any]] = []
    cadence_receipts = document if isinstance(document, list) else []
    if len(cadence_receipts) != 2:
        issues.append("cadence-two-run-proof-missing")
    run_one = cadence_receipts[0] if cadence_receipts and isinstance(cadence_receipts[0], Mapping) else {}
    run_two = cadence_receipts[1] if len(cadence_receipts) > 1 and isinstance(cadence_receipts[1], Mapping) else {}
    for index, receipt in enumerate(cadence_receipts):
        declared, valid = declared_contract_digest(receipt, "receipt_digest")
        if declared is None:
            issues.append(f"cadence-receipt-digest-missing:{index}")
        elif not valid:
            issues.append(f"cadence-receipt-digest-mismatch:{index}")
    if (
        run_one.get("run_number") != 1
        or run_one.get("previous_cadence_receipt_digest") is not None
        or run_one.get("fixed_point", {}).get("status") != "not_applicable"
    ):
        issues.append("cadence-run-one-invalid")
    run_one_readiness = run_one.get("readiness")
    if not isinstance(run_one_readiness, Mapping) or (
        run_one_readiness.get("ready") is not False
        or run_one_readiness.get("status") != "incomplete"
        or run_one_readiness.get("exact_all") is not False
    ):
        issues.append("cadence-run-one-false-ready")
    if run_two.get("previous_cadence_receipt_digest") != run_one.get("receipt_digest") or run_two.get(
        "output_digest"
    ) != run_one.get("output_digest"):
        issues.append("cadence-two-run-binding-mismatch")
    document = run_two
    receipts = document.get("stage_receipts", []) if isinstance(document, Mapping) else []
    predecessor: str | None = None
    for index, stage in enumerate(CADENCE_STAGES):
        item = receipts[index] if index < len(receipts) and isinstance(receipts[index], Mapping) else None
        if item is None or item.get("stage") != stage:
            issues.append(f"cadence-stage-missing:{stage}")
            observed.append({"stage": stage, "status": "missing"})
            continue
        status = str(item.get("status") or "unknown")
        receipt_digest = item.get("receipt_digest")
        if status != "completed":
            issues.append(f"cadence-stage-not-complete:{stage}")
        if item.get("predecessor_receipt_digest") != predecessor:
            issues.append(f"cadence-predecessor-mismatch:{stage}")
        predecessor = str(receipt_digest or "")
        observed.append(
            {
                "stage": stage,
                "status": safe_token(status, "unknown"),
                "receipt_digest": safe_token(receipt_digest),
            }
        )
    if len(receipts) != len(CADENCE_STAGES):
        issues.append("cadence-stage-count-mismatch")
    full_receipts = stage_receipts.get("receipts", [])
    expected_summaries = [
        {
            "stage": receipt.get("stage"),
            "stage_receipt_id": receipt.get("stage_receipt_id"),
            "reference": receipt.get("receipt_target"),
            "status": receipt.get("status"),
            "receipt_digest": receipt.get("receipt_digest"),
            "predecessor_receipt_digest": receipt.get("predecessor_receipt_digest"),
        }
        for receipt in full_receipts
        if isinstance(receipt, Mapping)
    ]
    if receipts != expected_summaries:
        issues.append("cadence-stage-receipt-chain-mismatch")
    fixed_point = document.get("fixed_point", {}) if isinstance(document, Mapping) else {}
    proven = (
        isinstance(fixed_point, Mapping)
        and fixed_point.get("status") == "proven"
        and fixed_point.get("new_event_count") == 0
        and fixed_point.get("changed_byte_count") == 0
        and fixed_point.get("replayed_completed_children") == 0
        and fixed_point.get("previous_output_digest") == run_one.get("output_digest")
        and fixed_point.get("output_digest_matches_previous") is True
        and document.get("run_number") == 2
        and document.get("previous_cadence_receipt_digest") is not None
    )
    if not proven:
        issues.append("cadence-fixed-point-not-proven")
    issues.extend(strict_readiness_issues(document, "cadence"))
    return {
        "required_order": list(CADENCE_STAGES),
        "observed": observed,
        "run_count": len(cadence_receipts),
        "fixed_point_proven": proven,
        "complete": not issues,
    }, issues


def assertion_projection(
    document: Any,
    *,
    events_by_id: Mapping[str, Mapping[str, Any]],
    envelopes_by_id: Mapping[str, Mapping[str, Any]],
    testament: Any,
    snapshot_at: str | None,
    receipt_bindings: Mapping[str, str],
) -> tuple[dict[str, Any], list[str]]:
    records = document if isinstance(document, list) else [document] if isinstance(document, Mapping) else []
    issues: list[str] = []
    class_counts: dict[str, int] = {}
    verified = 0
    assertion_ids: list[str] = []
    ratification = (
        testament.get("ratification")
        if isinstance(testament, Mapping) and isinstance(testament.get("ratification"), Mapping)
        else {}
    )
    constitutional_record_reference = ratification.get("constitutional_record_reference")
    constitutional_record_digest = digest_value(ratification) if ratification else None
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            issues.append(f"assertion-invalid-record:{index}")
            continue
        assertion_ids.append(str(record.get("assertion_id") or ""))
        assertion_class = str(record.get("assertion_class") or record.get("class") or "unknown")
        class_counts[assertion_class] = class_counts.get(assertion_class, 0) + 1
        state = str(record.get("verification_state") or record.get("state") or "unverified").lower()
        evidence = record.get("evidence_references")
        groups: list[Any] = []
        evidence_types: set[str] = set()
        evidence_fingerprints: list[tuple[str, ...]] = []
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
            record_evidence_ids = [str(item.get("evidence_id") or "") for item in evidence if isinstance(item, Mapping)]
            if len(record_evidence_ids) != len(set(record_evidence_ids)):
                issues.append(f"assertion-duplicate-evidence-id:{index}")
            for evidence_index, item in enumerate(evidence):
                if not isinstance(item, Mapping):
                    continue
                evidence_type = item.get("evidence_type")
                reference = item.get("reference")
                body_hash = item.get("body_hash")
                evidence_resolved = False
                fingerprint: tuple[str, ...] | None = None
                if evidence_type == "immutable_source_event":
                    event = resolve_reference(reference, events_by_id)
                    basis = event.get("identity_basis") if isinstance(event, Mapping) else None
                    evidence_resolved = bool(isinstance(basis, Mapping) and body_hash == basis.get("content_hash"))
                    if evidence_resolved:
                        fingerprint = ("event", str(event.get("event_id")), str(body_hash))
                elif evidence_type in {"primary_source", "secondary_source"}:
                    envelope = resolve_reference(reference, envelopes_by_id)
                    evidence_resolved = bool(isinstance(envelope, Mapping) and body_hash == envelope.get("body_hash"))
                    if evidence_resolved:
                        fingerprint = ("source", str(envelope.get("source_id")), str(body_hash))
                elif evidence_type in {"owner_record", "fresh_verifier_receipt"}:
                    evidence_resolved = receipt_bindings.get(str(reference)) == body_hash
                    if evidence_resolved:
                        fingerprint = ("receipt", str(body_hash))
                elif evidence_type == "ratified_constitutional_record":
                    evidence_resolved = (
                        reference == constitutional_record_reference and body_hash == constitutional_record_digest
                    )
                    if evidence_resolved:
                        fingerprint = (
                            "ratification",
                            str(constitutional_record_reference),
                            str(constitutional_record_digest),
                        )
                elif evidence_type == "artifact":
                    event = resolve_reference(reference, events_by_id)
                    envelope = resolve_reference(reference, envelopes_by_id)
                    if isinstance(event, Mapping):
                        basis = event.get("identity_basis")
                        evidence_resolved = bool(isinstance(basis, Mapping) and body_hash == basis.get("content_hash"))
                        if evidence_resolved:
                            fingerprint = ("event", str(event.get("event_id")), str(body_hash))
                    elif isinstance(envelope, Mapping):
                        evidence_resolved = body_hash == envelope.get("body_hash")
                        if evidence_resolved:
                            fingerprint = ("source", str(envelope.get("source_id")), str(body_hash))
                    else:
                        evidence_resolved = receipt_bindings.get(str(reference)) == body_hash
                        if evidence_resolved:
                            fingerprint = ("receipt", str(body_hash))
                if not evidence_resolved:
                    issues.append(f"assertion-evidence-unresolved:{index}:{evidence_index}")
                elif fingerprint is not None:
                    evidence_fingerprints.append(fingerprint)
            if len(evidence_fingerprints) != len(set(evidence_fingerprints)):
                issues.append(f"assertion-duplicate-underlying-evidence:{index}")
        group_count = len({canonical_json(item) for item in groups})
        if assertion_class in {"external_fact", "external-fact"} and (
            group_count < 2 or len(set(evidence_fingerprints)) < 2
        ):
            issues.append(f"assertion-independent-evidence-insufficient:{index}")
        if assertion_class in {"operator_directive", "operator-directive"}:
            required = {"immutable_source_event", "ratified_constitutional_record"}
            if group_count < 2:
                issues.append(f"assertion-independent-evidence-insufficient:{index}")
            if not required.issubset(evidence_types):
                issues.append(f"assertion-operator-authority-incomplete:{index}")
            immutable_references = {
                str(item.get("reference"))
                for item in (evidence if isinstance(evidence, list) else [])
                if isinstance(item, Mapping) and item.get("evidence_type") == "immutable_source_event"
            }
            if not immutable_references or not all(
                resolve_reference(reference, events_by_id) is not None for reference in immutable_references
            ):
                issues.append(f"assertion-operator-event-unresolved:{index}")
            constitutional_references = {
                str(item.get("reference"))
                for item in (evidence if isinstance(evidence, list) else [])
                if isinstance(item, Mapping) and item.get("evidence_type") == "ratified_constitutional_record"
            }
            if not isinstance(testament, Mapping) or testament.get("status") != "ratified":
                issues.append(f"assertion-ratified-record-unresolved:{index}")
            elif not constitutional_references or constitutional_record_reference not in constitutional_references:
                issues.append(f"assertion-constitutional-record-unresolved:{index}")
        if assertion_class in {"current_state", "current-state"}:
            required = {"owner_record", "fresh_verifier_receipt"}
            freshness = record.get("freshness")
            verified_at = parse_timestamp(freshness.get("verified_at")) if isinstance(freshness, Mapping) else None
            snapshot_time = parse_timestamp(snapshot_at)
            max_age = freshness.get("max_age_seconds") if isinstance(freshness, Mapping) else None
            computed_fresh = bool(
                verified_at is not None
                and snapshot_time is not None
                and verified_at <= snapshot_time
                and isinstance(max_age, int)
                and not isinstance(max_age, bool)
                and (snapshot_time - verified_at).total_seconds() <= max_age
            )
            if (
                not required.issubset(evidence_types)
                or group_count < 2
                or len(set(evidence_fingerprints)) < 2
                or not (isinstance(freshness, Mapping) and freshness.get("status") == "fresh" and computed_fresh)
            ):
                issues.append(f"assertion-current-state-evidence-incomplete:{index}")
        if state == "verified":
            verified += 1
        else:
            issues.append(f"assertion-not-verified:{index}")
    if not records:
        issues.append("assertions-empty")
    if len(assertion_ids) != len(set(assertion_ids)):
        issues.append("assertion-duplicate-id")
    return {
        "total": len(records),
        "verified": verified,
        "assertion_ids": sorted(assertion_ids),
        "class_counts": {key: class_counts[key] for key in sorted(class_counts)},
    }, issues


def testament_projection(
    document: Any,
    *,
    events_by_id: Mapping[str, Mapping[str, Any]],
    assertions_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(document, Mapping):
        return {"status": "missing", "ready": False}, ["testament-missing"]
    issues: list[str] = []
    status = str(document.get("status") or "")
    directive = str(document.get("directive") or "")
    if not directive.strip():
        issues.append("testament-directive-empty")
    if document.get("directive_hash") != f"sha256:{digest_bytes(directive.encode('utf-8'))}":
        issues.append("testament-directive-hash-mismatch")
    if status != "ratified":
        issues.append("testament-not-ratified")
    ratification = document.get("ratification")
    if status == "ratified":
        if not isinstance(ratification, Mapping):
            issues.append("testament-ratification-missing")
        else:
            authority_events = ratification.get("authority_events", [])
            authority_event_ids = [str(item.get("event_id")) for item in authority_events if isinstance(item, Mapping)]
            if (
                not isinstance(authority_events, list)
                or not authority_events
                or not set(authority_event_ids).issubset(events_by_id)
            ):
                issues.append("testament-authority-events-unresolved")
            if len(authority_event_ids) != len(set(authority_event_ids)):
                issues.append("testament-authority-events-duplicate")
            for index, authority_event in enumerate(authority_events):
                if not isinstance(authority_event, Mapping):
                    continue
                event = events_by_id.get(str(authority_event.get("event_id") or ""))
                identity_basis = event.get("identity_basis") if isinstance(event, Mapping) else None
                expected_content_hash = (
                    identity_basis.get("content_hash") if isinstance(identity_basis, Mapping) else None
                )
                if not isinstance(event, Mapping) or (
                    authority_event.get("source_envelope_reference") != event.get("source_envelope_reference")
                    or authority_event.get("role") != event.get("normalized_role")
                    or authority_event.get("authority_class") != event.get("authority_class")
                    or authority_event.get("content_hash") != expected_content_hash
                ):
                    issues.append(f"testament-authority-event-evidence-mismatch:{index}")
            assertion_reference = ratification.get("assertion_evidence_reference")
            assertion = resolve_reference(assertion_reference, assertions_by_id)
            if not isinstance(assertion, Mapping):
                issues.append("testament-assertion-evidence-unresolved")
            elif (
                assertion.get("assertion_class") != "operator_directive"
                or assertion.get("verification_state") != "verified"
            ):
                issues.append("testament-controlling-assertion-invalid")
            citations = document.get("citations")
            if (
                not isinstance(citations, list)
                or not citations
                or len(citations) != len(set(map(str, citations)))
                or assertion_reference not in citations
                or not all(resolve_reference(reference, assertions_by_id) is not None for reference in citations)
            ):
                issues.append("testament-citations-unresolved")
            candidate = dict(document)
            candidate["status"] = "candidate"
            candidate.pop("ratification", None)
            candidate.pop("supersession", None)
            if ratification.get("candidate_digest") != digest_value(candidate):
                issues.append("testament-candidate-digest-mismatch")
            if ratification.get("controlling_formulation") != directive:
                issues.append("testament-controlling-formulation-mismatch")
            coverage = ratification.get("constitutional_coverage")
            coverage_ready = (
                isinstance(coverage, Mapping)
                and coverage.get("exact_all") is True
                and coverage.get("blocked_scopes") == []
                and coverage.get("missing_requirements") == []
                and coverage.get("ready") is True
            )
            if not coverage_ready:
                issues.append("testament-constitutional-coverage-blocked")
    return {
        "status": status,
        "directive_count": int(bool(document.get("directive"))),
        "ready": not issues,
    }, issues


def ideal_form_projection(
    document: Any,
    *,
    assertion_ids: set[str],
    verified_predicate_receipts: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    records = document.get("ideal_forms", []) if isinstance(document, Mapping) else []
    issues: list[str] = []
    ideal_ids: list[str] = []
    verified = 0
    projected: list[dict[str, Any]] = []
    for index, item in enumerate(records):
        if not isinstance(item, Mapping):
            issues.append(f"ideal-form-invalid-record:{index}")
            continue
        ideal_id = str(item.get("ideal_form_id") or "")
        ideal_ids.append(ideal_id)
        predicates = item.get("predicates", [])
        predicate_ids = [
            str(predicate.get("predicate_id") or "") for predicate in predicates if isinstance(predicate, Mapping)
        ]
        if len(predicate_ids) != len(set(predicate_ids)):
            issues.append(f"ideal-form-duplicate-predicate-id:{index}")
        results: list[str] = []
        for predicate_index, predicate in enumerate(predicates if isinstance(predicates, list) else []):
            if not isinstance(predicate, Mapping):
                issues.append(f"ideal-form-predicate-invalid:{index}:{predicate_index}")
                results.append("fail")
                continue
            receipt = verified_predicate_receipts.get(str(predicate.get("receipt_reference") or ""))
            receipt_predicate = receipt.get("predicate") if isinstance(receipt, Mapping) else None
            if (
                not isinstance(receipt, Mapping)
                or not isinstance(receipt_predicate, Mapping)
                or receipt_predicate.get("predicate_id") != predicate.get("predicate_id")
            ):
                issues.append(f"ideal-form-predicate-receipt-unresolved:{index}:{predicate_index}")
                results.append("fail")
                continue
            derived_result = (
                "pass"
                if receipt.get("status") == "completed"
                else "blocked"
                if receipt.get("status") == "blocked"
                else "fail"
            )
            if predicate.get("result") != derived_result:
                issues.append(f"ideal-form-predicate-result-mismatch:{index}:{predicate_index}")
            results.append(derived_result)
        total = len(predicates) if isinstance(predicates, list) else 0
        passed = sum(result == "pass" for result in results)
        expected_state = "verified" if total and passed == total else "blocked" if "blocked" in results else "partial"
        distance = item.get("distance_to_ideal")
        if not isinstance(distance, Mapping):
            issues.append(f"ideal-form-distance-missing:{index}")
            distance = {}
        if (
            item.get("implementation_state") != expected_state
            or distance.get("classification") != expected_state
            or distance.get("verified_predicates") != passed
            or distance.get("total_predicates") != total
        ):
            issues.append(f"ideal-form-derived-status-mismatch:{index}")
        residuals = item.get("residual_gaps")
        if expected_state == "verified":
            verified += 1
            if residuals != []:
                issues.append(f"ideal-form-verified-residuals-nonempty:{index}")
        elif not isinstance(residuals, list) or not residuals:
            issues.append(f"ideal-form-incomplete-residuals-empty:{index}")
        predicate_receipt_references = {
            str(predicate.get("receipt_reference")) for predicate in predicates if isinstance(predicate, Mapping)
        }
        derivation = item.get("derivation")
        derived_receipts = (
            set(map(str, derivation.get("receipt_references", [])))
            if isinstance(derivation, Mapping) and isinstance(derivation.get("receipt_references"), list)
            else set()
        )
        if (
            not predicate_receipt_references
            or predicate_receipt_references != derived_receipts
            or not predicate_receipt_references.issubset(verified_predicate_receipts)
        ):
            issues.append(f"ideal-form-receipt-derivation-mismatch:{index}")
        assertion_references = item.get("assertion_evidence_references")
        if (
            not isinstance(assertion_references, list)
            or not assertion_references
            or not all(reference_resolves(reference, assertion_ids) for reference in assertion_references)
        ):
            issues.append(f"ideal-form-assertion-reference-unresolved:{index}")
        projected.append(
            {
                "id": safe_token(ideal_id, f"ideal-{index}"),
                "implementation_state": expected_state,
                "verified_predicates": passed,
                "total_predicates": total,
            }
        )
    if not records:
        issues.append("ideal-forms-empty")
    if len(ideal_ids) != len(set(ideal_ids)):
        issues.append("ideal-form-duplicate-id")
    coverage = document.get("coverage", {}) if isinstance(document, Mapping) else {}
    if not isinstance(coverage, Mapping) or (
        coverage.get("registered") != len(records)
        or coverage.get("verified") != verified
        or coverage.get("blocked")
        != sum(item.get("implementation_state") == "blocked" for item in records if isinstance(item, Mapping))
        or coverage.get("incomplete")
        != sum(item.get("implementation_state") == "partial" for item in records if isinstance(item, Mapping))
    ):
        issues.append("ideal-form-coverage-mismatch")
    issues.extend(strict_readiness_issues(document, "ideal-forms"))
    return {
        "count": len(records),
        "verified": verified,
        "ideal_ids": sorted(ideal_ids),
        "ideal_forms": projected,
        "ready": not issues,
    }, issues


def parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def self_image_projection(
    document: Any,
    *,
    snapshot_at: str | None,
    generated_at: str | None,
    evidence_ids: set[str],
    ideal_ids: set[str],
    ideal_predicate_ids: set[str],
) -> tuple[dict[str, Any], list[str]]:
    registry_projection = document.get("registry_projection", []) if isinstance(document, Mapping) else []
    registered = document.get("registered_node_ids", []) if isinstance(document, Mapping) else []
    images = document.get("self_images", []) if isinstance(document, Mapping) else []
    issues: list[str] = []
    registry_node_ids = [str(item.get("uid") or "") for item in registry_projection if isinstance(item, Mapping)]
    if not isinstance(document, Mapping) or document.get("registry_reference") != "#/registry_projection":
        issues.append("self-images-registry-reference-unresolved")
    if not registry_projection:
        issues.append("self-images-registry-projection-empty")
    if registry_node_ids != sorted(registry_node_ids) or len(registry_node_ids) != len(set(registry_node_ids)):
        issues.append("self-images-registry-projection-invalid")
    if (
        not isinstance(document, Mapping)
        or document.get("registry_digest") != digest_value(registry_projection)
        or list(map(str, registered)) != registry_node_ids
    ):
        issues.append("self-images-registry-denominator-mismatch")
    image_ids = [str(item.get("node_id") or "") for item in images if isinstance(item, Mapping)]
    if not registered:
        issues.append("self-images-registered-nodes-empty")
    if not images:
        issues.append("self-images-empty")
    if len(image_ids) != len(set(image_ids)):
        issues.append("self-images-duplicate-node-id")
    if set(image_ids) != set(str(item) for item in registered) or len(image_ids) != len(registered):
        issues.append("self-images-exact-one-coverage-failed")
    expected_node_types = {
        "organ": "organ",
        "repo": "repository",
        "module": "module",
        "document": "document",
        "session": "session",
        "variable": "artifact",
        "metric": "artifact",
    }
    images_by_id = {str(item.get("node_id")): item for item in images if isinstance(item, Mapping)}
    for index, node in enumerate(registry_projection):
        image = images_by_id.get(str(node.get("uid"))) if isinstance(node, Mapping) else None
        if (
            not isinstance(node, Mapping)
            or not isinstance(image, Mapping)
            or image.get("node_type") != expected_node_types.get(str(node.get("entity_type")))
        ):
            issues.append(f"self-images-registry-node-mismatch:{index}")
    snapshot_time = parse_timestamp(snapshot_at)
    generated_time = parse_timestamp(generated_at)
    if snapshot_time is None or generated_time is None or generated_time < snapshot_time:
        issues.append("self-images-snapshot-window-invalid")
    for index, item in enumerate(images):
        if not isinstance(item, Mapping):
            issues.append(f"self-image-invalid:{index}")
            continue
        reconciled_at = parse_timestamp(item.get("reconciled_at"))
        if snapshot_time is None or generated_time is None or reconciled_at is None or reconciled_at < snapshot_time:
            issues.append(f"self-image-stale:{index}")
        elif reconciled_at > generated_time:
            issues.append(f"self-image-future:{index}")
        evidence_references = item.get("evidence_references")
        if (
            not isinstance(evidence_references, list)
            or not evidence_references
            or not all(reference_resolves(reference, evidence_ids) for reference in evidence_references)
        ):
            issues.append(f"self-image-evidence-unresolved:{index}")
        relations = item.get("relations")
        if not isinstance(relations, Mapping):
            issues.append(f"self-image-relations-invalid:{index}")
        else:
            for direction in ("incoming", "outgoing"):
                related = relations.get(direction)
                if not isinstance(related, list):
                    issues.append(f"self-image-relations-invalid:{index}:{direction}")
                    continue
                for relation_index, relation in enumerate(related):
                    relation_evidence = relation.get("evidence_references") if isinstance(relation, Mapping) else None
                    if (
                        not isinstance(relation, Mapping)
                        or not isinstance(relation_evidence, list)
                        or not relation_evidence
                        or not all(reference_resolves(reference, evidence_ids) for reference in relation_evidence)
                    ):
                        issues.append(f"self-image-relation-evidence-unresolved:{index}:{direction}:{relation_index}")
        observations = item.get("observations")
        if not isinstance(observations, list) or not observations:
            issues.append(f"self-image-observations-empty:{index}")
        else:
            for observation_index, observation in enumerate(observations):
                references = observation.get("evidence_references") if isinstance(observation, Mapping) else None
                if (
                    not isinstance(references, list)
                    or not references
                    or not all(reference_resolves(reference, evidence_ids) for reference in references)
                ):
                    issues.append(f"self-image-observation-evidence-unresolved:{index}:{observation_index}")
        active_ideals = item.get("active_ideal_forms")
        if not isinstance(active_ideals, list) or not active_ideals:
            issues.append(f"self-image-active-ideals-empty:{index}")
        else:
            for ideal_index, ideal in enumerate(active_ideals):
                if not isinstance(ideal, Mapping):
                    issues.append(f"self-image-active-ideal-invalid:{index}:{ideal_index}")
                    continue
                predicate_references = ideal.get("predicate_references")
                ideal_evidence = ideal.get("evidence_references")
                if not reference_resolves(ideal.get("form_id"), ideal_ids):
                    issues.append(f"self-image-active-ideal-unresolved:{index}:{ideal_index}")
                if (
                    not isinstance(predicate_references, list)
                    or not predicate_references
                    or not all(reference_resolves(reference, ideal_predicate_ids) for reference in predicate_references)
                ):
                    issues.append(f"self-image-active-ideal-predicate-unresolved:{index}:{ideal_index}")
                if (
                    not isinstance(ideal_evidence, list)
                    or not ideal_evidence
                    or not all(reference_resolves(reference, evidence_ids) for reference in ideal_evidence)
                ):
                    issues.append(f"self-image-active-ideal-evidence-unresolved:{index}:{ideal_index}")
    counts = document.get("counts", {}) if isinstance(document, Mapping) else {}
    if not isinstance(counts, Mapping) or (
        counts.get("registered") != len(registered) or counts.get("exported") != len(images)
    ):
        issues.append("self-images-counts-mismatch")
    issues.extend(strict_readiness_issues(document, "self-images"))
    return {
        "registered_count": len(registered),
        "self_image_count": len(images),
        "node_ids": sorted(image_ids),
        "ready": not issues,
    }, issues


def atlas_projection(
    document: Any,
    *,
    ideal_ids: set[str],
    self_image_ids: set[str],
    source_envelope_ids: set[str],
    event_ids: set[str],
    assertion_ids: set[str],
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(document, Mapping):
        return {
            "status": "missing",
            "zoom_levels": [],
            "timeline_counts": {"operator_intent": 0, "artifact": 0},
            "ideal_forms": [],
            "self_image_count": 0,
        }, ["atlas-missing"]
    issues: list[str] = []
    canonical_order = ("system", "organ", "repository", "document", "session", "atom")
    source_references = document.get("source_envelope_references")
    if (
        not isinstance(source_references, list)
        or not source_references
        or not all(reference_resolves(reference, source_envelope_ids) for reference in source_references)
    ):
        issues.append("atlas-source-envelope-reference-unresolved")
    resolved_source_references = {
        reference.partition(":")[2] if reference.partition(":")[2] in source_envelope_ids else reference
        for reference in (map(str, source_references) if isinstance(source_references, list) else [])
    }
    if resolved_source_references != source_envelope_ids:
        issues.append("atlas-source-envelope-set-mismatch")
    assertion_references = document.get("assertion_evidence_references")
    if (
        not isinstance(assertion_references, list)
        or not assertion_references
        or not all(reference_resolves(reference, assertion_ids) for reference in assertion_references)
    ):
        issues.append("atlas-assertion-reference-unresolved")
    resolved_assertion_references = {
        reference.partition(":")[2] if reference.partition(":")[2] in assertion_ids else reference
        for reference in (map(str, assertion_references) if isinstance(assertion_references, list) else [])
    }
    if resolved_assertion_references != assertion_ids:
        issues.append("atlas-assertion-set-mismatch")
    raw_zoom = document.get("zoom_levels", {})
    zoom_levels: list[dict[str, Any]] = []
    zoom_node_ids: set[str] = set()
    zoom_self_image_ids: list[str] = []
    if not isinstance(raw_zoom, Mapping) or set(raw_zoom) != set(canonical_order):
        issues.append("atlas-zoom-set-incomplete")
        raw_zoom = raw_zoom if isinstance(raw_zoom, Mapping) else {}
    for level_id in canonical_order:
        nodes = raw_zoom.get(level_id, [])
        count = len(nodes) if isinstance(nodes, list) else 0
        if count == 0:
            issues.append(f"atlas-zoom-empty:{level_id}")
        if isinstance(nodes, list):
            for index, node in enumerate(nodes):
                if not isinstance(node, Mapping):
                    issues.append(f"atlas-zoom-invalid-node:{level_id}:{index}")
                    continue
                node_id = str(node.get("node_id") or "")
                if node_id in zoom_node_ids:
                    issues.append(f"atlas-zoom-duplicate-node:{level_id}:{index}")
                zoom_node_ids.add(node_id)
                self_image_reference = str(node.get("self_image_reference") or "")
                if not reference_resolves(self_image_reference, self_image_ids):
                    issues.append(f"atlas-self-image-reference-unresolved:{level_id}:{index}")
                else:
                    suffix = self_image_reference.partition(":")[2]
                    zoom_self_image_ids.append(suffix if suffix in self_image_ids else self_image_reference)
                references = node.get("ideal_form_references", [])
                if not isinstance(references, list) or not set(map(str, references)).issubset(ideal_ids):
                    issues.append(f"atlas-ideal-reference-unresolved:{level_id}:{index}")
        zoom_levels.append({"id": level_id, "node_count": count})
    if Counter(zoom_self_image_ids) != Counter({node_id: 1 for node_id in self_image_ids}):
        issues.append("atlas-zoom-self-image-coverage-mismatch")
    timelines = document.get("timelines", {})
    timeline_counts = {
        lane: len(timelines.get(lane, []))
        if isinstance(timelines, Mapping) and isinstance(timelines.get(lane), list)
        else 0
        for lane in ("operator_intent", "artifact")
    }
    for lane, count in timeline_counts.items():
        if count == 0:
            issues.append(f"atlas-timeline-empty:{lane}")
        entries = timelines.get(lane, []) if isinstance(timelines, Mapping) else []
        for index, entry in enumerate(entries if isinstance(entries, list) else []):
            if not isinstance(entry, Mapping):
                issues.append(f"atlas-timeline-invalid-entry:{lane}:{index}")
                continue
            if lane == "operator_intent" and not reference_resolves(entry.get("event_reference"), event_ids):
                issues.append(f"atlas-timeline-event-unresolved:{lane}:{index}")
            entry_sources = entry.get("source_envelope_references")
            if (
                not isinstance(entry_sources, list)
                or not entry_sources
                or not all(reference_resolves(reference, source_envelope_ids) for reference in entry_sources)
            ):
                issues.append(f"atlas-timeline-source-unresolved:{lane}:{index}")
    atlas_ideal_ids = (
        set(map(str, document.get("ideal_forms", []))) if isinstance(document.get("ideal_forms"), list) else set()
    )
    atlas_self_ids = (
        set(map(str, document.get("self_images", []))) if isinstance(document.get("self_images"), list) else set()
    )
    if atlas_ideal_ids != ideal_ids:
        issues.append("atlas-ideal-set-mismatch")
    resolved_atlas_self_ids = {
        reference.partition(":")[2] if reference.partition(":")[2] in self_image_ids else reference
        for reference in atlas_self_ids
    }
    if resolved_atlas_self_ids != self_image_ids:
        issues.append("atlas-self-image-set-mismatch")
    if document.get("citation_debt") != []:
        issues.append("atlas-citation-debt-nonzero")
    coverage = document.get("coverage", {})
    if not isinstance(coverage, Mapping) or coverage.get("exact_all") is not True:
        issues.append("atlas-exact-all-false")
    elif (
        coverage.get("source_count") != len(source_envelope_ids)
        or coverage.get("event_count") != len(event_ids)
        or coverage.get("node_count") != len(zoom_node_ids)
        or coverage.get("node_count") != len(self_image_ids)
        or coverage.get("ideal_form_count") != len(ideal_ids)
    ):
        issues.append("atlas-coverage-counts-mismatch")
    relationships = document.get("relationships")
    if not isinstance(relationships, list) or not relationships:
        issues.append("atlas-relationships-empty")
    else:
        relationship_ids: list[str] = []
        for index, relationship in enumerate(relationships):
            if not isinstance(relationship, Mapping):
                issues.append(f"atlas-relationship-invalid:{index}")
                continue
            relationship_ids.append(str(relationship.get("relationship_id") or ""))
            if (
                relationship.get("from_node_id") not in zoom_node_ids
                or relationship.get("to_node_id") not in zoom_node_ids
            ):
                issues.append(f"atlas-relationship-node-unresolved:{index}")
        if len(relationship_ids) != len(set(relationship_ids)):
            issues.append("atlas-relationship-duplicate-id")
    return {
        "status": "ok" if not issues else "invalid",
        "zoom_levels": zoom_levels,
        "timeline_counts": timeline_counts,
        "ideal_forms": sorted(atlas_ideal_ids),
        "self_image_count": len(atlas_self_ids),
    }, issues


def atlas_receipt_projection(
    document: Any,
    *,
    atlas: Mapping[str, Any],
    source_envelopes: Any,
    assertions: Any,
    ideal_forms: Any,
    self_images: Any,
    iceberg_atlas: Any,
) -> tuple[dict[str, Any], list[str]]:
    issues = strict_readiness_issues(document, "atlas-receipt")
    if not isinstance(document, Mapping):
        return {"ready": False}, issues
    predicates = document.get("predicate_results", {})
    if not isinstance(predicates, Mapping) or not predicates or not all(value is True for value in predicates.values()):
        issues.append("atlas-receipt-predicates-incomplete")
    if document.get("timeline_counts") != atlas.get("timeline_counts"):
        issues.append("atlas-receipt-timeline-counts-mismatch")
    expected_zooms = {
        str(item.get("id")): item.get("node_count")
        for item in atlas.get("zoom_levels", [])
        if isinstance(item, Mapping)
    }
    if document.get("zoom_counts") != expected_zooms:
        issues.append("atlas-receipt-zoom-counts-mismatch")
    source_set = document.get("source_envelope_set")
    source_records = source_envelopes if isinstance(source_envelopes, list) else []
    if not isinstance(source_set, Mapping) or (
        source_set.get("digest") != digest_value(source_records) or source_set.get("count") != len(source_records)
    ):
        issues.append("atlas-receipt-source-envelope-digest-mismatch")
    assertion_set = document.get("assertion_evidence_set")
    assertion_records = assertions if isinstance(assertions, list) else []
    if not isinstance(assertion_set, Mapping) or (
        assertion_set.get("digest") != digest_value(assertion_records)
        or assertion_set.get("count") != len(assertion_records)
    ):
        issues.append("atlas-receipt-assertion-digest-mismatch")
    ideal_reference = document.get("ideal_form_register")
    if (
        not isinstance(ideal_reference, Mapping)
        or not isinstance(ideal_forms, Mapping)
        or (
            ideal_reference.get("artifact_id") != ideal_forms.get("register_id")
            or ideal_reference.get("digest") != ideal_forms.get("register_digest")
        )
    ):
        issues.append("atlas-receipt-ideal-form-digest-mismatch")
    self_reference = document.get("node_self_image_set")
    if (
        not isinstance(self_reference, Mapping)
        or not isinstance(self_images, Mapping)
        or (
            self_reference.get("artifact_id") != self_images.get("set_id")
            or self_reference.get("digest") != self_images.get("set_digest")
            or self_reference.get("count") != len(self_images.get("self_images", []))
        )
    ):
        issues.append("atlas-receipt-self-image-digest-mismatch")
    atlas_reference = document.get("iceberg_atlas")
    if (
        not isinstance(atlas_reference, Mapping)
        or not isinstance(iceberg_atlas, Mapping)
        or (
            atlas_reference.get("artifact_id") != iceberg_atlas.get("atlas_id")
            or atlas_reference.get("digest") != iceberg_atlas.get("atlas_digest")
        )
    ):
        issues.append("atlas-receipt-atlas-digest-mismatch")
    return {
        "ready": not issues,
        "predicate_count": len(predicates) if isinstance(predicates, Mapping) else 0,
    }, issues


SELF_DIGEST_FIELDS: dict[str, str] = {
    "source_census": "census_digest",
    "coverage_receipt": "receipt_hash",
    "ideal_forms": "register_digest",
    "self_images": "set_digest",
    "iceberg_atlas": "atlas_digest",
    "normalization_parity": "receipt_digest",
    "atlas_receipt": "receipt_digest",
}


def declared_contract_digest(document: Any, field: str) -> tuple[str | None, bool]:
    if not isinstance(document, Mapping):
        return None, False
    declared = document.get(field)
    payload = {key: value for key, value in document.items() if key != field}
    computed = digest_value(payload)
    return str(declared) if declared is not None else None, declared == computed


def snapshot_bundle_projection(
    document: Any,
    *,
    documents: Mapping[str, Any],
    cadence: Mapping[str, Any],
    stage_receipts: Mapping[str, Any],
    public_inputs: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(document, Mapping):
        return {"ready": False}, ["snapshot-bundle-missing"]
    issues: list[str] = []
    snapshot_id = str(document.get("snapshot_id") or "")
    governed_input_keys = (
        "source_census",
        "source_envelopes",
        "normalized_events",
        "normalization_parity",
        "lineage_graph",
        "governance_testament",
        "assertion_evidence",
        "coverage_receipt",
        "ideal_forms",
        "iceberg_atlas",
        "self_images",
        "atlas_receipt",
    )
    contracts_by_key = {spec.key: spec.contract for spec in INPUT_SPECS}
    bundle_reference_fields = {
        "source_census": "source_census",
        "normalization_parity": "normalization_parity_receipt",
        "lineage_graph": "lineage_graph",
        "governance_testament": "governance_testament",
        "coverage_receipt": "coverage",
        "ideal_forms": "ideal_form_register",
        "self_images": "node_self_image_set",
        "iceberg_atlas": "iceberg_atlas",
        "atlas_receipt": "governance_atlas_receipt",
    }
    stage_outputs = stage_receipts.get("output_bindings", [])
    for key in governed_input_keys:
        metadata = public_inputs.get(key, {})
        raw_digest = metadata.get("sha256")
        expected_digest = f"sha256:{raw_digest}" if isinstance(raw_digest, str) else None
        matches = [
            output
            for output in stage_outputs
            if isinstance(output, Mapping)
            and output.get("contract") == contracts_by_key.get(key)
            and output.get("digest") == expected_digest
        ]
        if len(matches) != 1:
            issues.append(f"snapshot-bundle-stage-output-binding-mismatch:{key}")
            continue
        bundle_field = bundle_reference_fields.get(key)
        bundle_reference = document.get(bundle_field) if bundle_field else None
        if bundle_field and (
            not isinstance(bundle_reference, Mapping)
            or matches[0].get("reference") != bundle_reference.get("reference")
        ):
            issues.append(f"snapshot-bundle-stage-output-reference-mismatch:{key}")

    for key, field in SELF_DIGEST_FIELDS.items():
        owner_document = documents.get(key)
        declared, valid = declared_contract_digest(owner_document, field)
        if declared is None:
            issues.append(f"digest-missing:{key}")
        elif not valid:
            issues.append(f"digest-mismatch:{key}")

    if document.get("normalized_events") != documents.get("normalized_events"):
        issues.append("snapshot-bundle-normalized-events-mismatch")
    if document.get("source_envelopes") != documents.get("source_envelopes"):
        issues.append("snapshot-bundle-source-envelopes-mismatch")
    if document.get("assertion_evidence") != documents.get("assertion_evidence"):
        issues.append("snapshot-bundle-assertion-evidence-mismatch")

    reference_contracts: tuple[tuple[str, str, str, str, str], ...] = (
        ("source_census", "source_census", "census_id", "census_digest", "census_id"),
        ("lineage_graph", "lineage_graph", "graph_id", "", "artifact_id"),
        (
            "governance_testament",
            "governance_testament",
            "testament_id",
            "",
            "artifact_id",
        ),
        ("coverage", "coverage_receipt", "receipt_id", "receipt_hash", "receipt_id"),
        ("ideal_form_register", "ideal_forms", "register_id", "register_digest", "artifact_id"),
        ("node_self_image_set", "self_images", "set_id", "set_digest", "artifact_id"),
        ("iceberg_atlas", "iceberg_atlas", "atlas_id", "atlas_digest", "artifact_id"),
        (
            "normalization_parity_receipt",
            "normalization_parity",
            "receipt_id",
            "receipt_digest",
            "receipt_id",
        ),
        (
            "governance_atlas_receipt",
            "atlas_receipt",
            "atlas_receipt_id",
            "receipt_digest",
            "receipt_id",
        ),
    )
    for bundle_key, owner_key, owner_id_key, owner_digest_key, bundle_id_key in reference_contracts:
        reference = document.get(bundle_key)
        owner = documents.get(owner_key)
        if not isinstance(reference, Mapping) or not isinstance(owner, Mapping):
            issues.append(f"snapshot-bundle-reference-missing:{bundle_key}")
            continue
        expected_digest = owner.get(owner_digest_key) if owner_digest_key else digest_value(owner)
        if (
            reference.get(bundle_id_key) != owner.get(owner_id_key)
            or reference.get("digest") != expected_digest
            or reference.get("snapshot_id") != snapshot_id
        ):
            issues.append(f"snapshot-bundle-reference-mismatch:{bundle_key}")

    source_census_reference = document.get("source_census")
    source_census = documents.get("source_census")
    if (
        not isinstance(source_census_reference, Mapping)
        or not isinstance(source_census, Mapping)
        or (source_census_reference.get("raw_unit_count") != len(source_census.get("raw_units", [])))
    ):
        issues.append("snapshot-bundle-source-census-summary-mismatch")
    lineage_reference = document.get("lineage_graph")
    lineage_graph = documents.get("lineage_graph")
    if (
        not isinstance(lineage_reference, Mapping)
        or not isinstance(lineage_graph, Mapping)
        or (lineage_reference.get("node_count") != len(lineage_graph.get("nodes", [])))
    ):
        issues.append("snapshot-bundle-lineage-summary-mismatch")
    testament_reference = document.get("governance_testament")
    testament = documents.get("governance_testament")
    testament_coverage = (
        testament.get("ratification", {}).get("constitutional_coverage")
        if isinstance(testament, Mapping) and isinstance(testament.get("ratification"), Mapping)
        else {}
    )
    if (
        not isinstance(testament_reference, Mapping)
        or not isinstance(testament, Mapping)
        or (
            testament_reference.get("status") != testament.get("status")
            or testament_reference.get("constitutional_coverage_ready")
            is not (isinstance(testament_coverage, Mapping) and testament_coverage.get("ready") is True)
        )
    ):
        issues.append("snapshot-bundle-testament-summary-mismatch")
    coverage_reference = document.get("coverage")
    coverage_receipt = documents.get("coverage_receipt")
    if (
        not isinstance(coverage_reference, Mapping)
        or not isinstance(coverage_receipt, Mapping)
        or (
            coverage_reference.get("exact_all") is not coverage_receipt.get("exact_all")
            or coverage_reference.get("ready") is not coverage_receipt.get("ready")
        )
    ):
        issues.append("snapshot-bundle-coverage-summary-mismatch")
    ideal_reference = document.get("ideal_form_register")
    ideal_forms = documents.get("ideal_forms")
    if (
        not isinstance(ideal_reference, Mapping)
        or not isinstance(ideal_forms, Mapping)
        or (
            ideal_reference.get("count") != len(ideal_forms.get("ideal_forms", []))
            or ideal_reference.get("ready")
            is not (isinstance(ideal_forms.get("readiness"), Mapping) and ideal_forms["readiness"].get("ready") is True)
        )
    ):
        issues.append("snapshot-bundle-ideal-summary-mismatch")
    self_reference = document.get("node_self_image_set")
    self_images = documents.get("self_images")
    if (
        not isinstance(self_reference, Mapping)
        or not isinstance(self_images, Mapping)
        or (
            self_reference.get("count") != len(self_images.get("self_images", []))
            or self_reference.get("ready")
            is not (isinstance(self_images.get("readiness"), Mapping) and self_images["readiness"].get("ready") is True)
        )
    ):
        issues.append("snapshot-bundle-self-image-summary-mismatch")
    atlas_reference = document.get("iceberg_atlas")
    iceberg_atlas = documents.get("iceberg_atlas")
    if (
        not isinstance(atlas_reference, Mapping)
        or not isinstance(iceberg_atlas, Mapping)
        or (
            atlas_reference.get("timeline_count")
            != sum(
                len(value)
                for value in (
                    iceberg_atlas.get("timelines", {}).values()
                    if isinstance(iceberg_atlas.get("timelines"), Mapping)
                    else []
                )
                if isinstance(value, list)
            )
            or atlas_reference.get("zoom_count")
            != len(
                iceberg_atlas.get("zoom_levels", {}) if isinstance(iceberg_atlas.get("zoom_levels"), Mapping) else {}
            )
        )
    ):
        issues.append("snapshot-bundle-atlas-summary-mismatch")
    parity_reference = document.get("normalization_parity_receipt")
    parity = documents.get("normalization_parity")
    if (
        not isinstance(parity_reference, Mapping)
        or not isinstance(parity, Mapping)
        or (
            parity_reference.get("ready")
            is not (isinstance(parity.get("readiness"), Mapping) and parity["readiness"].get("ready") is True)
        )
    ):
        issues.append("snapshot-bundle-parity-summary-mismatch")
    atlas_receipt_reference = document.get("governance_atlas_receipt")
    atlas_receipt = documents.get("atlas_receipt")
    if (
        not isinstance(atlas_receipt_reference, Mapping)
        or not isinstance(atlas_receipt, Mapping)
        or (
            atlas_receipt_reference.get("ready")
            is not (
                isinstance(atlas_receipt.get("readiness"), Mapping) and atlas_receipt["readiness"].get("ready") is True
            )
        )
    ):
        issues.append("snapshot-bundle-atlas-receipt-summary-mismatch")

    cadence_receipts = documents.get("cadence_receipt")
    bundle_cadence = document.get("governance_cadence_receipts")
    if not isinstance(cadence_receipts, list) or not isinstance(bundle_cadence, list):
        issues.append("snapshot-bundle-cadence-references-missing")
    elif len(cadence_receipts) != 2 or len(bundle_cadence) != 2:
        issues.append("snapshot-bundle-two-run-proof-missing")
    else:
        for index, (owner, reference) in enumerate(zip(cadence_receipts, bundle_cadence, strict=True)):
            if (
                not isinstance(owner, Mapping)
                or not isinstance(reference, Mapping)
                or (
                    reference.get("receipt_id") != owner.get("cadence_receipt_id")
                    or reference.get("digest") != owner.get("receipt_digest")
                    or reference.get("run_number") != owner.get("run_number")
                    or reference.get("output_digest") != owner.get("output_digest")
                )
            ):
                issues.append(f"snapshot-bundle-cadence-reference-mismatch:{index}")

    final_cadence = (
        cadence_receipts[-1]
        if isinstance(cadence_receipts, list) and cadence_receipts and isinstance(cadence_receipts[-1], Mapping)
        else {}
    )
    full_stage_receipts = stage_receipts.get("receipts", [])
    stage_references = document.get("governance_stage_receipts")
    expected_stage_references = [
        {
            "contract_name": "governance-stage-receipt.v1",
            "stage": item.get("stage"),
            "receipt_id": item.get("stage_receipt_id"),
            "reference": item.get("receipt_target"),
            "snapshot_id": snapshot_id,
            "digest": item.get("receipt_digest"),
            "status": item.get("status"),
        }
        for item in full_stage_receipts
        if isinstance(item, Mapping)
    ]
    if not isinstance(stage_references, list) or stage_references != expected_stage_references:
        issues.append("snapshot-bundle-stage-references-mismatch")
    final_cadence_summaries = final_cadence.get("stage_receipts", [])
    expected_cadence_summaries = [
        {
            "stage": item.get("stage"),
            "stage_receipt_id": item.get("stage_receipt_id"),
            "reference": item.get("receipt_target"),
            "status": item.get("status"),
            "receipt_digest": item.get("receipt_digest"),
            "predecessor_receipt_digest": item.get("predecessor_receipt_digest"),
        }
        for item in full_stage_receipts
        if isinstance(item, Mapping)
    ]
    if final_cadence_summaries != expected_cadence_summaries:
        issues.append("snapshot-bundle-cadence-stage-chain-mismatch")

    post_proof = document.get("post_proof_idempotence")
    if not isinstance(post_proof, Mapping) or (
        post_proof.get("status") != "proven"
        or post_proof.get("cadence_receipt_digest") != final_cadence.get("receipt_digest")
        or post_proof.get("output_digest") != final_cadence.get("output_digest")
        or any(
            post_proof.get(field) != 0
            for field in (
                "new_event_count",
                "changed_byte_count",
                "replayed_completed_children",
                "emitted_receipt_count",
            )
        )
    ):
        issues.append("snapshot-bundle-post-proof-idempotence-failed")

    issues.extend(strict_readiness_issues(document, "snapshot-bundle"))
    declared, valid = declared_contract_digest(document, "bundle_digest")
    if declared is None:
        issues.append("digest-missing:snapshot-bundle")
    elif not valid:
        issues.append("digest-mismatch:snapshot-bundle")
    if not cadence.get("fixed_point_proven"):
        issues.append("snapshot-bundle-fixed-point-unproven")
    return {
        "ready": not issues,
        "owner_reference_count": len(reference_contracts),
        "cadence_run_count": len(bundle_cadence) if isinstance(bundle_cadence, list) else 0,
    }, issues


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
    schema_root: Path | None = None,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = dict(configured_inputs() if input_paths is None else input_paths)
    configured_schema_root = paths.pop("schema_root", None)
    schema_root = schema_root or configured_schema_root or SCHEMA_ROOT
    documents: dict[str, Any] = {}
    public_inputs: dict[str, dict[str, Any]] = {}
    private_paths: dict[str, str | None] = {}
    blockers: list[dict[str, Any]] = []
    violations: list[str] = []
    snapshots: dict[str, str] = {}
    snapshot_digests: dict[str, str] = {}

    schema_catalog_ready = bool(schema_root is not None and schema_root.is_dir())
    private_paths["schema_catalog"] = str(schema_root) if schema_root is not None else None
    public_inputs["schema_catalog"] = {
        "contract": "public-governance-memory-schema-catalog",
        "state": "available" if schema_catalog_ready else "missing-configuration",
        "snapshot_id": None,
    }
    if not schema_catalog_ready:
        blockers.append(
            {
                "id": "owner-receipt:schema_catalog:missing-configuration",
                "input": "schema_catalog",
                "owner_reference": "parameter-contract:LIMEN_GOV_SCHEMA_ROOT",
                "failed_predicate": "public governance-memory schemas are available",
                "next_command": (
                    'LIMEN_GOV_SCHEMA_ROOT="$SCHEMA_DEFINITIONS_ROOT" '
                    "python3 scripts/governance-memory-readiness.py --strict"
                ),
            }
        )

    for spec in INPUT_SPECS:
        path = paths.get(spec.key)
        private_paths[spec.key] = str(path) if path is not None else None
        document, metadata = load_input(path, max_bytes=max_input_bytes)
        public_metadata = dict(metadata)
        public_metadata["contract"] = spec.contract
        if document is not None:
            documents[spec.key] = document
            snapshot_ids = extract_snapshot_ids(document)
            digests = extract_snapshot_digests(document)
            declared_contracts = extract_contract_ids(document)
            public_metadata["snapshot_id"] = snapshot_ids[0] if len(snapshot_ids) == 1 else None
            public_metadata["snapshot_digest"] = digests[0] if len(digests) == 1 else None
            public_metadata["declared_contract"] = (
                declared_contracts[0] if len(declared_contracts) == 1 else declared_contracts
            )
            if len(snapshot_ids) == 1:
                snapshots[spec.key] = snapshot_ids[0]
            elif len(snapshot_ids) > 1:
                violations.append(f"snapshot-id-mismatch:{spec.key}")
            elif spec.snapshot_required:
                violations.append(f"snapshot-id-missing:{spec.key}")
            if len(digests) == 1:
                snapshot_digests[spec.key] = digests[0]
            elif len(digests) > 1:
                violations.append(f"snapshot-digest-mismatch:{spec.key}")
            if not contract_matches(declared_contracts, spec.contract):
                violations.append(f"contract-mismatch:{spec.key}")
            if schema_catalog_ready and schema_root is not None:
                schema, diagnostic = load_schema(schema_root, spec.contract)
                if schema is None:
                    violations.append(f"schema-unavailable:{spec.key}:{diagnostic}")
                else:
                    violations.extend(schema_issues(document, spec, schema))
        else:
            blockers.append(blocker(spec, str(metadata["state"]), metadata.get("diagnostic")))
        public_inputs[spec.key] = public_metadata

    cadence_path = paths.get("cadence_receipt")
    if cadence_path is not None:
        for marker_name, issue in (
            ("governance-cadence-active.v1.json", "cadence-execution-active"),
            ("governance-cadence-invalidated.v1.json", "cadence-proof-invalidated"),
        ):
            if cadence_path.parent.joinpath(marker_name).is_file():
                violations.append(issue)

    snapshot_values = sorted(set(snapshots.values()))
    if len(snapshot_values) > 1:
        violations.append("snapshot-id-mismatch")
    snapshot_id = snapshot_values[0] if len(snapshot_values) == 1 else None
    snapshot_digest_values = sorted(set(snapshot_digests.values()))
    if len(snapshot_digest_values) > 1:
        violations.append("snapshot-digest-mismatch")
    snapshot_digest = snapshot_digest_values[0] if len(snapshot_digest_values) == 1 else None

    coverage_document = documents.get("coverage_receipt")
    if coverage_document is not None:
        coverage, coverage_issues = coverage_projection(coverage_document)
        violations.extend(coverage_issues)
    else:
        coverage = {
            "denominator": None,
            "source_ids": [],
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

    source_envelopes, envelope_issues = source_envelope_projection(documents.get("source_envelopes"))
    violations.extend(envelope_issues)
    envelopes_by_id = {
        str(record.get("source_id")): record
        for record in (documents.get("source_envelopes") if isinstance(documents.get("source_envelopes"), list) else [])
        if isinstance(record, Mapping)
    }
    normalized_events, normalized_issues = normalized_event_projection(
        documents.get("normalized_events"),
        envelopes_by_id=envelopes_by_id,
    )
    violations.extend(normalized_issues)
    events_by_id = {
        str(record.get("event_id")): record
        for record in (
            documents.get("normalized_events") if isinstance(documents.get("normalized_events"), list) else []
        )
        if isinstance(record, Mapping)
    }
    if not all(
        reference_resolves(reference, set(source_envelopes["source_ids"]))
        for reference in normalized_events["source_envelope_references"]
    ):
        violations.append("normalized-event-envelope-reference-unresolved")
    parity, parity_issues = normalization_parity_projection(
        documents.get("normalization_parity"),
        census=documents.get("source_census"),
        normalized_events=normalized_events,
        events_by_id=events_by_id,
    )
    violations.extend(parity_issues)
    lineage, lineage_issues = lineage_projection(
        documents.get("lineage_graph"),
        envelopes_by_id,
    )
    violations.extend(lineage_issues)

    known_coverage_ids = set(source_envelopes["source_ids"]) | set(census["raw_unit_ids"])
    if not all(reference_resolves(source_id, known_coverage_ids) for source_id in coverage["source_ids"]):
        violations.append("coverage-source-identity-unresolved")

    snapshot_bundle_document = documents.get("snapshot_bundle")
    snapshot_at = (
        str(snapshot_bundle_document.get("snapshot_at")) if isinstance(snapshot_bundle_document, Mapping) else None
    )
    snapshot_generated_at = (
        str(snapshot_bundle_document.get("generated_at")) if isinstance(snapshot_bundle_document, Mapping) else None
    )
    stage_receipts, stage_receipt_issues = stage_receipt_projection(documents.get("stage_receipts"))
    violations.extend(stage_receipt_issues)
    receipt_bindings = trusted_receipt_bindings(snapshot_bundle_document)
    assertions, assertion_issues = assertion_projection(
        documents.get("assertion_evidence"),
        events_by_id=events_by_id,
        envelopes_by_id=envelopes_by_id,
        testament=documents.get("governance_testament"),
        snapshot_at=snapshot_at,
        receipt_bindings=receipt_bindings,
    )
    violations.extend(assertion_issues)
    assertions_by_id = {
        str(record.get("assertion_id")): record
        for record in (
            documents.get("assertion_evidence") if isinstance(documents.get("assertion_evidence"), list) else []
        )
        if isinstance(record, Mapping)
    }
    testament, testament_issues = testament_projection(
        documents.get("governance_testament"),
        events_by_id=events_by_id,
        assertions_by_id=assertions_by_id,
    )
    violations.extend(testament_issues)
    ideal_forms, ideal_issues = ideal_form_projection(
        documents.get("ideal_forms"),
        assertion_ids=set(assertions["assertion_ids"]),
        verified_predicate_receipts=stage_receipts["receipt_records"],
    )
    violations.extend(ideal_issues)
    ideal_predicate_ids = {
        str(predicate.get("predicate_id"))
        for item in (
            documents.get("ideal_forms", {}).get("ideal_forms", [])
            if isinstance(documents.get("ideal_forms"), Mapping)
            else []
        )
        if isinstance(item, Mapping)
        for predicate in (item.get("predicates", []) if isinstance(item.get("predicates"), list) else [])
        if isinstance(predicate, Mapping)
    }
    evidence_ids = (
        set(receipt_bindings)
        | set(stage_receipts["receipt_records"])
        | {str(output.get("reference")) for output in stage_receipts["output_bindings"] if isinstance(output, Mapping)}
        | set(assertions["assertion_ids"])
        | set(normalized_events["event_ids"])
        | set(source_envelopes["source_ids"])
    )
    self_images, self_image_issues = self_image_projection(
        documents.get("self_images"),
        snapshot_at=snapshot_at,
        generated_at=snapshot_generated_at,
        evidence_ids=evidence_ids,
        ideal_ids=set(ideal_forms["ideal_ids"]),
        ideal_predicate_ids=ideal_predicate_ids,
    )
    violations.extend(self_image_issues)
    atlas, atlas_issues = atlas_projection(
        documents.get("iceberg_atlas"),
        ideal_ids=set(ideal_forms["ideal_ids"]),
        self_image_ids=set(self_images["node_ids"]),
        source_envelope_ids=set(source_envelopes["source_ids"]),
        event_ids=set(normalized_events["event_ids"]),
        assertion_ids=set(assertions["assertion_ids"]),
    )
    violations.extend(atlas_issues)
    atlas_receipt, atlas_receipt_issues = atlas_receipt_projection(
        documents.get("atlas_receipt"),
        atlas=atlas,
        source_envelopes=documents.get("source_envelopes"),
        assertions=documents.get("assertion_evidence"),
        ideal_forms=documents.get("ideal_forms"),
        self_images=documents.get("self_images"),
        iceberg_atlas=documents.get("iceberg_atlas"),
    )
    violations.extend(atlas_receipt_issues)
    cadence, cadence_issues = cadence_projection(
        documents.get("cadence_receipt"),
        stage_receipts=stage_receipts,
    )
    violations.extend(cadence_issues)
    snapshot_bundle, bundle_issues = snapshot_bundle_projection(
        snapshot_bundle_document,
        documents=documents,
        cadence=cadence,
        stage_receipts=stage_receipts,
        public_inputs=public_inputs,
    )
    violations.extend(bundle_issues)

    available_count = sum(
        1 for key, item in public_inputs.items() if key != "schema_catalog" and item["state"] == "available"
    )
    if violations:
        status = "blocked"
    elif (
        available_count == len(INPUT_SPECS)
        and schema_catalog_ready
        and coverage["exact_all"]
        and coverage["ready"]
        and census["ready"]
        and parity["ready"]
        and testament["ready"]
        and ideal_forms["ready"]
        and self_images["ready"]
        and atlas_receipt["ready"]
        and stage_receipts["complete"]
        and cadence["complete"]
        and snapshot_bundle["ready"]
    ):
        status = "ready"
    else:
        status = "degraded"

    core: dict[str, Any] = {
        "$schema": "governance-memory-readiness.v1",
        "surface": "redacted-read-model",
        "status": status,
        "snapshot_id": snapshot_id,
        "snapshot_digest": snapshot_digest,
        "inputs": public_inputs,
        "coverage": coverage,
        "source_census": census,
        "source_envelopes": source_envelopes,
        "normalized_events": normalized_events,
        "normalization_parity": parity,
        "lineage": lineage,
        "testament": testament,
        "stage_receipts": {
            "required_order": stage_receipts["required_order"],
            "observed": stage_receipts["observed"],
            "output_binding_count": len(stage_receipts["output_bindings"]),
            "complete": stage_receipts["complete"],
        },
        "cadence": cadence,
        "assertions": assertions,
        "ideal_forms": ideal_forms,
        "self_images": self_images,
        "atlas": atlas,
        "atlas_receipt": atlas_receipt,
        "snapshot_bundle": snapshot_bundle,
        "blockers": sorted(blockers, key=lambda item: item["id"]),
        "violations": sorted(set(violations)),
    }
    input_fingerprint = digest_value({key: value.get("sha256") for key, value in public_inputs.items()})
    core["input_fingerprint"] = input_fingerprint
    core["receipt_id"] = digest_value(core)
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
        lines.append(f"| `{key}` | `{item['contract']}` | `{item['state']}` | `{item.get('snapshot_id') or '—'}` |")
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
