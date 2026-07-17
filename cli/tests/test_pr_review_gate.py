"""Hermetic tests for the exact-head peer-review acceptance gate."""

from __future__ import annotations

import importlib.util
import base64
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pr-review-gate.py"
HEAD = "a17c" * 10
OLDER_HEAD = "b29d" * 10
NEWER_HEAD = "c31e" * 10
REPO = "signal-garden/orbit-index"
PR = 731
APP_SLUG = "keeper-review-gate-v7"


def _load():
    spec = importlib.util.spec_from_file_location("pr_review_gate_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _connection(nodes, *, has_next=False):
    return {"pageInfo": {"hasNextPage": has_next}, "nodes": nodes}


def _review(
    *,
    login="keeper-umber",
    state="APPROVED",
    head=HEAD,
    submitted="2026-07-16T18:03:22Z",
    review_id="RVW_heliotrope_09",
    association="COLLABORATOR",
):
    return {
        "id": review_id,
        "author": {"login": login},
        "authorAssociation": association,
        "state": state,
        "commit": {"oid": head},
        "submittedAt": submitted,
        "url": f"https://example.invalid/{review_id}",
    }


def _pr():
    return {
        "number": PR,
        "url": f"https://example.invalid/{REPO}/pull/{PR}",
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": HEAD,
        "author": {"login": "keeper-citrine"},
        "statusCheckRollup": {
            "contexts": _connection(
                [
                    {
                        "__typename": "CheckRun",
                        "name": "quartz-verify",
                        "status": "COMPLETED",
                        "conclusion": "SUCCESS",
                    },
                    {
                        "__typename": "StatusContext",
                        "context": "lattice-build",
                        "state": "SUCCESS",
                    },
                    # The base diagnostic publisher is running while it evaluates
                    # the snapshot; exact workflow provenance keeps this
                    # non-authoritative job from circularly blocking itself.
                    {
                        "__typename": "CheckRun",
                        "name": "limen review-gate diagnostic publisher",
                        "status": "IN_PROGRESS",
                        "conclusion": None,
                        "checkSuite": {
                            "app": {"slug": "github-actions"},
                            "workflowRun": {
                                "event": "pull_request_target",
                                "workflow": {"resourcePath": f"/{REPO}/actions/workflows/pr-review-gate.yml"},
                            },
                        },
                    },
                ]
            )
        },
        "reviewThreads": {
            "pageInfo": {"hasNextPage": False},
            "nodes": [
                {"isResolved": True, "isOutdated": False},
                {"isResolved": False, "isOutdated": True},
            ],
        },
        "comments": _connection([]),
        "reviews": {
            "pageInfo": {"hasNextPage": False},
            "nodes": [
                _review(),
                # COMMENTED is non-decisive and must not erase an active approval.
                _review(
                    state="COMMENTED",
                    submitted="2026-07-16T18:04:22Z",
                    review_id="RVW_indigo_comment",
                ),
            ],
        },
    }


def _signed_receipt_marker(
    tmp_path: Path,
    *,
    decision="APPROVED",
    reviewed_sha=HEAD,
    executing_keeper="keeper-citrine-agent",
    reviewing_keeper="keeper-umber",
    issued_at=None,
    expires_at=None,
    execution_issued_at=None,
    same_signing_key=False,
):
    ssh_keygen = shutil.which("ssh-keygen")
    if ssh_keygen is None:
        pytest.skip("ssh-keygen is required for the signed peer-review fixture")
    now = dt.datetime.now(dt.timezone.utc)
    issued_at = issued_at or now - dt.timedelta(minutes=1)
    expires_at = expires_at or now + dt.timedelta(hours=1)

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

    def make_key(principal):
        key_path = tmp_path / f"{principal}-key"
        subprocess.run(
            [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)],
            check=True,
            capture_output=True,
        )
        return key_path

    def sign(payload_bytes, key_path, namespace, name):
        payload_path = tmp_path / name
        payload_path.write_bytes(payload_bytes)
        subprocess.run(
            [ssh_keygen, "-Y", "sign", "-f", str(key_path), "-n", namespace, str(payload_path)],
            check=True,
            capture_output=True,
        )
        return payload_path.with_suffix(payload_path.suffix + ".sig").read_bytes()

    execution_payload = {
        "schema": "limen.pr_execution_receipt.v1",
        "repository": REPO,
        "pull_request": PR,
        "head_sha": reviewed_sha,
        "executing_keeper": executing_keeper,
        "executing_attempt_id": "attempt-citrine-731",
        "executing_session": "session-citrine-17",
        "trajectory_digest": "sha256:" + "a4" * 32,
        "issued_at": (execution_issued_at or issued_at).isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
    }
    execution_bytes = canonical(execution_payload)
    execution_digest = "sha256:" + hashlib.sha256(execution_bytes).hexdigest()
    payload = {
        "schema": "limen.pr_review_receipt.v1",
        "repository": REPO,
        "pull_request": PR,
        "reviewed_sha": reviewed_sha,
        "executing_keeper": executing_keeper,
        "executing_attempt_id": "attempt-citrine-731",
        "execution_receipt_digest": execution_digest,
        "reviewing_keeper": reviewing_keeper,
        "reviewing_session": "session-umber-09",
        "decision": decision,
        "unresolved_current_thread_count": 0,
        "review_evidence_digest": "sha256:" + "d7" * 32,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
    }
    payload_bytes = canonical(payload)
    execution_key = make_key(executing_keeper)
    review_key = execution_key if same_signing_key else make_key(reviewing_keeper)
    execution_signature = sign(
        execution_bytes,
        execution_key,
        "limen.pr_execution_receipt.v1",
        "execution-receipt.json",
    )
    signature = sign(payload_bytes, review_key, "limen.pr_review_receipt.v1", "review-receipt.json")
    execution_public = execution_key.with_suffix(".pub").read_text(encoding="utf-8").split()
    review_public = review_key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed_signers = tmp_path / "allowed-signers"
    allowed_signers.write_text(
        f"{executing_keeper} {execution_public[0]} {execution_public[1]}\n"
        f"{reviewing_keeper} {review_public[0]} {review_public[1]}\n",
        encoding="utf-8",
    )

    def encode(value):
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    marker = (
        "<!-- limen.pr_execution_receipt.v1 "
        f"payload={encode(execution_bytes)} signature={encode(execution_signature)} -->\n"
        "<!-- limen.pr_review_receipt.v1 "
        f"payload={encode(payload_bytes)} signature={encode(signature)} -->"
    )
    return marker, allowed_signers, payload


