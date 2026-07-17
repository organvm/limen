"""Pure, fixture-friendly semantics for the exact-head review gate."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

from limen.remote_predicate import canonical_json


SCHEMA = "limen.pr_review_gate.v1"
DIAGNOSTIC_SCHEMA = "limen.pr_review_gate.diagnostic.v1"
CHECK_RECEIPT_SCHEMA = "limen.pr_review_gate.check_receipt.v1"
GENERIC_ACTIONS_APP_SLUG = "github-actions"
RECEIPT_KIND = "github_pull_request_review"
PUBLISHER_CHECK_NAME = "limen review-gate diagnostic publisher"
TERMINAL_SUCCESS_CONCLUSIONS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})
TRUSTED_REVIEW_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
MAX_REPORT_CHECK_CONTEXTS = 200
HEAD_SHA = re.compile(r"^[0-9a-f]{40}$")
APP_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")


class GateError(RuntimeError):
    """Operational or input failure; acceptance must fail closed."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def report_evidence_digest(report: dict[str, Any]) -> str:
    return canonical_digest(
        {
            "repository": report.get("repository"),
            "pull_request": report.get("pull_request"),
            "head_sha": report.get("head_sha"),
            "executing_keeper": report.get("executing_keeper"),
            "execution_identity_source": report.get("execution_identity_source"),
            "last_push_authority": report.get("last_push_authority"),
            "snapshot_digest": report.get("snapshot_digest"),
            "checks": report.get("checks"),
            "review_threads": report.get("review_threads"),
            "reviewer_receipt": report.get("reviewer_receipt"),
            "files": report.get("files"),
            "comments": report.get("comments"),
        }
    )


def configured_review_gate_app_slug(value: str | None) -> str | None:
    """Validate a dedicated App identity, never the shared Actions App."""

    if value is None or not value.strip():
        return None
    slug = value.strip()
    if not APP_SLUG.fullmatch(slug):
        raise GateError("review-gate App slug is invalid")
    if slug == GENERIC_ACTIONS_APP_SLUG:
        raise GateError("review-gate App slug must identify a dedicated App, not generic github-actions")
    return slug


