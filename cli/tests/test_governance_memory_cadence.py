from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "governance-memory-cadence.py"


def _load(name: str = "governance_memory_cadence_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _worker(tmp_path: Path) -> Path:
    path = tmp_path / "worker.py"
    path.write_text(
        """
import json
import os
import hashlib
from pathlib import Path
import rfc8785

stage = os.environ["LIMEN_GOV_STAGE"]
if log_bytes := int(os.environ.get("FIXTURE_LOG_BYTES", "0")):
    print("x" * log_bytes, flush=True)
run_root = Path(os.environ["LIMEN_GOV_RUN_ROOT"])
if scratch_bytes := int(os.environ.get("FIXTURE_SCRATCH_BYTES", "0")):
    (run_root / "intermediate.bin").write_bytes(b"x" * scratch_bytes)
counter_path = run_root / "executions.json"
counter = json.loads(counter_path.read_text()) if counter_path.exists() else {}
counter[stage] = counter.get(stage, 0) + 1
counter_path.write_text(json.dumps(counter, sort_keys=True))
targets_path = run_root / "stage-receipt-targets.json"
targets = json.loads(targets_path.read_text()) if targets_path.exists() else {}
targets[stage] = os.environ["LIMEN_GOV_STAGE_RECEIPTS"]
targets_path.write_text(json.dumps(targets, sort_keys=True))

fail_stage = os.environ.get("FIXTURE_FAIL_STAGE")
failure_gate = run_root / "allow-failed-stage"
traversal = int(os.environ["LIMEN_GOV_TRAVERSAL"])
attempt = int(os.environ["LIMEN_GOV_STAGE_ATTEMPT"])
output = run_root / "artifacts" / f"{stage}.json"
output.parent.mkdir(parents=True, exist_ok=True)
if traversal == 1 and stage == fail_stage and not failure_gate.exists():
    raise SystemExit(17)
fail_proof = run_root / "fail-proof-stage"
if traversal >= 2 and fail_proof.exists() and fail_proof.read_text().strip() == stage:
    raise SystemExit(23)
mutate_fail_proof = run_root / "mutate-fail-proof-stage"
if (
    traversal >= 2
    and attempt == 1
    and mutate_fail_proof.exists()
    and mutate_fail_proof.read_text().strip() == stage
):
    output.write_text('{"mutated_by_failed_proof":true}')
    raise SystemExit(29)

metrics = Path(os.environ["LIMEN_GOV_STAGE_METRICS_OUT"])
if traversal == 1:
    readiness = {
        "exact_all": True,
        "unresolved_blockers": [],
        "quarantines": [],
        "missing_requirements": [],
        "citation_debt": [],
        "incomplete_predicates": [],
        "ready": True,
        "status": "ready",
    }
    debt_stage = run_root / "owner-debt-stage"
    if debt_stage.exists() and debt_stage.read_text().strip() == stage:
        readiness["unresolved_blockers"] = [f"owner:{stage}:blocked"]
        readiness["ready"] = False
        readiness["status"] = "blocked"
    document = {
        "snapshot_id": os.environ["LIMEN_GOV_SNAPSHOT_ID"],
        "stage": stage,
        "readiness": readiness,
    }
    if stage == "receipt":
        document = {
            "contract_name": "governance-snapshot-bundle-pre-proof.v1",
            "contract_version": 1,
            "snapshot_id": os.environ["LIMEN_GOV_SNAPSHOT_ID"],
            "snapshot_at": os.environ["LIMEN_GOV_SNAPSHOT_AT"],
            "snapshot_digest": "sha256:" + "a" * 64,
            "readiness": readiness,
            "bundle_payload": {
                "bundle_id": (
                    "fixture-cadence:"
                    + os.environ["LIMEN_GOV_SNAPSHOT_ID"]
                    + ":bundle"
                ),
                "source_census": {"receipt_id": "source-census"},
                "normalized_events": [{"event_id": "event-1"}],
                "source_envelopes": [{"source_id": "source-1"}],
                "assertion_evidence": [{"assertion_id": "assertion-1"}],
                "lineage_graph": {"artifact_id": "lineage-1"},
                "governance_testament": {"artifact_id": "testament-1"},
                "coverage": {"receipt_id": "coverage-1"},
                "ideal_form_register": {"artifact_id": "ideals-1"},
                "node_self_image_set": {"artifact_id": "self-images-1"},
                "iceberg_atlas": {"artifact_id": "atlas-1"},
                "normalization_parity_receipt": {"receipt_id": "parity-1"},
                "governance_atlas_receipt": {"receipt_id": "atlas-receipt-1"},
            },
        }
    padding = " " * int(os.environ.get("FIXTURE_ARTIFACT_PADDING", "0"))
    output.write_text(json.dumps(document, sort_keys=True) + padding)
    child_id = f"{stage}-child"
    input_digest = "sha256:" + hashlib.sha256(f"{stage}:input".encode()).hexdigest()
    output_digest = "sha256:" + hashlib.sha256(f"{stage}:output".encode()).hexdigest()
    child = {
        "child_id": child_id,
        "status": "completed",
        "input_digest": input_digest,
        "output_digest": output_digest,
    }
    emitted_events = 1 if stage == "parse" else 0
else:
    prior = json.loads(Path(os.environ["LIMEN_GOV_PRIOR_STAGE_RECEIPT"]).read_text())
    prior_child = prior["child_receipts"][0]
    child_id = prior_child["child_id"]
    child = {
        "child_id": child_id,
        "status": "skipped_completed",
        "input_digest": prior_child["input_digest"],
        "output_digest": prior_child["output_digest"],
        "prior_receipt_digest": "sha256:" + hashlib.sha256(rfc8785.dumps(prior_child)).hexdigest(),
    }
    emitted_events = 0

metrics.write_text(json.dumps({
    "resume_token": None,
    "completed_child_ids": [child_id],
    "pending_child_ids": [],
    "child_receipts": [child],
    "emitted_events": emitted_events,
}, sort_keys=True))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def _predicate_worker(tmp_path: Path) -> Path:
    path = tmp_path / "predicate_worker.py"
    path.write_text(
        """
import json
import os
from pathlib import Path

stage = os.environ["LIMEN_GOV_STAGE"]
run_root = Path(os.environ["LIMEN_GOV_RUN_ROOT"])
if os.environ.get("LIMEN_GOV_PREDICATE_MODE") != "1":
    raise SystemExit(31)
counter_path = run_root / "predicate-executions.json"
counter = json.loads(counter_path.read_text()) if counter_path.exists() else {}
counter[stage] = counter.get(stage, 0) + 1
counter_path.write_text(json.dumps(counter, sort_keys=True))
predicate_failure = run_root / "fail-predicate-stage"
if predicate_failure.exists() and predicate_failure.read_text().strip() == stage:
    raise SystemExit(19)
predicate_mutation = run_root / "mutate-predicate-stage"
if predicate_mutation.exists() and predicate_mutation.read_text().strip() == stage:
    output = run_root / "artifacts" / f"{stage}.json"
    output.write_text('{"mutated_by_predicate":true}')
raise SystemExit(0)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def _schema_catalog(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "schemas"
    root.mkdir(exist_ok=True)
    contracts = {
        "governance-stage-receipt.v1": "governance-stage-receipt.v1.schema.json",
        "governance-snapshot-bundle.v1": "governance-snapshot-bundle.v1.schema.json",
    }
    required = {
        "governance-stage-receipt.v1": [
            "contract_name",
            "contract_version",
            "stage_receipt_id",
            "receipt_digest",
        ],
        "governance-snapshot-bundle.v1": [
            "contract_name",
            "contract_version",
            "bundle_id",
            "governance_stage_receipts",
            "governance_cadence_receipts",
            "post_proof_idempotence",
            "readiness",
            "bundle_digest",
        ],
    }
    for contract_name, filename in contracts.items():
        (root / filename).write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": required[contract_name],
                    "properties": {
                        "contract_name": {"const": contract_name},
                        "contract_version": {"const": 1},
                    },
                    "additionalProperties": True,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return {"root": str(root), "contracts": contracts}


def _execution_policy(module, tmp_path: Path) -> dict[str, object]:
    scratch_root = tmp_path
    mount_point = scratch_root
    while not module.os.path.ismount(mount_point):
        mount_point = mount_point.parent
    receipt_payload = {
        "contract_name": module.SCRATCH_RECEIPT_CONTRACT,
        "contract_version": 1,
        "owner_reference": module.SCRATCH_OWNER_REFERENCE,
        "scratch_root_digest": module.digest_value({"scratch_root": str(scratch_root.resolve())}),
        "mount_point_digest": module.digest_value({"mount_point": str(mount_point.resolve())}),
        "device_id": scratch_root.stat().st_dev,
        "mount_status": "mounted",
        "backup_status": "excluded",
        "verification_status": "verified",
        "verification_predicate": "predicate:domus-non-backed-scratch",
    }
    receipt = {
        **receipt_payload,
        "receipt_digest": module.digest_value(receipt_payload),
    }
    receipt_path = tmp_path / "domus-scratch-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    archive_root = tmp_path.parent / f"{tmp_path.name}-archive-finals"
    archive_root.mkdir(exist_ok=True)
    return {
        "max_full_attempts": 2,
        "aggregate_output_budget_bytes": 10_000_000,
        "scratch_authority": {
            "root": str(scratch_root),
            "receipt": str(receipt_path),
        },
        "final_receipt_promotion": {
            "root": str(archive_root),
            "owner_reference": "archive:governance-memory-final-receipts",
        },
    }


def _config(module, tmp_path: Path, *, fail_stage: str | None = None) -> Path:
    worker = _worker(tmp_path)
    predicate_worker = _predicate_worker(tmp_path)
    seed = tmp_path / "seed.json"
    seed.write_text('{"seed":true}\n', encoding="utf-8")
    stages = {}
    previous_stage = None
    worker_digest = module.digest_file(worker)[0]
    predicate_worker_digest = module.digest_file(predicate_worker)[0]
    for stage in module.STAGES:
        if previous_stage is None:
            inputs = [
                {
                    "artifact_id": "fixture-seed",
                    "reference": "fixture://seed",
                    "path": str(seed),
                    "contract": "fixture-seed.v1",
                    "input_kind": "snapshot_anchor",
                    "snapshot_id": "snapshot-fixture",
                    "snapshot_digest": "sha256:" + "a" * 64,
                }
            ]
        else:
            inputs = [
                {
                    "artifact_id": f"{previous_stage}-output",
                    "reference": f"fixture://outputs/{previous_stage}",
                    "path": f"run/artifacts/{previous_stage}.json",
                    "contract": f"{previous_stage}-fixture.v1",
                    "input_kind": "predecessor_output",
                }
            ]
        stages[stage] = {
            "owner_reference": f"owner:{stage}",
            "owner_revision": {
                "kind": "file",
                "path": str(worker),
                "digest": worker_digest,
            },
            "predicate": {
                "predicate_id": f"predicate:{stage}",
                "command": [sys.executable, str(predicate_worker)],
                "receipt_command": f"predicate://verify/{stage}",
                "expected_result": f"{stage} owner predicate passes",
                "revision": {
                    "kind": "file",
                    "path": str(predicate_worker),
                    "digest": predicate_worker_digest,
                },
            },
            "receipt_target": f"receipt:{stage}",
            "cwd": str(tmp_path),
            "command": [sys.executable, str(worker)],
            "env": ({"FIXTURE_FAIL_STAGE": fail_stage} if fail_stage else {}),
            "inputs": inputs,
            "outputs": [
                {
                    "artifact_id": f"{stage}-output",
                    "reference": f"fixture://outputs/{stage}",
                    "path": f"artifacts/{stage}.json",
                    "contract": (module.PRE_PROOF_BUNDLE_CONTRACT if stage == "receipt" else f"{stage}-fixture.v1"),
                }
            ],
            "readiness_evidence": {
                "artifact_id": f"{stage}-output",
            },
            "execution_profile": {
                "max_items": 10,
                "timeout_seconds": 5,
                "max_attempts": 1,
                "max_log_bytes": 100_000,
                "max_artifact_bytes": 100_000,
            },
        }
        previous_stage = stage
    path = tmp_path / "cadence.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "contract_name": "governance-cadence-config.v1",
                "cadence_id": "fixture-cadence",
                "owner_reference": "owner:governance-cadence",
                "snapshot_digest": "sha256:" + "a" * 64,
                "execution_policy": _execution_policy(module, tmp_path),
                "schema_catalog": _schema_catalog(tmp_path),
                "stages": stages,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _write_repair_receipt(
    module,
    *,
    config: Path,
    run_root: Path,
) -> None:
    (
        _public_config,
        stages,
        config_digest,
        snapshot_digest,
        _owner_reference,
        _policy,
    ) = module.load_config(
        config,
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        run_root=run_root,
    )
    ledger = json.loads(module.attempt_ledger_path(run_root).read_text())
    failure = ledger["attempts"][-1]
    spec = next(item for item in stages if item.stage == failure["failure_stage"])
    payload = {
        "contract_name": module.REPAIR_RECEIPT_CONTRACT,
        "contract_version": 1,
        "snapshot_id": "snapshot-fixture",
        "snapshot_digest": snapshot_digest,
        "config_digest": config_digest,
        "stage": spec.stage,
        "owner_reference": spec.owner_reference,
        "owner_revision": spec.owner_revision.value,
        "predicate": spec.predicate.public(),
        "predicate_revision": spec.predicate.revision.value,
        "prior_failure_digest": failure["failure_digest"],
        "status": "verified",
    }
    receipt = {**payload, "receipt_digest": module.digest_value(payload)}
    path = module.repair_receipt_path(run_root, spec.stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_complete_run_reaches_two_run_proof_then_byte_fixed_point(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_fixed_point")
    config = _config(module, tmp_path)
    run_root = tmp_path / "run"

    first, first_stats = module.run_cadence(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=run_root,
    )
    before = {
        path.relative_to(run_root): path.read_bytes()
        for path in sorted(run_root.rglob("*.json"))
        if path.name not in {"executions.json", "predicate-executions.json"}
    }
    second, second_stats = module.run_cadence(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=run_root,
    )
    after = {
        path.relative_to(run_root): path.read_bytes()
        for path in sorted(run_root.rglob("*.json"))
        if path.name not in {"executions.json", "predicate-executions.json"}
    }

    run_one = json.loads((run_root / "receipts" / "governance-cadence-receipt.run-1.v1.json").read_text())
    assert first["run_number"] == 2
    assert first["fixed_point"]["status"] == "proven"
    assert first["previous_cadence_receipt_digest"] == run_one["receipt_digest"]
    assert first["output_digest"] == run_one["output_digest"]
    assert run_one["readiness"]["exact_all"] is False
    assert run_one["readiness"]["ready"] is False
    assert run_one["readiness"]["status"] == "incomplete"
    assert "cadence:run-two-fixed-point-proof" in run_one["readiness"]["missing_requirements"]
    assert first["readiness"]["exact_all"] is True
    assert first["readiness"]["ready"] is True
    assert run_one["fixed_point"]["previous_output_digest"] is None
    assert first["fixed_point"]["previous_output_digest"] == run_one["output_digest"]
    assert first == second
    assert before == after
    assert len(first["stage_receipts"]) == 9
    assert first_stats.run_one.invoked_stages == module.STAGES
    assert first_stats.run_one.executed_stages == module.STAGES
    assert first_stats.run_one.new_events == 1
    assert first_stats.run_two.invoked_stages == module.STAGES
    assert first_stats.run_two.executed_stages == ()
    assert first_stats.run_two.skipped_stages == module.STAGES
    assert first_stats.run_two.new_events == 0
    assert first_stats.run_two.changed_receipts == 0
    assert first_stats.run_two.replayed_completed_children == 0
    assert first_stats.aggregate_receipts_written == 4
    assert second_stats.run_one.invoked_stages == ()
    assert second_stats.run_one.executed_stages == ()
    assert second_stats.run_two.invoked_stages == module.STAGES
    assert second_stats.run_two.executed_stages == ()
    assert second_stats.aggregate_receipts_written == 0
    assert module.post_proof_idempotence(second, second_stats) == {
        "probe_id": f"{second['cadence_receipt_id']}:idempotence",
        "invoked_at": "2026-07-16T00:00:00Z",
        "cadence_receipt_digest": second["receipt_digest"],
        "output_digest": second["output_digest"],
        "status": "proven",
        "new_event_count": 0,
        "changed_byte_count": 0,
        "replayed_completed_children": 0,
        "emitted_receipt_count": 0,
    }
    assert json.loads((run_root / "executions.json").read_text()) == {stage: 3 for stage in module.STAGES}
    assert json.loads((run_root / "predicate-executions.json").read_text()) == {stage: 3 for stage in module.STAGES}


def test_exact_second_invocation_changes_no_governed_output_or_receipt(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_cadence_strict_cli")
    config = _config(module, tmp_path)
    run_root = tmp_path / "run"

    args = [
        "--snapshot-id",
        "snapshot-fixture",
        "--snapshot-at",
        "2026-07-16T00:00:00Z",
        "--config",
        str(config),
        "--run-root",
        str(run_root),
        "--strict",
        "--write",
    ]
    assert module.main(args) == 1
    governed_paths = [
        *sorted((run_root / "artifacts").glob("*.json")),
        *sorted((run_root / "receipts").glob("*.json")),
        run_root / "governance-stage-receipts.v1.json",
        run_root / "governance-cadence-receipts.v1.json",
    ]
    before = {path.relative_to(run_root): path.read_bytes() for path in governed_paths}
    assert module.main(args) == 0
    after = {path.relative_to(run_root): path.read_bytes() for path in governed_paths}
    assert before == after
    run_two = json.loads((run_root / "receipts" / "governance-cadence-receipt.run-2.v1.json").read_text())
    run_one = json.loads((run_root / "receipts" / "governance-cadence-receipt.run-1.v1.json").read_text())
    assert run_two["fixed_point"]["status"] == "proven"
    assert run_two["fixed_point"]["new_event_count"] == 0
    assert run_two["fixed_point"]["changed_byte_count"] == 0
    assert run_two["fixed_point"]["replayed_completed_children"] == 0
    assert run_one["fixed_point"]["previous_output_digest"] is None
    assert run_two["fixed_point"]["previous_output_digest"] == run_one["output_digest"]
    assert run_one["readiness"]["exact_all"] is False
    assert run_one["readiness"]["ready"] is False
    assert run_two["readiness"]["exact_all"] is True
    assert run_two["readiness"]["ready"] is True
    assert (run_root / "post-proof-idempotence.v1.json").is_file()
    stage_collection = json.loads((run_root / "governance-stage-receipts.v1.json").read_text())
    assert stage_collection == [json.loads(module.receipt_path(run_root, stage).read_text()) for stage in module.STAGES]
    assert json.loads((run_root / "stage-receipt-targets.json").read_text()) == {
        stage: str(run_root / "governance-stage-receipts.v1.json") for stage in module.STAGES
    }
    bundle_path = run_root / "governance-snapshot-bundle.v1.json"
    bundle = json.loads(bundle_path.read_text())
    assert bundle["contract_name"] == "governance-snapshot-bundle.v1"
    assert bundle["governance_stage_receipts"] == [
        {
            "contract_name": "governance-stage-receipt.v1",
            "stage": item["stage"],
            "receipt_id": item["stage_receipt_id"],
            "reference": item["receipt_target"],
            "snapshot_id": "snapshot-fixture",
            "digest": item["receipt_digest"],
            "status": item["status"],
        }
        for item in stage_collection
    ]
    assert [item["run_number"] for item in bundle["governance_cadence_receipts"]] == [
        1,
        2,
    ]
    assert bundle["governance_cadence_receipts"][0]["ready"] is False
    assert bundle["governance_cadence_receipts"][1]["ready"] is True
    assert bundle["readiness"] == run_two["readiness"]
    assert bundle["post_proof_idempotence"] == json.loads((run_root / "post-proof-idempotence.v1.json").read_text())
    assert bundle["bundle_digest"] == module.digest_value(
        {key: value for key, value in bundle.items() if key != "bundle_digest"}
    )
    bundle_before = bundle_path.read_bytes()
    assert module.main(args) == 0
    assert bundle_path.read_bytes() == bundle_before
    assert json.loads((run_root / "executions.json").read_text()) == {stage: 4 for stage in module.STAGES}
    assert json.loads((run_root / "predicate-executions.json").read_text()) == {stage: 4 for stage in module.STAGES}


def test_run_two_readiness_is_derived_from_owner_debt(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_owner_debt")
    config = _config(module, tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "owner-debt-stage").write_text("classify", encoding="utf-8")

    run_two, _stats = module.run_cadence(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=run_root,
    )
    run_one = json.loads((run_root / "receipts" / "governance-cadence-receipt.run-1.v1.json").read_text())

    assert run_one["readiness"]["exact_all"] is False
    assert run_one["readiness"]["ready"] is False
    assert run_two["fixed_point"]["status"] == "proven"
    assert run_two["readiness"] == {
        "exact_all": True,
        "unresolved_blockers": ["owner:classify:blocked"],
        "quarantines": [],
        "missing_requirements": [],
        "citation_debt": [],
        "incomplete_predicates": [],
        "ready": False,
        "status": "blocked",
    }


def test_blocked_fixed_point_is_sealed_without_becoming_ready(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_blocked_fixed_point")
    config = _config(module, tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "owner-debt-stage").write_text("classify", encoding="utf-8")
    args = [
        "--snapshot-id",
        "snapshot-fixture",
        "--snapshot-at",
        "2026-07-16T00:00:00Z",
        "--config",
        str(config),
        "--run-root",
        str(run_root),
        "--strict",
        "--write",
    ]

    assert module.main(args) == 1
    assert module.main(args) == 1
    post_proof = run_root / "post-proof-idempotence.v1.json"
    bundle_path = run_root / "governance-snapshot-bundle.v1.json"
    assert post_proof.is_file()
    bundle = json.loads(bundle_path.read_text())
    assert bundle["post_proof_idempotence"]["status"] == "proven"
    assert bundle["readiness"]["ready"] is False
    assert bundle["readiness"]["status"] == "blocked"
    assert bundle["readiness"]["unresolved_blockers"] == ["owner:classify:blocked"]

    before = {
        path.relative_to(run_root): path.read_bytes()
        for path in sorted(run_root.rglob("*.json"))
        if path.name not in {"executions.json", "predicate-executions.json"}
    }
    assert module.main(args) == 1
    after = {
        path.relative_to(run_root): path.read_bytes()
        for path in sorted(run_root.rglob("*.json"))
        if path.name not in {"executions.json", "predicate-executions.json"}
    }
    assert after == before


def test_resume_skips_completed_predecessors_after_interruption(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_resume")
    config = _config(module, tmp_path, fail_stage="classify")
    run_root = tmp_path / "run"

    with pytest.raises(module.CadenceError, match="stage classify failed"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )
    first_counts = json.loads((run_root / "executions.json").read_text())
    assert first_counts == {"classify": 1, "discover": 1, "parse": 1, "snapshot": 1}

    (run_root / "allow-failed-stage").write_text("continue", encoding="utf-8")
    with pytest.raises(module.CadenceError, match="verified repair receipt"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )
    _write_repair_receipt(
        module,
        config=config,
        run_root=run_root,
    )
    _, stats = module.run_cadence(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=run_root,
    )
    second_counts = json.loads((run_root / "executions.json").read_text())

    assert stats.run_one.skipped_stages == ("discover", "snapshot", "parse")
    assert stats.run_one.invoked_stages == module.STAGES[3:]
    assert stats.run_one.executed_stages == module.STAGES[3:]
    assert stats.run_two.skipped_stages == module.STAGES
    assert stats.run_two.invoked_stages == module.STAGES
    assert stats.run_two.executed_stages == ()
    assert second_counts["discover"] == 2
    assert second_counts["snapshot"] == 2
    assert second_counts["parse"] == 2
    assert second_counts["classify"] == 3
    assert all(second_counts[stage] == 2 for stage in module.STAGES if stage != "classify")


def test_incomplete_stage_set_fails_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_missing")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    document["stages"].pop("validate")
    config.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(module.CadenceError, match="stages must be exact"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_unbounded_profile_and_outside_output_fail_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_bounds")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    document["stages"]["discover"]["execution_profile"]["timeout_seconds"] = 0
    config.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(module.CadenceError, match="timeout_seconds"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )

    document["stages"]["discover"]["execution_profile"]["timeout_seconds"] = 5
    document["stages"]["discover"]["outputs"][0]["path"] = "../escape.json"
    config.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(module.CadenceError, match="output must remain under"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_tampered_output_replays_only_changed_stage_when_digest_is_restored(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_tamper")
    config = _config(module, tmp_path)
    run_root = tmp_path / "run"
    module.run_cadence(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=run_root,
    )
    (run_root / "artifacts" / "reconcile.json").write_text("tampered", encoding="utf-8")

    _, stats = module.run_cadence(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=run_root,
    )

    assert stats.run_one.executed_stages == ("reconcile",)
    assert stats.run_one.skipped_stages == (*module.STAGES[:4], *module.STAGES[5:])
    assert stats.run_two.invoked_stages == module.STAGES
    assert stats.run_two.executed_stages == ()
    assert stats.run_two.skipped_stages == module.STAGES


def test_predicate_is_executable_and_failure_invalidates_prior_claim(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_predicate")
    config = _config(module, tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "fail-predicate-stage").write_text("discover", encoding="utf-8")

    with pytest.raises(module.CadenceError, match="stage discover failed"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )

    invalidated = json.loads((run_root / "governance-cadence-receipts.v1.json").read_text())
    assert invalidated["contract_name"] == "governance-cadence-invalidated.v1"
    assert (run_root / "governance-cadence-invalidated.v1.json").is_file()


def test_stale_proof_is_invalidated_when_second_owner_traversal_fails(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_stale_proof")
    config = _config(module, tmp_path)
    run_root = tmp_path / "run"
    args = [
        "--snapshot-id",
        "snapshot-fixture",
        "--snapshot-at",
        "2026-07-16T00:00:00Z",
        "--config",
        str(config),
        "--run-root",
        str(run_root),
        "--strict",
        "--write",
    ]
    assert module.main(args) == 1
    assert module.main(args) == 0
    assert (run_root / "post-proof-idempotence.v1.json").is_file()
    (run_root / "fail-proof-stage").write_text("classify", encoding="utf-8")

    with pytest.raises(module.CadenceError, match="stage classify proof failed"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )

    invalidated = json.loads((run_root / "governance-cadence-receipts.v1.json").read_text())
    assert invalidated["contract_name"] == "governance-cadence-invalidated.v1"
    assert not (run_root / "post-proof-idempotence.v1.json").exists()
    assert not (run_root / "governance-cadence-active.v1.json").exists()


def test_stage_retry_profile_above_one_fails_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_no_stage_retries")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    document["stages"]["reconcile"]["execution_profile"]["max_attempts"] = 3
    config.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(module.CadenceError, match="max_attempts"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_stage_dataflow_must_consume_exact_predecessor_output(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_dataflow")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    document["stages"]["snapshot"]["inputs"] = document["stages"]["discover"]["inputs"]
    config.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(module.CadenceError, match="must exactly cover every output"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_extra_inputs_must_be_typed_and_snapshot_bound(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_external_anchor")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    document["stages"]["snapshot"]["inputs"].append(
        {
            "artifact_id": "snapshot-external-anchor",
            "reference": "fixture://snapshot/external-anchor",
            "path": str(tmp_path / "seed.json"),
            "contract": "fixture-anchor.v1",
            "input_kind": "snapshot_anchor",
            "snapshot_id": "snapshot-fixture",
            "snapshot_digest": "sha256:" + "a" * 64,
        }
    )
    config.write_text(yaml.safe_dump(document), encoding="utf-8")

    validated = module.validate_only(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=tmp_path / "run",
    )
    assert validated["status"] == "validated"

    document["stages"]["snapshot"]["inputs"][-1]["snapshot_digest"] = "sha256:" + "b" * 64
    config.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(module.CadenceError, match="exact frozen snapshot"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )

    for field in ("snapshot_digest", "snapshot_id", "input_kind"):
        document["stages"]["snapshot"]["inputs"][-1].pop(field, None)
    config.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(module.CadenceError, match="input_kind"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_public_receipt_references_reject_paths_and_sensitive_literals(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_public_references")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    document["stages"]["discover"]["receipt_target"] = "/Users/example/private/receipt.json"
    config.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(module.CadenceError, match="public-safe stable reference"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )
    document["stages"]["discover"]["receipt_target"] = "token:plaintext-sensitive-value"
    config.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(module.CadenceError, match="public-safe stable reference"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_owner_revision_mismatch_fails_before_execution(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_owner_revision")
    config = _config(module, tmp_path)
    (tmp_path / "worker.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    with pytest.raises(module.CadenceError, match="owner revision file does not match"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_predicate_is_independent_and_separately_revision_pinned(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_predicate_revision")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    discover = document["stages"]["discover"]
    discover["predicate"]["command"] = discover["command"]
    discover["predicate"]["revision"] = discover["owner_revision"]
    config.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(module.CadenceError, match="predicate command must be independent"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )

    config = _config(module, tmp_path)
    (tmp_path / "predicate_worker.py").write_text(
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    with pytest.raises(module.CadenceError, match="predicate revision file does not match"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_runtime_schema_catalog_fails_closed_before_stage_receipt_write(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_cadence_stage_schema")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    stage_schema = (
        Path(document["schema_catalog"]["root"])
        / document["schema_catalog"]["contracts"]["governance-stage-receipt.v1"]
    )
    schema = json.loads(stage_schema.read_text())
    schema["required"].append("schema_gate")
    stage_schema.write_text(json.dumps(schema), encoding="utf-8")
    run_root = tmp_path / "run"

    with pytest.raises(module.CadenceError, match="public schema validation failed"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )

    assert not module.receipt_path(run_root, "discover").exists()
    assert (run_root / "governance-cadence-invalidated.v1.json").is_file()


def test_unavailable_runtime_schema_catalog_fails_closed(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_missing_schema")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    document["schema_catalog"]["root"] = str(tmp_path / "missing-schema-root")
    config.write_text(yaml.safe_dump(document), encoding="utf-8")
    run_root = tmp_path / "run"

    with pytest.raises(module.CadenceError, match="available directory"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )

    assert (run_root / "governance-cadence-invalidated.v1.json").is_file()
    assert not module.receipt_path(run_root, "discover").exists()


def test_final_bundle_schema_is_runtime_configured_and_validated(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_cadence_bundle_schema")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    bundle_schema = (
        Path(document["schema_catalog"]["root"])
        / document["schema_catalog"]["contracts"]["governance-snapshot-bundle.v1"]
    )
    schema = json.loads(bundle_schema.read_text())
    schema["required"].append("seal_gate")
    bundle_schema.write_text(json.dumps(schema), encoding="utf-8")
    run_root = tmp_path / "run"
    args = [
        "--snapshot-id",
        "snapshot-fixture",
        "--snapshot-at",
        "2026-07-16T00:00:00Z",
        "--config",
        str(config),
        "--run-root",
        str(run_root),
        "--strict",
        "--write",
    ]

    assert module.main(args) == 1
    assert module.main(args) == 1
    assert not (run_root / "governance-snapshot-bundle.v1.json").exists()
    assert (run_root / "governance-cadence-invalidated.v1.json").is_file()
    assert not (run_root / "post-proof-idempotence.v1.json").exists()


def test_owner_revision_preflight_failure_invalidates_stale_success(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_owner_revision_invalidation")
    config = _config(module, tmp_path)
    run_root = tmp_path / "run"
    module.run_cadence(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=run_root,
    )
    (tmp_path / "worker.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    with pytest.raises(module.CadenceError, match="owner revision file does not match"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )

    invalidated = json.loads((run_root / "governance-cadence-receipts.v1.json").read_text())
    assert invalidated["contract_name"] == "governance-cadence-invalidated.v1"
    assert (run_root / "governance-cadence-invalidated.v1.json").is_file()


def test_output_limit_is_aggregate_across_declared_artifacts(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_aggregate_output")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    discover = document["stages"]["discover"]
    discover["outputs"].append(
        {
            **discover["outputs"][0],
            "artifact_id": "discover-output-alias",
            "reference": "fixture://outputs/discover-alias",
        }
    )
    document["stages"]["snapshot"]["inputs"].append(
        {
            **discover["outputs"][1],
            "path": "run/artifacts/discover.json",
            "input_kind": "predecessor_output",
        }
    )
    discover["execution_profile"]["max_artifact_bytes"] = 490
    config.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(module.CadenceError, match="aggregate byte limit"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_log_limit_does_not_cap_owner_artifact_files(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_separate_log_limit")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    discover = document["stages"]["discover"]
    discover["env"]["FIXTURE_ARTIFACT_PADDING"] = "4096"
    discover["execution_profile"]["max_log_bytes"] = 128
    config.write_text(yaml.safe_dump(document), encoding="utf-8")
    run_root = tmp_path / "run"

    module.run_cadence(
        snapshot_id="snapshot-fixture",
        snapshot_at="2026-07-16T00:00:00Z",
        config_path=config,
        run_root=run_root,
    )

    assert (run_root / "artifacts" / "discover.json").stat().st_size > 128
    assert (run_root / "logs" / "traversal-1" / "discover.attempt-1.log").stat().st_size <= 128


def test_log_limit_is_enforced_by_parent_owned_drain(tmp_path: Path) -> None:
    module = _load("governance_memory_cadence_parent_log_limit")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    discover = document["stages"]["discover"]
    discover["env"]["FIXTURE_LOG_BYTES"] = "4096"
    discover["execution_profile"]["max_log_bytes"] = 128
    discover["execution_profile"]["max_attempts"] = 1
    config.write_text(yaml.safe_dump(document), encoding="utf-8")
    run_root = tmp_path / "run"

    with pytest.raises(module.CadenceError, match="log-byte-limit-exceeded"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )

    assert (run_root / "logs" / "traversal-1" / "discover.attempt-1.log").stat().st_size == 128


def test_second_failed_full_attempt_exhausts_snapshot_budget(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_cadence_two_full_attempts")
    config = _config(module, tmp_path, fail_stage="classify")
    run_root = tmp_path / "run"

    with pytest.raises(module.CadenceError, match="stage classify failed"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )
    _write_repair_receipt(module, config=config, run_root=run_root)
    with pytest.raises(module.CadenceError, match="stage classify failed"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )
    before = json.loads((run_root / "executions.json").read_text())

    with pytest.raises(module.CadenceError, match="consumed its 2 full cadence attempts"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=run_root,
        )

    assert json.loads((run_root / "executions.json").read_text()) == before
    ledger = json.loads(module.attempt_ledger_path(run_root).read_text())
    assert [attempt["status"] for attempt in ledger["attempts"]] == [
        "failed",
        "failed",
    ]


def test_snapshot_wide_output_budget_counts_undeclared_intermediates(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_cadence_total_output_budget")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    document["execution_policy"]["aggregate_output_budget_bytes"] = 4_500_000
    document["stages"]["discover"]["env"]["FIXTURE_SCRATCH_BYTES"] = "5000000"
    config.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(module.CadenceError, match="aggregate output-byte budget exceeded"):
        module.run_cadence(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_scratch_authority_must_be_live_and_backup_excluded(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_cadence_scratch_authority")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    receipt_path = Path(document["execution_policy"]["scratch_authority"]["receipt"])
    receipt = json.loads(receipt_path.read_text())
    receipt["backup_status"] = "included"
    payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    receipt["receipt_digest"] = module.digest_value(payload)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(module.CadenceError, match="backup-excluded"):
        module.validate_only(
            snapshot_id="snapshot-fixture",
            snapshot_at="2026-07-16T00:00:00Z",
            config_path=config,
            run_root=tmp_path / "run",
        )


def test_final_promotion_copies_only_four_verified_receipts(
    tmp_path: Path,
) -> None:
    module = _load("governance_memory_cadence_final_promotion")
    config = _config(module, tmp_path)
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    archive_root = Path(document["execution_policy"]["final_receipt_promotion"]["root"])
    run_root = tmp_path / "run"
    args = [
        "--snapshot-id",
        "snapshot-fixture",
        "--snapshot-at",
        "2026-07-16T00:00:00Z",
        "--config",
        str(config),
        "--run-root",
        str(run_root),
        "--strict",
        "--write",
    ]

    assert module.main(args) == 1
    assert module.main(args) == 0
    assert sorted(path.name for path in archive_root.iterdir()) == sorted(module.FINAL_PROMOTION_FILENAMES)
    for filename in module.FINAL_PROMOTION_FILENAMES:
        assert module.digest_file(archive_root / filename) == module.digest_file(run_root / filename)
    assert not (archive_root / "logs").exists()
    assert not (archive_root / "artifacts").exists()
    assert not (archive_root / module.attempt_ledger_path(run_root).name).exists()
