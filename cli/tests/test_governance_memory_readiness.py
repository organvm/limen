from __future__ import annotations

import importlib.util
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "governance-memory-readiness.py"
SNAPSHOT_ID = "snapshot-fixture"
SNAPSHOT_AT = "2026-07-16T18:00:00Z"
SNAPSHOT_DIGEST = "sha256:" + "a" * 64
DIGEST_ALGORITHM = "sha256-rfc8785-excluding-self-digest-v1"


def _load(name: str = "governance_memory_readiness_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _file_digest(module, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    return "sha256:" + module.digest_bytes(raw)


def _ready() -> dict[str, object]:
    return {
        "exact_all": True,
        "unresolved_blockers": [],
        "quarantines": [],
        "missing_requirements": [],
        "citation_debt": [],
        "incomplete_predicates": [],
        "ready": True,
        "status": "ready",
    }


def _seal(
    module,
    document: dict[str, object],
    field: str,
    *,
    include_algorithm: bool = True,
) -> dict[str, object]:
    if include_algorithm:
        document["digest_algorithm"] = DIGEST_ALGORITHM
    document.pop(field, None)
    document[field] = module.digest_value(document)
    return document


def _schema_catalog(module, tmp_path: Path) -> Path:
    root = tmp_path / "schema-definitions"
    schemas = root / "schemas"
    schemas.mkdir(parents=True)
    for spec in module.INPUT_SPECS:
        _write(
            schemas / f"{spec.contract}.schema.json",
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["contract_name"],
                "properties": {"contract_name": {"const": spec.contract}},
                "additionalProperties": True,
            },
        )
    return root


def _self_image(node_id: str, node_type: str) -> dict[str, object]:
    return {
        "contract_name": "node-self-image.v1",
        "contract_version": 1,
        "node_id": node_id,
        "node_type": node_type,
        "display_name": node_id,
        "owner_reference": "owner:fixture",
        "relations": {"incoming": [], "outgoing": []},
        "cursors": {"memory": "memory:1", "event": "event:1"},
        "digests": {
            "constitutional": "sha256:" + "1" * 64,
            "topology": "sha256:" + "2" * 64,
        },
        "observations": [
            {
                "key": "state",
                "value": "verified",
                "observed_at": "2026-07-16T18:01:00Z",
                "evidence_references": ["receipt:reconcile"],
            }
        ],
        "active_ideal_forms": [
            {
                "form_id": "ideal:fixture",
                "implementation_state": "verified",
                "distance_to_ideal": 0,
                "predicate_references": ["predicate:fixture"],
                "evidence_references": ["receipt:reconcile"],
            }
        ],
        "reconciled_at": "2026-07-16T18:01:00Z",
        "evidence_references": ["receipt:reconcile"],
    }


def _cadence_receipt(
    module,
    *,
    run_number: int,
    previous_digest: str | None,
    stage_receipts: list[dict[str, object]],
) -> dict[str, object]:
    output_digest = "sha256:" + "e" * 64
    readiness = (
        _ready()
        if run_number == 2
        else {
            "exact_all": False,
            "unresolved_blockers": [],
            "quarantines": [],
            "missing_requirements": ["fixed-point-proof"],
            "citation_debt": [],
            "incomplete_predicates": ["fixed-point-proof"],
            "ready": False,
            "status": "incomplete",
        }
    )
    payload: dict[str, object] = {
        "contract_name": "governance-cadence-receipt.v1",
        "contract_version": 1,
        "cadence_receipt_id": f"cadence:fixture:run-{run_number}",
        "run_id": f"cadence:fixture:run-{run_number}",
        "run_number": run_number,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "owner_reference": "owner:cadence",
        "started_at": SNAPSHOT_AT,
        "completed_at": SNAPSHOT_AT,
        "input_digest": "sha256:" + "d" * 64,
        "output_digest": output_digest,
        "previous_cadence_receipt_digest": previous_digest,
        "stage_receipts": stage_receipts,
        "fixed_point": {
            "status": "not_applicable" if run_number == 1 else "proven",
            "new_event_count": 1 if run_number == 1 else 0,
            "changed_byte_count": 1024 if run_number == 1 else 0,
            "replayed_completed_children": 0,
            "previous_output_digest": None if run_number == 1 else output_digest,
            "output_digest_matches_previous": run_number == 2,
        },
        "readiness": readiness,
        "digest_algorithm": DIGEST_ALGORITHM,
    }
    payload["receipt_digest"] = module.digest_value(payload)
    return payload


