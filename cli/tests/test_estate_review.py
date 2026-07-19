from __future__ import annotations

import datetime as dt
import copy
import json
from pathlib import Path

from click.testing import CliRunner

from limen.cli import main
from limen.estate_review.config import ReviewConfig, derive_windows
from limen.estate_review.model import (
    UTC,
    canonical_repository,
    canonicalize_sessions,
    claude_identity,
    classify_receipt,
    cumulative_delta,
    event_executor_role,
    native_metric,
    semantic_receipt_link,
    session_role_counts,
)
from limen.estate_review.pipeline import (
    _finalize_reconciliation_state,
    _owner_link_summary,
)
from limen.estate_review import reconcile
from limen.estate_review.reconcile import copilot_ask_id, estate_census
from limen.estate_review.render import build_artifact, validate_artifact_contract
from limen.estate_review.render import stable_json
from limen.estate_review.sources import (
    NativeCollectors,
    _canonical_digest,
    _session_ref_hash,
    collect_prompt_atoms,
)


def t(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def test_windows_follow_america_new_york_calendar_rules() -> None:
    completed, rolling = derive_windows(t("2026-07-19T15:11:00Z"))

    assert completed.start == t("2026-07-06T04:00:00Z")
    assert completed.end == t("2026-07-13T04:00:00Z")
    assert rolling.start == t("2026-07-12T15:11:00Z")
    assert rolling.end == t("2026-07-19T15:11:00Z")


def test_codex_pre_window_cumulative_baseline_emits_only_in_window_delta(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    output = root / "report"
    output.mkdir(parents=True)
    home = tmp_path / "home"
    session = home / ".codex" / "sessions" / "2026" / "07" / "one.jsonl"
    session.parent.mkdir(parents=True)
    rows = [
        {
            "timestamp": "2026-07-06T03:00:00Z",
            "type": "session_meta",
            "payload": {"id": "native-one"},
        },
        {
            "timestamp": "2026-07-06T03:30:00Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 20,
                        "output_tokens": 10,
                    }
                },
            },
        },
        {
            "timestamp": "2026-07-06T04:30:00Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 140,
                        "cached_input_tokens": 30,
                        "output_tokens": 18,
                    }
                },
            },
        },
    ]
    session.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    config = ReviewConfig.from_values(
        root=root,
        snapshot_at="2026-07-19T15:11:00Z",
        output_dir=output,
    )

    fragments, _coverage = NativeCollectors(config, home=home).codex()
    event = fragments[0]["token_events"][0]["components"]

    assert event == {
        "uncached_input_tokens": 30,
        "output_tokens": 8,
        "reasoning_output_tokens": 0,
        "cached_input_tokens": 10,
    }


def test_cumulative_token_reset_uses_new_meter_as_delta() -> None:
    assert cumulative_delta(
        {"input_tokens": 7, "output_tokens": 3},
        {"input_tokens": 120, "output_tokens": 80},
    ) == {"input_tokens": 7, "output_tokens": 3}


def test_historical_check_must_complete_by_snapshot() -> None:
    base = {
        "created_at": "2026-07-17T10:00:00Z",
        "merged_at": "2026-07-17T11:00:00Z",
        "base_ref": "main",
        "default_branch": "main",
        "commits": [{"committed_at": "2026-07-17T10:05:00Z"}],
    }
    before = {
        **base,
        "checks": [
            {
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "completed_at": "2026-07-17T10:30:00Z",
            }
        ],
    }
    after = {
        **base,
        "checks": [
            {
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "completed_at": "2026-07-19T16:00:00Z",
            }
        ],
    }
    missing = {
        **base,
        "checks": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
    }

    assert classify_receipt(before, snapshot_at=t("2026-07-19T15:11:00Z"))[0] == "verified_done"
    assert classify_receipt(after, snapshot_at=t("2026-07-19T15:11:00Z"))[0] == "verified_partial"
    assert classify_receipt(missing, snapshot_at=t("2026-07-19T15:11:00Z"))[0] == "verified_partial"


