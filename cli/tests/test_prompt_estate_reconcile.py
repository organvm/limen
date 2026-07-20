from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-estate-reconcile.py"
PRIORITY_SCRIPT = ROOT / "scripts" / "prompt-priority-map.py"
DIGEST = "a" * 64


def _source_adapter_contract() -> dict:
    path = ROOT / "cli" / "src" / "limen" / "prompt_sources.py"
    spec = importlib.util.spec_from_file_location("prompt_sources_estate_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.source_adapter_contract()


def _policy_digest() -> str:
    spec = importlib.util.spec_from_file_location("prompt_priority_policy_estate_fixture", PRIORITY_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.current_policy_digest()


def _load():
    spec = importlib.util.spec_from_file_location("prompt_estate_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _atom(atom_id: str, *, owner: str | None = None) -> dict:
    return {
        "atom_id": atom_id,
        "kind": "ask",
        "authority": "operator",
        "priority_score": 80.0,
        "priority_reasons": ["system_leverage"],
        "dimensions": {"system_leverage": 1.0},
        "outcome": {
            "disposition": "unassessed",
            "owner": owner,
            "owner_route": "TABVLARIVS/prompt-control" if owner else None,
        },
        "is_current_intent": True,
    }


def _projection(atoms: list[dict], *, scope: str = "all") -> dict:
    payload = {
        "version": 1,
        "semantic_digest": DIGEST,
        "policy_digest": _policy_digest(),
        "source_cursor_digest": "c" * 64,
        "source_scope": {
            "scanner_version": _source_adapter_contract()["scanner_version"],
            "scope": scope,
            "target_scope": "all",
            "all_baseline_complete": True,
            "all_source_manifest_digest": "d" * 64,
            "pending_files": 0,
            "source_error_count": 0,
            "source_unit_count": 1,
            "source_units_digest": hashlib.sha256(b'["fixture"]').hexdigest(),
            "unsupported_source_count": 0,
            "unsupported_units_digest": hashlib.sha256(b"{}").hexdigest(),
            "unresolved_unit_count": 0,
            "unresolved_units_digest": hashlib.sha256(b"[]").hexdigest(),
            "source_manifest_digest": "d" * 64,
            "source_adapter_contract": _source_adapter_contract(),
            "excluded_source_count": 0,
            "source_exclusion_counts": {},
            "excluded_unit_receipts_digest": hashlib.sha256(b"{}").hexdigest(),
            "adapted_source_count": 0,
            "source_adapter_counts": {},
            "adapted_unit_receipts_digest": hashlib.sha256(b"{}").hexdigest(),
            "adapter_gaps": [],
            "adapter_gap_routes": [],
        },
        "coverage": {
            "atoms": len(atoms),
            "current_intents": sum(1 for atom in atoms if atom.get("is_current_intent", True)),
            "current_unresolved_atoms": sum(
                1
                for atom in atoms
                if atom.get("is_current_intent", True)
                and str((atom.get("outcome") or {}).get("disposition") or "unassessed") not in {"done", "superseded"}
            ),
        },
        "counts": {
            "dispositions": {"unassessed": len(atoms)},
            "kinds": {"ask": len(atoms)},
        },
        "validation": {"ok": True, "errors": []},
        "atoms": atoms,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    payload["projection_digest"] = hashlib.sha256(encoded).hexdigest()
    return payload


def _write_inputs(
    tmp_path: Path,
    *,
    atoms: list[dict],
    tasks: list[dict],
    scope: str = "all",
) -> tuple[Path, Path]:
    projection = tmp_path / "prompt-atoms.json"
    payload = _projection(atoms, scope=scope)
    projection.write_text(json.dumps(payload), encoding="utf-8")
    receipt = projection.with_suffix(".check.json")
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "prompt_atom_projection_check",
                "checker": "limen.prompt_corpus.check_ledger",
                "result": "pass",
                "projection_digest": payload["projection_digest"],
                "projection_file_sha256": hashlib.sha256(projection.read_bytes()).hexdigest(),
                "semantic_digest": payload["semantic_digest"],
                "policy_digest": payload["policy_digest"],
                "source_cursor_digest": payload["source_cursor_digest"],
            }
        ),
        encoding="utf-8",
    )
    receipt.chmod(0o600)
    board = tmp_path / "tasks.yaml"
    board.write_text(yaml.safe_dump({"version": "1.0", "tasks": tasks}), encoding="utf-8")
    return projection, board


def _build(
    module,
    *,
    projection: Path,
    board: Path,
    prs: list[dict] | None = None,
    worktrees: str = "",
):
    return module.build_reconciliation(
        projection_path=projection,
        tasks_path=board,
        open_prs=prs or [],
        open_prs_digest="e" * 64,
        open_prs_source="fixture",
        worktrees=module.parse_worktree_porcelain(worktrees),
        worktrees_digest="f" * 64,
        worktrees_source="fixture",
        repository_owner="organvm/limen",
        projection_check_receipt=projection.with_suffix(".check.json"),
        generated_at="2026-07-11T12:00:00+00:00",
    )


def _by_atom(snapshot: dict) -> dict[str, dict]:
    return {row["atom_id"]: row for row in snapshot["atom_reconciliation"]}


def _owner_links(path: Path, links: list[dict]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "limen.estate_session_review_owner_links.v1",
                "links": links,
            }
        ),
        encoding="utf-8",
    )
    return path


