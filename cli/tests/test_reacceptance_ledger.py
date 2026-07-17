import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("reacceptance_ledger", ROOT / "scripts" / "reacceptance-ledger.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

NOW = "2026-07-16T21:40:00Z"
HEAD = "a" * 40
NEW_HEAD = "b" * 40
SESSION_ID = "claude-session-sha256:" + "a" * 20
WORKFLOW_ID = "claude-workflow-sha256:" + "b" * 20
PR_ID = "pull_request:example/owner#7"


def scope():
    return {
        "schema": "limen.reacceptance_scope.v1",
        "boundary": {"starts_at": "2026-07-12T15:37:35Z"},
        "sessions": [SESSION_ID],
        "workflows": [WORKFLOW_ID],
        "pull_requests": [{"repository": "example/owner", "numbers": [7]}],
    }


def _connection(nodes, *, has_next=False):
    return {"pageInfo": {"hasNextPage": has_next}, "nodes": nodes}


def _fresh_pr_row(head=HEAD, *, state="OPEN"):
    row = MODULE._base_row("session", "temporary")
    row.update(
        {
            "id": PR_ID,
            "kind": "pull_request",
            "session": None,
            "exact_head": head,
            "review_findings": {
                "status": "current_remote_snapshot",
                "p1": 0,
                "p2": 0,
                "unclassified": 0,
                "unresolved_current": 0,
                "urls": [],
            },
            "receipt": {
                "status": state.lower(),
                "url": "https://example.invalid/example/owner/pull/7",
                "merge_commit": None,
                "review_decision": None,
                "draft": False,
                "merged_at": None,
                "closed_at": None,
            },
            "keeper": {
                "executing_keeper": "claude",
                "reviewing_keeper": None,
                "provider_route": "claude",
                "github_author": "keeper-citrine",
                "owner_surface": "example/owner",
            },
        }
    )
    return row


def valid_document():
    rows = [
        MODULE._base_row("session", SESSION_ID),
        MODULE._base_row("workflow", WORKFLOW_ID),
        _fresh_pr_row(),
    ]
    gates = MODULE._default_completion_gates()
    return {
        "schema": MODULE.SCHEMA,
        "refreshed_at": NOW,
        "scope": {
            "starts_at": "2026-07-12T15:37:35Z",
            "sessions": 1,
            "workflows": 1,
            "pull_requests": 1,
            "rows": 3,
        },
        "completion_gates": gates,
        "summary": MODULE._summary_for(rows, gates, refreshed_at=NOW),
        "rows": rows,
    }


def _predicate(exact_head=None):
    value = {
        "status": "verified",
        "result": "passed",
        "command": "scripts/verify-scoped.sh",
        "verified_at": NOW,
    }
    if exact_head is not None:
        value["exact_head"] = exact_head
    return value


def _receipt(disposition, exact_head=None):
    value = {
        "status": "verified",
        "disposition": disposition,
        "url": "https://example.invalid/receipts/terminal",
        "verified_at": NOW,
    }
    if exact_head is not None:
        value["exact_head"] = exact_head
    return value


def _mark_terminal(row, disposition, *, replacement=None):
    exact_head = row.get("exact_head")
    row["disposition"] = disposition
    row["predicate"] = _predicate(exact_head)
    receipt = row.setdefault("receipt", {})
    adjudication = _receipt(disposition, exact_head)
    if disposition == "accepted" and row.get("kind") == "pull_request":
        adjudication["review_gate_status"] = "accepted"
        row["keeper"]["reviewing_keeper"] = "codex"
    elif disposition == "reverted":
        adjudication["reversal_status"] = "verified"
    elif disposition == "superseded":
        assert replacement is not None
        adjudication["superseded_by"] = replacement["id"]
        if replacement.get("exact_head") is not None:
            adjudication["replacement_head"] = replacement["exact_head"]
    receipt["adjudication"] = adjudication


def _pass_completion_gates(document):
    document["completion_gates"] = {
        key: {
            "status": "passed",
            "predicate": _predicate(),
            "receipt": {
                "status": "verified",
                "url": f"https://example.invalid/gates/{key}",
                "verified_at": NOW,
            },
        }
        for key in MODULE.COMPLETION_GATE_KEYS
    }


def _refresh_summary(document):
    document["summary"] = MODULE._summary_for(
        document["rows"],
        document["completion_gates"],
        refreshed_at=document["refreshed_at"],
    )


def test_validate_requires_exact_frozen_denominator():
    document = valid_document()
    assert MODULE.validate_document(document, scope()) == []
    document["rows"].pop()
    errors = MODULE.validate_document(document, scope())
    assert any("row denominator mismatch" in error for error in errors)


def test_validate_requires_exact_frozen_row_identities_not_only_counts():
    document = valid_document()
    document["rows"][0]["id"] = "session:claude-session-sha256:" + "c" * 20
    errors = MODULE.validate_document(document, scope())
    assert any("frozen scope denominator" in error for error in errors)


@pytest.mark.parametrize("disposition", sorted(MODULE.TERMINAL_DISPOSITIONS))
def test_terminal_dispositions_fail_closed_without_verified_predicate_and_receipt(disposition):
    document = valid_document()
    document["rows"][0]["disposition"] = disposition
    _refresh_summary(document)

    errors = MODULE.validate_document(document, scope())

    assert any("predicate must be verified and passed" in error for error in errors)
    assert any("receipt" in error for error in errors)


def test_accepted_reverted_and_superseded_rows_require_and_accept_disposition_specific_evidence():
    document = valid_document()
    session, workflow, pull_request = document["rows"]
    _mark_terminal(session, "accepted")
    _mark_terminal(workflow, "superseded", replacement=session)
    _mark_terminal(pull_request, "reverted")
    _refresh_summary(document)

    assert MODULE.validate_document(document, scope()) == []

    pull_request["receipt"]["adjudication"].pop("reversal_status")
    workflow["receipt"]["adjudication"]["superseded_by"] = "pull_request:missing/replacement#8"
    errors = MODULE.validate_document(document, scope())
    assert any("safe reversal" in error for error in errors)
    assert any("accepted replacement row" in error for error in errors)


def test_accepted_pr_requires_zero_all_classified_debt_and_distinct_exact_head_review():
    document = valid_document()
    pull_request = document["rows"][2]
    _mark_terminal(pull_request, "accepted")
    pull_request["review_findings"]["unclassified"] = 1
    pull_request["review_findings"]["unresolved_current"] = 1
    pull_request["keeper"]["reviewing_keeper"] = "claude"
    pull_request["receipt"]["adjudication"]["exact_head"] = NEW_HEAD
    _refresh_summary(document)

    errors = MODULE.validate_document(document, scope())

    assert any("zero unclassified" in error for error in errors)
    assert any("distinct reviewing keeper" in error for error in errors)
    assert any("receipt exact_head does not match" in error for error in errors)


def test_release_ready_is_derived_only_when_all_rows_debt_and_completion_gates_pass():
    document = valid_document()
    session, workflow, pull_request = document["rows"]
    _mark_terminal(session, "accepted")
    _mark_terminal(workflow, "reverted")
    _mark_terminal(pull_request, "accepted")
    _pass_completion_gates(document)
    _refresh_summary(document)

    assert document["summary"]["release_ready"] is True
    assert MODULE.validate_document(document, scope()) == []

    document["summary"]["release_ready"] = False
    errors = MODULE.validate_document(document, scope())
    assert any("summary must be derived" in error for error in errors)


@pytest.mark.parametrize("blocker", ["p1", "p2", "unclassified", "row", "gate"])
def test_release_ready_rejects_each_unresolved_debt_or_completion_blocker(blocker):
    document = valid_document()
    session, workflow, pull_request = document["rows"]
    _mark_terminal(session, "accepted")
    _mark_terminal(workflow, "reverted")
    _mark_terminal(pull_request, "accepted")
    _pass_completion_gates(document)
    if blocker in {"p1", "p2", "unclassified"}:
        pull_request["review_findings"][blocker] = 1
        pull_request["review_findings"]["unresolved_current"] = 1
    elif blocker == "row":
        session["disposition"] = "repair_required"
    else:
        document["completion_gates"]["session_value_verified"] = {
            "status": "not_verified",
            "predicate": None,
            "receipt": None,
        }
    _refresh_summary(document)

    assert document["summary"]["release_ready"] is False
    document["summary"]["release_ready"] = True
    assert any("summary must be derived" in error for error in MODULE.validate_document(document, scope()))


def test_refresh_preserves_adjudicated_fields_by_stable_row_id(monkeypatch):
    previous = valid_document()
    prior_pr = previous["rows"][2]
    prior_pr["source_ask"]["adjudicated"] = True
    prior_pr["spend"] = {"status": "reconciled", "tokens": 42, "cost": "redacted"}
    prior_pr["predicate"]["owner_note"] = "preserve"
    prior_pr["receipt"]["adjudication_note"] = "preserve"
    prior_pr["keeper"]["reviewing_keeper"] = "codex"
    prior_pr["side_effects"] = {"status": "reconciled", "observed": ["owner_effect"]}
    fresh_pr = _fresh_pr_row(state="MERGED")
    fresh_pr["review_findings"]["p2"] = 1
    fresh_pr["review_findings"]["unresolved_current"] = 1
    monkeypatch.setattr(MODULE, "_pr_row", lambda item: copy.deepcopy(fresh_pr))

    refreshed = MODULE.build_document(scope(), workers=1, previous_document=previous)
    row = next(item for item in refreshed["rows"] if item["id"] == PR_ID)

    assert row["source_ask"]["adjudicated"] is True
    assert row["spend"]["tokens"] == 42
    assert row["predicate"]["owner_note"] == "preserve"
    assert row["receipt"]["adjudication_note"] == "preserve"
    assert row["receipt"]["status"] == "merged"
    assert row["keeper"]["reviewing_keeper"] == "codex"
    assert row["review_findings"]["p2"] == 1
    assert row["side_effects"]["status"] == "reconciled"


def test_refresh_refuses_to_carry_terminal_adjudication_across_head_change(monkeypatch):
    previous = valid_document()
    _mark_terminal(previous["rows"][2], "accepted")
    _refresh_summary(previous)
    monkeypatch.setattr(MODULE, "_pr_row", lambda item: _fresh_pr_row(NEW_HEAD))

    with pytest.raises(MODULE.LedgerError, match="stale: exact head changed"):
        MODULE.build_document(scope(), workers=1, previous_document=previous)


def test_refresh_refuses_same_head_accepted_row_when_current_review_debt_changes(monkeypatch):
    previous = valid_document()
    _mark_terminal(previous["rows"][2], "accepted")
    _refresh_summary(previous)
    fresh = _fresh_pr_row()
    fresh["review_findings"]["p2"] = 1
    fresh["review_findings"]["unresolved_current"] = 1
    monkeypatch.setattr(MODULE, "_pr_row", lambda item: fresh)

    with pytest.raises(MODULE.LedgerError, match="current review debt changed"):
        MODULE.build_document(scope(), workers=1, previous_document=previous)


def test_refresh_refuses_stable_id_kind_conflicts():
    fresh = MODULE._base_row("session", SESSION_ID)
    previous = MODULE._base_row("workflow", SESSION_ID)
    previous["id"] = fresh["id"]

    with pytest.raises(MODULE.LedgerError, match="identity conflict"):
        MODULE._merge_refreshed_row(fresh, previous)


def test_atomic_refresh_refuses_changed_destination(tmp_path):
    destination = tmp_path / "ledger.json"
    destination.write_text('{"version": 1}\n', encoding="utf-8")
    expected = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.write_text('{"version": 2}\n', encoding="utf-8")

    with pytest.raises(MODULE.LedgerError, match="changed after the prior ledger snapshot"):
        MODULE._write_atomic(destination, valid_document(), expected_digest=expected)

    assert json.loads(destination.read_text(encoding="utf-8")) == {"version": 2}


def _review_snapshot(*, threads_has_next=False, comments_has_next=False):
    return {
        "reviewThreads": _connection(
            [
                {
                    "isResolved": False,
                    "isOutdated": False,
                    "comments": _connection(
                        [{"body": "[P2] exact-head issue", "url": "https://example.invalid/thread/1"}],
                        has_next=comments_has_next,
                    ),
                }
            ],
            has_next=threads_has_next,
        )
    }


def test_review_thread_and_comment_connections_are_counted_only_when_complete():
    findings = MODULE._current_findings(_review_snapshot())

    assert findings["p2"] == findings["unresolved_current"] == 1
    assert "pageInfo { hasNextPage }" in MODULE.GRAPHQL
    assert "comments(first: 100)" in MODULE.GRAPHQL


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"threads_has_next": True}, "reviewThreads pagination is incomplete"),
        ({"comments_has_next": True}, "reviewThreads\\[0\\]\\.comments pagination is incomplete"),
    ],
)
def test_review_thread_or_nested_comment_pagination_fails_closed(kwargs, message):
    with pytest.raises(MODULE.LedgerError, match=message):
        MODULE._current_findings(_review_snapshot(**kwargs))


def test_review_severity_uses_arbitrary_text_not_provider_identity():
    assert MODULE._severity("![P1 Badge] exact-head race") == "p1"
    assert MODULE._severity("[P2] renamed fixture id") == "p2"
    assert MODULE._severity("ordinary review note") is None


def test_scope_rejects_raw_session_identifiers(tmp_path):
    raw_scope = scope()
    raw_scope["sessions"] = ["00000000-0000-0000-0000-000000000000"]
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(raw_scope), encoding="utf-8")

    with pytest.raises(MODULE.LedgerError, match="redacted truncated SHA-256"):
        MODULE.load_scope(path)


def test_scope_rejects_raw_workflow_identifiers(tmp_path):
    raw_scope = scope()
    raw_scope["workflows"] = ["wf_00000000-000"]
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(raw_scope), encoding="utf-8")

    with pytest.raises(MODULE.LedgerError, match="redacted truncated SHA-256"):
        MODULE.load_scope(path)