def test_incomplete_paginated_check_contexts_cannot_prove_done() -> None:
    receipt = {
        "created_at": "2026-07-17T10:00:00Z",
        "merged_at": "2026-07-17T11:00:00Z",
        "base_ref": "main",
        "default_branch": "main",
        "commits": [{"committed_at": "2026-07-17T10:05:00Z"}],
        "checks": [
            {
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "completed_at": "2026-07-17T10:30:00Z",
            }
        ],
        "historical_check_contexts_complete": False,
    }

    outcome, reason = classify_receipt(
        receipt,
        snapshot_at=t("2026-07-19T15:11:00Z"),
    )

    assert outcome == "verified_partial"
    assert "historical" in reason


def test_paginated_head_checks_combine_runs_and_statuses(monkeypatch) -> None:
    responses = [
        [
            {
                "check_runs": [
                    {
                        "name": "tests",
                        "status": "completed",
                        "conclusion": "success",
                        "completed_at": "2026-07-17T10:30:00Z",
                        "details_url": "https://example.test/check",
                    }
                ]
            }
        ],
        [
            [
                {
                    "context": "required",
                    "state": "success",
                    "created_at": "2026-07-17T10:31:00Z",
                    "target_url": "https://example.test/status",
                }
            ]
        ],
    ]
    monkeypatch.setattr(
        reconcile,
        "_run_json",
        lambda *_args, **_kwargs: responses.pop(0),
    )

    checks, complete = reconcile._paginated_head_checks(
        "organvm",
        "limen",
        "abc123",
    )

    assert complete is True
    assert [row["name"] for row in checks] == ["required", "tests"]


def test_local_paths_are_unknown_without_git_remote_evidence() -> None:
    assert canonical_repository("~/Workspace/limen") == "unknown"
    assert canonical_repository("/Users/example/limen") == "unknown"
    assert canonical_repository("/Volumes/Archive/private") == "unknown"
    assert canonical_repository("file:///tmp/repo") == "unknown"
    assert canonical_repository("https://github.com/organvm/limen.git") == "organvm/limen"


def test_fragment_merge_deduplicates_tokens_and_claude_child_identity() -> None:
    child, parent = claude_identity(
        {"sessionId": "root-session", "agentId": "child-agent"},
        "fallback",
    )
    rows = [
        {
            "agent": "claude",
            "native_id": child,
            "parent_id": parent,
            "start": "2026-07-17T10:00:00Z",
            "end": "2026-07-17T11:00:00Z",
            "events": 2,
            "token_events": [
                {
                    "event_id": "same",
                    "timestamp": "2026-07-17T10:30:00Z",
                    "components": {"input_tokens": 10},
                }
            ],
        },
        {
            "agent": "claude",
            "native_id": child,
            "parent_id": parent,
            "start": "2026-07-17T10:30:00Z",
            "end": "2026-07-17T12:00:00Z",
            "events": 3,
            "token_events": [
                {
                    "event_id": "same",
                    "timestamp": "2026-07-17T10:30:00Z",
                    "components": {"input_tokens": 10},
                }
            ],
        },
    ]

    canonical = canonicalize_sessions(rows)

    assert len(canonical) == 1
    assert canonical[0]["native_id"] == "child-agent"
    assert canonical[0]["parent_id"] == "root-session"
    assert len(canonical[0]["token_events"]) == 1
    assert session_role_counts(rows) == {"root": 0, "child": 1}


def test_fragment_merge_deduplicates_native_events() -> None:
    rows = [
        {
            "agent": "codex",
            "native_id": "same-session",
            "events": 2,
            "event_ids": ["one", "two"],
        },
        {
            "agent": "codex",
            "native_id": "same-session",
            "events": 2,
            "event_ids": ["one", "two"],
        },
    ]

    assert canonicalize_sessions(rows)[0]["events"] == 2


def test_pr_839_cannot_close_unrelated_cross_repository_ask() -> None:
    ask = {
        "source_atom_ids": ["pa-owner-a"],
        "canonical_repo": "organvm/repository-a",
    }
    receipt = {
        "source_atom_ids": ["pa-control-plane"],
        "canonical_repo": "organvm/limen",
        "url": "https://github.com/organvm/limen/pull/839",
        "predicate_result": {"passed": True},
    }

    linked, reason = semantic_receipt_link(ask, receipt)

    assert linked is False
    assert "assistance" in reason