def _documents(module) -> dict[str, object]:
    identity_basis = {
        "native_identity_namespace": "fixture-native-v1",
        "native_identifiers": {"conversation_id": "conversation-1", "event_id": "event-1"},
        "native_role": "user",
        "content_hash": "sha256:" + "b" * 64,
    }
    event_id = "evt_" + module.digest_value(identity_basis).removeprefix("sha256:")
    source_census = _seal(
        module,
        {
            "contract_name": "source-census.v1",
            "contract_version": 1,
            "census_id": "census:fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_at": SNAPSHOT_AT,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "manifest_reference": "config:fixture",
            "manifest_digest": "sha256:" + "1" * 64,
            "discovery_roots": [
                {
                    "root_id": "root:fixture",
                    "root_kind": "export",
                    "runtime_reference": "custody:fixture",
                    "config_reference": "config:fixture",
                }
            ],
            "seed_expectations": [],
            "raw_units": [
                {
                    "raw_unit_id": "raw_fixture",
                    "discovery_root_id": "root:fixture",
                    "source_family": "provider-renamable",
                    "source_instance": "instance-1",
                    "format_adapter": "fixture-json-v1",
                    "native_identifiers": {"event_id": "event-1"},
                    "acquisition_status": "acquired",
                    "content_hash": "sha256:" + "b" * 64,
                    "custody_pointer": "private-cas:event-1",
                    "evidence_references": ["receipt:acquisition"],
                }
            ],
        },
        "census_digest",
    )
    source_envelopes = [
        {
            "contract_name": "source-envelope.v1",
            "contract_version": 1,
            "source_id": "src_fixture",
            "source_family": "provider-renamable",
            "source_instance": "instance-1",
            "format_adapter": "fixture-json-v1",
            "custody_snapshot": {
                "snapshot_id": SNAPSHOT_ID,
                "captured_at": SNAPSHOT_AT,
                "snapshot_hash": SNAPSHOT_DIGEST,
                "custody_pointer": "private-cas:snapshot",
                "immutable": True,
            },
            "native_identifiers": {"event_id": "event-1"},
            "raw_unit_id": "raw_fixture",
            "raw_unit_content_hash": "sha256:" + "b" * 64,
            "role": "operator",
            "event_timestamp": "2026-07-16T17:59:00Z",
            "ingestion_timestamp": SNAPSHOT_AT,
            "authority_class": "operator_intent",
            "body_hash": "sha256:" + "b" * 64,
            "private_custody_pointer": "private-cas:event-1",
        }
    ]
    normalized_events = [
        {
            "contract_name": "normalized-event.v1",
            "contract_version": 1,
            "event_id": event_id,
            "identity_algorithm": "sha256-canonical-json-native-identity-role-content-v1",
            "identity_basis": identity_basis,
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "raw_unit_id": "raw_fixture",
            "raw_unit_content_hash": "sha256:" + "b" * 64,
            "source_family": "provider-renamable",
            "source_instance": "instance-1",
            "format_adapter": "fixture-json-v1",
            "normalized_role": "operator",
            "occurred_at": "2026-07-16T17:59:00Z",
            "authority_class": "operator_intent",
            "source_envelope_reference": "source:src_fixture",
            "evidence_references": ["receipt:adapter"],
        }
    ]
    assertion_evidence = [
        {
            "contract_name": "assertion-evidence.v1",
            "contract_version": 1,
            "assertion_id": "assertion-operator",
            "assertion_class": "operator_directive",
            "statement": "The operator directive is authoritative.",
            "verification_state": "verified",
            "evidence_references": [
                {
                    "evidence_id": "evidence-event",
                    "independence_group": "operator-event",
                    "evidence_type": "immutable_source_event",
                    "reference": f"event:{event_id}",
                    "body_hash": "sha256:" + "b" * 64,
                },
                {
                    "evidence_id": "evidence-ratification",
                    "independence_group": "constitutional-record",
                    "evidence_type": "ratified_constitutional_record",
                    "reference": "constitution:fixture",
                    "body_hash": "sha256:" + "c" * 64,
                },
            ],
        }
    ]
    lineage_graph = {
        "contract_name": "lineage-graph.v1",
        "contract_version": 1,
        "graph_id": "lineage:fixture",
        "generated_at": "2026-07-16T18:02:00Z",
        "frozen_snapshot_id": SNAPSHOT_ID,
        "nodes": [
            {
                "node_id": "lineage:operator",
                "lane": "operator_intent",
                "node_type": "source_event",
                "source_envelope_id": "src_fixture",
                "occurred_at": "2026-07-16T17:59:00Z",
                "authority_class": "operator_intent",
                "summary": "Operator event.",
                "content_hash": "sha256:" + "b" * 64,
                "review_state": "reviewed",
            },
            {
                "node_id": "lineage:artifact",
                "lane": "artifact",
                "node_type": "document",
                "source_envelope_id": "src_fixture",
                "occurred_at": SNAPSHOT_AT,
                "authority_class": "artifact",
                "summary": "Governed artifact.",
                "content_hash": "sha256:" + "c" * 64,
                "review_state": "reviewed",
            },
        ],
        "edges": [
            {
                "edge_id": "edge:implements",
                "from_node": "lineage:operator",
                "to_node": "lineage:artifact",
                "edge_type": "implements",
                "evidence_spans": [
                    {
                        "source_envelope_id": "src_fixture",
                        "reference": "source:src_fixture",
                        "body_hash": "sha256:" + "b" * 64,
                    }
                ],
                "confidence": 1,
                "review_state": "reviewed",
            }
        ],
    }
    governance_testament = {
        "contract_name": "governance-testament.v1",
        "contract_version": 1,
        "testament_id": "testament:fixture",
        "version": "1.0.0",
        "title": "Fixture testament",
        "status": "ratified",
        "directive": "Preserve operator authority and prove readiness.",
        "directive_hash": "sha256:" + "1" * 64,
        "layers": ["ontology", "cybernetics", "phenomenology"],
        "instruments": [{"instrument_id": "fixture", "reference": "spec:fixture", "status": "ratified"}],
        "axioms": [
            {
                "axiom_id": "axiom:fixture",
                "statement": "Authority and artifacts remain distinct.",
                "citation_references": ["assertion:assertion-operator"],
            }
        ],
        "ideal_form_references": ["ideal:fixture"],
        "ratification": {
            "ratified_at": SNAPSHOT_AT,
            "candidate_digest": "sha256:" + "4" * 64,
            "controlling_formulation": "Preserve operator authority and prove readiness.",
            "assertion_evidence_reference": "assertion:assertion-operator",
            "authority_events": [
                {
                    "event_id": event_id,
                    "source_envelope_reference": "source:src_fixture",
                    "role": "operator",
                    "authority_class": "operator_intent",
                    "content_hash": "sha256:" + "b" * 64,
                }
            ],
            "constitutional_coverage": {
                "scope_reference": "coverage:fixture",
                "exact_all": True,
                "blocked_scopes": [],
                "missing_requirements": [],
                "ready": True,
            },
            "constitutional_record_reference": "constitution:fixture",
            "source_lineage_references": ["lineage:operator"],
            "approver_reference": "owner:operator",
        },
        "predicates": [
            {
                "predicate_id": "predicate:fixture",
                "command": "verify fixture",
                "expected_result": "pass",
            }
        ],
        "citations": ["assertion:assertion-operator"],
    }
    governance_testament["directive_hash"] = "sha256:" + module.digest_bytes(
        governance_testament["directive"].encode("utf-8")
    )
    candidate_testament = dict(governance_testament)
    candidate_testament["status"] = "candidate"
    candidate_testament.pop("ratification")
    governance_testament["ratification"]["candidate_digest"] = module.digest_value(candidate_testament)
    assertion_evidence[0]["evidence_references"][1]["body_hash"] = module.digest_value(
        governance_testament["ratification"]
    )
    coverage_receipt = _seal(
        module,
        {
            "contract_name": "coverage-receipt.v1",
            "contract_version": 1,
            "receipt_id": "coverage:fixture",
            "snapshot_id": SNAPSHOT_ID,
            "generated_at": SNAPSHOT_AT,
            "denominator": {
                "discovery_manifest_reference": "config:fixture",
                "count": 1,
                "manifest_hash": "sha256:" + "1" * 64,
            },
            "sources": [
                {
                    "source_id": "src_fixture",
                    "status": "parsed",
                    "accessible": True,
                    "evidence_references": ["receipt:parse"],
                }
            ],
            "counts": {
                "acquired": 0,
                "parsed": 1,
                "quarantined": 0,
                "inaccessible": 0,
                "missing_expected": 0,
                "owner_blocked": 0,
            },
            "exact_all": True,
            "ready": True,
            "unresolved_blockers": [],
            "quarantines": [],
            "missing_requirements": [],
            "citation_debt": [],
            "incomplete_predicates": [],
            "closure_status": "ready",
            "residual_owners": [],
        },
        "receipt_hash",
        include_algorithm=False,
    )
    normalization_parity = _seal(
        module,
        {
            "contract_name": "normalization-parity-receipt.v1",
            "contract_version": 1,
            "receipt_id": "parity:fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "generated_at": SNAPSHOT_AT,
            "input_census": {
                "census_id": source_census["census_id"],
                "census_reference": "receipt:source-census",
                "census_digest": source_census["census_digest"],
                "raw_unit_ids": ["raw_fixture"],
                "raw_units": [
                    {
                        "raw_unit_id": "raw_fixture",
                        "content_hash": "sha256:" + "b" * 64,
                    }
                ],
            },
            "output_events": {
                "event_set_reference": "receipt:normalized-events",
                "event_set_digest": module.digest_value(normalized_events),
                "event_ids": [event_id],
            },
            "promotions": [
                {
                    "raw_unit_id": "raw_fixture",
                    "raw_unit_content_hash": "sha256:" + "b" * 64,
                    "event_ids": [event_id],
                }
            ],
            "readiness": _ready(),
        },
        "receipt_digest",
    )
    ideal_forms = _seal(
        module,
        {
            "contract_name": "ideal-form-register.v1",
            "contract_version": 1,
            "register_id": "ideal-register:fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "generated_at": SNAPSHOT_AT,
            "ideal_forms": [
                {
                    "ideal_form_id": "ideal:fixture",
                    "title": "Fixture ideal",
                    "controlling_formulation": "All predicates pass.",
                    "source_envelope_references": ["source:src_fixture"],
                    "lineage_references": ["lineage:operator"],
                    "owner_reference": "owner:fixture",
                    "implementation_state": "verified",
                    "distance_to_ideal": {
                        "classification": "verified",
                        "verified_predicates": 1,
                        "total_predicates": 1,
                    },
                    "predicates": [
                        {
                            "predicate_id": "predicate:fixture",
                            "statement": "Fixture passes.",
                            "result": "pass",
                            "receipt_reference": "receipt:validate",
                            "evidence_references": ["evidence:fixture"],
                        }
                    ],
                    "assertion_evidence_references": ["assertion:assertion-operator"],
                    "derivation": {
                        "algorithm": "predicate-receipt-status-v1",
                        "receipt_references": ["receipt:validate"],
                    },
                    "receipt_target": "receipt:ideal",
                    "residual_gaps": [],
                }
            ],
            "coverage": {"registered": 1, "verified": 1, "blocked": 0, "incomplete": 0},
            "readiness": _ready(),
        },
        "register_digest",
    )
    registry_projection = [
        {
            "uid": "ent_document_01J00000000000000000000000",
            "entity_type": "document",
            "lifecycle_status": "active",
        },
        {
            "uid": "ent_metric_01J00000000000000000000001",
            "entity_type": "metric",
            "lifecycle_status": "active",
        },
        {
            "uid": "ent_organ_01J00000000000000000000002",
            "entity_type": "organ",
            "lifecycle_status": "active",
        },
        {
            "uid": "ent_repo_01J00000000000000000000003",
            "entity_type": "repo",
            "lifecycle_status": "active",
        },
        {
            "uid": "ent_session_01J00000000000000000000004",
            "entity_type": "session",
            "lifecycle_status": "active",
        },
        {
            "uid": "ent_variable_01J00000000000000000000005",
            "entity_type": "variable",
            "lifecycle_status": "active",
        },
    ]
    node_types = {
        "ent_document_01J00000000000000000000000": "document",
        "ent_metric_01J00000000000000000000001": "artifact",
        "ent_organ_01J00000000000000000000002": "organ",
        "ent_repo_01J00000000000000000000003": "repository",
        "ent_session_01J00000000000000000000004": "session",
        "ent_variable_01J00000000000000000000005": "artifact",
    }
    self_images = _seal(
        module,
        {
            "contract_name": "node-self-image-set.v1",
            "contract_version": 1,
            "set_id": "self-images:fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "registry_reference": "#/registry_projection",
            "registry_projection": registry_projection,
            "registry_digest": module.digest_value(registry_projection),
            "registered_node_ids": list(node_types),
            "self_images": [_self_image(node_id, node_type) for node_id, node_type in node_types.items()],
            "counts": {"registered": len(node_types), "exported": len(node_types)},
            "readiness": _ready(),
        },
        "set_digest",
    )
    zoom_levels = {}
    zoom_node_ids = {
        "system": "ent_metric_01J00000000000000000000001",
        "organ": "ent_organ_01J00000000000000000000002",
        "repository": "ent_repo_01J00000000000000000000003",
        "document": "ent_document_01J00000000000000000000000",
        "session": "ent_session_01J00000000000000000000004",
        "atom": "ent_variable_01J00000000000000000000005",
    }
    for level, node_id in zoom_node_ids.items():
        zoom_levels[level] = [
            {
                "node_id": node_id,
                "title": level.title(),
                "summary": f"{level} fixture.",
                "self_image_reference": f"self-image:{node_id}",
                "ideal_form_references": ["ideal:fixture"],
                "evidence_references": ["receipt:atlas"],
            }
        ]
    iceberg_atlas = _seal(
        module,
        {
            "contract_name": "iceberg-atlas.v1",
            "contract_version": 1,
            "atlas_id": "atlas:fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "generated_at": SNAPSHOT_AT,
            "source_envelope_references": ["source:src_fixture"],
            "assertion_evidence_references": ["assertion:assertion-operator"],
            "timelines": {
                "operator_intent": [
                    {
                        "entry_id": "intent:1",
                        "event_reference": f"event:{event_id}",
                        "occurred_at": "2026-07-16T17:59:00Z",
                        "title": "Operator intent",
                        "source_envelope_references": ["source:src_fixture"],
                        "evidence_references": ["assertion:assertion-operator"],
                    }
                ],
                "artifact": [
                    {
                        "entry_id": "artifact:1",
                        "event_reference": "artifact:ideal-register",
                        "occurred_at": SNAPSHOT_AT,
                        "title": "Ideal register",
                        "source_envelope_references": ["source:src_fixture"],
                        "evidence_references": ["receipt:ideal"],
                    }
                ],
            },
            "zoom_levels": zoom_levels,
            "relationships": [
                {
                    "relationship_id": "relationship:fixture",
                    "from_node_id": zoom_node_ids["system"],
                    "to_node_id": zoom_node_ids["atom"],
                    "relationship_type": "contains",
                    "evidence_references": ["receipt:atlas"],
                }
            ],
            "ideal_forms": ["ideal:fixture"],
            "self_images": [f"self-image:{node_id}" for node_id in node_types],
            "coverage": {
                "exact_all": True,
                "source_count": 1,
                "event_count": 1,
                "node_count": 6,
                "ideal_form_count": 1,
            },
            "citation_debt": [],
        },
        "atlas_digest",
    )
    atlas_receipt = _seal(
        module,
        {
            "contract_name": "governance-atlas-receipt.v1",
            "contract_version": 1,
            "atlas_receipt_id": "atlas-receipt:fixture",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "owner_reference": "owner:atlas",
            "generated_at": SNAPSHOT_AT,
            "source_envelope_set": {
                "artifact_id": "source-envelope-set:fixture",
                "reference": "bundle:source-envelopes",
                "snapshot_id": SNAPSHOT_ID,
                "digest": module.digest_value(source_envelopes),
                "count": 1,
            },
            "assertion_evidence_set": {
                "artifact_id": "assertions:fixture",
                "reference": "bundle:assertions",
                "snapshot_id": SNAPSHOT_ID,
                "digest": module.digest_value(assertion_evidence),
                "count": 1,
            },
            "ideal_form_register": {
                "artifact_id": ideal_forms["register_id"],
                "reference": "receipt:ideal-register",
                "snapshot_id": SNAPSHOT_ID,
                "digest": ideal_forms["register_digest"],
            },
            "node_self_image_set": {
                "artifact_id": self_images["set_id"],
                "reference": "receipt:self-images",
                "snapshot_id": SNAPSHOT_ID,
                "digest": self_images["set_digest"],
                "count": 6,
            },
            "iceberg_atlas": {
                "artifact_id": iceberg_atlas["atlas_id"],
                "reference": "receipt:iceberg-atlas",
                "snapshot_id": SNAPSHOT_ID,
                "digest": iceberg_atlas["atlas_digest"],
            },
            "timeline_counts": {"operator_intent": 1, "artifact": 1},
            "zoom_counts": {level: 1 for level in zoom_levels},
            "predicate_results": {
                "source_envelopes_resolved": True,
                "assertions_verified": True,
                "ideal_forms_complete": True,
                "self_images_complete": True,
                "timelines_complete": True,
                "zooms_complete": True,
                "atlas_digest_verified": True,
            },
            "readiness": _ready(),
        },
        "receipt_digest",
    )
    governed_documents = {
        "source_census": ("receipt:source-census", "source-census.v1", source_census),
        "source_envelopes": ("artifact:source-envelopes", "source-envelope.v1", source_envelopes),
        "normalized_events": ("artifact:normalized-events", "normalized-event.v1", normalized_events),
        "normalization_parity": (
            "receipt:normalization-parity",
            "normalization-parity-receipt.v1",
            normalization_parity,
        ),
        "lineage_graph": ("receipt:lineage", "lineage-graph.v1", lineage_graph),
        "governance_testament": (
            "receipt:testament",
            "governance-testament.v1",
            governance_testament,
        ),
        "assertion_evidence": ("bundle:assertions", "assertion-evidence.v1", assertion_evidence),
        "coverage_receipt": ("receipt:coverage", "coverage-receipt.v1", coverage_receipt),
        "ideal_forms": ("receipt:ideal-register", "ideal-form-register.v1", ideal_forms),
        "self_images": ("receipt:self-images", "node-self-image-set.v1", self_images),
        "iceberg_atlas": ("receipt:iceberg-atlas", "iceberg-atlas.v1", iceberg_atlas),
        "atlas_receipt": ("receipt:atlas", "governance-atlas-receipt.v1", atlas_receipt),
    }
    stage_assignments = {
        "discover": ["source_census"],
        "snapshot": ["source_envelopes"],
        "parse": ["normalized_events", "normalization_parity"],
        "classify": ["coverage_receipt"],
        "reconcile": ["lineage_graph", "self_images"],
        "distill": ["governance_testament", "assertion_evidence"],
        "validate": ["ideal_forms"],
        "render": ["iceberg_atlas", "atlas_receipt"],
        "receipt": [],
    }
    stage_receipts: list[dict[str, object]] = []
    predecessor = None
    for index, stage in enumerate(module.CADENCE_STAGES):
        outputs = []
        for key in stage_assignments[stage]:
            reference, contract, value = governed_documents[key]
            raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
            outputs.append(
                {
                    "artifact_id": f"artifact:{key}",
                    "reference": reference,
                    "contract": contract,
                    "digest": _file_digest(module, value),
                    "size_bytes": len(raw),
                }
            )
        if not outputs:
            outputs = [
                {
                    "artifact_id": "artifact:preproof",
                    "reference": "artifact:preproof",
                    "contract": "governance-preproof-payload.v1",
                    "digest": "sha256:" + "f" * 64,
                    "size_bytes": 1,
                }
            ]
        predicate_id = "predicate:fixture" if stage == "validate" else f"predicate:{stage}"
        receipt_payload = {
            "contract_name": "governance-stage-receipt.v1",
            "contract_version": 1,
            "stage_receipt_id": f"stage:{stage}",
            "run_id": "cadence:fixture:stage-chain",
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_digest": SNAPSHOT_DIGEST,
            "stage": stage,
            "owner_reference": f"owner:{stage}",
            "predicate": {
                "predicate_id": predicate_id,
                "command": f"verify:{stage}",
                "expected_result": "pass",
            },
            "receipt_target": f"receipt:{stage}",
            "status": "completed",
            "started_at": SNAPSHOT_AT,
            "completed_at": SNAPSHOT_AT,
            "predecessor_receipt_digest": predecessor,
            "inputs": [
                {
                    "artifact_id": f"input:{stage}",
                    "reference": f"input:{stage}",
                    "digest": "sha256:" + "d" * 64,
                    "size_bytes": 1,
                }
            ],
            "outputs": outputs,
            "input_digest": "sha256:" + "c" * 64,
            "output_digest": module.digest_value(outputs),
            "execution_limits": {
                "max_work_items": 1,
                "timeout_seconds": 10,
                "max_retries": 0,
                "max_output_bytes": 1_000_000,
            },
            "cursor": {
                "resume_token": None,
                "completed_child_ids": [f"child:{stage}"],
                "pending_child_ids": [],
            },
            "child_receipts": [
                {
                    "child_id": f"child:{stage}",
                    "status": "completed",
                    "input_digest": "sha256:" + "a" * 64,
                    "output_digest": "sha256:" + "b" * 64,
                }
            ],
            "counts": {
                "attempted": 1,
                "completed": 1,
                "skipped_completed": 0,
                "failed": 0,
                "blocked": 0,
            },
            "digest_algorithm": DIGEST_ALGORITHM,
        }
        receipt = {
            **receipt_payload,
            "receipt_digest": module.digest_value(receipt_payload),
        }
        stage_receipts.append(receipt)
        predecessor = receipt["receipt_digest"]
    stage_summaries = [
        {
            "stage": receipt["stage"],
            "stage_receipt_id": receipt["stage_receipt_id"],
            "reference": receipt["receipt_target"],
            "status": receipt["status"],
            "receipt_digest": receipt["receipt_digest"],
            "predecessor_receipt_digest": receipt["predecessor_receipt_digest"],
        }
        for receipt in stage_receipts
    ]
    run_one = _cadence_receipt(
        module,
        run_number=1,
        previous_digest=None,
        stage_receipts=stage_summaries,
    )
    run_two = _cadence_receipt(
        module,
        run_number=2,
        previous_digest=run_one["receipt_digest"],
        stage_receipts=stage_summaries,
    )
    documents: dict[str, object] = {
        "source_census": source_census,
        "source_envelopes": source_envelopes,
        "normalized_events": normalized_events,
        "normalization_parity": normalization_parity,
        "lineage_graph": lineage_graph,
        "governance_testament": governance_testament,
        "assertion_evidence": assertion_evidence,
        "coverage_receipt": coverage_receipt,
        "ideal_forms": ideal_forms,
        "iceberg_atlas": iceberg_atlas,
        "self_images": self_images,
        "stage_receipts": stage_receipts,
        "cadence_receipt": [run_one, run_two],
        "atlas_receipt": atlas_receipt,
    }
    snapshot_bundle = {
        "contract_name": "governance-snapshot-bundle.v1",
        "contract_version": 1,
        "bundle_id": "bundle:fixture",
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_at": SNAPSHOT_AT,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "generated_at": "2026-07-16T18:02:00Z",
        "source_census": {
            "contract_name": "source-census.v1",
            "census_id": source_census["census_id"],
            "reference": "receipt:source-census",
            "snapshot_id": SNAPSHOT_ID,
            "digest": source_census["census_digest"],
            "raw_unit_count": 1,
        },
        "normalized_events": normalized_events,
        "source_envelopes": source_envelopes,
        "assertion_evidence": assertion_evidence,
        "lineage_graph": {
            "contract_name": "lineage-graph.v1",
            "artifact_id": lineage_graph["graph_id"],
            "reference": "receipt:lineage",
            "snapshot_id": SNAPSHOT_ID,
            "digest": module.digest_value(lineage_graph),
            "node_count": 2,
        },
        "governance_testament": {
            "contract_name": "governance-testament.v1",
            "artifact_id": governance_testament["testament_id"],
            "reference": "receipt:testament",
            "snapshot_id": SNAPSHOT_ID,
            "digest": module.digest_value(governance_testament),
            "status": "ratified",
            "constitutional_coverage_ready": True,
        },
        "coverage": {
            "contract_name": "coverage-receipt.v1",
            "receipt_id": coverage_receipt["receipt_id"],
            "reference": "receipt:coverage",
            "snapshot_id": SNAPSHOT_ID,
            "digest": coverage_receipt["receipt_hash"],
            "exact_all": True,
            "ready": True,
        },
        "ideal_form_register": {
            "contract_name": "ideal-form-register.v1",
            "artifact_id": ideal_forms["register_id"],
            "reference": "receipt:ideal-register",
            "snapshot_id": SNAPSHOT_ID,
            "digest": ideal_forms["register_digest"],
            "count": 1,
            "ready": True,
        },
        "node_self_image_set": {
            "contract_name": "node-self-image-set.v1",
            "artifact_id": self_images["set_id"],
            "reference": "receipt:self-images",
            "snapshot_id": SNAPSHOT_ID,
            "digest": self_images["set_digest"],
            "count": 6,
            "ready": True,
        },
        "iceberg_atlas": {
            "contract_name": "iceberg-atlas.v1",
            "artifact_id": iceberg_atlas["atlas_id"],
            "reference": "receipt:iceberg-atlas",
            "snapshot_id": SNAPSHOT_ID,
            "digest": iceberg_atlas["atlas_digest"],
            "timeline_count": 2,
            "zoom_count": 6,
        },
        "normalization_parity_receipt": {
            "contract_name": "normalization-parity-receipt.v1",
            "receipt_id": normalization_parity["receipt_id"],
            "reference": "receipt:normalization-parity",
            "snapshot_id": SNAPSHOT_ID,
            "digest": normalization_parity["receipt_digest"],
            "ready": True,
        },
        "governance_stage_receipts": [
            {
                "contract_name": "governance-stage-receipt.v1",
                "stage": item["stage"],
                "receipt_id": item["stage_receipt_id"],
                "reference": item["receipt_target"],
                "snapshot_id": SNAPSHOT_ID,
                "digest": item["receipt_digest"],
                "status": item["status"],
            }
            for item in stage_receipts
        ],
        "governance_cadence_receipts": [
            {
                "contract_name": "governance-cadence-receipt.v1",
                "receipt_id": receipt["cadence_receipt_id"],
                "reference": f"receipt:cadence:run-{receipt['run_number']}",
                "run_number": receipt["run_number"],
                "snapshot_id": SNAPSHOT_ID,
                "digest": receipt["receipt_digest"],
                "previous_receipt_digest": receipt["previous_cadence_receipt_digest"],
                "output_digest": receipt["output_digest"],
                "fixed_point_status": receipt["fixed_point"]["status"],
                "new_event_count": receipt["fixed_point"]["new_event_count"],
                "changed_byte_count": receipt["fixed_point"]["changed_byte_count"],
                "replayed_completed_children": receipt["fixed_point"]["replayed_completed_children"],
                "ready": receipt["readiness"]["ready"],
            }
            for receipt in (run_one, run_two)
        ],
        "governance_atlas_receipt": {
            "contract_name": "governance-atlas-receipt.v1",
            "receipt_id": atlas_receipt["atlas_receipt_id"],
            "reference": "receipt:atlas",
            "snapshot_id": SNAPSHOT_ID,
            "digest": atlas_receipt["receipt_digest"],
            "ready": True,
        },
        "post_proof_idempotence": {
            "probe_id": "probe:fixture",
            "invoked_at": SNAPSHOT_AT,
            "cadence_receipt_digest": run_two["receipt_digest"],
            "output_digest": run_two["output_digest"],
            "status": "proven",
            "new_event_count": 0,
            "changed_byte_count": 0,
            "replayed_completed_children": 0,
            "emitted_receipt_count": 0,
        },
        "readiness": _ready(),
        "digest_algorithm": DIGEST_ALGORITHM,
    }
    snapshot_bundle["bundle_digest"] = module.digest_value(snapshot_bundle)
    documents["snapshot_bundle"] = snapshot_bundle
    return documents


