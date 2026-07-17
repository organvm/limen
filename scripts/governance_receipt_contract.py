"""Pure contract logic for Limen's governance-memory receipt cadence owner.

This module reads and validates owner artifacts but never writes them.  The mutating
owner and the independent predicate intentionally share only these pure derivations.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import rfc8785


PRE_PROOF_CONTRACT = "governance-snapshot-bundle-pre-proof.v1"
RENDER_PROJECTION_CONTRACT = "engine-governance-render.v1"
READINESS_DEBT_FIELDS = (
    "unresolved_blockers",
    "quarantines",
    "missing_requirements",
    "citation_debt",
    "incomplete_predicates",
)
READINESS_STATUSES = {
    "incomplete",
    "blocked",
    "ready",
    "closed_with_owner_routed_debt",
}
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
PUBLIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,255}$")
EVENT_ID = re.compile(r"^evt_[0-9a-f]{64}$")


class ReceiptContractError(RuntimeError):
    """One direct receipt-stage input or runtime binding is invalid."""


@dataclass(frozen=True)
class Runtime:
    """The bounded cadence runtime injected by Limen."""

    stage: str
    attempt: int
    traversal: int
    proof_mode: bool
    metrics_path: Path
    stage_receipts_path: Path
    predecessor_receipt_digest: str
    prior_stage_receipt: Path | None
    max_items: int
    snapshot_id: str
    snapshot_at: str
    run_root: Path


@dataclass(frozen=True)
class ArtifactPaths:
    """Direct, acyclic owner artifacts consumed by the receipt stage."""

    source_census: Path
    normalized_events: Path
    source_envelopes: Path
    assertion_evidence: Path
    lineage_graph: Path
    governance_testament: Path
    coverage: Path
    ideal_form_register: Path
    node_self_image_set: Path
    iceberg_atlas: Path
    normalization_parity_receipt: Path
    governance_atlas_receipt: Path
    render_projection: Path


@dataclass(frozen=True)
class ReceiptPlan:
    """Fully derived deterministic output and its bounded child receipt."""

    document: dict[str, Any]
    document_bytes: bytes
    input_digest: str
    output_digest: str
    child_id: str
    bounded_units: int


def canonical_bytes(value: Any) -> bytes:
    """Return RFC 8785 bytes, rejecting values outside canonical JSON."""
    try:
        return rfc8785.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ReceiptContractError(f"value is not RFC 8785 canonical JSON: {exc}") from exc


def digest_value(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_bytes(value)).hexdigest()}"


def _reject_constant(value: str) -> None:
    raise ReceiptContractError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptContractError(f"duplicate JSON object key is forbidden: {key}")
        result[key] = value
    return result


def _decode_json(text: str, *, label: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ReceiptContractError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ReceiptContractError(f"{label} is not valid JSON: {exc}") from exc


def load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = _decode_json(path.read_text(encoding="utf-8"), label=label)
    except OSError as exc:
        raise ReceiptContractError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ReceiptContractError(f"{label} must contain one JSON object")
    return value


def load_jsonl_rows(path: Path, *, label: str) -> list[dict[str, Any]]:
    """Load a nonempty JSONL file containing exactly one object per physical line."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReceiptContractError(f"{label} is unreadable") from exc
    if not text.strip():
        raise ReceiptContractError(f"{label} must be nonempty")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        row = _decode_json(line, label=f"{label} line {line_number}")
        if not isinstance(row, dict):
            raise ReceiptContractError(f"{label} line {line_number} must contain one JSON object")
        rows.append(row)
    if not rows:
        raise ReceiptContractError(f"{label} must contain one or more JSON objects")
    return rows