def _owner_link(atom_id: str, **over) -> dict:
    row = {
        "prompt_atom_id": atom_id,
        "owner_type": "task",
        "canonical_owner_reference": f"task:{atom_id}",
        "predicate": "python3 scripts/check-owner.py",
        "receipt_target": f"github:organvm/limen:task:{atom_id}",
        "disposition": "durably_homed_open",
        "content_bindings": [f"binding:{atom_id}"],
    }
    row.update(over)
    return row


def test_reuses_one_existing_task_receipt_without_duplicate_minting(tmp_path: Path):
    module = _load()
    projection, board = _write_inputs(
        tmp_path,
        atoms=[_atom("pa-existing")],
        tasks=[
            {
                "id": "TASK-existing",
                "repo": "organvm/limen",
                "target_agent": "codex",
                "status": "open",
                "context": "Own pa-existing; receipt repeats pa-existing.",
                "labels": ["pa-existing"],
            }
        ],
    )
    board_before = board.read_bytes()

    snapshot = _build(module, projection=projection, board=board)

    row = _by_atom(snapshot)["pa-existing"]
    assert row["receipt_count"] == 1
    assert row["owner_receipts"][0]["receipts"][0]["receipt_id"] == "task:TASK-existing"
    assert row["unmatched"] is False
    assert snapshot["control"]["estate_mutations"] == 0
    assert snapshot["control"]["private_check"]["result"] == "pass"
    assert snapshot["coverage"]["matched_atom_ids"] == 1
    assert board.read_bytes() == board_before


def test_owner_link_index_requires_exactly_one_row_per_atom(tmp_path: Path):
    module = _load()
    path = _owner_links(
        tmp_path / "links.json",
        [_owner_link("pa-one"), _owner_link("pa-one")],
    )

    with pytest.raises(module.EstateReconciliationError, match="duplicate owner link"):
        module.load_owner_links(path, atom_ids={"pa-one"})

    missing = _owner_links(tmp_path / "missing.json", [_owner_link("pa-one")])
    with pytest.raises(module.EstateReconciliationError, match="not exhaustive"):
        module.load_owner_links(missing, atom_ids={"pa-one", "pa-two"})