def _evaluate(module, pr=None, **kwargs):
    return module.evaluate(
        pr or _pr(),
        repo=REPO,
        number=PR,
        expected_head=kwargs.pop("expected_head", HEAD),
        **kwargs,
    )


def _write_fixture(tmp_path: Path, pr=None) -> Path:
    path = tmp_path / "review-gate-fixture.json"
    path.write_text(
        json.dumps({"repository_name": REPO, "pullRequest": pr or _pr()}),
        encoding="utf-8",
    )
    return path


def test_accepts_exact_head_green_checks_resolved_threads_and_distinct_peer():
    module = _load()
    report = _evaluate(module)

    assert report["schema"] == "limen.pr_review_gate.v1"
    assert report["status"] == report["final_status"] == "accepted"
    assert report["ok"] is True
    assert report["head_sha"] == report["reviewed_sha"] == HEAD
    assert report["executing_keeper"] == "keeper-citrine"
    assert report["reviewing_keeper"] == "keeper-umber"
    assert report["reviewer_receipt"] == {
        "kind": "github_pull_request_review",
        "review_id": "RVW_heliotrope_09",
        "executing_keeper": "keeper-citrine",
        "reviewing_keeper": "keeper-umber",
        "reviewer_association": "COLLABORATOR",
        "reviewed_sha": HEAD,
        "state": "APPROVED",
        "submitted_at": "2026-07-16T18:03:22Z",
        "url": "https://example.invalid/RVW_heliotrope_09",
    }
    assert report["checks"]["total"] == 2
    assert report["checks"]["successful"] == 2
    assert report["review_threads"]["unresolved_current"] == 0
    assert report["review_threads"]["unresolved_outdated"] == 1
    assert report["reason_codes"] == []


def test_fixture_cli_is_read_only_and_emits_v1_json(tmp_path):
    fixture = _write_fixture(tmp_path)
    env = os.environ.copy()
    env["PATH"] = ""  # proves fixture/default mode cannot depend on gh or any helper binary
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
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["schema"] == "limen.pr_review_gate.v1"
    assert report["fixture"] is True
    assert report["publication"] == {"requested": False, "published": False}


def test_expected_head_mismatch_fails_closed():
    report = _evaluate(_load(), expected_head=NEWER_HEAD)
    assert report["status"] == "rejected"
    assert "expected_head_mismatch" in report["reason_codes"]


def test_head_change_during_live_evaluation_fails_closed():
    report = _evaluate(_load(), rechecked_head=NEWER_HEAD)
    assert report["status"] == "rejected"
    assert "head_changed" in report["reason_codes"]


