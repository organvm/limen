from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "governance-memory-readiness.py"


def _load(name: str = "governance_memory_readiness_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def _complete_paths(module, tmp_path: Path, *, snapshot_id: str = "snapshot-fixture") -> dict[str, Path]:
    stage_receipts = [
        {
            "stage": stage,
            "status": "complete",
            "cursor": f"cursor-{index}",
            "limit": 100,
            "receipt_id": f"receipt-{index}",
        }
        for index, stage in enumerate(module.CADENCE_STAGES)
    ]
    documents = {
        "source_census": [
            {
                "schema_version": "source-census.v1",
                "snapshot_id": snapshot_id,
                "unit_id": f"unit-{index}",
                "status": "parsed",
            }
            for index in range(4)
        ],
        "source_envelopes": [
            {
                "contract_name": "source-envelope.v1",
                "source_id": "source-fixture",
                "custody_snapshot": {"snapshot_id": snapshot_id},
            }
        ],
        "lineage_graph": {
            "contract_name": "lineage-graph.v1",
            "frozen_snapshot_id": snapshot_id,
            "nodes": [],
            "edges": [],
        },
        "governance_testament": {
            "contract_name": "governance-testament.v1",
            "directives": [],
        },
        "assertion_evidence": {
            "contract_name": "assertion-evidence.v1",
            "assertion_id": "assertion-fixture",
            "assertion_class": "external_fact",
            "verification_state": "verified",
            "evidence_references": [
                {"independence_group": "owner-record"},
                {"independence_group": "fresh-verifier"},
            ],
        },
        "coverage_receipt": {
            "schema_version": "coverage-receipt.v1",
            "snapshot_id": snapshot_id,
            "dynamic_denominator": 4,
            "status_counts": {"parsed": 4},
            "unassessed": 0,
            "duplicate_assignments": 0,
            "exact_all": True,
            "ready": True,
            "residual_owners": [],
        },
        "iceberg_atlas": {
            "contract": "iceberg-atlas.v1",
            "snapshot_id": snapshot_id,
            "zoom_levels": [
                {"id": "system", "node_count": 1},
                {"id": "organ", "node_count": 4},
                {"id": "repository", "node_count": 12},
                {"id": "document-session", "node_count": 30},
                {"id": "atom", "node_count": 80},
            ],
            "timelines": {"operator_intent": [{"id": "intent-1"}], "artifact": [{"id": "artifact-1"}]},
            "ideal_forms": [
                {
                    "id": "prime-directive",
                    "implementation_state": "partial",
                    "distance_to_ideal": 2,
                    "citation_debt": 0,
                }
            ],
            "self_image_count": 12,
            "stage_receipts": stage_receipts,
        },
        "self_images": {
            "contract_name": "node-self-image.v1",
            "self_images": [],
        },
    }
    return {key: _write(tmp_path / f"{key}.json", value) for key, value in documents.items()}


def test_complete_owner_receipts_produce_ready_deterministic_projection(tmp_path: Path) -> None:
    module = _load("governance_memory_ready")
    paths = _complete_paths(module, tmp_path)

    first, first_private = module.build_readiness(paths, max_input_bytes=100_000)
    second, second_private = module.build_readiness(paths, max_input_bytes=100_000)

    assert first == second
    assert first_private == second_private
    assert first["status"] == "ready"
    assert first["snapshot_id"] == "snapshot-fixture"
    assert first["coverage"]["exact_all"] is True
    assert first["cadence"]["complete"] is True
    assert first["atlas"]["timeline_counts"] == {"operator_intent": 1, "artifact": 1}
    assert [item["id"] for item in first["atlas"]["zoom_levels"]] == [
        "system",
        "organ",
        "repository",
        "document-session",
        "atom",
    ]
    assert "generated_at" not in first


def test_engine_atlas_mapping_projects_all_zoom_levels_and_ideal_distance(tmp_path: Path) -> None:
    module = _load("governance_memory_engine_atlas")
    paths = _complete_paths(module, tmp_path)
    atlas = json.loads(paths["iceberg_atlas"].read_text(encoding="utf-8"))
    atlas["zoom_levels"] = {
        "atom": [{"node_id": "atom-1"}, {"node_id": "atom-2"}],
        "document": [{"node_id": "document-1"}],
        "organ": [{"node_id": "organ-1"}],
        "repository": [{"node_id": "repository-1"}],
        "session": [{"node_id": "session-1"}],
        "system": [{"node_id": "system-1"}],
    }
    atlas["ideal_forms"] = [
        {
            "ideal_form_id": "ideal-form:iceberg-atlas",
            "implementation_state": "partial",
            "distance_fraction": 0.4,
            "distance_to_ideal": {
                "classification": "authority_gap",
                "total_predicates": 5,
                "verified_predicates": 3,
            },
            "citation_debt": 0,
        }
    ]
    _write(paths["iceberg_atlas"], atlas)

    public, _ = module.build_readiness(paths, max_input_bytes=100_000)

    assert public["atlas"]["zoom_levels"] == [
        {"id": "system", "node_count": 1},
        {"id": "organ", "node_count": 1},
        {"id": "repository", "node_count": 1},
        {"id": "document", "node_count": 1},
        {"id": "session", "node_count": 1},
        {"id": "atom", "node_count": 2},
    ]
    assert public["atlas"]["ideal_forms"] == [
        {
            "id": "ideal-form:iceberg-atlas",
            "implementation_state": "partial",
            "distance_to_ideal": 0.4,
            "citation_debt": 0,
        }
    ]


def test_write_outputs_reaches_byte_fixed_point(tmp_path: Path, monkeypatch) -> None:
    module = _load("governance_memory_fixed_point")
    paths = _complete_paths(module, tmp_path)
    monkeypatch.setattr(module, "PUBLIC_OUT", tmp_path / "public.json")
    monkeypatch.setattr(module, "PRIVATE_OUT", tmp_path / "private.json")
    monkeypatch.setattr(module, "DOC_OUT", tmp_path / "readiness.md")
    public, private = module.build_readiness(paths, max_input_bytes=100_000)
    markdown = module.render_markdown(public)

    first_changed = module.write_outputs(public, private, markdown)
    before = {path: path.read_bytes() for path in (module.PUBLIC_OUT, module.PRIVATE_OUT, module.DOC_OUT)}
    second_changed = module.write_outputs(public, private, markdown)
    after = {path: path.read_bytes() for path in before}

    assert len(first_changed) == 3
    assert second_changed == []
    assert before == after


def test_missing_and_malformed_inputs_stay_visible_without_stopping_other_inputs(tmp_path: Path) -> None:
    module = _load("governance_memory_quarantine")
    paths = _complete_paths(module, tmp_path)
    paths["source_census"] = None
    paths["lineage_graph"].write_text("{truncated", encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=100_000)

    assert public["status"] == "degraded"
    assert public["inputs"]["source_census"]["state"] == "missing-configuration"
    assert public["inputs"]["lineage_graph"]["state"] == "quarantined"
    assert public["inputs"]["governance_testament"]["state"] == "available"
    assert {item["input"] for item in public["blockers"]} == {"source_census", "lineage_graph"}
    assert all("/" not in item["owner_reference"] for item in public["blockers"])


def test_snapshot_mismatch_and_fabricated_exact_all_fail_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_mismatch")
    paths = _complete_paths(module, tmp_path)
    coverage = json.loads(paths["coverage_receipt"].read_text(encoding="utf-8"))
    coverage["snapshot_id"] = "other-snapshot"
    coverage["status_counts"] = {"parsed": 3}
    coverage["unassessed"] = 1
    coverage["exact_all"] = True
    paths["coverage_receipt"].write_text(json.dumps(coverage), encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=100_000)

    assert public["status"] == "blocked"
    assert public["snapshot_id"] is None
    assert public["coverage"]["exact_all"] is False
    assert "snapshot-id-mismatch" in public["violations"]
    assert "coverage-exact-all-contradicts-counts" in public["violations"]
    assert "coverage-unassessed-nonzero" in public["violations"]


def test_classified_inaccessible_sources_can_be_exact_but_remain_degraded(tmp_path: Path) -> None:
    module = _load("governance_memory_residual")
    paths = _complete_paths(module, tmp_path)
    coverage = json.loads(paths["coverage_receipt"].read_text(encoding="utf-8"))
    coverage["status_counts"] = {"parsed": 3, "inaccessible": 1}
    coverage["unassessed"] = 0
    coverage["ready"] = False
    coverage["residual_owners"] = [
        {
            "unit_id": "unit-3",
            "owner_reference": "owner-fixture",
            "failed_predicate": "fixture source is readable",
            "next_action": "hydrate fixture source",
        }
    ]
    paths["coverage_receipt"].write_text(json.dumps(coverage), encoding="utf-8")
    census = json.loads(paths["source_census"].read_text(encoding="utf-8"))
    census[3]["status"] = "inaccessible"
    census[3]["blocker"] = {
        "owner_reference": "owner-fixture",
        "failed_predicate": "fixture source is readable",
        "next_action": "hydrate fixture source",
    }
    paths["source_census"].write_text(json.dumps(census), encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=100_000)

    assert public["coverage"]["exact_all"] is True
    assert public["coverage"]["residual_count"] == 1
    assert public["status"] == "degraded"


def test_external_fact_needs_two_independent_evidence_groups(tmp_path: Path) -> None:
    module = _load("governance_memory_assertion")
    paths = _complete_paths(module, tmp_path)
    assertions = json.loads(paths["assertion_evidence"].read_text(encoding="utf-8"))
    assertions["evidence_references"] = [{"independence_group": "same-parent"}]
    paths["assertion_evidence"].write_text(json.dumps(assertions), encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=100_000)

    assert public["status"] == "blocked"
    assert "assertion-independent-evidence-insufficient:0" in public["violations"]


def test_operator_directive_needs_source_event_and_ratified_record(tmp_path: Path) -> None:
    module = _load("governance_memory_operator_authority")
    paths = _complete_paths(module, tmp_path)
    assertions = json.loads(paths["assertion_evidence"].read_text(encoding="utf-8"))
    assertions["assertion_class"] = "operator_directive"
    assertions["evidence_references"] = [
        {
            "evidence_type": "immutable_source_event",
            "independence_group": "operator-event",
        }
    ]
    paths["assertion_evidence"].write_text(json.dumps(assertions), encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=100_000)

    assert public["status"] == "blocked"
    assert "assertion-operator-authority-incomplete:0" in public["violations"]


def test_governance_heartbeat_wires_redacted_readiness_after_local_validator() -> None:
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    local = 'python3 "$LIMEN_ROOT/scripts/governance-organ.py"'
    readiness = 'python3 "$LIMEN_ROOT/scripts/governance-memory-readiness.py" --write'

    assert local in heartbeat
    assert readiness in heartbeat
    assert heartbeat.index(local) < heartbeat.index(readiness)


def test_duplicate_source_classification_fails_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_duplicate_source")
    paths = _complete_paths(module, tmp_path)
    census = json.loads(paths["source_census"].read_text(encoding="utf-8"))
    census[3]["unit_id"] = census[0]["unit_id"]
    paths["source_census"].write_text(json.dumps(census), encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=100_000)

    assert public["status"] == "blocked"
    assert public["source_census"]["duplicate_assignments"] == 1
    assert "source-census-duplicate-unit-id" in public["violations"]


def test_public_coverage_contract_adapts_without_changing_semantics(tmp_path: Path) -> None:
    module = _load("governance_memory_public_coverage")
    paths = _complete_paths(module, tmp_path)
    public_contract = {
        "contract_name": "coverage-receipt.v1",
        "snapshot_id": "snapshot-fixture",
        "denominator": {"count": 4},
        "sources": [
            {
                "source_id": f"unit-{index}",
                "status": "parsed",
                "accessible": True,
            }
            for index in range(4)
        ],
        "counts": {
            "acquired": 0,
            "parsed": 4,
            "quarantined": 0,
            "inaccessible": 0,
            "missing_expected": 0,
            "owner_blocked": 0,
        },
        "exact_all": True,
        "ready": True,
        "residual_owners": [],
    }
    paths["coverage_receipt"].write_text(json.dumps(public_contract), encoding="utf-8")

    public, _ = module.build_readiness(paths, max_input_bytes=100_000)

    assert public["status"] == "ready"
    assert public["coverage"]["exact_all"] is True
    assert public["coverage"]["ready"] is True
    assert not [item for item in public["violations"] if item.startswith("coverage-")]