def test_owner_link_index_accepts_separate_review_ask_rows(tmp_path: Path):
    module = _load()
    prompt_row = _owner_link("pa-one")
    review_row = _owner_link("unused")
    review_row.pop("prompt_atom_id")
    review_row["review_ask_id"] = "ask-copilot-deadbeef"
    review_row["canonical_owner_reference"] = "pull_request:organvm/limen#7"
    review_row["receipt_target"] = "github:organvm/limen:pull-request:7"
    path = _owner_links(tmp_path / "links.json", [prompt_row, review_row])

    loaded, _digest = module.load_owner_links(path, atom_ids={"pa-one"})

    assert set(loaded) == {"pa-one", "ask-copilot-deadbeef"}


def test_blocked_owner_link_requires_failed_gate_and_next_command(tmp_path: Path):
    module = _load()
    path = _owner_links(
        tmp_path / "links.json",
        [
            _owner_link(
                "pa-blocked",
                disposition="blocked",
                owner_type="blocker",
            )
        ],
    )

    with pytest.raises(module.EstateReconciliationError, match="failed gate or next command"):
        module.load_owner_links(path, atom_ids={"pa-blocked"})


def test_conflicting_receipt_claims_are_rejected(tmp_path: Path):
    module = _load()
    shared = "github:organvm/limen:pull-request:839"
    path = _owner_links(
        tmp_path / "links.json",
        [
            _owner_link("pa-one", receipt_target=shared),
            _owner_link(
                "pa-two",
                receipt_target=shared,
                canonical_owner_reference="task:other-owner",
            ),
        ],
    )

    with pytest.raises(module.EstateReconciliationError, match="conflicting receipt"):
        module.load_owner_links(path, atom_ids={"pa-one", "pa-two"})


def test_verified_owner_link_requires_timestamped_exact_head_proof(tmp_path: Path):
    module = _load()
    path = _owner_links(
        tmp_path / "links.json",
        [_owner_link("pa-done", disposition="verified_done")],
    )

    with pytest.raises(module.EstateReconciliationError, match="exact predicate proof"):
        module.load_owner_links(path, atom_ids={"pa-done"})

    complete = _owner_links(
        tmp_path / "complete.json",
        [
            _owner_link(
                "pa-done",
                disposition="verified_done",
                predicate_result={"passed": True},
                predicate_checked_at="2026-07-19T15:00:00Z",
                receipt_head_sha="a" * 40,
            )
        ],
    )
    loaded, _digest = module.load_owner_links(complete, atom_ids={"pa-done"})
    assert loaded["pa-done"]["disposition"] == "verified_done"


def test_projection_requires_hash_matched_private_core_check(tmp_path: Path):
    module = _load()
    projection, board = _write_inputs(
        tmp_path,
        atoms=[_atom("pa-verified")],
        tasks=[],
    )
    receipt = projection.with_suffix(".check.json")
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["projection_file_sha256"] = "0" * 64
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    receipt.chmod(0o600)

    with pytest.raises(module.EstateReconciliationError, match="does not match projection"):
        _build(module, projection=projection, board=board)


def test_exact_atom_id_matching_rejects_substrings_across_estate_surfaces(tmp_path: Path):
    module = _load()
    projection, board = _write_inputs(
        tmp_path,
        atoms=[_atom("pa-one"), _atom("pa-one-more"), _atom("pa-unmatched")],
        tasks=[
            {
                "id": "TASK-long",
                "repo": "organvm/limen",
                "target_agent": "codex",
                "status": "open",
                "context": "Exact pa-one-more, but prefixpa-one and pa-one-suffix are not pa-one.",
            }
        ],
    )
    prs = [
        {
            "number": 77,
            "url": "https://github.com/organvm/limen/pull/77",
            "state": "OPEN",
            "title": "Only pa-one-ish is present",
        }
    ]
    worktrees = "\n".join(
        [
            "worktree /tmp/private-root",
            f"HEAD {'1' * 40}",
            "branch refs/heads/pa-one",
            "",
        ]
    )

    snapshot = _build(
        module,
        projection=projection,
        board=board,
        prs=prs,
        worktrees=worktrees,
    )
    rows = _by_atom(snapshot)

    assert rows["pa-one"]["owner_receipts"][0]["receipts"][0]["surface"] == "worktree"
    assert rows["pa-one-more"]["owner_receipts"][0]["receipts"][0]["surface"] == "task"
    assert rows["pa-unmatched"]["unmatched"] is True
    assert rows["pa-unmatched"]["owner_receipts"] == []
    assert snapshot["unmatched_atom_ids"] == ["pa-unmatched"]