@pytest.mark.parametrize(
    ("node", "reason"),
    [
        (
            {
                "__typename": "CheckRun",
                "name": "renamed-pending-check",
                "status": "IN_PROGRESS",
                "conclusion": None,
            },
            "checks_pending",
        ),
        (
            {
                "__typename": "CheckRun",
                "name": "renamed-failed-check",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            },
            "checks_failed",
        ),
        (
            {"__typename": "UnfamiliarCheckType", "name": "renamed-unknown-check"},
            "checks_unknown",
        ),
    ],
)
def test_non_successful_current_head_checks_fail_closed(node, reason):
    pr = _pr()
    pr["statusCheckRollup"]["contexts"] = _connection([node])
    report = _evaluate(_load(), pr)
    assert report["status"] == "rejected"
    assert reason in report["reason_codes"]


def test_no_non_self_checks_fails_closed():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"] = _connection(
        [
            {
                "__typename": "CheckRun",
                "name": "limen.pr_review_gate.v1",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "checkSuite": {"app": {"slug": APP_SLUG}},
            },
            {
                "__typename": "CheckRun",
                "name": "limen review-gate diagnostic publisher",
                "status": "IN_PROGRESS",
                "conclusion": None,
                "checkSuite": {
                    "app": {"slug": "github-actions"},
                    "workflowRun": {
                        "event": "pull_request_review",
                        "workflow": {"resourcePath": f"/{REPO}/actions/workflows/pr-review-gate.yml"},
                    },
                },
            },
        ]
    )
    report = _evaluate(_load(), pr, review_gate_app_slug=APP_SLUG)
    assert report["status"] == "rejected"
    assert "checks_missing" in report["reason_codes"]


def test_app_bound_previous_gate_check_is_excluded_from_its_next_verdict():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(
        {
            "__typename": "CheckRun",
            "name": "limen.pr_review_gate.v1",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "checkSuite": {"app": {"slug": APP_SLUG}},
        }
    )

    report = _evaluate(_load(), pr, review_gate_app_slug=APP_SLUG)

    assert report["status"] == "accepted"
    assert report["checks"]["total"] == 2


def test_same_named_check_from_another_app_is_not_excluded():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(
        {
            "__typename": "CheckRun",
            "name": "limen.pr_review_gate.v1",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "checkSuite": {"app": {"slug": "untrusted-status-writer"}},
        }
    )

    report = _evaluate(_load(), pr, review_gate_app_slug=APP_SLUG)

    assert report["status"] == "rejected"
    assert "checks_failed" in report["reason_codes"]
    assert "review_gate_producer_untrusted" in report["reason_codes"]
    assert report["checks"]["total"] == 3


def test_generic_actions_same_named_success_is_not_excluded_or_authoritative():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(
        {
            "__typename": "CheckRun",
            "name": "limen.pr_review_gate.v1",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "checkSuite": {"app": {"slug": "github-actions"}},
        }
    )

    report = _evaluate(_load(), pr, review_gate_app_slug=APP_SLUG)

    assert report["status"] == "rejected"
    assert "review_gate_producer_untrusted" in report["reason_codes"]
    assert report["checks"]["total"] == 3
    assert report["checks"]["successful"] == 3


def test_legacy_same_named_status_context_is_not_a_circular_bypass():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(
        {
            "__typename": "StatusContext",
            "context": "limen.pr_review_gate.v1",
            "state": "SUCCESS",
        }
    )

    report = _evaluate(_load(), pr, review_gate_app_slug=APP_SLUG)

    assert report["status"] == "rejected"
    assert "review_gate_producer_untrusted" in report["reason_codes"]
    assert report["checks"]["total"] == 3


def test_dedicated_result_is_untrusted_when_publisher_config_is_missing():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(
        {
            "__typename": "CheckRun",
            "name": "limen.pr_review_gate.v1",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "checkSuite": {"app": {"slug": APP_SLUG}},
        }
    )

    report = _evaluate(_load(), pr)

    assert report["status"] == "rejected"
    assert "review_gate_producer_untrusted" in report["reason_codes"]


def test_generic_actions_diagnostic_result_is_excluded_as_non_authoritative():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"]["nodes"].append(
        {
            "__typename": "CheckRun",
            "name": "limen.pr_review_gate.diagnostic.v1",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "checkSuite": {"app": {"slug": "github-actions"}},
        }
    )

    report = _evaluate(_load(), pr)

    assert report["status"] == "accepted"
    assert report["checks"]["total"] == 2


def test_identically_named_untrusted_publisher_check_is_not_excluded():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"] = _connection(
        [
            {
                "__typename": "CheckRun",
                "name": "quartz-verify",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "limen review-gate diagnostic publisher",
                "status": "IN_PROGRESS",
                "conclusion": None,
                "checkSuite": {
                    "app": {"slug": "github-actions"},
                    "workflowRun": {
                        "event": "pull_request",
                        "workflow": {"resourcePath": f"/{REPO}/actions/workflows/pr-review-gate.yml"},
                    },
                },
            },
        ]
    )

    report = _evaluate(_load(), pr)

    assert report["status"] == "rejected"
    assert "checks_pending" in report["reason_codes"]


