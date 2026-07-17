"""Adversarial tests for the App-bound exact-head review gate."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

gate_cli = importlib.import_module("limen.review_gate.cli")
github = importlib.import_module("limen.review_gate.github")
model = importlib.import_module("limen.review_gate.model")

SCRIPT = ROOT / "scripts" / "pr-review-gate.py"
HEAD = "a17c" * 10
NEW_HEAD = "b29d" * 10
REPO = "signal-garden/orbit-index"
PR = 731
APP_SLUG = "keeper-review-gate-v7"
APP_ID = 424242


def _protection(*, app_id=APP_ID, last_push=True):
    return {
        "required_status_checks": {
            "strict": True,
            "checks": [
                {"context": "verify", "app_id": 1},
                {"context": model.SCHEMA, "app_id": app_id},
            ],
        },
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_last_push_approval": last_push,
            "required_approving_review_count": 1,
        },
        "required_conversation_resolution": {"enabled": True},
        "enforce_admins": {"enabled": True},
    }


def _connection(nodes, *, has_next=False, end_cursor=None):
    return {
        "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
        "nodes": nodes,
    }


def _review(*, login="keeper-umber", head=HEAD, state="APPROVED", submitted="2026-07-17T01:00:00Z"):
    return {
        "id": f"RVW-{login}-{state}",
        "author": {"login": login},
        "authorAssociation": "COLLABORATOR",
        "state": state,
        "commit": {"oid": head},
        "submittedAt": submitted,
        "url": f"https://example.invalid/reviews/{login}",
    }


def _project_check(name="verify", *, conclusion="SUCCESS"):
    return {
        "__typename": "CheckRun",
        "databaseId": 10,
        "name": name,
        "headSha": HEAD,
        "status": "COMPLETED",
        "conclusion": conclusion,
        "externalId": "",
        "startedAt": "2026-07-17T00:58:00Z",
        "completedAt": "2026-07-17T00:59:00Z",
        "output": {"title": name, "summary": ""},
        "checkSuite": {"app": {"id": 1, "slug": "github-actions"}, "workflowRun": None},
    }


def _pr():
    return {
        "number": PR,
        "url": f"https://example.invalid/{REPO}/pull/{PR}",
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": HEAD,
        "baseRefName": "main",
        "baseBranchProtection": _protection(),
        "author": {"login": "proposal-author"},
        "headCommitIdentity": {
            "oid": HEAD,
            "author": "keeper-citrine",
            "committer": "keeper-citrine",
        },
        "statusCheckRollup": {"contexts": _connection([_project_check()])},
        "reviewThreads": _connection([{"id": "T1", "isResolved": True, "isOutdated": False}]),
        "comments": _connection(
            [
                {
                    "id": "C1",
                    "createdAt": "2026-07-17T00:30:00Z",
                    "updatedAt": "2026-07-17T00:30:00Z",
                    "url": "https://example.invalid/comments/C1",
                    "author": {"login": "keeper-umber"},
                }
            ]
        ),
        "reviews": _connection([_review()]),
        "files": _connection([{"path": "src/orbit.py", "changeType": "MODIFIED", "additions": 4, "deletions": 1}]),
    }


def _evaluate(pr=None, **kwargs):
    pull = pr or _pr()
    app_slug = kwargs.get("review_gate_app_slug")
    kwargs.setdefault("rechecked_head", str(pull.get("headRefOid") or ""))
    kwargs.setdefault(
        "rechecked_snapshot_digest",
        model.snapshot_digest(
            pull,
            repo=REPO,
            review_gate_app_slug=app_slug,
        ),
    )
    return model.evaluate(
        pull,
        repo=REPO,
        number=PR,
        expected_head=kwargs.pop("expected_head", HEAD),
        **kwargs,
    )


def _app_check(report, *, conclusion="SUCCESS", app_slug=APP_SLUG, app_id=APP_ID, check_id=91):
    envelope = model.make_check_receipt(report)
    return {
        "__typename": "CheckRun",
        "databaseId": check_id,
        "name": model.SCHEMA,
        "headSha": report["head_sha"],
        "status": "COMPLETED",
        "conclusion": conclusion,
        "externalId": f"{model.CHECK_RECEIPT_SCHEMA}:{envelope['digest']}",
        "startedAt": "2026-07-17T01:01:00Z",
        "completedAt": "2026-07-17T01:02:00Z",
        "output": {"title": model.SCHEMA, "summary": model.check_receipt_summary(report)},
        "checkSuite": {"app": {"id": app_id, "slug": app_slug}, "workflowRun": None},
    }


def test_accepts_native_exact_head_peer_distinct_from_head_commit_executor():
    report = _evaluate()
    assert report["status"] == "accepted"
    assert report["executing_keeper"] == "keeper-citrine"
    assert report["execution_identity_source"] == "head_commit_committer"
    assert report["last_push_authority"] == {
        "source": "github_live_base_branch_protection",
        "branch": "main",
        "review_gate": {"context": model.SCHEMA, "app_id": APP_ID},
        "require_last_push_approval": True,
        "dismiss_stale_reviews": True,
        "required_conversation_resolution": True,
        "enforce_admins": True,
        "strict_current_head_checks": True,
        "required_approving_review_count": 1,
    }
    assert report["reviewing_keeper"] == "keeper-umber"
    assert report["reviewed_sha"] == HEAD
    assert report["checks"]["successful"] == 1
    assert report["files"]["count"] == 1
    assert report["comments"]["count"] == 1


def test_pr_author_is_not_misrepresented_as_last_executor():
    pr = _pr()
    pr["author"] = {"login": "different-proposal-author"}
    pr["headCommitIdentity"]["committer"] = "actual-last-commit-principal"
    pr["reviews"]["nodes"] = [_review(login="actual-last-commit-principal")]
    report = _evaluate(pr)
    assert report["executing_keeper"] == "actual-last-commit-principal"
    assert "exact_head_peer_approval_missing" in report["reason_codes"]


def test_missing_head_commit_identity_fails_closed():
    pr = _pr()
    pr["headCommitIdentity"] = {"oid": HEAD, "author": "", "committer": ""}
    report = _evaluate(pr)
    assert report["status"] == "rejected"
    assert "executor_identity_unavailable" in report["reason_codes"]

    mismatched = _pr()
    mismatched["headCommitIdentity"]["oid"] = NEW_HEAD
    assert "executor_identity_unavailable" in _evaluate(mismatched)["reason_codes"]


def test_web_flow_committer_cannot_create_false_peer_separation():
    pr = _pr()
    pr["headCommitIdentity"] = {
        "oid": HEAD,
        "author": "keeper-umber",
        "committer": "web-flow",
    }
    report = _evaluate(pr)
    assert report["executing_keeper"] == "keeper-umber"
    assert report["execution_identity_source"] == "head_commit_author_with_generic_committer"
    assert "exact_head_peer_approval_missing" in report["reason_codes"]


def test_reviewer_must_differ_from_both_distinct_author_and_committer():
    pr = _pr()
    pr["headCommitIdentity"] = {
        "oid": HEAD,
        "author": "keeper-umber",
        "committer": "keeper-citrine",
    }
    report = _evaluate(pr)
    assert report["execution_identities"]["distinct_principals"] == [
        "keeper-citrine",
        "keeper-umber",
    ]
    assert "exact_head_peer_approval_missing" in report["reason_codes"]


@pytest.mark.parametrize("conclusion", ["NEUTRAL", "SKIPPED"])
def test_neutral_or_skipped_only_ci_is_not_green(conclusion):
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"] = [_project_check(conclusion=conclusion)]
    report = _evaluate(pr)
    assert "checks_without_success" in report["reason_codes"]
    assert report["checks"]["successful"] == 0


def test_missing_or_untrusted_live_protection_fails_closed():
    missing = _pr()
    missing.pop("baseBranchProtection")
    assert "base_branch_protection_unavailable" in _evaluate(missing)["reason_codes"]

    wrong_app = _pr()
    wrong_app["baseBranchProtection"] = _protection(app_id=0)
    assert "base_branch_protection_unavailable" in _evaluate(wrong_app)["reason_codes"]

    no_last_push = _pr()
    no_last_push["baseBranchProtection"] = _protection(last_push=False)
    assert "base_branch_protection_unavailable" in _evaluate(no_last_push)["reason_codes"]


def test_published_receipt_must_match_protected_app_id_not_only_slug():
    accepted = _evaluate()
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(_app_check(accepted, app_slug=APP_SLUG, app_id=APP_ID + 1))
    report = _evaluate(pr, require_published_result=True)
    assert "published_review_gate_missing" in report["reason_codes"]


def test_local_signed_fallback_is_blocked_without_reading_caller_path(tmp_path):
    missing = tmp_path / "caller-controlled-signers"
    report = _evaluate(allowed_signers=missing)
    assert report["status"] == "rejected"
    assert "signed_fallback_unavailable" in report["reason_codes"]
    assert report["signed_receipts"]["status"] == "blocked_without_owner_authenticated_custody"


def test_untrusted_same_name_marker_spam_is_ignored_only_after_app_authentication():
    pr = _pr()
    for index in range(500):
        pr["statusCheckRollup"]["contexts"]["nodes"].append(
            {
                "__typename": "CheckRun",
                "databaseId": 1000 + index,
                "name": model.SCHEMA,
                "headSha": HEAD,
                "status": "IN_PROGRESS",
                "conclusion": None,
                "externalId": "attacker-marker",
                "output": {"title": "noise", "summary": "x" * 100},
                "checkSuite": {"app": {"id": 77, "slug": "untrusted-writer"}, "workflowRun": None},
            }
        )
    report = _evaluate(pr, review_gate_app_slug=APP_SLUG)
    assert report["status"] == "accepted"
    assert report["checks"]["total"] == 1
    assert report["checks"]["ignored_untrusted_gate_markers"] == 500


def test_app_evaluator_excludes_own_result_but_consumer_requires_valid_success():
    initial = _evaluate(review_gate_app_slug=APP_SLUG)
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(_app_check(initial))

    evaluator = _evaluate(pr, review_gate_app_slug=APP_SLUG)
    consumer = _evaluate(
        pr,
        review_gate_app_slug=APP_SLUG,
        require_published_result=True,
    )

    assert evaluator["status"] == "accepted"
    assert evaluator["checks"]["total"] == 1
    assert consumer["status"] == "accepted"
    assert consumer["published_gate"]["valid_success"] is True


def test_consumer_rejects_missing_failed_or_stale_evidence_app_receipt():
    missing = _evaluate(require_published_result=True, review_gate_app_slug=APP_SLUG)
    assert "published_review_gate_missing" in missing["reason_codes"]

    accepted = _evaluate(review_gate_app_slug=APP_SLUG)
    failed_pr = _pr()
    failed_pr["statusCheckRollup"]["contexts"]["nodes"].append(_app_check(accepted, conclusion="FAILURE"))
    failed = _evaluate(
        failed_pr,
        review_gate_app_slug=APP_SLUG,
        require_published_result=True,
    )
    assert "published_review_gate_invalid" in failed["reason_codes"]

    stale_pr = _pr()
    stale_pr["files"]["nodes"][0]["additions"] = 99
    stale_pr["statusCheckRollup"]["contexts"]["nodes"].append(_app_check(accepted))
    stale = _evaluate(
        stale_pr,
        review_gate_app_slug=APP_SLUG,
        require_published_result=True,
    )
    assert "published_review_gate_stale_evidence" in stale["reason_codes"]


def test_consumer_rejects_manually_asserted_status_without_complete_v1_receipt():
    report = _evaluate(review_gate_app_slug=APP_SLUG)
    node = _app_check(report)
    manual = {
        "schema": model.CHECK_RECEIPT_SCHEMA,
        "receipt": {
            "schema": model.SCHEMA,
            "repository": REPO,
            "pull_request": PR,
            "head_sha": HEAD,
            "reviewed_sha": HEAD,
            "status": "accepted",
            "evidence_digest": report["evidence_digest"],
        },
    }
    manual["digest"] = model.canonical_digest(manual["receipt"])
    node["output"]["summary"] = json.dumps(manual, sort_keys=True, separators=(",", ":"))
    node["externalId"] = f"{model.CHECK_RECEIPT_SCHEMA}:{manual['digest']}"
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(node)
    rejected = _evaluate(
        pr,
        review_gate_app_slug=APP_SLUG,
        require_published_result=True,
    )
    assert "published_review_gate_invalid" in rejected["reason_codes"]


def test_consumer_rejects_semantically_forged_complete_receipt():
    forged = _evaluate(review_gate_app_slug=APP_SLUG)
    forged["reviewer_receipt"] = None
    forged["reviewing_keeper"] = None
    forged["evidence_digest"] = model.report_evidence_digest(forged)
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(_app_check(forged))

    rejected = _evaluate(
        pr,
        review_gate_app_slug=APP_SLUG,
        require_published_result=True,
    )

    assert "published_review_gate_invalid" in rejected["reason_codes"]


def test_two_snapshot_semantic_change_fails_even_when_head_is_unchanged():
    initial = _pr()
    final = _pr()
    final["reviewThreads"]["nodes"].append({"id": "T2", "isResolved": False, "isOutdated": False})
    report = _evaluate(
        final,
        rechecked_head=HEAD,
        rechecked_snapshot_digest=model.snapshot_digest(
            initial,
            repo=REPO,
            review_gate_app_slug=APP_SLUG,
        ),
        review_gate_app_slug=APP_SLUG,
    )
    assert "acceptance_evidence_changed" in report["reason_codes"]
    assert "unresolved_current_threads" in report["reason_codes"]


def test_sacrificial_unresolved_resolution_and_subsequent_commit_sequence():
    unresolved = _pr()
    unresolved["reviewThreads"]["nodes"][0]["isResolved"] = False
    assert "unresolved_current_threads" in _evaluate(unresolved)["reason_codes"]

    resolved = deepcopy(unresolved)
    resolved["reviewThreads"]["nodes"][0]["isResolved"] = True
    accepted = _evaluate(resolved, review_gate_app_slug=APP_SLUG)
    assert accepted["status"] == "accepted"

    with_receipt = deepcopy(resolved)
    with_receipt["statusCheckRollup"]["contexts"]["nodes"].append(_app_check(accepted))
    assert (
        _evaluate(
            with_receipt,
            review_gate_app_slug=APP_SLUG,
            require_published_result=True,
        )["status"]
        == "accepted"
    )

    pushed = deepcopy(resolved)
    pushed["headRefOid"] = NEW_HEAD
    pushed["headCommitIdentity"] = {
        "oid": NEW_HEAD,
        "author": "keeper-citrine",
        "committer": "keeper-citrine",
    }
    pushed["statusCheckRollup"]["contexts"]["nodes"][0]["headSha"] = NEW_HEAD
    report = model.evaluate(
        pushed,
        repo=REPO,
        number=PR,
        expected_head=NEW_HEAD,
        review_gate_app_slug=APP_SLUG,
        require_published_result=True,
    )
    assert "exact_head_peer_approval_missing" in report["reason_codes"]
    assert "published_review_gate_missing" in report["reason_codes"]


@pytest.mark.parametrize("key", ["contexts", "reviewThreads", "comments", "reviews", "files"])
def test_incomplete_fixture_connection_fails_closed(key):
    pr = _pr()
    if key == "contexts":
        pr["statusCheckRollup"]["contexts"]["pageInfo"]["hasNextPage"] = True
        code = "checks_incomplete"
    else:
        pr[key]["pageInfo"]["hasNextPage"] = True
        code = {
            "reviewThreads": "review_threads_incomplete",
            "comments": "comments_incomplete",
            "reviews": "reviews_incomplete",
            "files": "files_incomplete",
        }[key]
    assert code in _evaluate(pr)["reason_codes"]


def test_live_fetch_fully_paginates_checks_threads_comments_reviews_and_files(monkeypatch):
    cursors_seen: dict[str, list[str | None]] = {
        "checks": [],
        "reviewThreads": [],
        "comments": [],
        "reviews": [],
        "files": [],
    }

    page_nodes = {
        "checks": [_project_check("verify-one"), _project_check("verify-two")],
        "reviewThreads": [
            {"id": "T1", "isResolved": True, "isOutdated": False},
            {"id": "T2", "isResolved": True, "isOutdated": False},
        ],
        "comments": [
            {"id": "C1", "createdAt": "a", "updatedAt": "a", "url": "u", "author": {"login": "a"}},
            {"id": "C2", "createdAt": "b", "updatedAt": "b", "url": "v", "author": {"login": "b"}},
        ],
        "reviews": [_review(), _review(login="keeper-saffron", state="COMMENTED")],
        "files": [
            {"path": "a.py", "changeType": "ADDED", "additions": 1, "deletions": 0},
            {"path": "b.py", "changeType": "MODIFIED", "additions": 2, "deletions": 1},
        ],
    }

    def fake_run(args, **_kwargs):
        if any(str(value).endswith("/branches/main/protection") for value in args):
            return _protection()
        query = next(value.removeprefix("query=") for value in args if value.startswith("query="))
        if "commits(last: 1)" in query:
            return {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "number": PR,
                            "url": "u",
                            "state": "OPEN",
                            "isDraft": False,
                            "headRefOid": HEAD,
                            "baseRefName": "main",
                            "author": {"login": "proposal-author"},
                            "commits": {
                                "nodes": [
                                    {
                                        "commit": {
                                            "oid": HEAD,
                                            "author": {"user": {"login": "keeper-citrine"}},
                                            "committer": {"user": {"login": "keeper-citrine"}},
                                        }
                                    }
                                ]
                            },
                        }
                    }
                }
            }
        if "contexts(first:" in query:
            key, nested = "checks", "statusCheckRollup"
            graph_key = "contexts"
        else:
            nested = None
            for candidate in ("reviewThreads", "comments", "reviews", "files"):
                if f"{candidate}(first:" in query:
                    key = graph_key = candidate
                    break
            else:  # pragma: no cover
                raise AssertionError(query)
        cursor = next(
            (value.removeprefix("cursor=") for value in args if value.startswith("cursor=")),
            None,
        )
        cursors_seen[key].append(cursor)
        index = 0 if cursor is None else 1
        connection = _connection(
            [page_nodes[key][index]],
            has_next=index == 0,
            end_cursor=f"{key}-cursor" if index == 0 else None,
        )
        pull = {"headRefOid": HEAD}
        if nested:
            pull[nested] = {graph_key: connection}
        else:
            pull[graph_key] = connection
        return {"data": {"repository": {"pullRequest": pull}}}

    monkeypatch.setattr(github, "run_gh", fake_run)
    pull = github.fetch_pull_request(REPO, PR)
    assert pull["headCommitIdentity"]["committer"] == "keeper-citrine"
    assert len(pull["statusCheckRollup"]["contexts"]["nodes"]) == 2
    for key in cursors_seen:
        assert cursors_seen[key] == [None, f"{key}-cursor"]


def _rest_check(node):
    """Convert a GraphQL-shaped helper check to REST response keys."""
    return {
        "id": node["databaseId"],
        "name": node["name"],
        "head_sha": node["headSha"],
        "status": node["status"].lower(),
        "conclusion": node["conclusion"].lower(),
        "external_id": node["externalId"],
        "updated_at": node["completedAt"],
        "output": node["output"],
        "app": node["checkSuite"]["app"],
    }


def test_authoritative_publication_stably_updates_and_reads_back_receipt(monkeypatch):
    report = _evaluate(review_gate_app_slug=APP_SLUG)
    old = _rest_check(_app_check(report))
    old["external_id"] = "old-version"
    old["updated_at"] = "2026-07-17T01:00:00Z"
    calls = []
    written = {}

    def fake_run(args, *, timeout=45, input_text=None):
        calls.append((list(args), input_text))
        path = next((arg for arg in args if arg == "installation" or "check-runs" in arg), "")
        if path == "installation":
            return {"app_id": APP_ID, "app_slug": APP_SLUG}
        if "commits/" in path:
            return {"check_runs": [old]}
        if "--method" not in args:
            return old
        method = args[args.index("--method") + 1]
        if method == "PATCH":
            payload = json.loads(input_text)
            written.update(
                {
                    **payload,
                    "id": old["id"],
                    "head_sha": HEAD,
                    "external_id": payload["external_id"],
                    "updated_at": "2026-07-17T01:03:00Z",
                    "app": {"id": APP_ID, "slug": APP_SLUG},
                }
            )
            return written
        if path.endswith(f"check-runs/{old['id']}") and written:
            return written
        raise AssertionError((args, input_text))

    # Distinguish the CAS pre-read from the final readback.
    read_count = 0

    def sequenced_run(args, **kwargs):
        nonlocal read_count
        path = next((arg for arg in args if "check-runs/" in arg and "commits/" not in arg), "")
        if path and "--method" not in args:
            read_count += 1
            if read_count == 1:
                calls.append((list(args), kwargs.get("input_text")))
                return old
            calls.append((list(args), kwargs.get("input_text")))
            return written
        return fake_run(args, **kwargs)

    monkeypatch.setattr(github, "run_gh", sequenced_run)
    github.publish_status(report)

    assert report["publication"]["check_id"] == old["id"]
    assert report["publication"]["receipt_digest"].startswith("sha256:")
    assert any("--method" in args and args[args.index("--method") + 1] == "PATCH" for args, _ in calls)
    assert read_count == 2


def test_publication_cas_rejects_changed_existing_check(monkeypatch):
    report = _evaluate(review_gate_app_slug=APP_SLUG)
    old = _rest_check(_app_check(report))

    def fake_run(args, **_kwargs):
        path = next((arg for arg in args if arg == "installation" or "check-runs" in arg), "")
        if path == "installation":
            return {"app_id": APP_ID, "app_slug": APP_SLUG}
        if "commits/" in path:
            return {"check_runs": [old]}
        if path.endswith(f"check-runs/{old['id']}"):
            return {**old, "updated_at": "changed-concurrently"}
        raise AssertionError(args)

    monkeypatch.setattr(github, "run_gh", fake_run)
    with pytest.raises(model.GateError, match="changed before stable update"):
        github.publish_status(report)


def test_authoritative_publication_requires_live_dedicated_app_credentials_before_check_write(monkeypatch):
    report = _evaluate(review_gate_app_slug=APP_SLUG)
    calls = []
    monkeypatch.setattr(github, "run_gh", lambda args, **_kwargs: calls.append(args) or {})
    with pytest.raises(model.GateError, match="dedicated App installation identity"):
        github.publish_status(report)
    assert calls == [["api", "-H", "Accept: application/vnd.github+json", "installation"]]


def test_fixture_cli_is_read_only(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"repository_name": REPO, "pullRequest": _pr()}), encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = ""
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(PR),
            "--fixture",
            str(fixture),
            "--expected-head",
            HEAD,
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["publication"]["published"] is False


def test_workflow_is_diagnostic_only_and_has_no_local_signer_fallback():
    workflow = (ROOT / ".github/workflows/pr-review-gate.yml").read_text(encoding="utf-8")
    assert "--publish-diagnostic" in workflow
    assert "--publish-status" not in workflow
    assert "LIMEN_REVIEW_ALLOWED_SIGNERS" not in workflow
    assert "--allowed-signers" not in workflow
    assert "gh api --paginate --slurp" in workflow