@pytest.mark.parametrize("authority", ["partial", "legacy"])
def test_partial_and_legacy_projection_authority_fail_closed(
    tmp_path: Path,
    authority: str,
):
    module = _load()
    projection, board = _write_inputs(
        tmp_path,
        atoms=[_atom("pa-one")],
        tasks=[],
        scope="partial:all" if authority == "partial" else "all",
    )
    if authority == "legacy":
        payload = json.loads(projection.read_text(encoding="utf-8"))
        payload["authority"] = "legacy_session_batch"
        projection.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        module.EstateReconciliationError,
        match="exact all/all|legacy or foreign",
    ):
        _build(module, projection=projection, board=board)


def test_outputs_are_redacted_complete_and_report_live_counts(tmp_path: Path):
    module = _load()
    secret = "CLIENT_SECRET_PROMPT_DO_NOT_PUBLISH"
    projection, board = _write_inputs(
        tmp_path,
        atoms=[
            {**_atom("pa-redacted", owner="organvm/limen"), "intent": secret},
            _atom("pa-no-owner"),
        ],
        tasks=[
            {
                "id": "TASK-redacted",
                "repo": "organvm/limen",
                "target_agent": "codex",
                "status": "open",
                "title": secret,
                "context": f"{secret} pa-redacted /Users/alice/PrivateClient",
            },
            {
                "id": "TASK-human",
                "repo": "other/repo",
                "target_agent": "claude",
                "status": "needs_human",
                "context": "unrelated human gate",
            },
        ],
    )
    prs = [
        {
            "number": 81,
            "url": "https://github.com/other/repo/pull/81",
            "state": "OPEN",
            "title": secret,
            "body": f"{secret} pa-redacted anthony@example.com",
        },
        {
            "number": 82,
            "url": "https://github.com/other/repo/pull/82",
            "state": "CLOSED",
            "body": "pa-no-owner",
        },
    ]
    worktrees = "\n".join(
        [
            f"worktree /Users/alice/{secret}/pa-redacted",
            f"HEAD {'2' * 40}",
            f"branch refs/heads/{secret}",
            "",
            "worktree /tmp/prunable-pa-no-owner",
            f"HEAD {'3' * 40}",
            "branch refs/heads/stale",
            "prunable gitdir file points to non-existent location",
            "",
        ]
    )

    snapshot = _build(
        module,
        projection=projection,
        board=board,
        prs=prs,
        worktrees=worktrees,
    )
    markdown = module.render_markdown(snapshot)
    serialized = json.dumps(snapshot, sort_keys=True)
    row = _by_atom(snapshot)["pa-redacted"]

    assert secret not in serialized
    assert secret not in markdown
    assert "/Users/alice" not in serialized
    assert "anthony@example.com" not in serialized
    assert "pa-redacted" in markdown
    assert "pa-no-owner" in markdown
    assert row["duplicate_owner_conflict"] is True
    assert snapshot["coverage"]["duplicate_owner_conflicts"] == 1
    assert snapshot["live_counts"] == {
        "open_tasks": 1,
        "needs_human": 1,
        "open_prs": 1,
        "retained_worktrees": 1,
    }
    assert snapshot["control"]["matching"] == "exact_atom_id_only"
    assert snapshot["control"]["legacy_authority_accepted"] is False
    assert snapshot["unmatched_atom_ids"] == ["pa-no-owner"]