def test_collision_safe_copilot_ids_include_repository() -> None:
    left = copilot_ask_id("organvm/alpha", 7)
    right = copilot_ask_id("organvm/beta", 7)

    assert left != right
    assert copilot_ask_id("organvm/alpha", 7) == left


def test_missing_native_meter_and_non_executor_transition_stay_unknown() -> None:
    assert native_metric(None) is None
    assert event_executor_role({"agent": "heal-board", "status": "done"}) is None


def test_registry_owner_order_and_evidence_union_are_dynamic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        reconcile,
        "registry_owners",
        lambda _root: ["z-owner", "a-owner"],
    )
    repositories = {
        "z-owner": [{"full_name": "z-owner/repo-z", "name": "repo-z"}],
        "a-owner": [{"full_name": "a-owner/repo-a", "name": "repo-a"}],
    }
    monkeypatch.setattr(
        reconcile,
        "_owner_repositories",
        lambda owner: repositories[owner],
    )
    monkeypatch.setattr(
        reconcile,
        "_run_json",
        lambda _args: {"nameWithOwner": "outside/evidence"},
    )

    aliases, count, owners = estate_census(
        tmp_path,
        evidence_repositories=["outside/evidence"],
    )

    assert owners == ["z-owner", "a-owner"]
    assert count == 2
    assert aliases["repo-a"] == "a-owner/repo-a"
    assert aliases["outside/evidence"] == "outside/evidence"


def test_estate_review_cli_delegates_without_writing_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "start-worktree-session.sh").write_text("", encoding="utf-8")
    called: list[list[str]] = []
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "limen.estate_review.pipeline.main",
        lambda arguments: called.append(arguments) or 0,
    )

    result = CliRunner().invoke(
        main,
        ["estate-review", "--snapshot-at", "2026-07-19T15:11:00Z"],
    )

    assert result.exit_code == 0
    assert called and "--write" not in called[0] and "--check" not in called[0]


def test_report_uses_runtime_v1_and_exposes_required_partial_access_issue() -> None:
    artifact = build_artifact(
        {
            "snapshot_at": "2026-07-19T15:11:00Z",
            "asks": [],
            "comparison": [],
            "root_session_volume": [],
            "outcome_distribution": [],
            "deliverables": [],
            "session_appendix": {},
            "reconciliation": {"state": "partial"},
        }
    )

    assert artifact["manifest"]["version"] == 1
    assert artifact["snapshot"]["version"] == 1
    assert artifact["snapshot"]["status"] == "partial"
    assert artifact["snapshot"]["accessIssues"]
    assert validate_artifact_contract(artifact) == []


def test_report_reconciliation_fails_closed_without_prompt_or_owner_fixed_point() -> None:
    snapshot = {
        "reconciliation": {"state": "complete"},
        "owner_link_index": {
            "state": "pending",
            "prompt_authority_exact": False,
        },
    }

    _finalize_reconciliation_state(snapshot)

    assert snapshot["reconciliation"]["remote_state"] == "complete"
    assert snapshot["reconciliation"]["state"] == "partial"
    assert snapshot["reconciliation"]["completion_gates"] == {
        "remote_receipts": True,
        "prompt_authority": False,
        "owner_links": False,
    }