def test_manually_dispatched_base_diagnostic_publisher_is_excluded_by_full_provenance():
    pr = _pr()
    pr["statusCheckRollup"]["contexts"] = _connection(
        [
            {
                "__typename": "CheckRun",
                "name": "quartz-verify",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "limen review-gate diagnostic publisher",
                "status": "IN_PROGRESS",
                "conclusion": None,
                "checkSuite": {
                    "app": {"slug": "github-actions"},
                    "workflowRun": {
                        "event": "workflow_dispatch",
                        "workflow": {"resourcePath": f"/{REPO}/actions/workflows/pr-review-gate.yml"},
                    },
                },
            },
        ]
    )

    report = _evaluate(_load(), pr)

    assert report["status"] == "accepted"
    assert report["checks"]["total"] == 1


def test_unresolved_current_thread_fails_but_outdated_thread_does_not():
    pr = _pr()
    pr["reviewThreads"]["nodes"].append({"isResolved": False, "isOutdated": False})
    report = _evaluate(_load(), pr)
    assert report["status"] == "rejected"
    assert report["unresolved_current_thread_count"] == 1
    assert "unresolved_current_threads" in report["reason_codes"]


@pytest.mark.parametrize(
    "review",
    [
        _review(head=OLDER_HEAD),
        _review(login="keeper-citrine"),
        _review(association="NONE"),
    ],
    ids=["stale-head", "same-keeper", "untrusted-association"],
)
def test_stale_or_same_keeper_approval_is_not_a_receipt(review):
    pr = _pr()
    pr["reviews"]["nodes"] = [review]
    report = _evaluate(_load(), pr)
    assert report["status"] == "rejected"
    assert report["reviewer_receipt"] is None
    assert "exact_head_peer_approval_missing" in report["reason_codes"]


def test_same_github_login_can_use_separately_signed_keeper_receipt(tmp_path):
    module = _load()
    marker, allowed_signers, _payload = _signed_receipt_marker(tmp_path)
    pr = _pr()
    pr["author"] = {"login": "shared-operator"}
    pr["reviews"]["nodes"] = [_review(login="shared-operator")]
    pr["comments"] = _connection(
        [
            {
                "id": "IC_signed_umber",
                "body": marker,
                "createdAt": "2026-07-16T18:03:22Z",
                "updatedAt": "2026-07-16T18:03:22Z",
                "url": "https://example.invalid/signed-umber",
            }
        ]
    )

    report = _evaluate(module, pr, allowed_signers=allowed_signers)

    assert report["status"] == "accepted"
    assert report["reviewer_receipt"]["kind"] == "ssh_signed_peer_review"
    assert report["executing_keeper"] == "keeper-citrine-agent"
    assert report["reviewing_keeper"] == "keeper-umber"
    assert report["reviewed_sha"] == HEAD
    assert report["signed_receipts"] == {
        "enabled": True,
        "markers": 2,
        "execution_markers": 1,
        "execution_verified": 1,
        "verified": 1,
        "ignored": 0,
    }


def test_tampered_signed_receipt_cannot_replace_distinct_peer(tmp_path):
    module = _load()
    marker, allowed_signers, _payload = _signed_receipt_marker(tmp_path)
    payload_token = module.SIGNED_RECEIPT_MARKER.search(marker).group("payload")
    tampered_token = payload_token[:10] + ("A" if payload_token[10] != "A" else "B") + payload_token[11:]
    tampered = marker.replace(f"payload={payload_token}", f"payload={tampered_token}", 1)
    pr = _pr()
    pr["reviews"]["nodes"] = [_review(login=pr["author"]["login"])]
    pr["comments"] = _connection([{"id": "IC_tampered", "body": tampered}])

    report = _evaluate(module, pr, allowed_signers=allowed_signers)

    assert report["status"] == "rejected"
    assert "exact_head_peer_approval_missing" in report["reason_codes"]
    assert report["signed_receipts"]["verified"] == 0


def test_signed_review_without_executor_attestation_fails_closed(tmp_path):
    module = _load()
    marker, allowed_signers, _payload = _signed_receipt_marker(tmp_path)
    review_only = marker.splitlines()[-1]
    pr = _pr()
    pr["reviews"]["nodes"] = []
    pr["comments"] = _connection([{"id": "IC_review_only", "body": review_only}])

    report = _evaluate(module, pr, allowed_signers=allowed_signers)

    assert report["status"] == "rejected"
    assert "signed_receipt_invalid" in report["reason_codes"]
    assert "exact_head_peer_approval_missing" in report["reason_codes"]
    assert report["signed_receipts"]["execution_verified"] == 0