def configured_review_gate_app_id(value: int | str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        app_id = int(value)
    except (TypeError, ValueError) as exc:
        raise GateError("review-gate App id is invalid") from exc
    if isinstance(value, bool) or app_id <= 0:
        raise GateError("review-gate App id must be positive")
    return app_id


def _connection(container: Any, key: str) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(container, dict) or not isinstance(container.get(key), dict):
        return [], False
    connection = container[key]
    nodes = connection.get("nodes")
    page_info = connection.get("pageInfo")
    if not isinstance(nodes, list) or not isinstance(page_info, dict):
        return [], False
    if page_info.get("hasNextPage") is not False:
        return [node for node in nodes if isinstance(node, dict)], False
    if any(not isinstance(node, dict) for node in nodes):
        return [], False
    return list(nodes), True


def _check_app_slug(node: dict[str, Any]) -> str:
    suite = node.get("checkSuite")
    app = suite.get("app") if isinstance(suite, dict) else None
    if not isinstance(app, dict):
        app = node.get("app")
    return str(app.get("slug") or "") if isinstance(app, dict) else ""


def _trusted_diagnostic_publisher(node: dict[str, Any], repo: str) -> bool:
    if node.get("__typename") != "CheckRun" or node.get("name") != PUBLISHER_CHECK_NAME:
        return False
    suite = node.get("checkSuite")
    run = suite.get("workflowRun") if isinstance(suite, dict) else None
    workflow = run.get("workflow") if isinstance(run, dict) else None
    event = str(run.get("event") or "") if isinstance(run, dict) else ""
    return bool(
        _check_app_slug(node) == GENERIC_ACTIONS_APP_SLUG
        and isinstance(workflow, dict)
        and workflow.get("resourcePath") == f"/{repo}/actions/workflows/pr-review-gate.yml"
        and event
        in {
            "pull_request_target",
            "pull_request_review",
            "pull_request_review_comment",
            "issue_comment",
            "schedule",
            "workflow_dispatch",
        }
    )


def make_check_receipt(report: dict[str, Any]) -> dict[str, Any]:
    """Build the complete bounded receipt stored in the App CheckRun."""

    # Publication state is the transport envelope, not an acceptance input. All
    # other bounded v1 report fields are retained verbatim so a consumer can
    # reproduce the adjudication instead of trusting a hand-copied status string.
    receipt = {key: value for key, value in report.items() if key != "publication"}
    return {
        "schema": CHECK_RECEIPT_SCHEMA,
        "digest": canonical_digest(receipt),
        "receipt": receipt,
    }


def check_receipt_summary(report: dict[str, Any]) -> str:
    return canonical_json(make_check_receipt(report)).decode("utf-8")


def _parse_check_receipt_summary(summary: Any) -> dict[str, Any] | None:
    if not isinstance(summary, str) or not summary or len(summary.encode("utf-8")) > 65_535:
        return None
    try:
        value = json.loads(summary)
    except ValueError:
        return None
    if not isinstance(value, dict) or set(value) != {"schema", "digest", "receipt"}:
        return None
    receipt = value.get("receipt")
    if value.get("schema") != CHECK_RECEIPT_SCHEMA or not isinstance(receipt, dict):
        return None
    if value.get("digest") != canonical_digest(receipt):
        return None
    return value


def validate_check_run_receipt(
    node: dict[str, Any],
    *,
    repo: str,
    number: int,
    head: str,
    app_slug: str,
    require_success: bool,
) -> tuple[bool, str]:
    """Authenticate and read back one App-bound exact-head gate receipt."""

    if node.get("name") != SCHEMA or _check_app_slug(node) != app_slug:
        return False, "check is not owned by the configured review-gate App"
    observed_head = str(node.get("headSha") or node.get("head_sha") or "")
    if observed_head != head:
        return False, "check receipt is not bound to the current head"
    if str(node.get("status") or "").upper() != "COMPLETED":
        return False, "review-gate App check is not completed"
    conclusion = str(node.get("conclusion") or "").upper()
    if require_success and conclusion != "SUCCESS":
        return False, "review-gate App check is not successful"
    output = node.get("output")
    summary = output.get("summary") if isinstance(output, dict) else None
    envelope = _parse_check_receipt_summary(summary)
    if envelope is None:
        return False, "review-gate App check has no valid bounded receipt"
    receipt = envelope["receipt"]
    required_report_fields = {
        "schema",
        "status",
        "final_status",
        "ok",
        "evaluated_at",
        "repository",
        "pull_request",
        "url",
        "fixture",
        "expected_head",
        "head_sha",
        "rechecked_head_sha",
        "snapshot_digest",
        "rechecked_snapshot_digest",
        "reviewed_sha",
        "executing_keeper",
        "execution_identity_source",
        "last_push_authority",
        "reviewing_keeper",
        "reviewer_receipt",
        "signed_receipts",
        "unresolved_current_thread_count",
        "checks",
        "published_gate",
        "review_threads",
        "files",
        "comments",
        "evidence_digest",
        "reason_codes",
        "reasons",
    }
    if set(receipt) != required_report_fields:
        return False, "review-gate App receipt is not the complete bounded v1 report"
    if (
        receipt.get("schema") != SCHEMA
        or receipt.get("repository") != repo
        or receipt.get("pull_request") != number
        or receipt.get("head_sha") != head
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(receipt.get("evidence_digest") or ""))
    ):
        return False, "review-gate App receipt target or evidence digest is invalid"
    if receipt.get("status") == "accepted" and receipt.get("reviewed_sha") != head:
        return False, "accepted review-gate App receipt is not reviewed on the current head"
    reasons = receipt.get("reasons")
    reason_codes = receipt.get("reason_codes")
    if (
        receipt.get("final_status") != receipt.get("status")
        or receipt.get("ok") is not (receipt.get("status") == "accepted")
        or not isinstance(reasons, list)
        or any(not isinstance(reason, dict) for reason in reasons)
        or reason_codes != [reason.get("code") for reason in reasons]
    ):
        return False, "review-gate App receipt adjudication fields disagree"
    if receipt.get("evidence_digest") != report_evidence_digest(receipt):
        return False, "review-gate App receipt evidence digest is not reproducible"
    if receipt.get("status") == "accepted":
        checks = receipt.get("checks")
        reviewer = receipt.get("reviewer_receipt")
        threads = receipt.get("review_threads")
        if (
            reasons
            or receipt.get("fixture") is not False
            or receipt.get("rechecked_head_sha") != head
            or receipt.get("snapshot_digest") != receipt.get("rechecked_snapshot_digest")
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(receipt.get("snapshot_digest") or ""))
            or receipt.get("unresolved_current_thread_count") != 0
            or not isinstance(checks, dict)
            or checks.get("total", 0) <= 0
            or any(checks.get(field) != 0 for field in ("pending", "failed", "unknown"))
            or not isinstance(threads, dict)
            or threads.get("unresolved_current") != 0
            or not isinstance(reviewer, dict)
            or reviewer.get("kind") != RECEIPT_KIND
            or reviewer.get("state") != "APPROVED"
            or reviewer.get("reviewed_sha") != head
            or reviewer.get("executing_keeper") != receipt.get("executing_keeper")
            or reviewer.get("reviewing_keeper") != receipt.get("reviewing_keeper")
            or str(reviewer.get("reviewing_keeper") or "").casefold()
            == str(reviewer.get("executing_keeper") or "").casefold()
            or reviewer.get("reviewer_association") not in TRUSTED_REVIEW_ASSOCIATIONS
            or receipt.get("execution_identity_source") not in {"head_commit_committer", "head_commit_author"}
            or receipt.get("last_push_authority")
            != {
                "source": "github_native_branch_protection",
                "require_last_push_approval": True,
                "login": None,
            }
        ):
            return False, "accepted review-gate App receipt contains failing acceptance evidence"
    expected_external_id = f"{CHECK_RECEIPT_SCHEMA}:{envelope['digest']}"
    external_id = str(node.get("externalId") or node.get("external_id") or "")
    if external_id != expected_external_id:
        return False, "review-gate App receipt digest does not match external_id"
    expected_conclusion = "SUCCESS" if receipt.get("status") == "accepted" else "FAILURE"
    if conclusion != expected_conclusion:
        return False, "review-gate App conclusion disagrees with its receipt"
    if require_success and receipt.get("status") != "accepted":
        return False, "review-gate App receipt is not accepted"
    return True, ""