def _complete_paths(module, tmp_path: Path) -> dict[str, Path]:
    documents = _documents(module)
    paths = {key: _write(tmp_path / f"{key}.json", value) for key, value in documents.items()}
    paths["schema_root"] = _schema_catalog(module, tmp_path)
    return paths


def _read(paths: dict[str, Path], key: str):
    return json.loads(paths[key].read_text(encoding="utf-8"))


def test_complete_owner_receipts_produce_ready_deterministic_projection(tmp_path: Path) -> None:
    module = _load("governance_memory_ready")
    paths = _complete_paths(module, tmp_path)

    first, first_private = module.build_readiness(paths, max_input_bytes=1_000_000)
    second, second_private = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert first == second
    assert first_private == second_private
    assert first["status"] == "ready"
    assert first["snapshot_id"] == SNAPSHOT_ID
    assert first["snapshot_digest"] == SNAPSHOT_DIGEST
    assert first["normalization_parity"]["exact_all"] is True
    assert first["cadence"]["fixed_point_proven"] is True
    assert first["atlas"]["timeline_counts"] == {"operator_intent": 1, "artifact": 1}
    assert [item["id"] for item in first["atlas"]["zoom_levels"]] == [
        "system",
        "organ",
        "repository",
        "document",
        "session",
        "atom",
    ]
    assert first["violations"] == []