def test_signed_review_requires_a_distinct_signing_key_not_only_a_distinct_principal(tmp_path):
    module = _load()
    marker, allowed_signers, _payload = _signed_receipt_marker(tmp_path, same_signing_key=True)
    pr = _pr()
    pr["reviews"]["nodes"] = []
    pr["comments"] = _connection([{"id": "IC_same_key", "body": marker}])

    report = _evaluate(module, pr, allowed_signers=allowed_signers)

    assert report["status"] == "rejected"
    assert "signed_receipt_invalid" in report["reason_codes"]
    assert "exact_head_peer_approval_missing" in report["reason_codes"]
    assert any("distinct signing keys" in reason["message"] for reason in report["reasons"])


def test_signed_review_must_follow_its_bound_execution_receipt(tmp_path):
    module = _load()
    now = dt.datetime.now(dt.timezone.utc)
    marker, allowed_signers, _payload = _signed_receipt_marker(
        tmp_path,
        issued_at=now - dt.timedelta(minutes=2),
        execution_issued_at=now - dt.timedelta(minutes=1),
        expires_at=now + dt.timedelta(hours=1),
    )
    pr = _pr()
    pr["reviews"]["nodes"] = []
    pr["comments"] = _connection([{"id": "IC_presigned_review", "body": marker}])

    report = _evaluate(module, pr, allowed_signers=allowed_signers)

    assert report["status"] == "rejected"
    assert "signed_receipt_invalid" in report["reason_codes"]
    assert any("predates" in reason["message"] for reason in report["reasons"])


def test_signed_review_refuses_mutable_or_indirect_trust_owner(tmp_path):
    module = _load()
    marker, allowed_signers, _payload = _signed_receipt_marker(tmp_path)
    pr = _pr()
    pr["reviews"]["nodes"] = []
    pr["comments"] = _connection([{"id": "IC_signed", "body": marker}])

    allowed_signers.chmod(0o666)
    with pytest.raises(module.GateError, match="group- or world-writable"):
        _evaluate(module, pr, allowed_signers=allowed_signers)

    allowed_signers.chmod(0o600)
    linked = tmp_path / "linked-signers"
    linked.symlink_to(allowed_signers)
    with pytest.raises(module.GateError, match="not a regular file"):
        _evaluate(module, pr, allowed_signers=linked)


def test_signed_changes_request_blocks_native_peer_approval(tmp_path):
    module = _load()
    marker, allowed_signers, _payload = _signed_receipt_marker(tmp_path, decision="CHANGES_REQUESTED")
    pr = _pr()
    pr["comments"] = _connection([{"id": "IC_signed_changes", "body": marker}])

    report = _evaluate(module, pr, allowed_signers=allowed_signers)

    assert report["reviewer_receipt"]["kind"] == "github_pull_request_review"
    assert report["status"] == "rejected"
    assert "changes_requested" in report["reason_codes"]


def test_expired_authenticated_receipt_fails_closed(tmp_path):
    module = _load()
    now = dt.datetime.now(dt.timezone.utc)
    marker, allowed_signers, _payload = _signed_receipt_marker(
        tmp_path,
        issued_at=now - dt.timedelta(hours=2),
        expires_at=now - dt.timedelta(hours=1),
    )
    pr = _pr()
    pr["reviews"]["nodes"] = []
    pr["comments"] = _connection([{"id": "IC_expired", "body": marker}])

    report = _evaluate(module, pr, allowed_signers=allowed_signers)

    assert report["status"] == "rejected"
    assert "signed_receipt_invalid" in report["reason_codes"]
    assert "exact_head_peer_approval_missing" in report["reason_codes"]


def test_later_changes_requested_invalidates_earlier_approval():
    pr = _pr()
    pr["reviews"]["nodes"] = [
        _review(submitted="2026-07-16T18:03:22Z"),
        _review(
            state="CHANGES_REQUESTED",
            submitted="2026-07-16T18:05:22Z",
            review_id="RVW_saffron_changes",
        ),
    ]
    report = _evaluate(_load(), pr)
    assert report["status"] == "rejected"
    assert "exact_head_peer_approval_missing" in report["reason_codes"]