def test_owner_link_summary_rejects_structurally_empty_owner(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "estate-session-review-owner-links.json").write_text(
        json.dumps(
            {
                "schema": "limen.estate_session_review_owner_links.v1",
                "links": [
                    {
                        "prompt_atom_id": "pa-one",
                        "owner_type": "task",
                        "canonical_owner_reference": "task:one",
                        "disposition": "durably_homed_open",
                        "predicate": "",
                        "receipt_target": "",
                        "content_bindings": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    summary = _owner_link_summary(
        tmp_path,
        [{"ask": "pa-one"}],
        {
            "available": True,
            "coverage": {},
            "source_scope": {
                "scope": "all",
                "target_scope": "all",
                "all_baseline_complete": True,
            },
        },
    )

    assert summary["state"] == "pending"
    assert summary["invalid"] > 0


def test_exact_private_prompt_lineage_joins_without_exposing_prompt_text(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    private = root / ".limen-private" / "session-corpus" / "prompt-atoms"
    private.mkdir(parents=True)
    public = {
        "version": 1,
        "semantic_digest": "semantic",
        "source_cursor_digest": "cursor",
        "source_scope": {
            "scope": "all",
            "target_scope": "all",
            "all_baseline_complete": True,
            "pending_files": 0,
            "source_errors": [],
            "adapter_gaps": [],
        },
        "coverage": {"atoms": 1},
        "unresolved_atoms": [],
        "unresolved_atoms_truncated": 0,
        "validation": {"ok": True, "errors": []},
    }
    public["projection_digest"] = _canonical_digest(public)
    (root / "docs" / "prompt-atom-ledger.json").write_text(
        json.dumps(public),
        encoding="utf-8",
    )
    (private / "prompt-atom-ledger.json").write_text(
        json.dumps(
            {
                "public_projection_digest": public["projection_digest"],
                "semantic_digest": "semantic",
                "source_cursor_digest": "cursor",
            }
        ),
        encoding="utf-8",
    )
    native_id = "native-session"
    (private / "prompt-events.jsonl").write_text(
        json.dumps(
            {
                "occurrence": {
                    "occurrence_id": "po-one",
                    "timestamp": "2026-07-17T10:00:00Z",
                    "source": "codex-sessions",
                    "session_ref_hash": _session_ref_hash(f"codex:{native_id}"),
                },
                "atoms": [
                    {
                        "atom_id": "pa-one",
                        "kind": "ask",
                        "source": "codex-sessions",
                        "session_ref_hash": _session_ref_hash(f"codex:{native_id}"),
                        "intent": "private prompt text must not appear",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (private / "prompt-atom-outcomes.jsonl").write_text("", encoding="utf-8")
    config = ReviewConfig.from_values(
        root=root,
        snapshot_at="2026-07-19T15:11:00Z",
        output_dir=root / "report",
    )
    sessions = [
        {
            "agent": "codex",
            "native_id": native_id,
            "source_atom_ids": [],
            "coverage_flags": [],
            "_prompt_session_refs": [f"codex:{native_id}"],
        }
    ]

    asks, coverage = collect_prompt_atoms(config, sessions)

    assert asks == [
        {
            "ask": "pa-one",
            "source_atom_ids": ["pa-one"],
            "agent": "codex",
            "subject": "ask",
            "canonical_repo": "unknown",
            "executor_role": "executor",
            "outcome": "coverage_unknown",
            "predicate_result": None,
            "predicate_checked_at": None,
            "receipt_head_sha": None,
            "receipt": None,
            "observed_at": "2026-07-17T10:00:00Z",
            "coverage_flags": [],
        }
    ]
    assert sessions[0]["source_atom_ids"] == ["pa-one"]
    assert coverage["asks_in_window"] == 1
    assert "private prompt text" not in json.dumps(asks)


def test_bare_native_id_cannot_infer_prompt_session_binding(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    private = root / ".limen-private" / "session-corpus" / "prompt-atoms"
    private.mkdir(parents=True)
    public = {
        "version": 1,
        "semantic_digest": "semantic",
        "source_cursor_digest": "cursor",
        "source_scope": {
            "scope": "all",
            "target_scope": "all",
            "all_baseline_complete": True,
            "pending_files": 0,
            "source_errors": [],
            "adapter_gaps": [],
        },
        "coverage": {"atoms": 1},
        "unresolved_atoms": [],
        "unresolved_atoms_truncated": 0,
        "validation": {"ok": True, "errors": []},
    }
    public["projection_digest"] = _canonical_digest(public)
    (root / "docs" / "prompt-atom-ledger.json").write_text(
        json.dumps(public),
        encoding="utf-8",
    )
    (private / "prompt-atom-ledger.json").write_text(
        json.dumps(
            {
                "public_projection_digest": public["projection_digest"],
                "semantic_digest": "semantic",
                "source_cursor_digest": "cursor",
            }
        ),
        encoding="utf-8",
    )
    (private / "prompt-events.jsonl").write_text(
        json.dumps(
            {
                "occurrence": {
                    "occurrence_id": "po-one",
                    "timestamp": "2026-07-17T10:00:00Z",
                    "source": "codex-sessions",
                    "session_ref_hash": _session_ref_hash("codex:native-session"),
                },
                "atoms": [{"atom_id": "pa-one", "kind": "ask"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (private / "prompt-atom-outcomes.jsonl").write_text("", encoding="utf-8")
    config = ReviewConfig.from_values(
        root=root,
        snapshot_at="2026-07-19T15:11:00Z",
        output_dir=root / "report",
    )
    sessions = [
        {
            "agent": "codex",
            "native_id": "native-session",
            "source_atom_ids": [],
            "coverage_flags": ["coverage_unknown"],
        }
    ]

    collect_prompt_atoms(config, sessions)

    assert sessions[0]["source_atom_ids"] == []
    assert sessions[0]["coverage_flags"] == ["coverage_unknown"]


def test_repeated_reconciliation_is_byte_identical(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ReviewConfig.from_values(
        root=tmp_path,
        snapshot_at="2026-07-19T15:11:00Z",
        output_dir=tmp_path / "report",
    )
    raw = {
        "schema": "limen.seven_agent_estate_review.v2",
        "snapshot_at": "2026-07-19T15:11:00Z",
        "windows": [],
        "coverage": {},
        "asks": [
            {
                "ask": "pa-one",
                "source_atom_ids": ["pa-one"],
                "agent": "codex",
                "observed_at": "2026-07-17T10:00:00Z",
                "outcome": "coverage_unknown",
                "canonical_repo": "organvm/limen",
            }
        ],
        "_sessions": [],
    }
    monkeypatch.setattr(
        reconcile,
        "estate_census",
        lambda *_args, **_kwargs: ({"organvm/limen": "organvm/limen"}, 1, ["organvm"]),
    )
    monkeypatch.setattr(reconcile, "coding_agent_receipts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(reconcile, "batch_receipts", lambda *_args, **_kwargs: ({}, []))

    first = reconcile.reconcile_snapshot(copy.deepcopy(raw), config)
    second = reconcile.reconcile_snapshot(copy.deepcopy(raw), config)

    assert stable_json(first) == stable_json(second)


def test_exact_owner_link_predicate_proves_matching_head_without_ci_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ReviewConfig.from_values(
        root=tmp_path,
        snapshot_at="2026-07-19T15:11:00Z",
        output_dir=tmp_path / "report",
    )
    url = "https://github.com/organvm/limen/pull/7"
    raw = {
        "schema": "limen.seven_agent_estate_review.v2",
        "snapshot_at": "2026-07-19T15:11:00Z",
        "windows": [],
        "coverage": {},
        "asks": [
            {
                "ask": "pa-one",
                "source_atom_ids": ["pa-one"],
                "agent": "codex",
                "observed_at": "2026-07-17T10:00:00Z",
                "outcome": "coverage_unknown",
                "canonical_repo": "organvm/limen",
            }
        ],
        "_sessions": [],
    }
    receipt = {
        "url": url,
        "canonical_repo": "organvm/limen",
        "created_at": "2026-07-17T10:00:00Z",
        "merged_at": "2026-07-17T11:00:00Z",
        "base_ref": "main",
        "default_branch": "main",
        "head_sha": "a" * 40,
        "commits": [{"committed_at": "2026-07-17T10:05:00Z"}],
        "checks": [],
        "historical_check_contexts_complete": True,
    }
    monkeypatch.setattr(
        reconcile,
        "estate_census",
        lambda *_args, **_kwargs: ({"organvm/limen": "organvm/limen"}, 1, ["organvm"]),
    )
    monkeypatch.setattr(reconcile, "coding_agent_receipts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        reconcile,
        "batch_receipts",
        lambda *_args, **_kwargs: ({url: receipt}, []),
    )

    result = reconcile.reconcile_snapshot(
        raw,
        config,
        receipt_urls_by_ask={
            "pa-one": [
                {
                    "url": url,
                    "predicate_result": {"passed": True},
                    "predicate_checked_at": "2026-07-17T12:00:00Z",
                    "receipt_head_sha": "a" * 40,
                }
            ]
        },
    )

    assert result["asks"][0]["outcome"] == "verified_done"