def load_rows(path: Path, *, label: str, wrapper_fields: Sequence[str] = ()) -> list[dict[str, Any]]:
    """Load a JSON array, one object, or one explicitly named object wrapper."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReceiptContractError(f"{label} is unreadable") from exc
    if not text.strip():
        raise ReceiptContractError(f"{label} must be nonempty")
    value = _decode_json(text, label=label)
    if isinstance(value, dict):
        wrapped = next(
            (value[field] for field in wrapper_fields if field in value and isinstance(value[field], list)),
            None,
        )
        value = wrapped if wrapped is not None else [value]
    if not isinstance(value, list) or not value or not all(isinstance(row, dict) for row in value):
        raise ReceiptContractError(f"{label} must contain one or more JSON objects")
    return [dict(row) for row in value]


def _positive_integer(value: str | None, label: str) -> int:
    try:
        parsed = int(value or "")
    except ValueError as exc:
        raise ReceiptContractError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise ReceiptContractError(f"{label} must be a positive integer")
    return parsed


def _utc_timestamp(value: str, label: str) -> str:
    if not value.endswith("Z"):
        raise ReceiptContractError(f"{label} must be an explicit UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReceiptContractError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ReceiptContractError(f"{label} must be UTC")
    return value


def validate_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ReceiptContractError(f"{label} must be a sha256 digest")
    return value


def validate_public_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not PUBLIC_ID.fullmatch(value):
        raise ReceiptContractError(f"{label} must be a bounded public identifier")
    return value


def cadence_runtime(*, predicate: bool = False) -> Runtime:
    """Parse and cross-check the exact owner runtime without inventing defaults."""
    stage = os.environ.get("LIMEN_GOV_STAGE", "")
    if stage != "receipt":
        raise ReceiptContractError(f"LIMEN_GOV_STAGE must be 'receipt', got {stage!r}")
    attempt = _positive_integer(os.environ.get("LIMEN_GOV_STAGE_ATTEMPT"), "stage attempt")
    traversal = _positive_integer(os.environ.get("LIMEN_GOV_TRAVERSAL"), "traversal")
    proof_text = os.environ.get("LIMEN_GOV_PROOF_MODE")
    if proof_text not in {"0", "1"}:
        raise ReceiptContractError("LIMEN_GOV_PROOF_MODE must be 0 or 1")
    proof_mode = proof_text == "1"
    if proof_mode != (traversal >= 2):
        raise ReceiptContractError("proof mode contradicts traversal number")
    if predicate and os.environ.get("LIMEN_GOV_PREDICATE_MODE") != "1":
        raise ReceiptContractError("independent predicate requires LIMEN_GOV_PREDICATE_MODE=1")
    metrics_text = os.environ.get("LIMEN_GOV_STAGE_METRICS_OUT", "").strip()
    receipts_text = os.environ.get("LIMEN_GOV_STAGE_RECEIPTS", "").strip()
    run_root_text = os.environ.get("LIMEN_GOV_RUN_ROOT", "").strip()
    predecessor = validate_digest(
        os.environ.get("LIMEN_GOV_PREDECESSOR_RECEIPT_DIGEST"),
        "predecessor receipt digest",
    )
    if not metrics_text or not receipts_text or not run_root_text:
        raise ReceiptContractError("metrics, stage-receipt collection, and run-root paths are required")
    snapshot_id = validate_public_id(
        os.environ.get("LIMEN_GOV_SNAPSHOT_ID"),
        "snapshot ID",
    )
    snapshot_at = _utc_timestamp(
        os.environ.get("LIMEN_GOV_SNAPSHOT_AT", ""),
        "snapshot timestamp",
    )
    prior_text = os.environ.get("LIMEN_GOV_PRIOR_STAGE_RECEIPT", "").strip()
    prior = Path(prior_text).resolve() if prior_text else None
    if proof_mode != (prior is not None):
        raise ReceiptContractError("only proof traversal may bind a prior stage receipt")
    return Runtime(
        stage=stage,
        attempt=attempt,
        traversal=traversal,
        proof_mode=proof_mode,
        metrics_path=Path(metrics_text).resolve(),
        stage_receipts_path=Path(receipts_text).resolve(),
        predecessor_receipt_digest=predecessor,
        prior_stage_receipt=prior,
        max_items=_positive_integer(os.environ.get("LIMEN_GOV_MAX_ITEMS"), "maximum items"),
        snapshot_id=snapshot_id,
        snapshot_at=snapshot_at,
        run_root=Path(run_root_text).resolve(),
    )


def require_path_below(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ReceiptContractError(f"{label} must remain below the cadence run root") from exc
    return resolved


def add_owner_arguments(parser: argparse.ArgumentParser) -> None:
    """Declare the identical direct-input interface used by owner and predicate."""
    parser.add_argument("--source-census", required=True, type=Path)
    parser.add_argument("--normalized-events", required=True, type=Path)
    parser.add_argument("--source-envelopes", required=True, type=Path)
    parser.add_argument("--assertion-evidence", required=True, type=Path)
    parser.add_argument("--lineage-graph", required=True, type=Path)
    parser.add_argument("--governance-testament", required=True, type=Path)
    parser.add_argument("--coverage", required=True, type=Path)
    parser.add_argument("--ideal-form-register", required=True, type=Path)
    parser.add_argument("--node-self-image-set", required=True, type=Path)
    parser.add_argument("--iceberg-atlas", required=True, type=Path)
    parser.add_argument("--normalization-parity-receipt", required=True, type=Path)
    parser.add_argument("--governance-atlas-receipt", required=True, type=Path)
    parser.add_argument("--render-projection", required=True, type=Path)
    parser.add_argument("--snapshot-digest", required=True)
    parser.add_argument("--cadence-id", required=True)
    parser.add_argument("--output", required=True, type=Path)


def paths_from_args(args: argparse.Namespace) -> ArtifactPaths:
    return ArtifactPaths(
        source_census=args.source_census.resolve(),
        normalized_events=args.normalized_events.resolve(),
        source_envelopes=args.source_envelopes.resolve(),
        assertion_evidence=args.assertion_evidence.resolve(),
        lineage_graph=args.lineage_graph.resolve(),
        governance_testament=args.governance_testament.resolve(),
        coverage=args.coverage.resolve(),
        ideal_form_register=args.ideal_form_register.resolve(),
        node_self_image_set=args.node_self_image_set.resolve(),
        iceberg_atlas=args.iceberg_atlas.resolve(),
        normalization_parity_receipt=args.normalization_parity_receipt.resolve(),
        governance_atlas_receipt=args.governance_atlas_receipt.resolve(),
        render_projection=args.render_projection.resolve(),
    )


def _require_contract(
    document: Mapping[str, Any],
    name: str,
    *,
    label: str,
) -> None:
    if document.get("contract_name") != name or document.get("contract_version") != 1:
        raise ReceiptContractError(f"{label} must use {name} contract version 1")


def _embedded_digest(document: Mapping[str, Any], field: str, label: str) -> str:
    actual = validate_digest(document.get(field), f"{label} {field}")
    body = {key: value for key, value in document.items() if key != field}
    if actual != digest_value(body):
        raise ReceiptContractError(f"{label} {field} does not bind its RFC 8785 content")
    return actual


def _debt_list(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) and item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise ReceiptContractError(f"{label} must be a unique nonempty-string list")
    return sorted(value)


def standard_readiness(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReceiptContractError(f"{label} must be an object")
    exact_all = value.get("exact_all")
    ready = value.get("ready")
    status = value.get("status")
    if not isinstance(exact_all, bool) or not isinstance(ready, bool):
        raise ReceiptContractError(f"{label} exact_all and ready must be booleans")
    if status not in READINESS_STATUSES:
        raise ReceiptContractError(f"{label} has an invalid status")
    result: dict[str, Any] = {
        "exact_all": exact_all,
        **{field: _debt_list(value.get(field), f"{label}.{field}") for field in READINESS_DEBT_FIELDS},
        "ready": ready,
        "status": status,
    }
    computed_ready = exact_all and not any(result[field] for field in READINESS_DEBT_FIELDS)
    if ready != computed_ready or (ready != (status == "ready")):
        raise ReceiptContractError(f"{label} contains an internally inconsistent readiness claim")
    return result


def _merge_readiness(
    values: Sequence[Mapping[str, Any]],
    *,
    derived_debt: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    debt: dict[str, set[str]] = {field: set() for field in READINESS_DEBT_FIELDS}
    exact_all = True
    for value in values:
        exact_all = exact_all and bool(value["exact_all"])
        for field in READINESS_DEBT_FIELDS:
            debt[field].update(value[field])
    for field in READINESS_DEBT_FIELDS:
        debt[field].update(derived_debt.get(field, ()))
    normalized_debt = {field: sorted(debt[field]) for field in READINESS_DEBT_FIELDS}
    ready = exact_all and not any(normalized_debt.values())
    if ready:
        status = "ready"
    elif normalized_debt["unresolved_blockers"] or normalized_debt["quarantines"]:
        status = "blocked"
    else:
        status = "incomplete"
    return {
        "exact_all": exact_all,
        **normalized_debt,
        "ready": ready,
        "status": status,
    }


def _coverage_readiness(
    coverage: Mapping[str, Any],
    *,
    raw_unit_count: int,
) -> dict[str, Any]:
    _require_contract(coverage, "coverage-receipt.v1", label="coverage receipt")
    denominator = coverage.get("denominator")
    sources = coverage.get("sources")
    counts = coverage.get("counts")
    if (
        not isinstance(denominator, Mapping)
        or denominator.get("count") != raw_unit_count
        or not isinstance(sources, list)
        or len(sources) != raw_unit_count
        or not isinstance(counts, Mapping)
    ):
        raise ReceiptContractError("coverage denominator does not equal the source census")
    statuses = (
        "acquired",
        "parsed",
        "quarantined",
        "inaccessible",
        "missing_expected",
        "owner_blocked",
    )
    observed = {status: 0 for status in statuses}
    derived_blockers: list[str] = []
    derived_quarantines: list[str] = []
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ReceiptContractError(f"coverage source {index} must be an object")
        source_id = validate_public_id(source.get("source_id"), f"coverage source {index} ID")
        status = source.get("status")
        if source_id in source_ids or status not in observed:
            raise ReceiptContractError("coverage sources must have unique IDs and canonical statuses")
        source_ids.add(source_id)
        observed[str(status)] += 1
        if status == "quarantined":
            derived_quarantines.append(source_id)
        elif status in {"inaccessible", "missing_expected", "owner_blocked"}:
            derived_blockers.append(source_id)
    if any(counts.get(status) != observed[status] for status in statuses):
        raise ReceiptContractError("coverage counts do not match its classified sources")
    exact_all = len(sources) == raw_unit_count
    declared_exact = coverage.get("exact_all")
    declared_ready = coverage.get("ready")
    status = coverage.get("closure_status")
    if declared_exact is not exact_all or not isinstance(declared_ready, bool) or status not in READINESS_STATUSES:
        raise ReceiptContractError("coverage classification/readiness fields are invalid")
    debt = {field: _debt_list(coverage.get(field), f"coverage.{field}") for field in READINESS_DEBT_FIELDS}
    if not set(derived_blockers).issubset(debt["unresolved_blockers"]):
        raise ReceiptContractError("coverage omits blocker classifications from readiness debt")
    if not set(derived_quarantines).issubset(debt["quarantines"]):
        raise ReceiptContractError("coverage omits quarantine classifications from readiness debt")
    computed_ready = exact_all and not any(debt.values())
    if declared_ready != computed_ready or (declared_ready != (status == "ready")):
        raise ReceiptContractError("coverage contains a false readiness claim")
    return {
        "exact_all": exact_all,
        **debt,
        "ready": declared_ready,
        "status": status,
    }


def _snapshot_bound(
    document: Mapping[str, Any],
    *,
    runtime: Runtime,
    snapshot_digest: str,
    label: str,
) -> None:
    if document.get("snapshot_id") != runtime.snapshot_id:
        raise ReceiptContractError(f"{label} does not bind the cadence snapshot ID")
    if "snapshot_digest" in document and document.get("snapshot_digest") != snapshot_digest:
        raise ReceiptContractError(f"{label} does not bind the cadence snapshot digest")
    if "snapshot_at" in document and document.get("snapshot_at") != runtime.snapshot_at:
        raise ReceiptContractError(f"{label} does not bind the cadence snapshot timestamp")


def _sorted_unique_rows(
    rows: Sequence[dict[str, Any]],
    *,
    id_field: str,
    label: str,
) -> list[dict[str, Any]]:
    ids: list[str] = []
    for index, row in enumerate(rows):
        value = row.get(id_field)
        if not isinstance(value, str) or not value:
            raise ReceiptContractError(f"{label} {index} is missing {id_field}")
        ids.append(value)
    if len(ids) != len(set(ids)):
        raise ReceiptContractError(f"{label} contain duplicate {id_field} values")
    return sorted((dict(row) for row in rows), key=lambda row: str(row[id_field]))


def _render_readiness(
    projection: Mapping[str, Any],
    *,
    runtime: Runtime,
    snapshot_digest: str,
) -> dict[str, Any]:
    _require_contract(projection, RENDER_PROJECTION_CONTRACT, label="render projection")
    if (
        projection.get("stage") != "render"
        or projection.get("snapshot_id") != runtime.snapshot_id
        or projection.get("snapshot_at") != runtime.snapshot_at
        or projection.get("snapshot_digest") != snapshot_digest
        or not isinstance(projection.get("bounded_units"), int)
        or projection.get("bounded_units", 0) <= 0
    ):
        raise ReceiptContractError("render projection does not bind the exact frozen snapshot")
    artifacts = projection.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ReceiptContractError("render projection must bind nonempty owner artifacts")
    references: set[str] = set()
    for artifact in artifacts:
        if (
            not isinstance(artifact, Mapping)
            or not isinstance(artifact.get("artifact_id"), str)
            or not isinstance(artifact.get("reference"), str)
        ):
            raise ReceiptContractError("render projection has an invalid artifact descriptor")
        validate_digest(artifact.get("digest"), "render artifact digest")
        reference = str(artifact["reference"])
        if "/" in reference or "\\" in reference or reference.startswith("."):
            raise ReceiptContractError("render projection references must be public artifact names")
        references.add(reference)
    if not {
        "iceberg-atlas.public.json",
        "governance-atlas-receipt.json",
    }.issubset(references):
        raise ReceiptContractError("render projection omits Atlas or Atlas-receipt evidence")
    _embedded_digest(projection, "projection_digest", "render projection")
    return standard_readiness(projection.get("readiness"), label="render projection readiness")


def _testament_readiness(
    testament: Mapping[str, Any],
) -> tuple[bool, list[str], list[str]]:
    _require_contract(testament, "governance-testament.v1", label="governance testament")
    testament_id = validate_public_id(testament.get("testament_id"), "testament ID")
    status = testament.get("status")
    missing: list[str] = []
    incomplete: list[str] = []
    constitutional_ready = False
    ratification = testament.get("ratification")
    if status == "ratified":
        if not isinstance(ratification, Mapping):
            raise ReceiptContractError("ratified testament is missing its ratification evidence")
        coverage = ratification.get("constitutional_coverage")
        authority_events = ratification.get("authority_events")
        if (
            not isinstance(coverage, Mapping)
            or coverage.get("exact_all") is not True
            or coverage.get("ready") is not True
            or coverage.get("blocked_scopes") != []
            or coverage.get("missing_requirements") != []
            or not isinstance(authority_events, list)
            or not authority_events
        ):
            raise ReceiptContractError("ratified testament lacks ready constitutional authority")
        constitutional_ready = True
    elif status == "candidate":
        if ratification is not None:
            raise ReceiptContractError("candidate testament must not predeclare ratification")
        missing.append(f"governance-testament:{testament_id}:ratification-required")
    elif status in {"draft", "superseded"}:
        missing.append(f"governance-testament:{testament_id}:{status}")
    else:
        raise ReceiptContractError("governance testament status is invalid")
    predicates = testament.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        incomplete.append(f"governance-testament:{testament_id}:predicates")
    return constitutional_ready, missing, incomplete


def _assertion_debt(assertions: Sequence[Mapping[str, Any]]) -> list[str]:
    debt: list[str] = []
    for assertion in assertions:
        _require_contract(assertion, "assertion-evidence.v1", label="assertion evidence")
        assertion_id = validate_public_id(assertion.get("assertion_id"), "assertion ID")
        state = assertion.get("verification_state")
        if state not in {"unverified", "verified", "stale", "disputed"}:
            raise ReceiptContractError("assertion verification_state is invalid")
        references = assertion.get("evidence_references")
        if not isinstance(references, list) or not all(isinstance(item, str) and item for item in references):
            raise ReceiptContractError("assertion evidence references are invalid")
        if state != "verified" or len(references) < 2 or len(references) != len(set(references)):
            debt.append(f"assertion:{assertion_id}:verification")
    return debt


def _atlas_shape_debt(
    atlas: Mapping[str, Any],
) -> tuple[list[str], list[str], int, int]:
    timelines = atlas.get("timelines")
    zooms = atlas.get("zoom_levels")
    if not isinstance(timelines, Mapping) or len(timelines) != 2:
        raise ReceiptContractError("Iceberg Atlas must declare exactly two timeline lanes")
    if not isinstance(zooms, Mapping) or len(zooms) != 6:
        raise ReceiptContractError("Iceberg Atlas must declare exactly six zoom levels")
    missing: list[str] = []
    for lane, entries in timelines.items():
        if not isinstance(entries, list) or not entries:
            missing.append(f"iceberg-atlas:timeline:{lane}")
    for zoom, entries in zooms.items():
        if not isinstance(entries, list) or not entries:
            missing.append(f"iceberg-atlas:zoom:{zoom}")
    coverage = atlas.get("coverage")
    if not isinstance(coverage, Mapping) or not isinstance(coverage.get("exact_all"), bool):
        raise ReceiptContractError("Iceberg Atlas coverage is invalid")
    if coverage["exact_all"] is not True:
        missing.append("iceberg-atlas:coverage")
    citation_debt = _debt_list(atlas.get("citation_debt"), "iceberg-atlas.citation_debt")
    return (
        missing,
        [f"iceberg-atlas:citation:{item}" for item in citation_debt],
        2,
        6,
    )


def _count_sequence(document: Mapping[str, Any], field: str, label: str) -> int:
    value = document.get(field)
    if not isinstance(value, list) or not value:
        raise ReceiptContractError(f"{label}.{field} must be a nonempty list")
    return len(value)


def _input_descriptors(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "artifact_id": artifact_id,
            "digest": digest_value(value),
        }
        for artifact_id, value in sorted(inputs.items())
    ]


def build_receipt_plan(
    *,
    paths: ArtifactPaths,
    runtime: Runtime,
    snapshot_digest: str,
    cadence_id: str,
) -> ReceiptPlan:
    """Validate all direct inputs and derive the only governed receipt output."""
    snapshot_digest = validate_digest(snapshot_digest, "snapshot digest")
    cadence_id = validate_public_id(cadence_id, "cadence ID")

    census = load_object(paths.source_census, label="source census")
    _require_contract(census, "source-census.v1", label="source census")
    _snapshot_bound(census, runtime=runtime, snapshot_digest=snapshot_digest, label="source census")
    census_digest = _embedded_digest(census, "census_digest", "source census")
    raw_units = census.get("raw_units")
    if not isinstance(raw_units, list) or not raw_units:
        raise ReceiptContractError("source census must contain raw units")
    raw_ids: list[str] = []
    raw_hashes: dict[str, str | None] = {}
    for raw in raw_units:
        if not isinstance(raw, Mapping):
            raise ReceiptContractError("source census raw units must be objects")
        raw_id = validate_public_id(raw.get("raw_unit_id"), "raw unit ID")
        content_hash = raw.get("content_hash")
        if content_hash is not None:
            validate_digest(content_hash, f"{raw_id} content hash")
        raw_ids.append(raw_id)
        raw_hashes[raw_id] = content_hash
    if len(raw_ids) != len(set(raw_ids)):
        raise ReceiptContractError("source census raw unit IDs must be unique")

    events = _sorted_unique_rows(
        load_jsonl_rows(paths.normalized_events, label="normalized events"),
        id_field="event_id",
        label="normalized events",
    )
    sources = _sorted_unique_rows(
        load_jsonl_rows(paths.source_envelopes, label="source envelopes"),
        id_field="source_id",
        label="source envelopes",
    )
    assertions = _sorted_unique_rows(
        load_rows(
            paths.assertion_evidence,
            label="assertion evidence",
            wrapper_fields=("assertion_evidence", "assertions"),
        ),
        id_field="assertion_id",
        label="assertion evidence",
    )
    source_ids = {str(source["source_id"]) for source in sources}
    for source in sources:
        _require_contract(source, "source-envelope.v1", label="source envelope")
        custody = source.get("custody_snapshot")
        if (
            not isinstance(custody, Mapping)
            or custody.get("snapshot_id") != runtime.snapshot_id
            or custody.get("snapshot_hash") != snapshot_digest
        ):
            raise ReceiptContractError("source envelope does not bind the cadence snapshot")
        raw_id = source.get("raw_unit_id")
        if raw_id not in raw_hashes or source.get("raw_unit_content_hash") != raw_hashes[raw_id]:
            raise ReceiptContractError("source envelope does not bind its census raw unit")
    referenced_source_ids: set[str] = set()
    for event in events:
        _require_contract(event, "normalized-event.v1", label="normalized event")
        if (
            not EVENT_ID.fullmatch(str(event.get("event_id", "")))
            or event.get("snapshot_id") != runtime.snapshot_id
            or event.get("snapshot_digest") != snapshot_digest
        ):
            raise ReceiptContractError("normalized event does not bind the cadence snapshot")
        raw_id = event.get("raw_unit_id")
        if raw_id not in raw_hashes or event.get("raw_unit_content_hash") != raw_hashes[raw_id]:
            raise ReceiptContractError("normalized event does not bind its census raw unit")
        reference = event.get("source_envelope_reference")
        if not isinstance(reference, str) or "#" not in reference:
            raise ReceiptContractError("normalized event source envelope reference is invalid")
        source_id = reference.rsplit("#", 1)[-1]
        if source_id not in source_ids:
            raise ReceiptContractError("normalized event references an absent source envelope")
        referenced_source_ids.add(source_id)
    if referenced_source_ids != source_ids:
        raise ReceiptContractError("source envelope set contains unreferenced or missing rows")

    lineage = load_object(paths.lineage_graph, label="lineage graph")
    _require_contract(lineage, "lineage-graph.v1", label="lineage graph")
    if lineage.get("frozen_snapshot_id") != runtime.snapshot_id:
        raise ReceiptContractError("lineage graph does not bind the cadence snapshot")
    node_count = _count_sequence(lineage, "nodes", "lineage graph")
    edges = lineage.get("edges")
    if not isinstance(edges, list):
        raise ReceiptContractError("lineage graph edges must be a list")

    testament = load_object(paths.governance_testament, label="governance testament")
    constitutional_ready, testament_missing, testament_incomplete = _testament_readiness(testament)

    coverage = load_object(paths.coverage, label="coverage receipt")
    _snapshot_bound(coverage, runtime=runtime, snapshot_digest=snapshot_digest, label="coverage")
    coverage_digest = _embedded_digest(coverage, "receipt_hash", "coverage receipt")
    coverage_ready = _coverage_readiness(coverage, raw_unit_count=len(raw_units))
    denominator = coverage["denominator"]
    if denominator.get("manifest_hash") != census.get("manifest_digest"):
        raise ReceiptContractError("coverage denominator differs from census manifest")

    ideals = load_object(paths.ideal_form_register, label="ideal-form register")
    _require_contract(ideals, "ideal-form-register.v1", label="ideal-form register")
    _snapshot_bound(ideals, runtime=runtime, snapshot_digest=snapshot_digest, label="ideal-form register")
    ideals_digest = _embedded_digest(ideals, "register_digest", "ideal-form register")
    ideals_count = _count_sequence(ideals, "ideal_forms", "ideal-form register")
    ideals_ready = standard_readiness(ideals.get("readiness"), label="ideal-form readiness")

    self_images = load_object(paths.node_self_image_set, label="node self-image set")
    _require_contract(self_images, "node-self-image-set.v1", label="node self-image set")
    _snapshot_bound(
        self_images,
        runtime=runtime,
        snapshot_digest=snapshot_digest,
        label="node self-image set",
    )
    self_images_digest = _embedded_digest(self_images, "set_digest", "node self-image set")
    image_count = _count_sequence(self_images, "self_images", "node self-image set")
    registered_ids = self_images.get("registered_node_ids")
    if (
        not isinstance(registered_ids, list)
        or len(registered_ids) != image_count
        or len(registered_ids) != len(set(registered_ids))
    ):
        raise ReceiptContractError("node self-image set is not exact-one per registered node")
    self_images_ready = standard_readiness(
        self_images.get("readiness"),
        label="node self-image readiness",
    )

    atlas = load_object(paths.iceberg_atlas, label="Iceberg Atlas")
    _require_contract(atlas, "iceberg-atlas.v1", label="Iceberg Atlas")
    _snapshot_bound(atlas, runtime=runtime, snapshot_digest=snapshot_digest, label="Iceberg Atlas")
    atlas_digest = _embedded_digest(atlas, "atlas_digest", "Iceberg Atlas")
    atlas_missing, atlas_citation_debt, timeline_count, zoom_count = _atlas_shape_debt(atlas)

    parity = load_object(paths.normalization_parity_receipt, label="normalization parity receipt")
    _require_contract(
        parity,
        "normalization-parity-receipt.v1",
        label="normalization parity receipt",
    )
    _snapshot_bound(
        parity,
        runtime=runtime,
        snapshot_digest=snapshot_digest,
        label="normalization parity receipt",
    )
    parity_digest = _embedded_digest(parity, "receipt_digest", "normalization parity receipt")
    parity_ready = standard_readiness(parity.get("readiness"), label="normalization parity readiness")
    parity_census = parity.get("input_census")
    promotions = parity.get("promotions")
    output_events = parity.get("output_events")
    if (
        not isinstance(parity_census, Mapping)
        or parity_census.get("census_id") != census.get("census_id")
        or parity_census.get("census_digest") != census_digest
        or set(parity_census.get("raw_unit_ids", [])) != set(raw_ids)
        or not isinstance(promotions, list)
        or not isinstance(output_events, Mapping)
        or set(output_events.get("event_ids", [])) != {str(event["event_id"]) for event in events}
    ):
        raise ReceiptContractError("normalization parity receipt differs from census or event set")
    promotion_ids = [promotion.get("raw_unit_id") for promotion in promotions if isinstance(promotion, Mapping)]
    if len(promotion_ids) != len(promotions) or sorted(promotion_ids) != sorted(raw_ids):
        raise ReceiptContractError("normalization parity crosswalk is not exact-one per raw unit")

    atlas_receipt = load_object(paths.governance_atlas_receipt, label="governance Atlas receipt")
    _require_contract(
        atlas_receipt,
        "governance-atlas-receipt.v1",
        label="governance Atlas receipt",
    )
    _snapshot_bound(
        atlas_receipt,
        runtime=runtime,
        snapshot_digest=snapshot_digest,
        label="governance Atlas receipt",
    )
    atlas_receipt_digest = _embedded_digest(
        atlas_receipt,
        "receipt_digest",
        "governance Atlas receipt",
    )
    atlas_receipt_ready = standard_readiness(
        atlas_receipt.get("readiness"),
        label="governance Atlas receipt readiness",
    )
    if (
        atlas_receipt.get("iceberg_atlas", {}).get("digest") != atlas_digest
        or atlas_receipt.get("ideal_form_register", {}).get("digest") != ideals_digest
        or atlas_receipt.get("node_self_image_set", {}).get("digest") != self_images_digest
    ):
        raise ReceiptContractError("governance Atlas receipt does not bind Atlas inputs")

    render_projection = load_object(paths.render_projection, label="render projection")
    render_ready = _render_readiness(
        render_projection,
        runtime=runtime,
        snapshot_digest=snapshot_digest,
    )
    if render_ready != atlas_receipt_ready:
        raise ReceiptContractError("render projection readiness differs from Atlas receipt")

    bounded_units = sum(
        (
            len(raw_units),
            len(events),
            len(sources),
            len(assertions),
            node_count,
            len(edges),
            ideals_count,
            image_count,
            len(promotions),
            timeline_count,
            zoom_count,
        ),
    )
    if bounded_units > runtime.max_items:
        raise ReceiptContractError(
            f"receipt denominator {bounded_units} exceeds LIMEN_GOV_MAX_ITEMS",
        )

    derived_debt = {
        "unresolved_blockers": [],
        "quarantines": [],
        "missing_requirements": [*testament_missing, *atlas_missing],
        "citation_debt": [*_assertion_debt(assertions), *atlas_citation_debt],
        "incomplete_predicates": testament_incomplete,
    }
    readiness = _merge_readiness(
        [
            coverage_ready,
            parity_ready,
            ideals_ready,
            self_images_ready,
            atlas_receipt_ready,
            render_ready,
        ],
        derived_debt=derived_debt,
    )
    if testament.get("status") != "ratified" or not constitutional_ready:
        if readiness["ready"]:
            raise ReceiptContractError("non-ratified testament cannot produce a ready bundle")

    payload = {
        "bundle_id": f"{cadence_id}:{runtime.snapshot_id}:bundle",
        "source_census": {
            "contract_name": "source-census.v1",
            "census_id": census["census_id"],
            "reference": f"receipt:source-census:{census['census_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": census_digest,
            "raw_unit_count": len(raw_units),
        },
        "normalized_events": events,
        "source_envelopes": sources,
        "assertion_evidence": assertions,
        "lineage_graph": {
            "contract_name": "lineage-graph.v1",
            "artifact_id": lineage["graph_id"],
            "reference": f"artifact:lineage-graph:{lineage['graph_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": digest_value(lineage),
            "node_count": node_count,
        },
        "governance_testament": {
            "contract_name": "governance-testament.v1",
            "artifact_id": testament["testament_id"],
            "reference": f"artifact:governance-testament:{testament['testament_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": digest_value(testament),
            "status": testament["status"],
            "constitutional_coverage_ready": constitutional_ready,
        },
        "coverage": {
            "contract_name": "coverage-receipt.v1",
            "receipt_id": coverage["receipt_id"],
            "reference": f"receipt:coverage:{coverage['receipt_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": coverage_digest,
            "exact_all": coverage_ready["exact_all"],
            "ready": coverage_ready["ready"],
        },
        "ideal_form_register": {
            "contract_name": "ideal-form-register.v1",
            "artifact_id": ideals["register_id"],
            "reference": f"artifact:ideal-form-register:{ideals['register_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": ideals_digest,
            "count": ideals_count,
            "ready": ideals_ready["ready"],
        },
        "node_self_image_set": {
            "contract_name": "node-self-image-set.v1",
            "artifact_id": self_images["set_id"],
            "reference": f"artifact:node-self-image-set:{self_images['set_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": self_images_digest,
            "count": image_count,
            "ready": self_images_ready["ready"],
        },
        "iceberg_atlas": {
            "contract_name": "iceberg-atlas.v1",
            "artifact_id": atlas["atlas_id"],
            "reference": f"artifact:iceberg-atlas:{atlas['atlas_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": atlas_digest,
            "timeline_count": timeline_count,
            "zoom_count": zoom_count,
        },
        "normalization_parity_receipt": {
            "contract_name": "normalization-parity-receipt.v1",
            "receipt_id": parity["receipt_id"],
            "reference": f"receipt:normalization-parity:{parity['receipt_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": parity_digest,
            "ready": parity_ready["ready"],
        },
        "governance_atlas_receipt": {
            "contract_name": "governance-atlas-receipt.v1",
            "receipt_id": atlas_receipt["atlas_receipt_id"],
            "reference": f"receipt:governance-atlas:{atlas_receipt['atlas_receipt_id']}",
            "snapshot_id": runtime.snapshot_id,
            "digest": atlas_receipt_digest,
            "ready": atlas_receipt_ready["ready"],
        },
    }
    document = {
        "contract_name": PRE_PROOF_CONTRACT,
        "contract_version": 1,
        "snapshot_id": runtime.snapshot_id,
        "snapshot_at": runtime.snapshot_at,
        "snapshot_digest": snapshot_digest,
        "readiness": readiness,
        "bundle_payload": payload,
    }
    direct_inputs = {
        "assertion_evidence": assertions,
        "coverage": coverage,
        "governance_atlas_receipt": atlas_receipt,
        "governance_testament": testament,
        "iceberg_atlas": atlas,
        "ideal_form_register": ideals,
        "lineage_graph": lineage,
        "node_self_image_set": self_images,
        "normalization_parity_receipt": parity,
        "normalized_events": events,
        "render_projection": render_projection,
        "source_census": census,
        "source_envelopes": sources,
    }
    input_digest = digest_value(
        {
            "snapshot_id": runtime.snapshot_id,
            "snapshot_at": runtime.snapshot_at,
            "snapshot_digest": snapshot_digest,
            "predecessor_receipt_digest": runtime.predecessor_receipt_digest,
            "cadence_id": cadence_id,
            "bounded_units": bounded_units,
            "inputs": _input_descriptors(direct_inputs),
        },
    )
    return ReceiptPlan(
        document=document,
        document_bytes=canonical_bytes(document) + b"\n",
        input_digest=input_digest,
        output_digest=digest_value(document),
        child_id=f"governance-receipt:{runtime.snapshot_id}",
        bounded_units=bounded_units,
    )


def child_receipt_digest(child: Mapping[str, Any]) -> str:
    return digest_value(
        {
            "child_id": child["child_id"],
            "status": child["status"],
            "input_digest": child["input_digest"],
            "output_digest": child["output_digest"],
        },
    )


def proof_child(plan: ReceiptPlan, runtime: Runtime) -> dict[str, Any]:
    """Bind the exact completed child from traversal one."""
    if runtime.prior_stage_receipt is None:
        raise ReceiptContractError("proof traversal requires its prior stage receipt")
    prior = load_object(runtime.prior_stage_receipt, label="prior receipt-stage receipt")
    children = prior.get("child_receipts")
    if (
        prior.get("stage") != "receipt"
        or prior.get("snapshot_id") != runtime.snapshot_id
        or not isinstance(children, list)
    ):
        raise ReceiptContractError("prior receipt-stage receipt is incompatible")
    matches = [child for child in children if isinstance(child, Mapping) and child.get("child_id") == plan.child_id]
    if len(matches) != 1:
        raise ReceiptContractError("prior receipt-stage child is missing or duplicated")
    prior_child = matches[0]
    if (
        prior_child.get("status") != "completed"
        or prior_child.get("input_digest") != plan.input_digest
        or prior_child.get("output_digest") != plan.output_digest
    ):
        raise ReceiptContractError("receipt proof input or output differs from traversal one")
    return {
        "child_id": plan.child_id,
        "status": "skipped_completed",
        "input_digest": plan.input_digest,
        "output_digest": plan.output_digest,
        "prior_receipt_digest": child_receipt_digest(prior_child),
    }


def expected_metrics(plan: ReceiptPlan, runtime: Runtime) -> dict[str, Any]:
    child = (
        proof_child(plan, runtime)
        if runtime.proof_mode
        else {
            "child_id": plan.child_id,
            "status": "completed",
            "input_digest": plan.input_digest,
            "output_digest": plan.output_digest,
        }
    )
    return {
        "resume_token": None,
        "completed_child_ids": [plan.child_id],
        "pending_child_ids": [],
        "child_receipts": [child],
        "emitted_events": 0,
    }


def validate_output(path: Path, plan: ReceiptPlan) -> None:
    try:
        observed = path.read_bytes()
    except OSError as exc:
        raise ReceiptContractError("receipt-stage governed output is unreadable") from exc
    if observed != plan.document_bytes:
        raise ReceiptContractError("receipt-stage governed output is not byte-identical to its inputs")
    parsed = _decode_json(observed.decode("utf-8"), label="receipt-stage governed output")
    if parsed != plan.document or digest_value(parsed) != plan.output_digest:
        raise ReceiptContractError("receipt-stage governed output digest is invalid")


def validate_metrics(path: Path, plan: ReceiptPlan, runtime: Runtime) -> None:
    observed = load_object(path, label="receipt-stage metrics")
    if observed != expected_metrics(plan, runtime):
        raise ReceiptContractError("receipt-stage metrics differ from the exact bounded child")


__all__ = [
    "ArtifactPaths",
    "ReceiptContractError",
    "ReceiptPlan",
    "Runtime",
    "add_owner_arguments",
    "build_receipt_plan",
    "cadence_runtime",
    "canonical_bytes",
    "digest_value",
    "expected_metrics",
    "paths_from_args",
    "require_path_below",
    "validate_metrics",
    "validate_output",
]