def test_one_peer_cannot_approve_while_another_still_requests_changes():
    pr = _pr()
    pr["reviews"]["nodes"] = [
        _review(login="keeper-umber", review_id="RVW_approved_peer"),
        _review(
            login="keeper-saffron",
            state="CHANGES_REQUESTED",
            submitted="2026-07-16T18:05:22Z",
            review_id="RVW_changes_peer",
        ),
    ]
    report = _evaluate(_load(), pr)
    assert report["status"] == "rejected"
    assert report["reviewer_receipt"] is not None
    assert "changes_requested" in report["reason_codes"]


@pytest.mark.parametrize(
    "connection_path",
    ["checks", "threads", "reviews"],
)
def test_incomplete_graphql_page_fails_closed(connection_path):
    pr = _pr()
    if connection_path == "checks":
        pr["statusCheckRollup"]["contexts"]["pageInfo"]["hasNextPage"] = True
        expected = "checks_incomplete"
    elif connection_path == "threads":
        pr["reviewThreads"]["pageInfo"]["hasNextPage"] = True
        expected = "review_threads_incomplete"
    else:
        pr["reviews"]["pageInfo"]["hasNextPage"] = True
        expected = "reviews_incomplete"
    report = _evaluate(_load(), pr)
    assert report["status"] == "rejected"
    assert expected in report["reason_codes"]