def _published_result(
    nodes: list[dict[str, Any]],
    *,
    repo: str,
    number: int,
    head: str,
    app_slug: str | None,
    required: bool,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    authenticated = [
        node
        for node in nodes
        if node.get("__typename") == "CheckRun"
        and node.get("name") == SCHEMA
        and app_slug is not None
        and _check_app_slug(node) == app_slug
    ]
    authenticated.sort(
        key=lambda node: (
            str(node.get("completedAt") or node.get("startedAt") or ""),
            int(node.get("databaseId") or 0),
        )
    )
    latest = authenticated[-1] if authenticated else None
    valid = False
    detail = ""
    receipt_evidence_digest = None
    if latest is not None and app_slug is not None:
        valid, detail = validate_check_run_receipt(
            latest,
            repo=repo,
            number=number,
            head=head,
            app_slug=app_slug,
            require_success=True,
        )
        output = latest.get("output")
        envelope = _parse_check_receipt_summary(output.get("summary") if isinstance(output, dict) else None)
        if envelope is not None:
            receipt_evidence_digest = envelope["receipt"].get("evidence_digest")
    if required:
        if app_slug is None:
            errors.append(
                {
                    "code": "review_gate_app_unconfigured",
                    "message": "consumer requires an explicit dedicated review-gate App identity",
                }
            )
        elif latest is None:
            errors.append(
                {
                    "code": "published_review_gate_missing",
                    "message": "the dedicated App has not published a current-head review receipt",
                }
            )
        elif not valid:
            errors.append({"code": "published_review_gate_invalid", "message": detail})
    return (
        {
            "required": required,
            "app_slug": app_slug,
            "authenticated_count": len(authenticated),
            "valid_success": valid,
            "check_id": latest.get("databaseId") if latest else None,
            "receipt_evidence_digest": receipt_evidence_digest,
        },
        errors,
    )


def _check_summary(
    pr: dict[str, Any],
    *,
    repo: str,
    number: int,
    head: str,
    review_gate_app_slug: str | None,
    require_published_result: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    rollup = pr.get("statusCheckRollup")
    nodes, complete = _connection(rollup, "contexts")
    if not complete:
        errors.append({"code": "checks_incomplete", "message": "current-head check pagination is incomplete"})

    published, published_errors = _published_result(
        nodes,
        repo=repo,
        number=number,
        head=head,
        app_slug=review_gate_app_slug,
        required=require_published_result,
    )
    errors.extend(published_errors)
    rows: list[dict[str, str]] = []
    successful = pending = failed = unknown = ignored_untrusted_gate_markers = 0
    for node in nodes:
        kind = str(node.get("__typename") or "")
        name = str(node.get("name") or node.get("context") or "")
        if name == SCHEMA:
            # Authenticate before counting or parsing. Lookalike contexts cannot create a
            # pre-authentication resource or liveness denial.
            if kind == "CheckRun" and review_gate_app_slug and _check_app_slug(node) == review_gate_app_slug:
                continue
            ignored_untrusted_gate_markers += 1
            continue
        if name == DIAGNOSTIC_SCHEMA and kind == "CheckRun" and _check_app_slug(node) == GENERIC_ACTIONS_APP_SLUG:
            continue
        if _trusted_diagnostic_publisher(node, repo):
            continue
        if kind == "CheckRun":
            status = str(node.get("status") or "").upper()
            conclusion = str(node.get("conclusion") or "").upper()
            if status != "COMPLETED":
                classification = "pending"
                pending += 1
            elif conclusion in TERMINAL_SUCCESS_CONCLUSIONS:
                classification = "successful"
                successful += 1
            elif conclusion:
                classification = "failed"
                failed += 1
            else:
                classification = "unknown"
                unknown += 1
            rows.append(
                {
                    "kind": "check_run",
                    "name": name,
                    "status": status,
                    "conclusion": conclusion,
                    "classification": classification,
                }
            )
        elif kind == "StatusContext":
            state = str(node.get("state") or "").upper()
            if state == "SUCCESS":
                classification = "successful"
                successful += 1
            elif state in {"PENDING", "EXPECTED"}:
                classification = "pending"
                pending += 1
            elif state:
                classification = "failed"
                failed += 1
            else:
                classification = "unknown"
                unknown += 1
            rows.append(
                {
                    "kind": "status_context",
                    "name": name,
                    "state": state,
                    "classification": classification,
                }
            )
        else:
            unknown += 1
            rows.append({"kind": "unknown", "name": name, "classification": "unknown"})

    if complete and not rows:
        errors.append({"code": "checks_missing", "message": "no project checks exist on the current head"})
    if pending:
        errors.append({"code": "checks_pending", "message": f"{pending} current-head check(s) are pending"})
    if failed:
        errors.append({"code": "checks_failed", "message": f"{failed} current-head check(s) failed"})
    if unknown:
        errors.append({"code": "checks_unknown", "message": f"{unknown} current-head check(s) have unknown state"})
    contexts_digest = canonical_digest(rows)
    return (
        {
            "total": len(rows),
            "successful": successful,
            "pending": pending,
            "failed": failed,
            "unknown": unknown,
            "ignored_untrusted_gate_markers": ignored_untrusted_gate_markers,
            "contexts_digest": contexts_digest,
            "contexts": rows[:MAX_REPORT_CHECK_CONTEXTS],
            "contexts_truncated": max(0, len(rows) - MAX_REPORT_CHECK_CONTEXTS),
        },
        published,
        errors,
    )


def _thread_summary(pr: dict[str, Any]) -> tuple[dict[str, int], list[dict[str, str]]]:
    nodes, complete = _connection(pr, "reviewThreads")
    errors: list[dict[str, str]] = []
    if not complete:
        errors.append({"code": "review_threads_incomplete", "message": "review-conversation pagination is incomplete"})
    resolved = unresolved_current = unresolved_outdated = 0
    for node in nodes:
        if node.get("isResolved") is True:
            resolved += 1
        elif node.get("isOutdated") is True:
            unresolved_outdated += 1
        else:
            unresolved_current += 1
    if unresolved_current:
        errors.append(
            {
                "code": "unresolved_current_threads",
                "message": f"{unresolved_current} current review conversation(s) are unresolved",
            }
        )
    return (
        {
            "total": len(nodes),
            "resolved": resolved,
            "unresolved_current": unresolved_current,
            "unresolved_outdated": unresolved_outdated,
        },
        errors,
    )


def _latest_decisive_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, tuple[str, int, dict[str, Any]]] = {}
    for index, review in enumerate(reviews):
        state = str(review.get("state") or "").upper()
        author = review.get("author")
        login = str(author.get("login") or "") if isinstance(author, dict) else ""
        if state not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"} or not login:
            continue
        submitted = str(review.get("submittedAt") or "")
        key = login.casefold()
        previous = latest.get(key)
        if previous is None or (submitted, index) >= (previous[0], previous[1]):
            latest[key] = (submitted, index, review)
    return [entry[2] for entry in sorted(latest.values(), key=lambda entry: (entry[0], entry[1]))]


def _execution_identity(pr: dict[str, Any]) -> tuple[str, str]:
    identity = pr.get("headCommitIdentity")
    if not isinstance(identity, dict):
        return "", ""
    committer = str(identity.get("committer") or "")
    author = str(identity.get("author") or "")
    if committer:
        return committer, "head_commit_committer"
    if author:
        return author, "head_commit_author"
    return "", ""


def _review_receipt(
    pr: dict[str, Any],
    *,
    head: str,
    executing_keeper: str,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    reviews, complete = _connection(pr, "reviews")
    errors: list[dict[str, str]] = []
    if not complete:
        errors.append({"code": "reviews_incomplete", "message": "peer-review pagination is incomplete"})
    latest = _latest_decisive_reviews(reviews)
    changes = [review for review in latest if str(review.get("state") or "").upper() == "CHANGES_REQUESTED"]
    if changes:
        errors.append({"code": "changes_requested", "message": f"{len(changes)} active peer review(s) request changes"})
    candidates: list[dict[str, Any]] = []
    for review in latest:
        if str(review.get("state") or "").upper() != "APPROVED":
            continue
        author = review.get("author")
        reviewer = str(author.get("login") or "") if isinstance(author, dict) else ""
        commit = review.get("commit")
        reviewed_sha = str(commit.get("oid") or "") if isinstance(commit, dict) else ""
        association = str(review.get("authorAssociation") or "").upper()
        if (
            not reviewer
            or not executing_keeper
            or reviewer.casefold() == executing_keeper.casefold()
            or association not in TRUSTED_REVIEW_ASSOCIATIONS
            or reviewed_sha != head
        ):
            continue
        candidates.append(
            {
                "kind": RECEIPT_KIND,
                "review_id": str(review.get("id") or ""),
                "executing_keeper": executing_keeper,
                "reviewing_keeper": reviewer,
                "reviewer_association": association,
                "reviewed_sha": reviewed_sha,
                "state": "APPROVED",
                "submitted_at": str(review.get("submittedAt") or ""),
                "url": str(review.get("url") or ""),
            }
        )
    if not candidates:
        errors.append(
            {
                "code": "exact_head_peer_approval_missing",
                "message": "no native reviewer distinct from the head-commit executor approved the exact head",
            }
        )
        return None, errors
    return max(candidates, key=lambda row: (row["submitted_at"], row["review_id"])), errors


def _bounded_connection_digest(pr: dict[str, Any], key: str) -> tuple[int, str | None, bool]:
    nodes, complete = _connection(pr, key)
    return len(nodes), canonical_digest(nodes) if complete else None, complete


def snapshot_digest(
    pr: dict[str, Any],
    *,
    repo: str,
    review_gate_app_slug: str | None,
) -> str:
    """Digest only acceptance inputs, excluding the gate's own outputs."""

    rollup = pr.get("statusCheckRollup")
    check_nodes, checks_complete = _connection(rollup, "contexts")
    project_checks = []
    for node in check_nodes:
        name = str(node.get("name") or node.get("context") or "")
        if name == SCHEMA:
            continue
        if name == DIAGNOSTIC_SCHEMA and _check_app_slug(node) == GENERIC_ACTIONS_APP_SLUG:
            continue
        if _trusted_diagnostic_publisher(node, repo):
            continue
        project_checks.append(node)
    connections = {}
    for key in ("reviewThreads", "comments", "reviews", "files"):
        nodes, complete = _connection(pr, key)
        connections[key] = {"complete": complete, "nodes": nodes}
    return canonical_digest(
        {
            "number": pr.get("number"),
            "url": pr.get("url"),
            "state": pr.get("state"),
            "isDraft": pr.get("isDraft"),
            "headRefOid": pr.get("headRefOid"),
            "author": pr.get("author"),
            "headCommitIdentity": pr.get("headCommitIdentity"),
            "checks": {"complete": checks_complete, "nodes": project_checks},
            **connections,
        }
    )


def evaluate(
    pr: dict[str, Any],
    *,
    repo: str,
    number: int,
    expected_head: str | None = None,
    rechecked_head: str | None = None,
    rechecked_snapshot_digest: str | None = None,
    fixture: bool = False,
    allowed_signers: Any = None,
    review_gate_app_slug: str | None = None,
    require_published_result: bool = False,
) -> dict[str, Any]:
    """Evaluate one complete snapshot without side effects."""

    reasons: list[dict[str, str]] = []
    if allowed_signers is not None:
        reasons.append(
            {
                "code": "signed_fallback_unavailable",
                "message": "local allowed-signers files are not an authenticated production custody source",
            }
        )
    head = str(pr.get("headRefOid") or "")
    if int(pr.get("number") or 0) != number:
        reasons.append({"code": "pull_request_mismatch", "message": "response PR number differs"})
    if str(pr.get("state") or "").upper() != "OPEN":
        reasons.append({"code": "pull_request_not_open", "message": "pull request is not open"})
    if pr.get("isDraft") is not False:
        reasons.append({"code": "pull_request_draft", "message": "pull request is draft or unknown"})
    if not HEAD_SHA.fullmatch(head):
        reasons.append({"code": "head_unavailable", "message": "full current head SHA is unavailable"})
    if expected_head is not None and head != expected_head:
        reasons.append({"code": "expected_head_mismatch", "message": "expected and observed heads differ"})
    if rechecked_head is not None and head != rechecked_head:
        reasons.append({"code": "head_changed", "message": "PR head changed between complete snapshots"})
    final_snapshot_digest = snapshot_digest(
        pr,
        repo=repo,
        review_gate_app_slug=review_gate_app_slug,
    )
    if rechecked_snapshot_digest is not None and final_snapshot_digest != rechecked_snapshot_digest:
        reasons.append(
            {
                "code": "acceptance_evidence_changed",
                "message": "checks, conversations, comments, reviews, files, or identity changed between snapshots",
            }
        )

    executing_keeper, execution_source = _execution_identity(pr)
    if not executing_keeper:
        reasons.append(
            {
                "code": "executor_identity_unavailable",
                "message": "head commit has no GitHub committer or author identity",
            }
        )
    checks, published, check_errors = _check_summary(
        pr,
        repo=repo,
        number=number,
        head=head,
        review_gate_app_slug=review_gate_app_slug,
        require_published_result=require_published_result,
    )
    threads, thread_errors = _thread_summary(pr)
    receipt, review_errors = _review_receipt(pr, head=head, executing_keeper=executing_keeper)
    reasons.extend(check_errors)
    reasons.extend(thread_errors)
    reasons.extend(review_errors)

    files_count, files_digest, files_complete = _bounded_connection_digest(pr, "files")
    comments_count, comments_digest, comments_complete = _bounded_connection_digest(pr, "comments")
    if not files_complete:
        reasons.append({"code": "files_incomplete", "message": "changed-file pagination is incomplete"})
    if not comments_complete:
        reasons.append({"code": "comments_incomplete", "message": "comment pagination is incomplete"})

    evidence = {
        "repository": repo,
        "pull_request": number,
        "head_sha": head,
        "executing_keeper": executing_keeper,
        "execution_identity_source": execution_source,
        "last_push_authority": {
            "source": "github_native_branch_protection",
            "require_last_push_approval": True,
            "login": None,
        },
        "snapshot_digest": final_snapshot_digest,
        "checks": checks,
        "review_threads": threads,
        "reviewer_receipt": receipt,
        "files": {"count": files_count, "digest": files_digest},
        "comments": {"count": comments_count, "digest": comments_digest},
    }
    evidence_digest = canonical_digest(evidence)
    if (
        require_published_result
        and published.get("valid_success") is True
        and published.get("receipt_evidence_digest") != evidence_digest
    ):
        reasons.append(
            {
                "code": "published_review_gate_stale_evidence",
                "message": "the App receipt does not bind the current normalized acceptance evidence",
            }
        )
    accepted = not reasons
    evaluated_at = utc_now()
    return {
        "schema": SCHEMA,
        "status": "accepted" if accepted else "rejected",
        "final_status": "accepted" if accepted else "rejected",
        "ok": accepted,
        "evaluated_at": evaluated_at,
        "repository": repo,
        "pull_request": number,
        "url": str(pr.get("url") or ""),
        "fixture": fixture,
        "expected_head": expected_head,
        "head_sha": head or None,
        "rechecked_head_sha": rechecked_head,
        "snapshot_digest": final_snapshot_digest,
        "rechecked_snapshot_digest": rechecked_snapshot_digest,
        "reviewed_sha": receipt.get("reviewed_sha") if receipt else None,
        "executing_keeper": executing_keeper or None,
        "execution_identity_source": execution_source or None,
        "last_push_authority": evidence["last_push_authority"],
        "reviewing_keeper": receipt.get("reviewing_keeper") if receipt else None,
        "reviewer_receipt": receipt,
        "signed_receipts": {
            "enabled": False,
            "status": "blocked_without_owner_authenticated_custody",
        },
        "unresolved_current_thread_count": threads["unresolved_current"],
        "checks": checks,
        "published_gate": published,
        "review_threads": threads,
        "files": evidence["files"],
        "comments": evidence["comments"],
        "evidence_digest": evidence_digest,
        "reason_codes": [reason["code"] for reason in reasons],
        "reasons": reasons,
        "publication": {"requested": False, "published": False, "check_id": None, "receipt_digest": None},
    }


def error_report(*, repo: str, number: int, expected_head: str | None, message: str) -> dict[str, Any]:
    report = {
        "schema": SCHEMA,
        "status": "error",
        "final_status": "error",
        "ok": False,
        "evaluated_at": utc_now(),
        "repository": repo,
        "pull_request": number,
        "url": "",
        "fixture": False,
        "expected_head": expected_head,
        "head_sha": None,
        "rechecked_head_sha": None,
        "snapshot_digest": None,
        "rechecked_snapshot_digest": None,
        "reviewed_sha": None,
        "executing_keeper": None,
        "execution_identity_source": None,
        "last_push_authority": None,
        "reviewing_keeper": None,
        "reviewer_receipt": None,
        "signed_receipts": None,
        "unresolved_current_thread_count": None,
        "checks": None,
        "published_gate": None,
        "review_threads": None,
        "files": None,
        "comments": None,
        "evidence_digest": None,
        "reason_codes": ["operational_error"],
        "reasons": [{"code": "operational_error", "message": message}],
        "publication": {"requested": False, "published": False, "check_id": None, "receipt_digest": None},
    }
    report["evidence_digest"] = report_evidence_digest(report)
    return report
