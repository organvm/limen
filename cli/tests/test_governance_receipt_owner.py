from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import rfc8785


ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / "scripts" / "governance-receipt-owner.py"
PREDICATE = ROOT / "scripts" / "governance-receipt-predicate.py"
SNAPSHOT_ID = "snapshot-fixture"
SNAPSHOT_AT = "2026-07-16T20:00:00Z"
SNAPSHOT_DIGEST = "sha256:" + "a" * 64
PREDECESSOR_DIGEST = "sha256:" + "f" * 64
RAW_ID = "raw_" + "1" * 64
RAW_BLOCKED_ID = "raw_" + "2" * 64
SOURCE_ID = "src_" + "1" * 64
SOURCE_BLOCKED_ID = "src_" + "2" * 64
SECOND_SOURCE_ID = "src_" + "3" * 64
EVENT_ID = "evt_" + "1" * 64
SECOND_EVENT_ID = "evt_" + "2" * 64
CONTENT_DIGEST = "sha256:" + "b" * 64
BODY_DIGEST = "sha256:" + "c" * 64


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _sealed(document: dict, field: str) -> dict:
    body = deepcopy(document)
    body.pop(field, None)
    body[field] = _digest(body)
    return body


def _readiness(
    *,
    ready: bool,
    blockers: list[str] | None = None,
    quarantines: list[str] | None = None,
    missing: list[str] | None = None,
    citation: list[str] | None = None,
    incomplete: list[str] | None = None,
    status: str | None = None,
) -> dict:
    blockers = blockers or []
    quarantines = quarantines or []
    missing = missing or []
    citation = citation or []
    incomplete = incomplete or []
    return {
        "exact_all": True,
        "unresolved_blockers": blockers,
        "quarantines": quarantines,
        "missing_requirements": missing,
        "citation_debt": citation,
        "incomplete_predicates": incomplete,
        "ready": ready,
        "status": status or ("ready" if ready else "blocked"),
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


def _artifacts(
    root: Path,
    *,
    candidate: bool,
    blocked_source: bool = False,
    assertion_as_list: bool = False,
    multiple_events: bool = False,
) -> dict[str, Path]:
    raw_units = [
        {
            "raw_unit_id": RAW_ID,
            "acquisition_status": "acquired",
            "content_hash": CONTENT_DIGEST,
        },
    ]
    coverage_sources = [{"source_id": SOURCE_ID, "status": "parsed"}]
    coverage_counts = {
        "acquired": 0,
        "parsed": 1,
        "quarantined": 0,
        "inaccessible": 0,
        "missing_expected": 0,
        "owner_blocked": 0,
    }
    coverage_blockers: list[str] = []
    parity_blockers: list[str] = []
    promotions: list[dict] = [
        {
            "raw_unit_id": RAW_ID,
            "raw_unit_content_hash": CONTENT_DIGEST,
            "event_ids": [EVENT_ID],
        },
    ]
    if multiple_events:
        coverage_sources.append({"source_id": SECOND_SOURCE_ID, "status": "parsed"})
        coverage_counts["parsed"] = 2
    if blocked_source:
        raw_units.append(
            {
                "raw_unit_id": RAW_BLOCKED_ID,
                "acquisition_status": "blocked",
                "content_hash": None,
            },
        )
        coverage_blockers = [SOURCE_BLOCKED_ID]
        parity_blockers = [RAW_BLOCKED_ID]
        promotions.append(
            {
                "raw_unit_id": RAW_BLOCKED_ID,
                "raw_unit_content_hash": None,
                "disposition": {
                    "type": "blocked",
                    "owner_reference": "owner:custody",
                    "failed_predicate": "owner export acquired",
                    "next_action": "Acquire the owner export.",
                    "evidence_references": ["receipt:custody-blocker"],
                },
            },
        )

    census = _sealed(
        {
            "contract_name": "source-census.v1",
            "contract_version": 1,
            "census_id": "census-fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_at": SNAPSHOT_AT,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "manifest_reference": "config:source-manifest",
            "manifest_digest": "sha256:" + "d" * 64,
            "discovery_roots": [{"root_id": "root-fixture"}],
            "seed_expectations": [],
            "raw_units": raw_units,
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
        },
        "census_digest",
    )
    event = {
        "contract_name": "normalized-event.v1",
        "contract_version": 1,
        "event_id": EVENT_ID,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "raw_unit_id": RAW_ID,
        "raw_unit_content_hash": CONTENT_DIGEST,
        "source_envelope_reference": f"source-envelope.v1.jsonl#{SOURCE_ID}",
    }
    events = [event]
    if multiple_events:
        events.append(
            {
                **event,
                "event_id": SECOND_EVENT_ID,
                "source_envelope_reference": (
                    f"source-envelope.v1.jsonl#{SECOND_SOURCE_ID}"
                ),
            },
        )
    source = {
        "contract_name": "source-envelope.v1",
        "contract_version": 1,
        "source_id": SOURCE_ID,
        "raw_unit_id": RAW_ID,
        "raw_unit_content_hash": CONTENT_DIGEST,
        "custody_snapshot": {
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_hash": SNAPSHOT_DIGEST,
        },
        "native_identifiers": {"event_id": "native-1"},
        "role": "operator",
        "authority_class": "operator_intent",
        "body_hash": BODY_DIGEST,
    }
    source_envelopes = [source]
    if multiple_events:
        source_envelopes.append(
            {
                **source,
                "source_id": SECOND_SOURCE_ID,
                "native_identifiers": {"event_id": "native-2"},
            },
        )
    assertion = {
        "contract_name": "assertion-evidence.v1",
        "contract_version": 1,
        "assertion_id": "assertion-fixture",
        "assertion_class": "operator_directive",
        "statement": "The frozen operator directive controls.",
        "verification_state": "verified",
        "evidence_references": ["source:one", "source:two"],
    }
    lineage = {
        "contract_name": "lineage-graph.v1",
        "contract_version": 1,
        "graph_id": "lineage-fixture",
        "generated_at": SNAPSHOT_AT,
        "frozen_snapshot_id": SNAPSHOT_ID,
        "nodes": [
            {
                "node_id": (
                    "node-fixture" if index == 0 else f"node-fixture-{index + 1}"
                ),
                "source_envelope_id": row["source_id"],
            }
            for index, row in enumerate(coverage_sources)
        ],
        "edges": [],
    }
    if candidate:
        testament = {
            "contract_name": "governance-testament.v1",
            "contract_version": 1,
            "testament_id": "testament-fixture",
            "status": "candidate",
            "predicates": [{"predicate_id": "predicate-fixture"}],
        }
    else:
        testament = {
            "contract_name": "governance-testament.v1",
            "contract_version": 1,
            "testament_id": "testament-fixture",
            "status": "ratified",
            "predicates": [{"predicate_id": "predicate-fixture"}],
            "ratification": {
                "constitutional_coverage": {
                    "exact_all": True,
                    "ready": True,
                    "blocked_scopes": [],
                    "missing_requirements": [],
                },
                "authority_events": [{"event_id": EVENT_ID}],
            },
        }
    coverage_ready = not blocked_source
    coverage = _sealed(
        {
            "contract_name": "coverage-receipt.v1",
            "contract_version": 1,
            "receipt_id": "coverage-fixture",
            "snapshot_id": SNAPSHOT_ID,
            "generated_at": SNAPSHOT_AT,
            "denominator": {
                "count": len(coverage_sources),
                "discovery_manifest_reference": "coverage-fixture#/sources",
                "manifest_hash": _digest(coverage_sources),
            },
            "sources": coverage_sources,
            "counts": coverage_counts,
            "exact_all": True,
            "ready": coverage_ready,
            "unresolved_blockers": coverage_blockers,
            "quarantines": [],
            "missing_requirements": [],
            "citation_debt": [],
            "incomplete_predicates": [],
            "closure_status": ("ready" if coverage_ready else "closed_with_owner_routed_debt"),
            "residual_owners": [],
        },
        "receipt_hash",
    )
    parity_ready = not blocked_source
    parity = _sealed(
        {
            "contract_name": "normalization-parity-receipt.v1",
            "contract_version": 1,
            "receipt_id": "parity-fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "generated_at": SNAPSHOT_AT,
            "input_census": {
                "census_id": census["census_id"],
                "census_digest": census["census_digest"],
                "raw_unit_ids": [row["raw_unit_id"] for row in raw_units],
            },
            "output_events": {"event_ids": [EVENT_ID]},
            "promotions": promotions,
            "readiness": _readiness(
                ready=parity_ready,
                blockers=parity_blockers,
                status=("ready" if parity_ready else "closed_with_owner_routed_debt"),
            ),
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
        },
        "receipt_digest",
    )
    if multiple_events:
        parity["output_events"]["event_ids"].append(SECOND_EVENT_ID)
        parity["promotions"][0]["event_ids"].append(SECOND_EVENT_ID)
        parity = _sealed(parity, "receipt_digest")
    ideals = _sealed(
        {
            "contract_name": "ideal-form-register.v1",
            "contract_version": 1,
            "register_id": "ideals-fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "generated_at": SNAPSHOT_AT,
            "ideal_forms": [{"ideal_id": "ideal-fixture"}],
            "readiness": _readiness(ready=True),
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
        },
        "register_digest",
    )
    images = _sealed(
        {
            "contract_name": "node-self-image-set.v1",
            "contract_version": 1,
            "set_id": "self-images-fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "registered_node_ids": ["node-fixture"],
            "self_images": [{"node_id": "node-fixture"}],
            "readiness": _readiness(ready=True),
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
        },
        "set_digest",
    )
    atlas = _sealed(
        {
            "contract_name": "iceberg-atlas.v1",
            "contract_version": 1,
            "atlas_id": "atlas-fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "generated_at": SNAPSHOT_AT,
            "timelines": {
                "operator_intent": [{"event_id": EVENT_ID}],
                "artifact": [{"artifact_id": "artifact-fixture"}],
            },
            "zoom_levels": {
                "system": [{"node_id": "node-fixture"}],
                "organ": [{"node_id": "node-fixture"}],
                "repository": [{"node_id": "node-fixture"}],
                "document": [{"node_id": "node-fixture"}],
                "session": [{"node_id": "node-fixture"}],
                "atom": [{"node_id": "node-fixture"}],
            },
            "coverage": {"exact_all": True},
            "citation_debt": [],
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
        },
        "atlas_digest",
    )
    atlas_owner_ready = not candidate and not blocked_source
    atlas_missing = [] if atlas_owner_ready else ["render:owner-readiness"]
    atlas_readiness = _readiness(
        ready=atlas_owner_ready,
        missing=atlas_missing,
        status=("ready" if atlas_owner_ready else "incomplete"),
    )
    atlas_receipt = _sealed(
        {
            "contract_name": "governance-atlas-receipt.v1",
            "contract_version": 1,
            "atlas_receipt_id": "atlas-receipt-fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "iceberg_atlas": {"digest": atlas["atlas_digest"]},
            "ideal_form_register": {"digest": ideals["register_digest"]},
            "node_self_image_set": {"digest": images["set_digest"]},
            "readiness": atlas_readiness,
            "digest_algorithm": "sha256-rfc8785-excluding-self-digest-v1",
        },
        "receipt_digest",
    )
    render_projection = _sealed(
        {
            "contract_name": "engine-governance-render.v1",
            "contract_version": 1,
            "stage": "render",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_at": SNAPSHOT_AT,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "bounded_units": 7,
            "artifacts": [
                {
                    "artifact_id": "iceberg-atlas.public.json",
                    "reference": "iceberg-atlas.public.json",
                    "digest": "sha256:" + "3" * 64,
                },
                {
                    "artifact_id": "governance-atlas-receipt.json",
                    "reference": "governance-atlas-receipt.json",
                    "digest": "sha256:" + "4" * 64,
                },
            ],
            "readiness": atlas_readiness,
            "digest_algorithm": "sha256-rfc8785-excluding-projection-digest-v1",
        },
        "projection_digest",
    )

    paths = {
        "source_census": root / "source-census.json",
        "normalized_events": root / "normalized-events.jsonl",
        "source_envelopes": root / "source-envelopes.jsonl",
        "assertion_evidence": root / "assertions.json",
        "lineage_graph": root / "lineage.json",
        "governance_testament": root / "testament.json",
        "coverage": root / "coverage.json",
        "ideal_form_register": root / "ideals.json",
        "node_self_image_set": root / "self-images.json",
        "iceberg_atlas": root / "atlas.json",
        "normalization_parity_receipt": root / "parity.json",
        "governance_atlas_receipt": root / "atlas-receipt.json",
        "render_projection": root / "render-projection.json",
    }
    _write_json(paths["source_census"], census)
    _write_jsonl(paths["normalized_events"], events)
    _write_jsonl(paths["source_envelopes"], source_envelopes)
    _write_json(
        paths["assertion_evidence"],
        [assertion] if assertion_as_list else assertion,
    )
    _write_json(paths["lineage_graph"], lineage)
    _write_json(paths["governance_testament"], testament)
    _write_json(paths["coverage"], coverage)
    _write_json(paths["ideal_form_register"], ideals)
    _write_json(paths["node_self_image_set"], images)
    _write_json(paths["iceberg_atlas"], atlas)
    _write_json(paths["normalization_parity_receipt"], parity)
    _write_json(paths["governance_atlas_receipt"], atlas_receipt)
    _write_json(paths["render_projection"], render_projection)
    return paths


def _args(paths: dict[str, Path], output: Path) -> list[str]:
    values = [
        sys.executable,
        str(OWNER),
        "--source-census",
        str(paths["source_census"]),
        "--normalized-events",
        str(paths["normalized_events"]),
        "--source-envelopes",
        str(paths["source_envelopes"]),
        "--assertion-evidence",
        str(paths["assertion_evidence"]),
        "--lineage-graph",
        str(paths["lineage_graph"]),
        "--governance-testament",
        str(paths["governance_testament"]),
        "--coverage",
        str(paths["coverage"]),
        "--ideal-form-register",
        str(paths["ideal_form_register"]),
        "--node-self-image-set",
        str(paths["node_self_image_set"]),
        "--iceberg-atlas",
        str(paths["iceberg_atlas"]),
        "--normalization-parity-receipt",
        str(paths["normalization_parity_receipt"]),
        "--governance-atlas-receipt",
        str(paths["governance_atlas_receipt"]),
        "--render-projection",
        str(paths["render_projection"]),
        "--snapshot-digest",
        SNAPSHOT_DIGEST,
        "--cadence-id",
        "cadence-fixture",
        "--output",
        str(output),
    ]
    return values


def _env(
    run_root: Path,
    metrics: Path,
    *,
    proof: bool = False,
    prior: Path | None = None,
    max_items: int = 100,
    predicate: bool = False,
) -> dict[str, str]:
    result = {
        **os.environ,
        "LIMEN_GOV_STAGE": "receipt",
        "LIMEN_GOV_STAGE_ATTEMPT": "1",
        "LIMEN_GOV_TRAVERSAL": "2" if proof else "1",
        "LIMEN_GOV_PROOF_MODE": "1" if proof else "0",
        "LIMEN_GOV_STAGE_METRICS_OUT": str(metrics),
        "LIMEN_GOV_STAGE_RECEIPTS": str(run_root / "stage-receipts.json"),
        "LIMEN_GOV_PREDECESSOR_RECEIPT_DIGEST": PREDECESSOR_DIGEST,
        "LIMEN_GOV_PRIOR_STAGE_RECEIPT": str(prior or ""),
        "LIMEN_GOV_MAX_ITEMS": str(max_items),
        "LIMEN_GOV_SNAPSHOT_ID": SNAPSHOT_ID,
        "LIMEN_GOV_SNAPSHOT_AT": SNAPSHOT_AT,
        "LIMEN_GOV_RUN_ROOT": str(run_root),
    }
    if predicate:
        result["LIMEN_GOV_PREDICATE_MODE"] = "1"
    else:
        result.pop("LIMEN_GOV_PREDICATE_MODE", None)
    return result


def _run(
    command: list[str],
    env: dict[str, str],
    *,
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, result.stderr
    return result


def _first_traversal(
    tmp_path: Path,
    *,
    candidate: bool = True,
    blocked_source: bool = False,
    assertion_as_list: bool = False,
    multiple_events: bool = False,
) -> tuple[dict[str, Path], Path, Path, dict[str, str]]:
    inputs = _artifacts(
        tmp_path / "inputs",
        candidate=candidate,
        blocked_source=blocked_source,
        assertion_as_list=assertion_as_list,
        multiple_events=multiple_events,
    )
    run_root = tmp_path / "run"
    output = run_root / "artifacts" / "pre-proof.json"
    metrics = run_root / "metrics" / "receipt.json"
    env = _env(run_root, metrics)
    _run(_args(inputs, output), env)
    return inputs, output, metrics, env


def _prior_receipt(path: Path, metrics: Path) -> None:
    child_receipts = json.loads(metrics.read_text(encoding="utf-8"))["child_receipts"]
    _write_json(
        path,
        {
            "contract_name": "governance-stage-receipt.v1",
            "stage": "receipt",
            "snapshot_id": SNAPSHOT_ID,
            "child_receipts": child_receipts,
        },
    )


def test_candidate_bundle_is_honestly_blocked_and_accepts_assertion_object(
    tmp_path: Path,
) -> None:
    _, output, _, _ = _first_traversal(tmp_path, candidate=True)

    document = json.loads(output.read_text(encoding="utf-8"))

    assert document["contract_name"] == "governance-snapshot-bundle-pre-proof.v1"
    assert document["readiness"]["ready"] is False
    assert document["readiness"]["status"] == "incomplete"
    assert (
        "governance-testament:testament-fixture:ratification-required" in document["readiness"]["missing_requirements"]
    )
    testament = document["bundle_payload"]["governance_testament"]
    assert testament["status"] == "candidate"
    assert testament["constitutional_coverage_ready"] is False
    assert len(document["bundle_payload"]["assertion_evidence"]) == 1


def test_owner_unions_real_coverage_and_parity_debt(
    tmp_path: Path,
) -> None:
    _, output, _, _ = _first_traversal(
        tmp_path,
        candidate=False,
        blocked_source=True,
        assertion_as_list=True,
    )

    readiness = json.loads(output.read_text(encoding="utf-8"))["readiness"]

    assert readiness["exact_all"] is True
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert SOURCE_BLOCKED_ID in readiness["unresolved_blockers"]
    assert RAW_BLOCKED_ID in readiness["unresolved_blockers"]


def test_ratified_bundle_uses_exact_final_schema_reference_shapes(
    tmp_path: Path,
) -> None:
    _, output, _, _ = _first_traversal(tmp_path, candidate=False)

    document = json.loads(output.read_text(encoding="utf-8"))
    payload = document["bundle_payload"]

    assert document["readiness"] == _readiness(ready=True)
    assert set(payload) == {
        "bundle_id",
        "source_census",
        "normalized_events",
        "source_envelopes",
        "assertion_evidence",
        "lineage_graph",
        "governance_testament",
        "coverage",
        "ideal_form_register",
        "node_self_image_set",
        "iceberg_atlas",
        "normalization_parity_receipt",
        "governance_atlas_receipt",
    }
    expected_reference_keys = {
        "source_census": {
            "contract_name",
            "census_id",
            "reference",
            "snapshot_id",
            "digest",
            "raw_unit_count",
        },
        "lineage_graph": {
            "contract_name",
            "artifact_id",
            "reference",
            "snapshot_id",
            "digest",
            "node_count",
        },
        "governance_testament": {
            "contract_name",
            "artifact_id",
            "reference",
            "snapshot_id",
            "digest",
            "status",
            "constitutional_coverage_ready",
        },
        "coverage": {
            "contract_name",
            "receipt_id",
            "reference",
            "snapshot_id",
            "digest",
            "exact_all",
            "ready",
        },
        "ideal_form_register": {
            "contract_name",
            "artifact_id",
            "reference",
            "snapshot_id",
            "digest",
            "count",
            "ready",
        },
        "node_self_image_set": {
            "contract_name",
            "artifact_id",
            "reference",
            "snapshot_id",
            "digest",
            "count",
            "ready",
        },
        "iceberg_atlas": {
            "contract_name",
            "artifact_id",
            "reference",
            "snapshot_id",
            "digest",
            "timeline_count",
            "zoom_count",
        },
        "normalization_parity_receipt": {
            "contract_name",
            "receipt_id",
            "reference",
            "snapshot_id",
            "digest",
            "ready",
        },
        "governance_atlas_receipt": {
            "contract_name",
            "receipt_id",
            "reference",
            "snapshot_id",
            "digest",
            "ready",
        },
    }
    for field, keys in expected_reference_keys.items():
        assert set(payload[field]) == keys
        assert payload[field]["digest"].startswith("sha256:")
        assert "/" not in payload[field]["reference"]
    assert payload["iceberg_atlas"]["timeline_count"] == 2
    assert payload["iceberg_atlas"]["zoom_count"] == 6


def test_owner_loads_multirow_jsonl_and_keeps_scope_denominators_distinct(
    tmp_path: Path,
) -> None:
    _, output, _, _ = _first_traversal(
        tmp_path,
        candidate=False,
        multiple_events=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))["bundle_payload"]
    events = payload["normalized_events"]

    assert [event["event_id"] for event in events] == [EVENT_ID, SECOND_EVENT_ID]
    assert payload["source_census"]["raw_unit_count"] == 1
    assert len(payload["source_envelopes"]) == 2


def test_owner_rejects_coverage_that_omits_a_lineage_source(
    tmp_path: Path,
) -> None:
    inputs = _artifacts(
        tmp_path / "inputs",
        candidate=False,
        multiple_events=True,
    )
    coverage = json.loads(inputs["coverage"].read_text(encoding="utf-8"))
    coverage["sources"] = coverage["sources"][:1]
    coverage["counts"]["parsed"] = 1
    coverage["denominator"]["count"] = 1
    coverage["denominator"]["manifest_hash"] = _digest(coverage["sources"])
    coverage = _sealed(coverage, "receipt_hash")
    _write_json(inputs["coverage"], coverage)
    run_root = tmp_path / "run"

    result = _run(
        _args(inputs, run_root / "artifacts" / "pre-proof.json"),
        _env(run_root, run_root / "metrics" / "receipt.json"),
        expected=2,
    )

    assert "coverage classification/readiness fields are invalid" in result.stderr


def test_owner_rejects_a_non_object_jsonl_row_with_its_physical_line(
    tmp_path: Path,
) -> None:
    inputs = _artifacts(tmp_path / "inputs", candidate=False)
    with inputs["normalized_events"].open("a", encoding="utf-8") as stream:
        stream.write("[]\n")
    run_root = tmp_path / "run"
    output = run_root / "artifacts" / "pre-proof.json"
    metrics = run_root / "metrics" / "receipt.json"

    result = _run(
        _args(inputs, output),
        _env(run_root, metrics),
        expected=2,
    )

    assert "normalized events line 2 must contain one JSON object" in result.stderr
    assert not output.exists()
    assert not metrics.exists()


def test_proof_is_byte_identical_skipped_child_and_predicate_is_read_only(
    tmp_path: Path,
) -> None:
    inputs, output, metrics, first_env = _first_traversal(tmp_path, candidate=False)
    prior = tmp_path / "run" / "receipt-prior.json"
    _prior_receipt(prior, metrics)
    before = output.read_bytes()
    before_stat = output.stat()
    proof_metrics = tmp_path / "run" / "metrics" / "receipt-proof.json"
    proof_env = _env(
        tmp_path / "run",
        proof_metrics,
        proof=True,
        prior=prior,
    )

    _run(_args(inputs, output), proof_env)

    proof = json.loads(proof_metrics.read_text(encoding="utf-8"))
    assert proof["emitted_events"] == 0
    assert proof["child_receipts"][0]["status"] == "skipped_completed"
    assert proof["child_receipts"][0]["prior_receipt_digest"].startswith("sha256:")
    assert output.read_bytes() == before
    assert output.stat().st_ino == before_stat.st_ino
    assert output.stat().st_mtime_ns == before_stat.st_mtime_ns

    predicate_command = [sys.executable, str(PREDICATE), *_args(inputs, output)[2:]]
    predicate_env = {**proof_env, "LIMEN_GOV_PREDICATE_MODE": "1"}
    predicate_before = output.stat()
    _run(predicate_command, predicate_env)
    assert output.read_bytes() == before
    assert output.stat().st_ino == predicate_before.st_ino
    assert output.stat().st_mtime_ns == predicate_before.st_mtime_ns
    assert "governance-receipt-owner" not in PREDICATE.read_text(encoding="utf-8")
    assert "LIMEN_GOV_PREDICATE_MODE" not in first_env


def test_proof_rejects_output_tamper_without_repairing_it(
    tmp_path: Path,
) -> None:
    inputs, output, metrics, _ = _first_traversal(tmp_path, candidate=False)
    prior = tmp_path / "run" / "receipt-prior.json"
    _prior_receipt(prior, metrics)
    output.write_bytes(b'{"tampered":true}\n')
    proof_metrics = tmp_path / "run" / "metrics" / "receipt-proof.json"
    proof_env = _env(tmp_path / "run", proof_metrics, proof=True, prior=prior)

    _run(_args(inputs, output), proof_env, expected=2)

    assert output.read_bytes() == b'{"tampered":true}\n'
    assert not proof_metrics.exists()


def test_proof_rejects_changed_input(
    tmp_path: Path,
) -> None:
    inputs, output, metrics, _ = _first_traversal(tmp_path, candidate=False)
    prior = tmp_path / "run" / "receipt-prior.json"
    _prior_receipt(prior, metrics)
    assertion = json.loads(inputs["assertion_evidence"].read_text(encoding="utf-8"))
    assertion["statement"] = "Changed after traversal one."
    _write_json(inputs["assertion_evidence"], assertion)
    proof_metrics = tmp_path / "run" / "metrics" / "receipt-proof.json"
    proof_env = _env(tmp_path / "run", proof_metrics, proof=True, prior=prior)
    before = output.read_bytes()

    _run(_args(inputs, output), proof_env, expected=2)

    assert output.read_bytes() == before
    assert not proof_metrics.exists()


def test_max_items_fails_before_any_receipt_output(
    tmp_path: Path,
) -> None:
    inputs = _artifacts(tmp_path / "inputs", candidate=False)
    run_root = tmp_path / "run"
    output = run_root / "artifacts" / "pre-proof.json"
    metrics = run_root / "metrics" / "receipt.json"

    result = _run(
        _args(inputs, output),
        _env(run_root, metrics, max_items=1),
        expected=2,
    )

    assert "exceeds LIMEN_GOV_MAX_ITEMS" in result.stderr
    assert not output.exists()
    assert not metrics.exists()


def test_false_ready_coverage_is_rejected(
    tmp_path: Path,
) -> None:
    inputs = _artifacts(tmp_path / "inputs", candidate=False, blocked_source=True)
    coverage = json.loads(inputs["coverage"].read_text(encoding="utf-8"))
    coverage["ready"] = True
    coverage["closure_status"] = "ready"
    coverage = _sealed(coverage, "receipt_hash")
    _write_json(inputs["coverage"], coverage)
    run_root = tmp_path / "run"
    output = run_root / "artifacts" / "pre-proof.json"
    metrics = run_root / "metrics" / "receipt.json"

    result = _run(
        _args(inputs, output),
        _env(run_root, metrics),
        expected=2,
    )

    assert "false readiness claim" in result.stderr
    assert not output.exists()