def test_live_default_fetches_two_full_snapshots_but_never_publishes(monkeypatch, capsys):
    module = _load()
    fetched = []

    def fetch(repo, number):
        fetched.append((repo, number))
        return deepcopy(_pr())

    monkeypatch.setattr(module, "fetch_pull_request", fetch)

    def forbidden_publish(report, **kwargs):
        raise AssertionError("default mode must not publish")

    monkeypatch.setattr(module, "publish_status", forbidden_publish)
    code = module.main([str(PR), "--repo", REPO, "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert fetched == [(REPO, PR), (REPO, PR)]
    assert report["rechecked_head_sha"] == HEAD
    assert report["publication"] == {"requested": False, "published": False}


def test_explicit_publish_status_is_the_only_mutation(monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(module, "fetch_pull_request", lambda repo, number: deepcopy(_pr()))
    published = []
    monkeypatch.setattr(module, "publish_status", lambda report, **kwargs: published.append(deepcopy(report)))

    code = module.main(
        [
            str(PR),
            "--repo",
            REPO,
            "--review-gate-app-slug",
            APP_SLUG,
            "--publish-status",
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert len(published) == 1
    assert published[0]["head_sha"] == HEAD
    assert published[0]["publication"]["requested"] is True
    assert report["publication"] == {"requested": True, "published": True}


@pytest.mark.parametrize(
    "publisher_args",
    [[], ["--review-gate-app-slug", "github-actions"]],
    ids=["missing", "generic-actions"],
)
def test_authoritative_publication_requires_a_dedicated_app_identity(publisher_args, monkeypatch, capsys):
    module = _load()
    monkeypatch.delenv("LIMEN_REVIEW_GATE_APP_SLUG", raising=False)

    def forbidden_fetch(repo, number):
        raise AssertionError("invalid publisher identity must fail before live evaluation")

    def forbidden_publish(report, **kwargs):
        raise AssertionError("generic or unidentified publishers must not emit the authoritative schema")

    monkeypatch.setattr(module, "fetch_pull_request", forbidden_fetch)
    monkeypatch.setattr(module, "publish_status", forbidden_publish)
    code = module.main(
        [
            str(PR),
            "--repo",
            REPO,
            "--expected-head",
            HEAD,
            *publisher_args,
            "--publish-status",
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert code == 2
    assert report["status"] == "error"
    assert report["head_sha"] == HEAD
    assert report["publication"] == {"requested": True, "published": False}
    assert "dedicated" in report["reasons"][0]["message"]


def test_base_actions_can_publish_only_the_non_authoritative_diagnostic(monkeypatch, capsys):
    module = _load()
    monkeypatch.delenv("LIMEN_REVIEW_GATE_APP_SLUG", raising=False)
    monkeypatch.setattr(module, "fetch_pull_request", lambda repo, number: deepcopy(_pr()))
    published = []

    def publish(report, *, check_name, publisher_app_slug):
        published.append((deepcopy(report), check_name))

    monkeypatch.setattr(module, "publish_status", publish)
    code = module.main([str(PR), "--repo", REPO, "--publish-diagnostic", "--json"])
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert report["publication"] == {"requested": True, "published": True}
    assert len(published) == 1
    assert published[0][1] == "limen.pr_review_gate.diagnostic.v1"
    assert published[0][0]["status"] == "accepted"


def test_operational_error_overwrites_old_success_with_exact_head_failure(monkeypatch, capsys):
    module = _load()
    fetch_count = 0

    def fetch(repo, number):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 2:
            raise module.GateError("simulated final-snapshot outage")
        return deepcopy(_pr())

    monkeypatch.setattr(module, "fetch_pull_request", fetch)
    published = []
    monkeypatch.setattr(module, "publish_status", lambda report, **kwargs: published.append(deepcopy(report)))

    code = module.main(
        [
            str(PR),
            "--repo",
            REPO,
            "--review-gate-app-slug",
            APP_SLUG,
            "--publish-status",
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert code == 2
    assert report["status"] == "error"
    assert report["head_sha"] == HEAD
    assert report["publication"] == {"requested": True, "published": True}
    assert len(published) == 1
    assert published[0]["status"] == "error"
    assert published[0]["head_sha"] == HEAD


def test_same_head_later_change_request_cannot_publish_stale_approval(monkeypatch, capsys):
    module = _load()
    initial = _pr()
    final = deepcopy(initial)
    final["reviews"]["nodes"].append(
        _review(
            state="CHANGES_REQUESTED",
            submitted="2026-07-16T18:05:22Z",
            review_id="RVW_same_head_changes",
        )
    )
    snapshots = iter([initial, final])
    monkeypatch.setattr(module, "fetch_pull_request", lambda repo, number: deepcopy(next(snapshots)))
    published = []
    monkeypatch.setattr(module, "publish_status", lambda report, **kwargs: published.append(deepcopy(report)))

    code = module.main(
        [
            str(PR),
            "--repo",
            REPO,
            "--review-gate-app-slug",
            APP_SLUG,
            "--publish-status",
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert code == 1
    assert report["head_sha"] == report["rechecked_head_sha"] == HEAD
    assert report["status"] == "rejected"
    assert "changes_requested" in report["reason_codes"]
    assert published[0]["status"] == "rejected"


@pytest.mark.parametrize(
    ("same_head_change", "reason"),
    [("thread_unresolved", "unresolved_current_threads"), ("check_failed", "checks_failed")],
)
def test_same_head_final_snapshot_invalidates_changed_acceptance_inputs(same_head_change, reason, monkeypatch, capsys):
    module = _load()
    initial = _pr()
    final = deepcopy(initial)
    if same_head_change == "thread_unresolved":
        final["reviewThreads"]["nodes"].append({"isResolved": False, "isOutdated": False})
    else:
        final["statusCheckRollup"]["contexts"]["nodes"][0]["conclusion"] = "FAILURE"
    snapshots = iter([initial, final])
    monkeypatch.setattr(module, "fetch_pull_request", lambda repo, number: deepcopy(next(snapshots)))
    published = []
    monkeypatch.setattr(module, "publish_status", lambda report, **kwargs: published.append(deepcopy(report)))

    code = module.main(
        [
            str(PR),
            "--repo",
            REPO,
            "--review-gate-app-slug",
            APP_SLUG,
            "--publish-status",
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert code == 1
    assert report["head_sha"] == report["rechecked_head_sha"] == HEAD
    assert reason in report["reason_codes"]
    assert published[0]["status"] == "rejected"


def test_initial_fetch_failure_publishes_failure_on_known_expected_head(monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(
        module,
        "fetch_pull_request",
        lambda repo, number: (_ for _ in ()).throw(module.GateError("simulated initial-snapshot outage")),
    )
    published = []
    monkeypatch.setattr(module, "publish_status", lambda report, **kwargs: published.append(deepcopy(report)))

    code = module.main(
        [
            str(PR),
            "--repo",
            REPO,
            "--expected-head",
            HEAD,
            "--review-gate-app-slug",
            APP_SLUG,
            "--publish-status",
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert code == 2
    assert report["status"] == "error"
    assert report["head_sha"] == HEAD
    assert report["publication"] == {"requested": True, "published": True}
    assert len(published) == 1
    assert published[0]["status"] == "error"
    assert published[0]["head_sha"] == HEAD


def test_publish_uses_exact_head_and_named_app_check(monkeypatch):
    module = _load()
    calls = []
    monkeypatch.setattr(
        module,
        "run_gh",
        lambda args, timeout=45: calls.append(list(args)) or {"app": {"slug": APP_SLUG}},
    )
    report = _evaluate(module)

    module.publish_status(report, publisher_app_slug=APP_SLUG)

    assert len(calls) == 1
    args = calls[0]
    assert args[:3] == ["api", "--method", "POST"]
    assert f"repos/{REPO}/check-runs" in args
    assert "name=limen.pr_review_gate.v1" in args
    assert f"head_sha={HEAD}" in args
    assert "status=completed" in args
    assert "conclusion=success" in args


@pytest.mark.parametrize("publisher_app_slug", [None, "github-actions"])
def test_publish_function_refuses_authoritative_schema_without_dedicated_app(monkeypatch, publisher_app_slug):
    module = _load()
    calls = []
    monkeypatch.setattr(module, "run_gh", lambda args, timeout=45: calls.append(list(args)) or {})

    with pytest.raises(module.GateError, match="dedicated"):
        module.publish_status(_evaluate(module), publisher_app_slug=publisher_app_slug)

    assert calls == []


def test_publish_function_names_actions_output_as_diagnostic(monkeypatch):
    module = _load()
    calls = []
    monkeypatch.setattr(
        module,
        "run_gh",
        lambda args, timeout=45: calls.append(list(args)) or {"app": {"slug": "github-actions"}},
    )

    module.publish_status(_evaluate(module), check_name=module.DIAGNOSTIC_SCHEMA)

    assert len(calls) == 1
    assert "name=limen.pr_review_gate.diagnostic.v1" in calls[0]
    assert "output[title]=limen.pr_review_gate.diagnostic.v1" in calls[0]
    assert "name=limen.pr_review_gate.v1" not in calls[0]


def test_authoritative_publication_verifies_the_actual_response_app(monkeypatch):
    module = _load()
    calls = []
    monkeypatch.setattr(
        module,
        "run_gh",
        lambda args, timeout=45: calls.append(list(args)) or {"app": {"slug": "github-actions"}},
    )

    with pytest.raises(module.GateError, match="expected keeper-review-gate-v7"):
        module.publish_status(_evaluate(module), publisher_app_slug=APP_SLUG)

    assert len(calls) == 1


def test_fixture_cannot_be_used_to_publish(tmp_path):
    fixture = _write_fixture(tmp_path)
    env = os.environ.copy()
    env["PATH"] = ""
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(PR),
            "--fixture",
            str(fixture),
            "--publish-status",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 2
    report = json.loads(proc.stdout)
    assert report["status"] == "error"
    assert "--fixture cannot be combined" in report["reasons"][0]["message"]


def test_quiet_suppresses_human_output_but_json_remains_explicit(tmp_path):
    fixture = _write_fixture(tmp_path)
    quiet = subprocess.run(
        [sys.executable, str(SCRIPT), str(PR), "--fixture", str(fixture), "--quiet"],
        capture_output=True,
        text=True,
    )
    explicit_json = subprocess.run(
        [sys.executable, str(SCRIPT), str(PR), "--fixture", str(fixture), "--quiet", "--json"],
        capture_output=True,
        text=True,
    )
    assert quiet.returncode == 0 and quiet.stdout == ""
    assert explicit_json.returncode == 0
    assert json.loads(explicit_json.stdout)["status"] == "accepted"


def test_scheduled_refresh_paginates_every_open_pr():
    workflow = (ROOT / ".github" / "workflows" / "pr-review-gate.yml").read_text(encoding="utf-8")

    assert "gh api --paginate --slurp" in workflow
    assert "repos/${GITHUB_REPOSITORY}/pulls?state=open&per_page=100" in workflow
    assert "gh pr list --state open --limit 100" not in workflow


def test_workflow_serializes_event_and_scheduled_refresh_per_pr_and_fails_on_errors():
    workflow = (ROOT / ".github" / "workflows" / "pr-review-gate.yml").read_text(encoding="utf-8")

    assert "github.event.issue.number" in workflow
    assert "group: pr-review-gate-${{ matrix.number }}" in workflow
    assert '*) exit "$rc"' in workflow
    assert "rejected_or_error" not in workflow


def test_base_workflow_publishes_only_a_clearly_non_authoritative_diagnostic():
    workflow = (ROOT / ".github" / "workflows" / "pr-review-gate.yml").read_text(encoding="utf-8")

    assert "limen review-gate diagnostic publisher" in workflow
    assert "--publish-diagnostic" in workflow
    assert "--publish-status" not in workflow
    assert "vars.LIMEN_REVIEW_GATE_APP_SLUG" in workflow
    assert '--review-gate-app-slug "$LIMEN_REVIEW_GATE_APP_SLUG"' in workflow
    assert "non-authoritative" in workflow
    assert "required limen.pr_review_gate.v1 CheckRun is reserved" in workflow
    assert "current app-bound result" not in workflow


def test_workflow_refreshes_signed_pr_comments_from_owner_injected_trust_root():
    workflow = (ROOT / ".github" / "workflows" / "pr-review-gate.yml").read_text(encoding="utf-8")

    assert "issue_comment:" in workflow
    assert "github.event.issue.pull_request" in workflow
    assert "vars.LIMEN_REVIEW_ALLOWED_SIGNERS_B64" in workflow
    assert '--allowed-signers "$signer_file"' in workflow
