#!/usr/bin/env python3
"""Fail-closed, exact-head pull-request review acceptance gate.

The default path is read-only.  It reads two bounded, complete GitHub GraphQL
snapshots, requires the head to remain stable across them, and evaluates only the
final snapshot.  This prevents a same-head review, conversation, comment, or
check change between samples from publishing a stale acceptance.  The only
mutation is an explicitly requested diagnostic or authoritative CheckRun.

Acceptance requires all of the following for the current PR head:

* the observed head matches ``--expected-head`` when one is supplied;
* every non-self status context is terminal-successful, with at least one check;
* there are no unresolved, non-outdated review conversations; and
* a latest decisive peer review approves that exact head.  The preferred receipt
  is a GitHub approval by a login distinct from the PR author.  When co-equal
  keepers share one GitHub login, an SSH-signed receipt from a separately
  custodied keeper principal may satisfy the same predicate.

Fixture mode consumes the GraphQL-shaped pull-request object without invoking
``gh`` and cannot be combined with status publication.

Exit codes: 0 accepted, 1 rejected by the gate, 2 input/GitHub/publication error.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.remote_predicate import canonical_json  # noqa: E402


SCHEMA = "limen.pr_review_gate.v1"
DIAGNOSTIC_SCHEMA = "limen.pr_review_gate.diagnostic.v1"
GENERIC_ACTIONS_APP_SLUG = "github-actions"
RECEIPT_KIND = "github_pull_request_review"
SIGNED_RECEIPT_SCHEMA = "limen.pr_review_receipt.v1"
SIGNED_RECEIPT_KIND = "ssh_signed_peer_review"
SIGNED_RECEIPT_NAMESPACE = SIGNED_RECEIPT_SCHEMA
EXECUTION_RECEIPT_SCHEMA = "limen.pr_execution_receipt.v1"
EXECUTION_RECEIPT_NAMESPACE = EXECUTION_RECEIPT_SCHEMA
SIGNED_RECEIPT_MAX_AGE = dt.timedelta(hours=24)
SIGNED_RECEIPT_MARKER = re.compile(
    r"<!--\s*limen\.pr_review_receipt\.v1\s+"
    r"payload=(?P<payload>[A-Za-z0-9_=-]+)\s+"
    r"signature=(?P<signature>[A-Za-z0-9_=-]+)\s*-->"
)
EXECUTION_RECEIPT_MARKER = re.compile(
    r"<!--\s*limen\.pr_execution_receipt\.v1\s+"
    r"payload=(?P<payload>[A-Za-z0-9_=-]+)\s+"
    r"signature=(?P<signature>[A-Za-z0-9_=-]+)\s*-->"
)
SAFE_KEEPER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+:/-]{0,127}$")
HEAD_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
APP_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")
MAX_SIGNED_RECEIPT_MARKERS = 32
# The base workflow is a diagnostic producer only. Its job is itself represented
# as a CheckRun while evaluating the PR, so identify it through the base workflow
# provenance rather than a name collision. The authoritative schema is reserved
# for a separately configured, non-generic GitHub App.
PUBLISHER_CHECK_NAME = "limen review-gate diagnostic publisher"
SIGNATURE_FINGERPRINT = re.compile(r"\bkey (SHA256:[A-Za-z0-9+/=]+)(?:\s|$)")
TERMINAL_SUCCESS_CONCLUSIONS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})
TRUSTED_REVIEW_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


GRAPHQL_QUERY = r"""
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      url
      state
      isDraft
      headRefOid
      author { login }
      statusCheckRollup {
        contexts(first: 100) {
          pageInfo { hasNextPage }
          nodes {
            __typename
            ... on CheckRun {
              name
              status
              conclusion
              detailsUrl
              checkSuite {
                app { slug }
                workflowRun {
                  event
                  workflow { resourcePath }
                }
              }
            }
            ... on StatusContext {
              context
              state
              targetUrl
            }
          }
        }
      }
      reviewThreads(first: 100) {
        pageInfo { hasNextPage }
        nodes {
          isResolved
          isOutdated
        }
      }
      comments(first: 100) {
        pageInfo { hasNextPage }
        nodes {
          id
          body
          createdAt
          updatedAt
          url
        }
      }
      reviews(first: 100) {
        pageInfo { hasNextPage }
        nodes {
          id
          author { login }
          authorAssociation
          state
          commit { oid }
          submittedAt
          url
        }
      }
    }
  }
}
"""


class GateError(RuntimeError):
    """Operational or input failure; acceptance must fail closed."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_gh(args: Sequence[str], *, timeout: int = 45) -> dict[str, Any]:
    """Run one bounded ``gh`` JSON command or raise a fail-closed GateError."""

    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GateError(f"GitHub command unavailable: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown GitHub error").strip()
        raise GateError(f"GitHub command failed: {detail}")
    try:
        value = json.loads(proc.stdout or "{}")
    except ValueError as exc:
        raise GateError("GitHub returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise GateError("GitHub returned a non-object JSON response")
    return value


def split_repo(repo: str) -> tuple[str, str]:
    parts = repo.strip().split("/")
    if len(parts) != 2 or not all(parts):
        raise GateError("--repo must be OWNER/NAME")
    return parts[0], parts[1]


def resolve_repo() -> str:
    data = run_gh(["repo", "view", "--json", "nameWithOwner"])
    repo = str(data.get("nameWithOwner") or "")
    split_repo(repo)
    return repo


def _graphql(repo: str, number: int, query: str) -> dict[str, Any]:
    owner, name = split_repo(repo)
    return run_gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={number}",
        ]
    )