def test_write_outputs_reaches_byte_fixed_point(tmp_path: Path, monkeypatch) -> None:
    module = _load("governance_memory_fixed_point")
    paths = _complete_paths(module, tmp_path)
    monkeypatch.setattr(module, "PUBLIC_OUT", tmp_path / "public.json")
    monkeypatch.setattr(module, "PRIVATE_OUT", tmp_path / "private.json")
    monkeypatch.setattr(module, "DOC_OUT", tmp_path / "readiness.md")
    public, private = module.build_readiness(paths, max_input_bytes=1_000_000)
    markdown = module.render_markdown(public)

    first_changed = module.write_outputs(public, private, markdown)
    before = {path: path.read_bytes() for path in (module.PUBLIC_OUT, module.PRIVATE_OUT, module.DOC_OUT)}
    second_changed = module.write_outputs(public, private, markdown)
    after = {path: path.read_bytes() for path in before}

    assert len(first_changed) == 3
    assert second_changed == []
    assert before == after


def test_missing_and_malformed_inputs_quarantine_independently(tmp_path: Path) -> None:
    module = _load("governance_memory_quarantine")
    paths = _complete_paths(module, tmp_path)
    paths["source_census"] = None
    paths["lineage_graph"].write_text("{truncated", encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert public["status"] == "blocked"
    assert public["inputs"]["source_census"]["state"] == "missing-configuration"
    assert public["inputs"]["lineage_graph"]["state"] == "quarantined"
    assert public["inputs"]["governance_testament"]["state"] == "available"
    assert {item["input"] for item in public["blockers"]} == {
        "source_census",
        "lineage_graph",
    }


@pytest.mark.parametrize(
    ("key", "mutate", "expected"),
    [
        ("source_census", lambda value: value.update(raw_units=[]), "source-census-empty"),
        ("source_envelopes", lambda value: value.clear(), "source-envelopes-empty"),
        ("normalized_events", lambda value: value.clear(), "normalized-events-empty"),
        (
            "governance_testament",
            lambda value: value.update(directive=""),
            "testament-directive-empty",
        ),
        ("assertion_evidence", lambda value: value.clear(), "assertions-empty"),
        ("lineage_graph", lambda value: value.update(nodes=[]), "lineage-nodes-empty"),
        ("ideal_forms", lambda value: value.update(ideal_forms=[]), "ideal-forms-empty"),
        ("self_images", lambda value: value.update(self_images=[]), "self-images-empty"),
    ],
)
def test_semantically_empty_owner_contracts_fail(
    tmp_path: Path,
    key: str,
    mutate,
    expected: str,
) -> None:
    module = _load(f"governance_memory_empty_{key}")
    paths = _complete_paths(module, tmp_path)
    value = _read(paths, key)
    mutate(value)
    _write(paths[key], value)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert public["status"] == "blocked"
    assert expected in public["violations"]


def test_undeclared_contract_and_schema_mismatch_fail_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_contract_mismatch")
    paths = _complete_paths(module, tmp_path)
    value = _read(paths, "governance_testament")
    value.pop("contract_name")
    _write(paths["governance_testament"], value)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "contract-mismatch:governance_testament" in public["violations"]
    assert any(item.startswith("schema-invalid:governance_testament") for item in public["violations"])


def test_stable_event_identity_ignores_provider_and_transport_order(tmp_path: Path) -> None:
    module = _load("governance_memory_event_identity")
    paths = _complete_paths(module, tmp_path)
    events = _read(paths, "normalized_events")
    event_id = events[0]["event_id"]
    events[0]["source_family"] = "provider-renamed-without-code-change"
    events[0]["transport_metadata"] = {"line_number": 900, "provider_order": 1}
    _write(paths["normalized_events"], events)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert public["normalized_events"]["event_ids"] == [event_id]
    assert not [item for item in public["violations"] if item.startswith("normalized-event-identity")]


def test_identity_and_promotion_crosswalk_tampering_fail_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_identity_parity")
    paths = _complete_paths(module, tmp_path)
    events = _read(paths, "normalized_events")
    events[0]["event_id"] = "evt_" + "0" * 64
    _write(paths["normalized_events"], events)
    parity = _read(paths, "normalization_parity")
    parity["promotions"][0]["raw_unit_id"] = "raw_unregistered"
    _write(paths["normalization_parity"], parity)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "normalized-event-identity-mismatch:0" in public["violations"]
    assert "normalization-parity-raw-unit-crosswalk-incomplete" in public["violations"]


def test_parity_binds_exact_census_and_event_set_digests(tmp_path: Path) -> None:
    module = _load("governance_memory_parity_digest_binding")
    paths = _complete_paths(module, tmp_path)
    parity = _read(paths, "normalization_parity")
    parity["input_census"]["census_digest"] = "sha256:" + "0" * 64
    parity["output_events"]["event_set_digest"] = "sha256:" + "1" * 64
    _write(paths["normalization_parity"], parity)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "normalization-parity-census-digest-mismatch" in public["violations"]
    assert "normalization-parity-event-set-digest-mismatch" in public["violations"]
    assert public["normalization_parity"]["ready"] is False


def test_source_census_units_must_resolve_discovery_roots_and_expectations(tmp_path: Path) -> None:
    module = _load("governance_memory_source_census_roots")
    paths = _complete_paths(module, tmp_path)
    census = _read(paths, "source_census")
    census["raw_units"][0]["discovery_root_id"] = "root:unregistered"
    census["raw_units"][0]["expectation_id"] = "expectation:unregistered"
    _write(paths["source_census"], census)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "source-census-discovery-root-unresolved:0" in public["violations"]
    assert "source-census-expectation-unresolved:0" in public["violations"]


def test_reviewed_transport_echo_disposition_is_not_readiness_debt() -> None:
    module = _load("governance_memory_transport_echo")
    census = {
        "census_id": "census:echo",
        "census_digest": "sha256:" + "1" * 64,
        "raw_units": [
            {
                "raw_unit_id": "raw_echo",
                "content_hash": "sha256:" + "2" * 64,
            }
        ],
    }
    parity = {
        "input_census": {
            "census_id": "census:echo",
            "census_digest": "sha256:" + "1" * 64,
            "raw_unit_ids": ["raw_echo"],
            "raw_units": [
                {
                    "raw_unit_id": "raw_echo",
                    "content_hash": "sha256:" + "2" * 64,
                }
            ],
        },
        "output_events": {
            "event_set_digest": module.digest_value([]),
            "event_ids": [],
        },
        "promotions": [
            {
                "raw_unit_id": "raw_echo",
                "raw_unit_content_hash": "sha256:" + "2" * 64,
                "disposition": {
                    "type": "ignored_transport_echo",
                    "owner_reference": "owner:normalizer",
                    "failed_predicate": "transport echo creates no authority event",
                    "next_action": "Retain the reviewed disposition.",
                    "evidence_references": ["review:echo"],
                },
            }
        ],
        "readiness": _ready(),
    }

    projection, issues = module.normalization_parity_projection(
        parity,
        census=census,
        normalized_events={
            "event_ids": [],
            "raw_unit_ids": [],
            "event_set_digest": module.digest_value([]),
        },
        events_by_id={},
    )

    assert issues == []
    assert projection["disposition_count"] == 1
    assert projection["blocking_disposition_count"] == 0
    assert projection["ready"] is True


def test_operator_assertion_needs_resolved_event_and_ratified_record(tmp_path: Path) -> None:
    module = _load("governance_memory_operator_authority")
    paths = _complete_paths(module, tmp_path)
    assertions = _read(paths, "assertion_evidence")
    assertions[0]["evidence_references"][0]["reference"] = "event:evt_" + "0" * 64
    _write(paths["assertion_evidence"], assertions)
    testament = _read(paths, "governance_testament")
    testament["status"] = "candidate"
    testament.pop("ratification")
    _write(paths["governance_testament"], testament)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "assertion-operator-event-unresolved:0" in public["violations"]
    assert "assertion-ratified-record-unresolved:0" in public["violations"]
    assert "testament-not-ratified" in public["violations"]


def test_assertion_gate_rejects_duplicate_underlying_stale_and_fabricated_evidence(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_assertion_truth")
    paths = _complete_paths(module, tmp_path)
    assertions = _read(paths, "assertion_evidence")
    first = assertions[0]["evidence_references"][0]
    assertions[0]["assertion_class"] = "external_fact"
    assertions[0]["evidence_references"][1] = {
        **first,
        "evidence_id": "evidence-duplicate-body",
        "independence_group": "different-label-same-source",
    }
    _write(paths["assertion_evidence"], assertions)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "assertion-duplicate-underlying-evidence:0" in public["violations"]
    assert "assertion-independent-evidence-insufficient:0" in public["violations"]

    assertions[0]["assertion_class"] = "current_state"
    assertions[0]["evidence_references"][0]["evidence_type"] = "owner_record"
    assertions[0]["evidence_references"][1]["evidence_type"] = "fresh_verifier_receipt"
    assertions[0]["freshness"] = {
        "observed_at": "2026-07-15T00:00:00Z",
        "expires_at": "2026-07-15T01:00:00Z",
        "status": "stale",
    }
    _write(paths["assertion_evidence"], assertions)
    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)
    assert "assertion-current-state-evidence-incomplete:0" in public["violations"]


def test_assertion_independence_collapses_type_labels_over_one_source(tmp_path: Path) -> None:
    module = _load("governance_memory_assertion_source_independence")
    paths = _complete_paths(module, tmp_path)
    assertions = _read(paths, "assertion_evidence")
    assertions[0]["assertion_class"] = "external_fact"
    assertions[0]["evidence_references"] = [
        {
            "evidence_id": "primary",
            "independence_group": "publisher",
            "evidence_type": "primary_source",
            "reference": "source:src_fixture",
            "body_hash": "sha256:" + "b" * 64,
        },
        {
            "evidence_id": "secondary-label",
            "independence_group": "aggregator",
            "evidence_type": "secondary_source",
            "reference": "source:src_fixture",
            "body_hash": "sha256:" + "b" * 64,
        },
    ]
    _write(paths["assertion_evidence"], assertions)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "assertion-duplicate-underlying-evidence:0" in public["violations"]
    assert "assertion-independent-evidence-insufficient:0" in public["violations"]


def test_current_state_requires_distinct_owner_and_verifier_receipts(tmp_path: Path) -> None:
    module = _load("governance_memory_current_state_independence")
    paths = _complete_paths(module, tmp_path)
    bundle = _read(paths, "snapshot_bundle")
    validate = next(item for item in bundle["governance_stage_receipts"] if item["stage"] == "validate")
    assertions = _read(paths, "assertion_evidence")
    assertions[0]["assertion_class"] = "current_state"
    assertions[0]["evidence_references"] = [
        {
            "evidence_id": "owner",
            "independence_group": "owner",
            "evidence_type": "owner_record",
            "reference": validate["reference"],
            "body_hash": validate["digest"],
        },
        {
            "evidence_id": "verifier",
            "independence_group": "verifier",
            "evidence_type": "fresh_verifier_receipt",
            "reference": validate["reference"],
            "body_hash": validate["digest"],
        },
    ]
    assertions[0]["freshness"] = {
        "verified_at": SNAPSHOT_AT,
        "max_age_seconds": 60,
        "status": "fresh",
    }
    _write(paths["assertion_evidence"], assertions)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "assertion-duplicate-underlying-evidence:0" in public["violations"]
    assert "assertion-current-state-evidence-incomplete:0" in public["violations"]


def test_ratification_rejects_fabricated_constitutional_record_and_coverage(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_ratification_truth")
    paths = _complete_paths(module, tmp_path)
    assertions = _read(paths, "assertion_evidence")
    assertions[0]["evidence_references"][1]["reference"] = "constitution:fabricated"
    _write(paths["assertion_evidence"], assertions)
    testament = _read(paths, "governance_testament")
    testament["citations"] = []
    coverage = testament["ratification"]["constitutional_coverage"]
    coverage["exact_all"] = False
    coverage["missing_requirements"] = ["operator-event:missing"]
    coverage["ready"] = True
    _write(paths["governance_testament"], testament)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "assertion-constitutional-record-unresolved:0" in public["violations"]
    assert "testament-citations-unresolved" in public["violations"]
    assert "testament-constitutional-coverage-blocked" in public["violations"]
    assert public["testament"]["ready"] is False


def test_constitutional_evidence_binds_the_exact_ratification_body(tmp_path: Path) -> None:
    module = _load("governance_memory_ratification_body")
    paths = _complete_paths(module, tmp_path)
    assertions = _read(paths, "assertion_evidence")
    assertions[0]["evidence_references"][1]["body_hash"] = "sha256:" + "0" * 64
    _write(paths["assertion_evidence"], assertions)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "assertion-evidence-unresolved:0:1" in public["violations"]


def test_ratification_requires_verified_operator_directive_and_bound_content(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_ratification_content")
    paths = _complete_paths(module, tmp_path)
    assertions = _read(paths, "assertion_evidence")
    assertions[0]["assertion_class"] = "external_fact"
    _write(paths["assertion_evidence"], assertions)
    testament = _read(paths, "governance_testament")
    testament["directive"] = "Unbound replacement directive."
    testament["ratification"]["candidate_digest"] = "sha256:" + "0" * 64
    testament["ratification"]["controlling_formulation"] = "Unrelated formulation."
    _write(paths["governance_testament"], testament)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "testament-controlling-assertion-invalid" in public["violations"]
    assert "testament-directive-hash-mismatch" in public["violations"]
    assert "testament-candidate-digest-mismatch" in public["violations"]
    assert "testament-controlling-formulation-mismatch" in public["violations"]


def test_current_state_freshness_is_recomputed_at_snapshot_time(tmp_path: Path) -> None:
    module = _load("governance_memory_current_state_freshness")
    paths = _complete_paths(module, tmp_path)
    bundle = _read(paths, "snapshot_bundle")
    stage_bindings = {item["reference"]: item["digest"] for item in bundle["governance_stage_receipts"]}
    assertions = _read(paths, "assertion_evidence")
    assertion = assertions[0]
    assertion["assertion_class"] = "current_state"
    assertion["evidence_references"] = [
        {
            "evidence_id": "owner-record",
            "independence_group": "owner",
            "evidence_type": "owner_record",
            "reference": "receipt:validate",
            "body_hash": stage_bindings["receipt:validate"],
        },
        {
            "evidence_id": "verifier-receipt",
            "independence_group": "verifier",
            "evidence_type": "fresh_verifier_receipt",
            "reference": "receipt:receipt",
            "body_hash": stage_bindings["receipt:receipt"],
        },
    ]
    assertion["freshness"] = {
        "verified_at": "2020-01-01T00:00:00Z",
        "max_age_seconds": 1,
        "status": "fresh",
    }
    _write(paths["assertion_evidence"], assertions)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "assertion-current-state-evidence-incomplete:0" in public["violations"]


def test_missing_authority_event_blocks_ratified_testament(tmp_path: Path) -> None:
    module = _load("governance_memory_missing_authority_event")
    paths = _complete_paths(module, tmp_path)
    testament = _read(paths, "governance_testament")
    testament["ratification"]["authority_events"][0]["event_id"] = "evt_" + "0" * 64
    _write(paths["governance_testament"], testament)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "testament-authority-events-unresolved" in public["violations"]
    assert public["testament"]["ready"] is False


def test_ratification_authority_event_must_match_immutable_event_evidence(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_authority_event_evidence")
    paths = _complete_paths(module, tmp_path)
    testament = _read(paths, "governance_testament")
    authority_event = testament["ratification"]["authority_events"][0]
    authority_event["content_hash"] = "sha256:" + "0" * 64
    authority_event["source_envelope_reference"] = "source:src_fabricated"
    _write(paths["governance_testament"], testament)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "testament-authority-event-evidence-mismatch:0" in public["violations"]


def test_ideal_and_atlas_references_must_resolve_through_snapshot(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_compiler_reference_truth")
    paths = _complete_paths(module, tmp_path)
    ideals = _read(paths, "ideal_forms")
    ideal = ideals["ideal_forms"][0]
    ideal["predicates"][0]["receipt_reference"] = "receipt:fabricated"
    ideal["derivation"]["receipt_references"] = ["receipt:fabricated"]
    _write(paths["ideal_forms"], ideals)
    atlas = _read(paths, "iceberg_atlas")
    atlas["source_envelope_references"] = ["source:src_fabricated"]
    atlas["assertion_evidence_references"] = ["assertion:fabricated"]
    atlas["timelines"]["operator_intent"][0]["event_reference"] = "event:evt_" + "0" * 64
    atlas["relationships"][0]["to_node_id"] = "node-missing"
    _write(paths["iceberg_atlas"], atlas)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "ideal-form-receipt-derivation-mismatch:0" in public["violations"]
    assert "atlas-source-envelope-reference-unresolved" in public["violations"]
    assert "atlas-assertion-reference-unresolved" in public["violations"]
    assert "atlas-timeline-event-unresolved:operator_intent:0" in public["violations"]
    assert "atlas-relationship-node-unresolved:0" in public["violations"]


def test_atlas_requires_exact_source_assertion_and_coverage_sets(tmp_path: Path) -> None:
    module = _load("governance_memory_atlas_exact_sets")
    paths = _complete_paths(module, tmp_path)
    atlas = _read(paths, "iceberg_atlas")
    atlas["source_envelope_references"] = ["source:src_fixture"]
    atlas["assertion_evidence_references"] = ["assertion:assertion-operator"]
    atlas["coverage"]["source_count"] = 999
    atlas["coverage"]["event_count"] = 999
    atlas["coverage"]["node_count"] = 999
    atlas["coverage"]["ideal_form_count"] = 999
    _write(paths["iceberg_atlas"], atlas)
    envelopes = _read(paths, "source_envelopes")
    extra_envelope = dict(envelopes[0])
    extra_envelope["source_id"] = "src_extra"
    envelopes.append(extra_envelope)
    _write(paths["source_envelopes"], envelopes)
    assertions = _read(paths, "assertion_evidence")
    extra_assertion = dict(assertions[0])
    extra_assertion["assertion_id"] = "assertion-extra"
    assertions.append(extra_assertion)
    _write(paths["assertion_evidence"], assertions)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "atlas-source-envelope-set-mismatch" in public["violations"]
    assert "atlas-assertion-set-mismatch" in public["violations"]
    assert "atlas-coverage-counts-mismatch" in public["violations"]


def test_cross_owner_evidence_and_denominator_links_fail_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_cross_owner_links")
    paths = _complete_paths(module, tmp_path)
    envelopes = _read(paths, "source_envelopes")
    envelopes[0]["role"] = "assistant"
    envelopes[0]["authority_class"] = "artifact"
    envelopes[0]["body_hash"] = "sha256:" + "0" * 64
    _write(paths["source_envelopes"], envelopes)
    assertions = _read(paths, "assertion_evidence")
    assertions[0]["evidence_references"][0]["body_hash"] = "sha256:" + "1" * 64
    _write(paths["assertion_evidence"], assertions)
    lineage = _read(paths, "lineage_graph")
    lineage["edges"][0]["evidence_spans"][0]["source_envelope_id"] = "src_fake"
    lineage["edges"][0]["evidence_spans"][0]["body_hash"] = "sha256:" + "2" * 64
    _write(paths["lineage_graph"], lineage)
    coverage = _read(paths, "coverage_receipt")
    coverage["sources"][0]["source_id"] = "src_unrelated"
    _write(paths["coverage_receipt"], coverage)
    events = _read(paths, "normalized_events")
    events[0]["raw_unit_id"] = "raw_unrelated"
    _write(paths["normalized_events"], events)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "normalized-event-envelope-evidence-mismatch:0" in public["violations"]
    assert "assertion-evidence-unresolved:0:0" in public["violations"]
    assert "lineage-edge-evidence-unresolved:0:0" in public["violations"]
    assert "coverage-source-identity-unresolved" in public["violations"]
    assert "normalization-parity-leaf-mapping-mismatch:0" in public["violations"]
    assert "normalization-parity-event-raw-unit-unresolved" in public["violations"]


def test_snapshot_and_atlas_receipt_summaries_bind_exact_owner_artifacts(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_receipt_summary_bindings")
    paths = _complete_paths(module, tmp_path)
    bundle = _read(paths, "snapshot_bundle")
    bundle["source_census"]["raw_unit_count"] = 999
    bundle["governance_testament"]["constitutional_coverage_ready"] = False
    bundle["coverage"]["exact_all"] = False
    bundle["coverage"]["ready"] = False
    _write(paths["snapshot_bundle"], bundle)
    atlas_receipt = _read(paths, "atlas_receipt")
    for field in (
        "source_envelope_set",
        "assertion_evidence_set",
        "ideal_form_register",
        "node_self_image_set",
        "iceberg_atlas",
    ):
        atlas_receipt[field]["digest"] = "sha256:" + "0" * 64
    _write(paths["atlas_receipt"], atlas_receipt)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "snapshot-bundle-source-census-summary-mismatch" in public["violations"]
    assert "snapshot-bundle-testament-summary-mismatch" in public["violations"]
    assert "snapshot-bundle-coverage-summary-mismatch" in public["violations"]
    assert "atlas-receipt-source-envelope-digest-mismatch" in public["violations"]
    assert "atlas-receipt-assertion-digest-mismatch" in public["violations"]
    assert "atlas-receipt-ideal-form-digest-mismatch" in public["violations"]
    assert "atlas-receipt-self-image-digest-mismatch" in public["violations"]
    assert "atlas-receipt-atlas-digest-mismatch" in public["violations"]


def test_self_image_duplicate_stale_and_atlas_content_fail_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_self_image_atlas")
    paths = _complete_paths(module, tmp_path)
    images = _read(paths, "self_images")
    images["self_images"][1]["node_id"] = images["self_images"][0]["node_id"]
    images["self_images"][0]["reconciled_at"] = "2026-07-15T00:00:00Z"
    _write(paths["self_images"], images)
    atlas = _read(paths, "iceberg_atlas")
    atlas["timelines"]["artifact"] = []
    atlas["zoom_levels"]["atom"] = []
    _write(paths["iceberg_atlas"], atlas)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "self-images-duplicate-node-id" in public["violations"]
    assert "self-image-stale:0" in public["violations"]
    assert "atlas-timeline-empty:artifact" in public["violations"]
    assert "atlas-zoom-empty:atom" in public["violations"]


def test_self_image_registry_projection_is_the_independent_denominator(tmp_path: Path) -> None:
    module = _load("governance_memory_self_image_registry")
    paths = _complete_paths(module, tmp_path)
    images = _read(paths, "self_images")
    images["registry_reference"] = "registry:arbitrary"
    images["registry_digest"] = "sha256:" + "0" * 64
    images["registered_node_ids"] = images["registered_node_ids"][:-1]
    _write(paths["self_images"], images)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "self-images-registry-reference-unresolved" in public["violations"]
    assert "self-images-registry-denominator-mismatch" in public["violations"]
    assert "self-images-exact-one-coverage-failed" in public["violations"]


def test_second_cadence_run_must_be_bound_and_zero_change(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_binding")
    paths = _complete_paths(module, tmp_path)
    cadence = _read(paths, "cadence_receipt")
    cadence[1]["previous_cadence_receipt_digest"] = "sha256:" + "0" * 64
    cadence[1]["fixed_point"]["changed_byte_count"] = 1
    _write(paths["cadence_receipt"], cadence)

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert "cadence-two-run-binding-mismatch" in public["violations"]
    assert "cadence-fixed-point-not-proven" in public["violations"]
    assert public["cadence"]["complete"] is False


def test_active_or_invalidated_cadence_marker_blocks_stale_success(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_marker")
    paths = _complete_paths(module, tmp_path)
    cadence_root = paths["cadence_receipt"].parent
    (cadence_root / "governance-cadence-active.v1.json").write_text("{}\n", encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)
    assert "cadence-execution-active" in public["violations"]

    (cadence_root / "governance-cadence-active.v1.json").unlink()
    (cadence_root / "governance-cadence-invalidated.v1.json").write_text("{}\n", encoding="utf-8")
    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)
    assert "cadence-proof-invalidated" in public["violations"]


def test_required_seed_expectation_cannot_disappear_from_denominator() -> None:
    module = _load("governance_memory_required_expectation")
    census = deepcopy(_documents(module)["source_census"])
    census["seed_expectations"] = [
        {
            "expectation_id": "expectation:perplexity",
            "source_family": "perplexity",
            "config_reference": "config:perplexity",
            "required": True,
        }
    ]

    projection, issues = module.source_census_projection(census)

    assert "source-census-required-expectation-unrepresented" in issues
    assert projection["unrepresented_required_expectation_ids"] == ["expectation:perplexity"]
    assert projection["ready"] is False


def test_parity_raw_unit_content_hash_must_match_census() -> None:
    module = _load("governance_memory_raw_content_binding")
    documents = _documents(module)
    parity = deepcopy(documents["normalization_parity"])
    parity["promotions"][0]["raw_unit_content_hash"] = "sha256:" + "0" * 64
    events = {item["event_id"]: item for item in documents["normalized_events"]}

    projection, issues = module.normalization_parity_projection(
        parity,
        census=documents["source_census"],
        normalized_events={
            "event_ids": list(events),
            "raw_unit_ids": ["raw_fixture"],
            "event_set_digest": module.digest_value(documents["normalized_events"]),
        },
        events_by_id=events,
    )

    assert "normalization-parity-raw-unit-content-hash-mismatch:0" in issues
    assert "normalization-parity-leaf-mapping-mismatch:0" in issues
    assert projection["ready"] is False


def test_ideal_predicate_requires_matching_verified_receipt() -> None:
    module = _load("governance_memory_ideal_receipt")
    documents = _documents(module)
    wrong_receipt = documents["stage_receipts"][0]

    projection, issues = module.ideal_form_projection(
        documents["ideal_forms"],
        assertion_ids={"assertion-operator"},
        verified_predicate_receipts={"receipt:validate": wrong_receipt},
    )

    assert "ideal-form-predicate-receipt-unresolved:0:0" in issues
    assert projection["ready"] is False


def test_self_image_future_and_unresolved_evidence_fail_closed() -> None:
    module = _load("governance_memory_self_image_traceability")
    images = deepcopy(_documents(module)["self_images"])
    images["self_images"][0]["reconciled_at"] = "2099-01-01T00:00:00Z"
    images["self_images"][0]["evidence_references"] = ["receipt:missing"]
    images["self_images"][0]["observations"][0]["evidence_references"] = ["receipt:missing"]
    images["self_images"][0]["active_ideal_forms"][0]["predicate_references"] = ["predicate:missing"]

    projection, issues = module.self_image_projection(
        images,
        snapshot_at=SNAPSHOT_AT,
        generated_at="2026-07-16T18:02:00Z",
        evidence_ids={"receipt:reconcile"},
        ideal_ids={"ideal:fixture"},
        ideal_predicate_ids={"predicate:fixture"},
    )

    assert "self-image-future:0" in issues
    assert "self-image-evidence-unresolved:0" in issues
    assert "self-image-observation-evidence-unresolved:0:0" in issues
    assert "self-image-active-ideal-predicate-unresolved:0:0" in issues
    assert projection["ready"] is False


def test_atlas_zoom_self_images_cover_exact_registered_set_once() -> None:
    module = _load("governance_memory_atlas_self_image_coverage")
    documents = _documents(module)
    atlas = deepcopy(documents["iceberg_atlas"])
    self_image_ids = set(documents["self_images"]["registered_node_ids"])
    first_reference = f"self-image:{sorted(self_image_ids)[0]}"
    for nodes in atlas["zoom_levels"].values():
        for node in nodes:
            node["self_image_reference"] = first_reference

    projection, issues = module.atlas_projection(
        atlas,
        ideal_ids={"ideal:fixture"},
        self_image_ids=self_image_ids,
        source_envelope_ids={"src_fixture"},
        event_ids={documents["normalized_events"][0]["event_id"]},
        assertion_ids={"assertion-operator"},
    )

    assert "atlas-zoom-self-image-coverage-mismatch" in issues
    assert projection["status"] == "invalid"


def test_snapshot_bundle_owner_documents_must_match_proven_stage_outputs() -> None:
    module = _load("governance_memory_stage_owner_binding")
    documents = _documents(module)
    stage_receipts, stage_issues = module.stage_receipt_projection(documents["stage_receipts"])
    assert stage_issues == []
    cadence, cadence_issues = module.cadence_projection(
        documents["cadence_receipt"],
        stage_receipts=stage_receipts,
    )
    assert cadence_issues == []
    tampered_stage_receipts = deepcopy(stage_receipts)
    source_output = next(
        item for item in tampered_stage_receipts["output_bindings"] if item.get("contract") == "source-census.v1"
    )
    source_output["digest"] = "sha256:" + "0" * 64
    public_inputs = {
        key: {"sha256": module.digest_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())}
        for key, value in documents.items()
    }

    projection, issues = module.snapshot_bundle_projection(
        documents["snapshot_bundle"],
        documents=documents,
        cadence=cadence,
        stage_receipts=tampered_stage_receipts,
        public_inputs=public_inputs,
    )

    assert "snapshot-bundle-stage-output-binding-mismatch:source_census" in issues
    assert projection["ready"] is False


def test_complete_fixture_passes_configured_public_schema_catalog(tmp_path: Path) -> None:
    schema_root_raw = os.environ.get("LIMEN_GOV_TEST_SCHEMA_ROOT", "").strip()
    if not schema_root_raw:
        pytest.skip("LIMEN_GOV_TEST_SCHEMA_ROOT is not configured")
    schema_root = Path(schema_root_raw).expanduser().resolve()
    module = _load("governance_memory_real_schema_catalog")
    paths = _complete_paths(module, tmp_path)
    paths["schema_root"] = schema_root

    public, _ = module.build_readiness(paths, max_input_bytes=1_000_000)

    assert public["status"] == "ready", public["violations"]
    assert public["violations"] == []


def test_governance_heartbeat_wires_real_cadence_before_redacted_readiness() -> None:
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    local = 'python3 "$LIMEN_ROOT/scripts/governance-organ.py"'
    cadence = 'python3 "$LIMEN_ROOT/scripts/governance-memory-cadence.py"'
    readiness = 'python3 "$LIMEN_ROOT/scripts/governance-memory-readiness.py" --strict --write'

    assert local in heartbeat
    assert cadence in heartbeat
    assert readiness in heartbeat
    assert heartbeat.index(local) < heartbeat.index(cadence) < heartbeat.index(readiness)