def _pull_request_from_graphql(data: dict[str, Any]) -> dict[str, Any]:
    try:
        pr = data["data"]["repository"]["pullRequest"]
    except (KeyError, TypeError) as exc:
        raise GateError("GitHub response omitted the pull request") from exc
    if not isinstance(pr, dict):
        raise GateError("pull request does not exist or is not readable")
    return pr


def fetch_pull_request(repo: str, number: int) -> dict[str, Any]:
    return _pull_request_from_graphql(_graphql(repo, number, GRAPHQL_QUERY))


def configured_review_gate_app_slug(value: str | None) -> str | None:
    """Validate an explicit dedicated-App identity, never generic Actions."""

    if value is None or not value.strip():
        return None
    slug = value.strip()
    if not APP_SLUG.fullmatch(slug):
        raise GateError("review-gate App slug is invalid")
    if slug == GENERIC_ACTIONS_APP_SLUG:
        raise GateError("review-gate App slug must identify a dedicated App, not generic github-actions")
    return slug


def load_fixture(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GateError(f"cannot read fixture: {exc}") from exc
    except ValueError as exc:
        raise GateError(f"fixture is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise GateError("fixture root must be a JSON object")

    fixture_repo = data.get("repository_name")
    if fixture_repo is not None and not isinstance(fixture_repo, str):
        raise GateError("fixture repository_name must be a string")

    if isinstance(data.get("data"), dict):
        return _pull_request_from_graphql(data), fixture_repo
    pr = data.get("pullRequest", data)
    if not isinstance(pr, dict):
        raise GateError("fixture must contain a pullRequest object")
    return pr, fixture_repo


def _connection(container: Any, key: str) -> tuple[list[dict[str, Any]], bool, bool]:
    """Return nodes, pagination flag, and availability for a GraphQL connection."""

    if not isinstance(container, dict) or not isinstance(container.get(key), dict):
        return [], False, False
    connection = container[key]
    nodes = connection.get("nodes")
    if not isinstance(nodes, list):
        return [], False, False
    clean_nodes = [node for node in nodes if isinstance(node, dict)]
    page_info = connection.get("pageInfo")
    complete = isinstance(page_info, dict) and page_info.get("hasNextPage") is False
    return clean_nodes, not complete, True


def _trusted_publisher_check(node: dict[str, Any], repo: str) -> bool:
    """Identify only the base-controlled review-gate workflow, never a name collision."""

    if node.get("__typename") != "CheckRun" or node.get("name") != PUBLISHER_CHECK_NAME:
        return False
    suite = node.get("checkSuite")
    app = suite.get("app") if isinstance(suite, dict) else None
    run = suite.get("workflowRun") if isinstance(suite, dict) else None
    workflow = run.get("workflow") if isinstance(run, dict) else None
    event = str(run.get("event") or "") if isinstance(run, dict) else ""
    expected_resource = f"/{repo}/actions/workflows/pr-review-gate.yml"
    return bool(
        isinstance(app, dict)
        and app.get("slug") == GENERIC_ACTIONS_APP_SLUG
        and isinstance(workflow, dict)
        and workflow.get("resourcePath") == expected_resource
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


def _trusted_gate_result(node: dict[str, Any], review_gate_app_slug: str | None) -> bool:
    """Identify only the configured dedicated App's prior authoritative result.

    The previous gate result cannot be an input to the next evaluation.  A PR-controlled
    check that merely copies the name is not excluded. Generic GitHub Actions is shared by
    every workflow in the repository and can never be this independent acceptance principal.
    """

    if (
        review_gate_app_slug is None
        or review_gate_app_slug == GENERIC_ACTIONS_APP_SLUG
        or node.get("__typename") != "CheckRun"
        or node.get("name") != SCHEMA
    ):
        return False
    suite = node.get("checkSuite")
    app = suite.get("app") if isinstance(suite, dict) else None
    return isinstance(app, dict) and app.get("slug") == review_gate_app_slug


def _diagnostic_gate_result(node: dict[str, Any]) -> bool:
    """Identify the explicitly non-authoritative Actions diagnostic result."""

    if node.get("__typename") != "CheckRun" or node.get("name") != DIAGNOSTIC_SCHEMA:
        return False
    suite = node.get("checkSuite")
    app = suite.get("app") if isinstance(suite, dict) else None
    return isinstance(app, dict) and app.get("slug") == GENERIC_ACTIONS_APP_SLUG


def check_summary(
    pr: dict[str, Any],
    *,
    repo: str,
    review_gate_app_slug: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    rollup = pr.get("statusCheckRollup")
    nodes, incomplete, available = _connection(rollup, "contexts")
    if not available:
        errors.append({"code": "checks_unavailable", "message": "current-head checks are unavailable"})
    if incomplete:
        errors.append({"code": "checks_incomplete", "message": "current-head check pagination is incomplete"})

    rows: list[dict[str, str]] = []
    successful = pending = failed = unknown = 0
    for node in nodes:
        kind = str(node.get("__typename") or "")
        name = str(node.get("name") or node.get("context") or "")
        if _trusted_gate_result(node, review_gate_app_slug):
            # Only the configured dedicated App's current/legacy result is this
            # predicate's own authoritative output.
            continue
        if _diagnostic_gate_result(node):
            # The base Actions workflow publishes this clearly separate diagnostic
            # name. It is evidence for operators, never an acceptance input.
            continue
        if name == SCHEMA:
            app_slug = ""
            suite = node.get("checkSuite")
            app = suite.get("app") if isinstance(suite, dict) else None
            if isinstance(app, dict):
                app_slug = str(app.get("slug") or "")
            producer = app_slug or ("legacy StatusContext" if kind == "StatusContext" else "unknown App")
            errors.append(
                {
                    "code": "review_gate_producer_untrusted",
                    "message": (f"{SCHEMA} was produced by {producer}, not the configured dedicated review-gate App"),
                }
            )
        if _trusted_publisher_check(node, repo):
            # Trusted current/older publisher jobs cannot be inputs to the verdict they produce.
            # Identity comes from the base-only workflow path, GitHub Actions app, and event type;
            # an identically named PR check remains a normal strict check.
            continue
        if kind == "CheckRun" or "status" in node or "conclusion" in node:
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
            continue
        if kind == "StatusContext" or "state" in node:
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
            continue
        unknown += 1
        rows.append({"kind": "unknown", "name": name, "classification": "unknown"})

    total = len(rows)
    if available and total == 0:
        errors.append({"code": "checks_missing", "message": "no non-review-gate checks exist on the current head"})
    if pending:
        errors.append({"code": "checks_pending", "message": f"{pending} current-head check(s) are pending"})
    if failed:
        errors.append({"code": "checks_failed", "message": f"{failed} current-head check(s) failed"})
    if unknown:
        errors.append({"code": "checks_unknown", "message": f"{unknown} current-head check(s) have unknown state"})

    return (
        {
            "total": total,
            "successful": successful,
            "pending": pending,
            "failed": failed,
            "unknown": unknown,
            "contexts": rows,
        },
        errors,
    )


def thread_summary(pr: dict[str, Any]) -> tuple[dict[str, int], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    nodes, incomplete, available = _connection(pr, "reviewThreads")
    if not available:
        errors.append({"code": "review_threads_unavailable", "message": "review conversations are unavailable"})
    if incomplete:
        errors.append({"code": "review_threads_incomplete", "message": "review-conversation pagination is incomplete"})

    resolved = unresolved_current = unresolved_outdated = 0
    for node in nodes:
        if node.get("isResolved") is True:
            resolved += 1
        elif node.get("isOutdated") is True:
            unresolved_outdated += 1
        else:
            # Missing flags are current and unresolved for fail-closed evaluation.
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
    """Latest APPROVED/CHANGES_REQUESTED/DISMISSED review for each login."""

    latest: dict[str, tuple[str, int, dict[str, Any]]] = {}
    decisive = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
    for index, review in enumerate(reviews):
        state = str(review.get("state") or "").upper()
        author = review.get("author")
        login = str(author.get("login") or "") if isinstance(author, dict) else ""
        if state not in decisive or not login:
            continue
        submitted = str(review.get("submittedAt") or "")
        key = login.casefold()
        previous = latest.get(key)
        if previous is None or (submitted, index) >= (previous[0], previous[1]):
            latest[key] = (submitted, index, review)
    return [item[2] for item in sorted(latest.values(), key=lambda value: (value[0], value[1]))]


def _decode_urlsafe(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64url value") from exc


def _parse_receipt_time(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("receipt timestamp is missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("receipt timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("receipt timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _read_allowed_signers(path: Path) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise GateError(f"cannot inspect peer-review allowed signers: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise GateError("peer-review allowed-signers owner is unavailable or not a regular file")
    if metadata.st_uid != os.getuid():
        raise GateError("peer-review allowed-signers owner is not owned by the executing user")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise GateError("peer-review allowed-signers owner is group- or world-writable")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise GateError(f"cannot safely open peer-review allowed signers: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise GateError("peer-review allowed-signers owner changed while opening")
        if opened.st_size > 64 * 1024:
            raise GateError("peer-review allowed-signers owner exceeds 64 KiB")
        value = bytearray()
        while True:
            chunk = os.read(descriptor, 8192)
            if not chunk:
                break
            value.extend(chunk)
            if len(value) > 64 * 1024:
                raise GateError("peer-review allowed-signers owner exceeds 64 KiB")
    except OSError as exc:
        raise GateError(f"cannot read peer-review allowed signers: {exc}") from exc
    finally:
        os.close(descriptor)
    try:
        lines = bytes(value).decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise GateError("peer-review allowed-signers owner is not UTF-8") from exc
    if not any(line.strip() and not line.lstrip().startswith("#") for line in lines):
        raise GateError("peer-review allowed-signers owner contains no keeper principals")
    return bytes(value)


def _verify_ssh_receipt_signature(
    payload: dict[str, Any],
    signature: bytes,
    *,
    reviewing_keeper: str,
    allowed_signers: bytes,
    namespace: str = SIGNED_RECEIPT_NAMESPACE,
) -> str | None:
    if not SAFE_KEEPER.fullmatch(reviewing_keeper):
        return None
    if not signature.startswith(b"-----BEGIN SSH SIGNATURE-----\n"):
        return None
    try:
        with (
            tempfile.NamedTemporaryFile(prefix="limen-pr-review-signers-") as signer_file,
            tempfile.NamedTemporaryFile(prefix="limen-pr-review-", suffix=".sig") as signature_file,
        ):
            signer_file.write(allowed_signers)
            signer_file.flush()
            signature_file.write(signature)
            signature_file.flush()
            proc = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    signer_file.name,
                    "-I",
                    reviewing_keeper,
                    "-n",
                    namespace,
                    "-s",
                    signature_file.name,
                ],
                input=canonical_json(payload),
                capture_output=True,
                timeout=10,
            )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    verification = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    match = SIGNATURE_FINGERPRINT.search(verification)
    return match.group(1) if match else None


def _canonical_digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload)).hexdigest()


def _validate_execution_payload(
    payload: dict[str, Any],
    *,
    repo: str,
    number: int,
    head: str,
    now: dt.datetime,
) -> tuple[bool, str | None]:
    required = {
        "schema",
        "repository",
        "pull_request",
        "head_sha",
        "executing_keeper",
        "executing_attempt_id",
        "executing_session",
        "trajectory_digest",
        "issued_at",
        "expires_at",
    }
    if set(payload) != required or payload.get("schema") != EXECUTION_RECEIPT_SCHEMA:
        return False, "signed execution receipt fields do not match the v1 schema"
    if payload.get("repository") != repo or payload.get("pull_request") != number:
        return False, None
    if payload.get("head_sha") != head:
        return False, None
    executing_keeper = str(payload.get("executing_keeper") or "")
    if not SAFE_KEEPER.fullmatch(executing_keeper):
        return False, "signed execution receipt keeper principal is invalid"
    for field in ("executing_attempt_id", "executing_session"):
        if not SAFE_KEEPER.fullmatch(str(payload.get(field) or "")):
            return False, f"signed execution receipt {field} is invalid"
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(payload.get("trajectory_digest") or "")):
        return False, "signed execution trajectory digest is invalid"
    try:
        issued_at = _parse_receipt_time(payload.get("issued_at"))
        expires_at = _parse_receipt_time(payload.get("expires_at"))
    except ValueError as exc:
        return False, str(exc)
    if expires_at <= issued_at or expires_at - issued_at > SIGNED_RECEIPT_MAX_AGE:
        return False, "signed execution receipt validity window is invalid"
    if issued_at > now + dt.timedelta(minutes=5):
        return False, "signed execution receipt is issued in the future"
    if now >= expires_at:
        return False, "signed execution receipt has expired"
    return True, None


def _validate_signed_payload(
    payload: dict[str, Any],
    *,
    repo: str,
    number: int,
    head: str,
    now: dt.datetime,
    execution_receipts: dict[str, dict[str, Any]],
    reviewing_key_fingerprint: str,
) -> tuple[bool, str | None]:
    required = {
        "schema",
        "repository",
        "pull_request",
        "reviewed_sha",
        "executing_keeper",
        "executing_attempt_id",
        "execution_receipt_digest",
        "reviewing_keeper",
        "reviewing_session",
        "decision",
        "unresolved_current_thread_count",
        "review_evidence_digest",
        "issued_at",
        "expires_at",
    }
    if set(payload) != required:
        return False, "signed receipt fields do not match the v1 schema"
    if payload.get("schema") != SIGNED_RECEIPT_SCHEMA:
        return False, "signed receipt schema is invalid"
    if payload.get("repository") != repo or payload.get("pull_request") != number:
        return False, None
    reviewed_sha = str(payload.get("reviewed_sha") or "")
    if reviewed_sha != head:
        # Exact-head dismissal: old signed receipts are evidence, not current authority.
        return False, None
    executing_keeper = str(payload.get("executing_keeper") or "")
    reviewing_keeper = str(payload.get("reviewing_keeper") or "")
    if (
        not SAFE_KEEPER.fullmatch(executing_keeper)
        or not SAFE_KEEPER.fullmatch(reviewing_keeper)
        or executing_keeper.casefold() == reviewing_keeper.casefold()
    ):
        return False, "signed receipt does not identify distinct keeper principals"
    for field in ("executing_attempt_id", "reviewing_session"):
        if not SAFE_KEEPER.fullmatch(str(payload.get(field) or "")):
            return False, f"signed receipt {field} is invalid"
    execution_digest = str(payload.get("execution_receipt_digest") or "")
    execution = execution_receipts.get(execution_digest)
    if execution is None:
        return False, "signed review does not bind a verified exact-head execution receipt"
    if execution.get("executing_keeper") != executing_keeper or execution.get("executing_attempt_id") != payload.get(
        "executing_attempt_id"
    ):
        return False, "signed review and execution receipt identities do not match"
    executing_key_fingerprint = str(execution.get("_signing_key_fingerprint") or "")
    if not executing_key_fingerprint or executing_key_fingerprint == reviewing_key_fingerprint:
        return False, "signed receipt executor and reviewer must use distinct signing keys"
    decision = str(payload.get("decision") or "").upper()
    if decision not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
        return False, "signed receipt decision is invalid"
    unresolved = payload.get("unresolved_current_thread_count")
    if not isinstance(unresolved, int) or isinstance(unresolved, bool) or unresolved < 0:
        return False, "signed receipt unresolved-current count is invalid"
    if decision == "APPROVED" and unresolved != 0:
        return False, "signed approval attests unresolved current conversations"
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(payload.get("review_evidence_digest") or "")):
        return False, "signed receipt review evidence digest is invalid"
    try:
        issued_at = _parse_receipt_time(payload.get("issued_at"))
        expires_at = _parse_receipt_time(payload.get("expires_at"))
        execution_issued_at = _parse_receipt_time(execution.get("issued_at"))
    except ValueError as exc:
        return False, str(exc)
    if issued_at < execution_issued_at:
        return False, "signed review predates its bound execution receipt"
    if expires_at <= issued_at or expires_at - issued_at > SIGNED_RECEIPT_MAX_AGE:
        return False, "signed receipt validity window is invalid"
    if issued_at > now + dt.timedelta(minutes=5):
        return False, "signed receipt is issued in the future"
    if now >= expires_at:
        return False, "signed receipt has expired"
    return True, None


def signed_review_receipts(
    pr: dict[str, Any],
    *,
    repo: str,
    number: int,
    head: str,
    allowed_signers: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    """Verify separately custodied keeper receipts embedded in bounded PR comments."""

    summary = {
        "enabled": False,
        "markers": 0,
        "execution_markers": 0,
        "execution_verified": 0,
        "verified": 0,
        "ignored": 0,
    }
    if allowed_signers is None:
        return [], [], summary
    trusted_signers = _read_allowed_signers(allowed_signers)
    summary["enabled"] = True
    comments, incomplete, available = _connection(pr, "comments")
    errors: list[dict[str, str]] = []
    if not available:
        errors.append({"code": "signed_receipts_unavailable", "message": "PR comments are unavailable"})
        return [], errors, summary
    if incomplete:
        errors.append(
            {"code": "signed_receipts_incomplete", "message": "signed-review comment pagination is incomplete"}
        )

    markers: list[tuple[dict[str, Any], re.Match[str]]] = []
    execution_markers: list[tuple[dict[str, Any], re.Match[str]]] = []
    for comment in comments:
        body = str(comment.get("body") or "")
        markers.extend((comment, match) for match in SIGNED_RECEIPT_MARKER.finditer(body))
        execution_markers.extend((comment, match) for match in EXECUTION_RECEIPT_MARKER.finditer(body))
    summary["markers"] = len(markers) + len(execution_markers)
    summary["execution_markers"] = len(execution_markers)
    if len(markers) > MAX_SIGNED_RECEIPT_MARKERS or len(execution_markers) > MAX_SIGNED_RECEIPT_MARKERS:
        errors.append(
            {
                "code": "signed_receipts_excess",
                "message": f"more than {MAX_SIGNED_RECEIPT_MARKERS} markers exist for one signed receipt kind",
            }
        )
        return [], errors, summary

    now = dt.datetime.now(dt.timezone.utc)
    execution_receipts: dict[str, dict[str, Any]] = {}
    for _comment, marker in execution_markers:
        try:
            payload_bytes = _decode_urlsafe(marker.group("payload"))
            signature = _decode_urlsafe(marker.group("signature"))
            payload = json.loads(payload_bytes)
        except (ValueError, UnicodeDecodeError):
            summary["ignored"] += 1
            continue
        if not isinstance(payload, dict) or canonical_json(payload) != payload_bytes:
            summary["ignored"] += 1
            continue
        executing_keeper = str(payload.get("executing_keeper") or "")
        signing_key_fingerprint = _verify_ssh_receipt_signature(
            payload,
            signature,
            reviewing_keeper=executing_keeper,
            allowed_signers=trusted_signers,
            namespace=EXECUTION_RECEIPT_NAMESPACE,
        )
        if signing_key_fingerprint is None:
            summary["ignored"] += 1
            continue
        valid, message = _validate_execution_payload(payload, repo=repo, number=number, head=head, now=now)
        if not valid:
            if message is not None:
                errors.append({"code": "signed_execution_receipt_invalid", "message": message})
            else:
                summary["ignored"] += 1
            continue
        execution_receipts[_canonical_digest(payload)] = {
            **payload,
            "_signing_key_fingerprint": signing_key_fingerprint,
        }
    summary["execution_verified"] = len(execution_receipts)

    verified: list[dict[str, Any]] = []
    for comment, marker in markers:
        try:
            payload_bytes = _decode_urlsafe(marker.group("payload"))
            signature = _decode_urlsafe(marker.group("signature"))
            payload = json.loads(payload_bytes)
        except (ValueError, UnicodeDecodeError):
            summary["ignored"] += 1
            continue
        if not isinstance(payload, dict) or canonical_json(payload) != payload_bytes:
            summary["ignored"] += 1
            continue
        reviewing_keeper = str(payload.get("reviewing_keeper") or "")
        signing_key_fingerprint = _verify_ssh_receipt_signature(
            payload,
            signature,
            reviewing_keeper=reviewing_keeper,
            allowed_signers=trusted_signers,
        )
        if signing_key_fingerprint is None:
            summary["ignored"] += 1
            continue
        valid, message = _validate_signed_payload(
            payload,
            repo=repo,
            number=number,
            head=head,
            now=now,
            execution_receipts=execution_receipts,
            reviewing_key_fingerprint=signing_key_fingerprint,
        )
        if not valid:
            if message is not None:
                errors.append({"code": "signed_receipt_invalid", "message": message})
            else:
                summary["ignored"] += 1
            continue
        verified.append(
            {
                "kind": SIGNED_RECEIPT_KIND,
                **payload,
                "state": str(payload["decision"]).upper(),
                "submitted_at": str(payload["issued_at"]),
                "comment_id": str(comment.get("id") or ""),
                "url": str(comment.get("url") or ""),
                "execution_signer_fingerprint": str(
                    execution_receipts[str(payload["execution_receipt_digest"])]["_signing_key_fingerprint"]
                ),
                "review_signer_fingerprint": signing_key_fingerprint,
            }
        )
    summary["verified"] = len(verified)
    return verified, errors, summary


def review_receipt(
    pr: dict[str, Any],
    head: str,
    *,
    repo: str,
    number: int,
    allowed_signers: Path | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    reviews, incomplete, available = _connection(pr, "reviews")
    if not available:
        errors.append({"code": "reviews_unavailable", "message": "peer reviews are unavailable"})
    if incomplete:
        errors.append({"code": "reviews_incomplete", "message": "peer-review pagination is incomplete"})

    author = pr.get("author")
    executing_keeper = str(author.get("login") or "") if isinstance(author, dict) else ""
    if not executing_keeper:
        errors.append({"code": "executing_keeper_unknown", "message": "PR author identity is unavailable"})

    candidates: list[dict[str, Any]] = []
    latest_reviews = _latest_decisive_reviews(reviews)
    active_change_requests = [
        review for review in latest_reviews if str(review.get("state") or "").upper() == "CHANGES_REQUESTED"
    ]
    if active_change_requests:
        errors.append(
            {
                "code": "changes_requested",
                "message": f"{len(active_change_requests)} peer keeper review(s) still request changes",
            }
        )

    for review in latest_reviews:
        if str(review.get("state") or "").upper() != "APPROVED":
            continue
        reviewer = review.get("author")
        reviewing_keeper = str(reviewer.get("login") or "") if isinstance(reviewer, dict) else ""
        commit = review.get("commit")
        reviewed_sha = str(commit.get("oid") or "") if isinstance(commit, dict) else ""
        association = str(review.get("authorAssociation") or "").upper()
        if not reviewing_keeper or reviewing_keeper.casefold() == executing_keeper.casefold():
            continue
        if association not in TRUSTED_REVIEW_ASSOCIATIONS:
            continue
        if reviewed_sha != head:
            continue
        candidates.append(
            {
                "kind": RECEIPT_KIND,
                "review_id": str(review.get("id") or ""),
                "executing_keeper": executing_keeper,
                "reviewing_keeper": reviewing_keeper,
                "reviewer_association": association,
                "reviewed_sha": reviewed_sha,
                "state": "APPROVED",
                "submitted_at": str(review.get("submittedAt") or ""),
                "url": str(review.get("url") or ""),
            }
        )

    signed, signed_errors, signed_summary = signed_review_receipts(
        pr,
        repo=repo,
        number=number,
        head=head,
        allowed_signers=allowed_signers,
    )
    errors.extend(signed_errors)
    latest_signed: dict[str, dict[str, Any]] = {}
    for receipt in signed:
        keeper = str(receipt.get("reviewing_keeper") or "").casefold()
        previous = latest_signed.get(keeper)
        if previous is None or (str(receipt.get("submitted_at") or ""), str(receipt.get("comment_id") or "")) >= (
            str(previous.get("submitted_at") or ""),
            str(previous.get("comment_id") or ""),
        ):
            latest_signed[keeper] = receipt
    signed_changes = [receipt for receipt in latest_signed.values() if receipt.get("state") == "CHANGES_REQUESTED"]
    if signed_changes:
        errors.append(
            {
                "code": "changes_requested",
                "message": f"{len(signed_changes)} signed peer keeper review(s) still request changes",
            }
        )
    candidates.extend(receipt for receipt in latest_signed.values() if receipt.get("state") == "APPROVED")

    if not candidates:
        errors.append(
            {
                "code": "exact_head_peer_approval_missing",
                "message": "no distinct peer keeper has an active APPROVED review on the exact head",
            }
        )
        return None, errors, signed_summary

    # Deterministic when more than one peer approved the same head: newest, then stable receipt id.
    chosen = max(
        candidates,
        key=lambda row: (
            str(row.get("submitted_at") or ""),
            str(row.get("review_id") or row.get("comment_id") or ""),
        ),
    )
    return chosen, errors, signed_summary


def evaluate(
    pr: dict[str, Any],
    *,
    repo: str,
    number: int,
    expected_head: str | None = None,
    rechecked_head: str | None = None,
    fixture: bool = False,
    allowed_signers: Path | None = None,
    review_gate_app_slug: str | None = None,
) -> dict[str, Any]:
    reasons: list[dict[str, str]] = []
    head = str(pr.get("headRefOid") or "")
    state = str(pr.get("state") or "").upper()
    draft = pr.get("isDraft")

    if int(pr.get("number") or 0) != number:
        reasons.append(
            {"code": "pull_request_mismatch", "message": "response PR number does not match the requested PR"}
        )
    if state != "OPEN":
        reasons.append({"code": "pull_request_not_open", "message": f"PR state is {state or 'unknown'}, not OPEN"})
    if draft is not False:
        reasons.append({"code": "pull_request_draft", "message": "PR is a draft or draft state is unavailable"})
    if not head:
        reasons.append({"code": "head_unavailable", "message": "current PR head identity is unavailable"})
    if expected_head is not None and head != expected_head:
        reasons.append(
            {
                "code": "expected_head_mismatch",
                "message": f"expected head {expected_head} but snapshot reports {head or 'none'}",
            }
        )
    if rechecked_head is not None and head != rechecked_head:
        reasons.append(
            {
                "code": "head_changed",
                "message": (
                    "PR head was not stable across the two live snapshots: "
                    f"first {rechecked_head or 'none'}, final {head or 'none'}"
                ),
            }
        )

    checks, check_errors = check_summary(pr, repo=repo, review_gate_app_slug=review_gate_app_slug)
    threads, thread_errors = thread_summary(pr)
    receipt, review_errors, signed_summary = review_receipt(
        pr,
        head,
        repo=repo,
        number=number,
        allowed_signers=allowed_signers,
    )
    reasons.extend(check_errors)
    reasons.extend(thread_errors)
    reasons.extend(review_errors)

    accepted = not reasons
    status = "accepted" if accepted else "rejected"
    return {
        "schema": SCHEMA,
        "status": status,
        "final_status": status,
        "ok": accepted,
        "evaluated_at": utc_now(),
        "repository": repo,
        "pull_request": number,
        "url": str(pr.get("url") or ""),
        "fixture": fixture,
        "expected_head": expected_head,
        "head_sha": head or None,
        "rechecked_head_sha": rechecked_head,
        "reviewed_sha": receipt.get("reviewed_sha") if receipt else None,
        "executing_keeper": receipt.get("executing_keeper")
        if receipt
        else (str((pr.get("author") or {}).get("login") or "") if isinstance(pr.get("author"), dict) else None),
        "reviewing_keeper": receipt.get("reviewing_keeper") if receipt else None,
        "reviewer_receipt": receipt,
        "signed_receipts": signed_summary,
        "unresolved_current_thread_count": threads["unresolved_current"],
        "checks": checks,
        "review_threads": threads,
        "reason_codes": [reason["code"] for reason in reasons],
        "reasons": reasons,
        "publication": {"requested": False, "published": False},
    }


def error_report(*, repo: str, number: int, expected_head: str | None, message: str) -> dict[str, Any]:
    return {
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
        "reviewed_sha": None,
        "executing_keeper": None,
        "reviewing_keeper": None,
        "reviewer_receipt": None,
        "signed_receipts": None,
        "unresolved_current_thread_count": None,
        "checks": None,
        "review_threads": None,
        "reason_codes": ["operational_error"],
        "reasons": [{"code": "operational_error", "message": message}],
        "publication": {"requested": False, "published": False},
    }


def publish_status(
    report: dict[str, Any],
    *,
    check_name: str = SCHEMA,
    publisher_app_slug: str | None = None,
) -> None:
    repo = str(report.get("repository") or "")
    head = str(report.get("head_sha") or "")
    split_repo(repo)
    if not head:
        raise GateError("cannot publish without an exact head SHA")
    if check_name not in {SCHEMA, DIAGNOSTIC_SCHEMA}:
        raise GateError("refusing to publish an unknown review-gate check name")
    if check_name == SCHEMA and configured_review_gate_app_slug(publisher_app_slug) is None:
        raise GateError(f"publishing {SCHEMA} requires a configured dedicated non-generic GitHub App")
    accepted = report.get("status") == "accepted"
    conclusion = "success" if accepted else "failure"
    if accepted:
        description = "accepted: exact-head checks, conversations, and peer review"
    else:
        codes = report.get("reason_codes") or ["rejected"]
        description = "rejected: " + ", ".join(str(code) for code in codes[:4])
    args = [
        "api",
        "--method",
        "POST",
        f"repos/{repo}/check-runs",
        "-f",
        f"name={check_name}",
        "-f",
        f"head_sha={head}",
        "-f",
        "status=completed",
        "-f",
        f"conclusion={conclusion}",
        "-f",
        f"output[title]={check_name}",
        "-f",
        f"output[summary]={description[:65535]}",
    ]
    url = str(report.get("url") or "")
    if url:
        args.extend(["-f", f"details_url={url}"])
    published = run_gh(args)
    app = published.get("app")
    actual_app_slug = str(app.get("slug") or "") if isinstance(app, dict) else ""
    expected_app_slug = publisher_app_slug if check_name == SCHEMA else GENERIC_ACTIONS_APP_SLUG
    if actual_app_slug != expected_app_slug:
        raise GateError(
            f"published {check_name} under App {actual_app_slug or 'unknown'}, expected {expected_app_slug}"
        )


def emit(report: dict[str, Any], *, as_json: bool, quiet: bool) -> None:
    if as_json:
        print(json.dumps(report, sort_keys=True))
        return
    if quiet:
        return
    head = str(report.get("head_sha") or "unavailable")
    label = str(report.get("status") or "error").upper()
    print(f"pr-review-gate: {label} {report.get('repository')}#{report.get('pull_request')} @ {head}")
    checks = report.get("checks")
    threads = report.get("review_threads")
    if isinstance(checks, dict):
        print(
            "  checks: "
            f"total={checks['total']} successful={checks['successful']} "
            f"pending={checks['pending']} failed={checks['failed']} unknown={checks['unknown']}"
        )
    if isinstance(threads, dict):
        print(
            "  conversations: "
            f"unresolved_current={threads['unresolved_current']} "
            f"unresolved_outdated={threads['unresolved_outdated']}"
        )
    receipt = report.get("reviewer_receipt")
    if isinstance(receipt, dict):
        print(f"  peer review: {receipt['reviewing_keeper']} approved {receipt['reviewed_sha']}")
    for reason in report.get("reasons") or []:
        print(f"  HOLD [{reason['code']}]: {reason['message']}")


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("PR must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("PR must be a positive integer")
    return number


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("PR", type=positive_int, help="pull-request number")
    ap.add_argument("--repo", help="GitHub repository as OWNER/NAME (defaults to current repository)")
    ap.add_argument("--expected-head", help="full expected PR head identity")
    ap.add_argument("--fixture", type=Path, help="read a GraphQL-shaped JSON fixture instead of GitHub")
    ap.add_argument(
        "--allowed-signers",
        type=Path,
        help=(
            "Domus-owned OpenSSH allowed-signers file for same-login peer receipts; "
            "defaults to LIMEN_REVIEW_ALLOWED_SIGNERS when set"
        ),
    )
    ap.add_argument(
        "--review-gate-app-slug",
        help=(
            "dedicated GitHub App slug trusted to publish the authoritative schema CheckRun; "
            "defaults to LIMEN_REVIEW_GATE_APP_SLUG"
        ),
    )
    ap.add_argument("--json", action="store_true", help="emit the v1 report as JSON")
    ap.add_argument("--quiet", action="store_true", help="suppress the human report (JSON remains explicit)")
    publishing = ap.add_mutually_exclusive_group()
    publishing.add_argument(
        "--publish-status",
        action="store_true",
        help=(
            f"publish authoritative {SCHEMA}; requires a configured dedicated App identity "
            "and must be invoked under that App's credentials"
        ),
    )
    publishing.add_argument(
        "--publish-diagnostic",
        action="store_true",
        help=f"publish non-authoritative base-workflow diagnostic {DIAGNOSTIC_SCHEMA}",
    )
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo = args.repo or ""
    allowed_signers = args.allowed_signers
    review_gate_app_slug: str | None = None
    publication_requested = args.publish_status or args.publish_diagnostic
    publication_check_name = DIAGNOSTIC_SCHEMA if args.publish_diagnostic else SCHEMA
    authoritative_publication_ready = False
    publication_head = args.expected_head if args.expected_head and HEAD_SHA.fullmatch(args.expected_head) else None
    if allowed_signers is None and os.environ.get("LIMEN_REVIEW_ALLOWED_SIGNERS"):
        allowed_signers = Path(os.environ["LIMEN_REVIEW_ALLOWED_SIGNERS"])
    if args.fixture and publication_requested:
        report = error_report(
            repo=repo,
            number=args.PR,
            expected_head=args.expected_head,
            message="--fixture cannot be combined with check publication",
        )
        emit(report, as_json=args.json, quiet=args.quiet)
        return 2

    try:
        raw_app_slug = args.review_gate_app_slug
        if raw_app_slug is None and not args.fixture:
            raw_app_slug = os.environ.get("LIMEN_REVIEW_GATE_APP_SLUG")
        review_gate_app_slug = configured_review_gate_app_slug(raw_app_slug)
        if args.publish_status:
            if review_gate_app_slug is None:
                raise GateError(
                    "--publish-status requires LIMEN_REVIEW_GATE_APP_SLUG or "
                    "--review-gate-app-slug naming a dedicated non-generic GitHub App"
                )
            authoritative_publication_ready = True
        if args.fixture:
            pr, fixture_repo = load_fixture(args.fixture)
            repo = repo or fixture_repo or "fixture/fixture"
            split_repo(repo)
            report = evaluate(
                pr,
                repo=repo,
                number=args.PR,
                expected_head=args.expected_head,
                fixture=True,
                allowed_signers=allowed_signers,
                review_gate_app_slug=review_gate_app_slug,
            )
        else:
            repo = repo or resolve_repo()
            split_repo(repo)
            initial_pr = fetch_pull_request(repo, args.PR)
            initial_head = str(initial_pr.get("headRefOid") or "")
            if HEAD_SHA.fullmatch(initial_head):
                publication_head = initial_head

            # Fetch every acceptance input again immediately before the gate's
            # output/publication effect.  A head-only recheck is insufficient:
            # reviews, conversations, comments, and checks can all change while
            # the exact commit SHA remains unchanged.  Evaluate only this final
            # complete snapshot and use the initial head solely as a stability
            # constraint.
            final_pr = fetch_pull_request(repo, args.PR)
            final_head = str(final_pr.get("headRefOid") or "")
            if HEAD_SHA.fullmatch(final_head):
                publication_head = final_head
            report = evaluate(
                final_pr,
                repo=repo,
                number=args.PR,
                expected_head=args.expected_head,
                rechecked_head=initial_head,
                allowed_signers=allowed_signers,
                review_gate_app_slug=review_gate_app_slug,
            )
    except GateError as exc:
        report = error_report(
            repo=repo,
            number=args.PR,
            expected_head=args.expected_head,
            message=str(exc),
        )
        if publication_head is not None:
            report["head_sha"] = publication_head
        if publication_requested:
            report["publication"]["requested"] = True
            may_publish = args.publish_diagnostic or authoritative_publication_ready
            if may_publish:
                try:
                    publish_status(
                        report,
                        check_name=publication_check_name,
                        publisher_app_slug=review_gate_app_slug,
                    )
                except GateError as publish_exc:
                    report["reason_codes"].append("status_publication_failed")
                    report["reasons"].append({"code": "status_publication_failed", "message": str(publish_exc)})
                else:
                    report["publication"]["published"] = True
        emit(report, as_json=args.json, quiet=args.quiet)
        return 2

    if publication_requested:
        report["publication"]["requested"] = True
        try:
            publish_status(
                report,
                check_name=publication_check_name,
                publisher_app_slug=review_gate_app_slug,
            )
        except GateError as exc:
            report["status"] = "error"
            report["final_status"] = "error"
            report["ok"] = False
            report["reason_codes"].append("status_publication_failed")
            report["reasons"].append({"code": "status_publication_failed", "message": str(exc)})
            emit(report, as_json=args.json, quiet=args.quiet)
            return 2
        report["publication"]["published"] = True

    emit(report, as_json=args.json, quiet=args.quiet)
    return 0 if report["status"] == "accepted" else 1


if __name__ == "__main__":
    sys.exit(main())
