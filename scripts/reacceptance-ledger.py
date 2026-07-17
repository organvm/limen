#!/usr/bin/env python3
"""Build or validate the redacted shared-keeper reacceptance ledger.

The historical denominator is frozen in ``scope.json``.  A live refresh reads GitHub but writes
nothing unless ``--write`` is supplied.  Raw prompts and private paths are never read: source asks
remain opaque references to the private prompt-corpus owner.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = ROOT / "docs" / "reviews" / "claude-reacceptance-2026-07-16"
SCOPE_PATH = REVIEW_DIR / "scope.json"
LEDGER_PATH = REVIEW_DIR / "ledger.json"
SCHEMA = "limen.reacceptance_ledger.v1"
REDACTED_SESSION_ID = re.compile(r"^claude-session-sha256:[0-9a-f]{20}$")
REDACTED_WORKFLOW_ID = re.compile(r"^claude-workflow-sha256:[0-9a-f]{20}$")
ALLOWED_DISPOSITIONS = {"accepted", "repair_required", "reverted", "superseded"}
TERMINAL_DISPOSITIONS = ALLOWED_DISPOSITIONS - {"repair_required"}
COMPLETION_GATE_KEYS = {
    "open_prs_closed_or_reaccepted",
    "session_value_verified",
    "no_stale_inflight_custody",
    "privacy_containment_terminal",
    "continuation_fixed_point",
}
REMOTE_RECEIPT_KEYS = {
    "status",
    "url",
    "merge_commit",
    "review_decision",
    "draft",
    "merged_at",
    "closed_at",
}
SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_ROW_KEYS = {
    "id",
    "kind",
    "source_ask",
    "session",
    "spend",
    "exact_head",
    "side_effects",
    "review_findings",
    "predicate",
    "receipt",
    "keeper",
    "disposition",
}

GRAPHQL = """
query ReacceptancePullRequest($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number url state isDraft headRefOid baseRefName mergedAt closedAt reviewDecision
      author { login }
      mergeCommit { oid }
      reviewThreads(first: 100) {
        pageInfo { hasNextPage }
        nodes {
          isResolved isOutdated
          comments(first: 100) {
            pageInfo { hasNextPage }
            nodes { body url author { login } }
          }
        }
      }
    }
  }
}
"""

SIDE_EFFECTS: dict[tuple[str, int], list[str]] = {
    ("organvm/limen", 1089): ["privacy_material_publicly_reachable"],
    ("organvm/limen", 1100): ["media_custody_or_visibility_changed"],
    ("organvm/limen", 1119): ["nominal_check_path_performed_remote_storage_writes"],
    ("organvm/limen", 1144): ["worktree_roots_moved_or_quarantined"],
    ("organvm/limen", 1147): ["backblaze_xml_changed_before_review"],
    ("organvm/limen", 1149): ["private_prompt_checkpoint_or_seal_changed"],
    ("organvm/limen", 1150): ["mail_self_test_sent"],
    ("organvm/universal-mail--automation", 171): ["mail_send_path_exercised"],
    ("organvm/application-pipeline", 77): ["private_material_committed_to_public_history"],
    ("organvm/application-pipeline", 78): ["current_tree_cleanup_did_not_remove_public_history"],
}


class LedgerError(RuntimeError):
    """A fail-closed ledger or remote-read error."""


def load_json(path: Path) -> dict[str, Any]:
    value, _digest = load_json_snapshot(path)
    return value


def load_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LedgerError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError(f"{path} must contain a JSON object")
    return value, hashlib.sha256(payload).hexdigest()


def load_scope(path: Path = SCOPE_PATH) -> dict[str, Any]:
    scope = load_json(path)
    if scope.get("schema") != "limen.reacceptance_scope.v1":
        raise LedgerError("unsupported or missing reacceptance scope schema")
    sessions = scope.get("sessions")
    if not isinstance(sessions, list) or any(
        not isinstance(identifier, str) or not REDACTED_SESSION_ID.fullmatch(identifier) for identifier in sessions
    ):
        raise LedgerError("scope sessions must contain only redacted truncated SHA-256 identifiers")
    if len(sessions) != len(set(sessions)):
        raise LedgerError("scope sessions must be unique")
    workflows = scope.get("workflows")
    if not isinstance(workflows, list) or any(
        not isinstance(identifier, str) or not REDACTED_WORKFLOW_ID.fullmatch(identifier) for identifier in workflows
    ):
        raise LedgerError("scope workflows must contain only redacted truncated SHA-256 identifiers")
    if len(workflows) != len(set(workflows)):
        raise LedgerError("scope workflows must be unique")
    prs = expand_prs(scope)
    if len(prs) != len(set(prs)):
        raise LedgerError("scope pull requests must be unique")
    return scope


def expand_prs(scope: dict[str, Any]) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for group in scope.get("pull_requests", []):
        repository = group.get("repository")
        numbers = group.get("numbers")
        if not isinstance(repository, str) or not isinstance(numbers, list):
            raise LedgerError("each pull_requests group needs repository and numbers")
        rows.extend((repository, int(number)) for number in numbers)
    return rows


def _redacted_ask(reference: str) -> dict[str, Any]:
    return {
        "status": "redacted",
        "reference": reference,
        "private_owner": "private_prompt_corpus_owner",
    }


def _unreconciled_spend() -> dict[str, Any]:
    return {"status": "unreconciled", "tokens": None, "cost": None}


def _base_row(kind: str, identifier: str) -> dict[str, Any]:
    session = identifier if kind == "session" else None
    return {
        "id": f"{kind}:{identifier}",
        "kind": kind,
        "source_ask": _redacted_ask(f"private_prompt_corpus:{identifier}"),
        "session": session,
        "spend": _unreconciled_spend(),
        "exact_head": None,
        "side_effects": {"status": "unreconciled", "observed": []},
        "review_findings": {
            "status": "not_applicable",
            "p1": 0,
            "p2": 0,
            "unclassified": 0,
            "unresolved_current": 0,
            "urls": [],
        },
        "predicate": {
            "status": "not_verified",
            "command": None,
            "requirement": "source ask, spend, outputs, effects, predicate, and receipt reconcile",
        },
        "receipt": {"status": "missing", "url": None},
        "keeper": {
            "executing_keeper": "claude",
            "reviewing_keeper": None,
            "provider_route": "claude",
            "owner_surface": "shared_peer_keepers",
        },
        "disposition": "repair_required",
    }


def _default_completion_gates() -> dict[str, dict[str, Any]]:
    return {key: {"status": "not_verified", "predicate": None, "receipt": None} for key in sorted(COMPLETION_GATE_KEYS)}


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _evidence_reference_present(evidence: dict[str, Any]) -> bool:
    url = evidence.get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return True
    digest = evidence.get("digest")
    owner = evidence.get("owner")
    return bool(isinstance(digest, str) and SHA256_DIGEST.fullmatch(digest) and isinstance(owner, str) and owner)


def _verified_predicate_errors(
    predicate: Any,
    *,
    label: str,
    exact_head: str | None = None,
    as_of: dt.datetime | None = None,
) -> list[str]:
    if not isinstance(predicate, dict):
        return [f"{label} predicate must be an object"]
    errors: list[str] = []
    if predicate.get("status") != "verified" or predicate.get("result") != "passed":
        errors.append(f"{label} predicate must be verified and passed")
    if not isinstance(predicate.get("command"), str) or not predicate["command"].strip():
        errors.append(f"{label} predicate must name the executed command")
    verified_at = _parse_timestamp(predicate.get("verified_at"))
    if verified_at is None:
        errors.append(f"{label} predicate verified_at must be an ISO-8601 timestamp with timezone")
    elif as_of is not None and verified_at > as_of + dt.timedelta(minutes=5):
        errors.append(f"{label} predicate verification is newer than the ledger snapshot")
    if exact_head is not None and predicate.get("exact_head") != exact_head:
        errors.append(f"{label} predicate exact_head does not match the row")
    return errors


def _verified_receipt_errors(
    evidence: Any,
    *,
    label: str,
    exact_head: str | None = None,
    disposition: str | None = None,
    as_of: dt.datetime | None = None,
) -> list[str]:
    if not isinstance(evidence, dict):
        return [f"{label} receipt must be an object"]
    errors: list[str] = []
    if evidence.get("status") != "verified":
        errors.append(f"{label} receipt status must be verified")
    if disposition is not None and evidence.get("disposition") != disposition:
        errors.append(f"{label} receipt disposition must be {disposition}")
    if not _evidence_reference_present(evidence):
        errors.append(f"{label} receipt needs a durable URL or owner-bound SHA-256 digest")
    verified_at = _parse_timestamp(evidence.get("verified_at"))
    if verified_at is None:
        errors.append(f"{label} receipt verified_at must be an ISO-8601 timestamp with timezone")
    elif as_of is not None and verified_at > as_of + dt.timedelta(minutes=5):
        errors.append(f"{label} receipt verification is newer than the ledger snapshot")
    if exact_head is not None and evidence.get("exact_head") != exact_head:
        errors.append(f"{label} receipt exact_head does not match the row")
    return errors


def _finding_count(row: dict[str, Any], field: str) -> int | None:
    findings = row.get("review_findings")
    if not isinstance(findings, dict):
        return None
    if field not in findings:
        if field == "unclassified" and row.get("kind") != "pull_request":
            return 0
        return None
    value = findings.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _terminal_row_errors(
    row: dict[str, Any],
    rows_by_id: dict[str, dict[str, Any]],
    *,
    as_of: dt.datetime | None,
) -> list[str]:
    disposition = row.get("disposition")
    if disposition not in TERMINAL_DISPOSITIONS:
        return []
    label = f"row {row.get('id', '<missing>')}"
    exact_head = row.get("exact_head") if isinstance(row.get("exact_head"), str) else None
    errors = _verified_predicate_errors(
        row.get("predicate"),
        label=label,
        exact_head=exact_head,
        as_of=as_of,
    )
    receipt = row.get("receipt")
    adjudication = receipt.get("adjudication") if isinstance(receipt, dict) else None
    errors.extend(
        _verified_receipt_errors(
            adjudication,
            label=label,
            exact_head=exact_head,
            disposition=str(disposition),
            as_of=as_of,
        )
    )

    if disposition == "accepted":
        for field in ("p1", "p2", "unclassified"):
            value = _finding_count(row, field)
            if value is None or value != 0:
                errors.append(f"{label} accepted disposition requires zero {field} review debt")
        if row.get("kind") == "pull_request":
            keeper = row.get("keeper")
            executing = str(keeper.get("executing_keeper") or "") if isinstance(keeper, dict) else ""
            reviewing = str(keeper.get("reviewing_keeper") or "") if isinstance(keeper, dict) else ""
            if not executing or not reviewing or executing.casefold() == reviewing.casefold():
                errors.append(f"{label} accepted PR requires a distinct reviewing keeper")
            if not isinstance(adjudication, dict) or adjudication.get("review_gate_status") != "accepted":
                errors.append(f"{label} accepted PR receipt must record accepted exact-head review gate status")
    elif disposition == "reverted":
        if not isinstance(adjudication, dict) or adjudication.get("reversal_status") != "verified":
            errors.append(f"{label} reverted receipt must verify the safe reversal")
    elif disposition == "superseded":
        replacement_id = adjudication.get("superseded_by") if isinstance(adjudication, dict) else None
        replacement = rows_by_id.get(replacement_id) if isinstance(replacement_id, str) else None
        if replacement is None or replacement.get("disposition") != "accepted":
            errors.append(f"{label} superseded receipt must link an accepted replacement row")
        elif replacement.get("exact_head") is not None and adjudication.get("replacement_head") != replacement.get(
            "exact_head"
        ):
            errors.append(f"{label} superseded receipt replacement_head does not match the accepted replacement")
    return errors


def _completion_gate_errors(gates: Any, *, as_of: dt.datetime | None) -> list[str]:
    if not isinstance(gates, dict):
        return ["completion_gates must be an object"]
    actual = set(gates)
    if actual != COMPLETION_GATE_KEYS:
        return [f"completion_gates keys must be exactly {sorted(COMPLETION_GATE_KEYS)}"]
    errors: list[str] = []
    for key in sorted(COMPLETION_GATE_KEYS):
        gate = gates[key]
        label = f"completion gate {key}"
        if not isinstance(gate, dict):
            errors.append(f"{label} must be an object")
            continue
        status = gate.get("status")
        if status not in {"passed", "failed", "not_verified"}:
            errors.append(f"{label} status must be passed, failed, or not_verified")
        if status == "passed":
            errors.extend(_verified_predicate_errors(gate.get("predicate"), label=label, as_of=as_of))
            errors.extend(_verified_receipt_errors(gate.get("receipt"), label=label, as_of=as_of))
    return errors


def _release_ready(
    rows: list[dict[str, Any]],
    completion_gates: Any,
    *,
    as_of: dt.datetime | None,
) -> bool:
    if not rows or any(
        not isinstance(row, dict) or row.get("disposition") not in TERMINAL_DISPOSITIONS for row in rows
    ):
        return False
    rows_by_id = {str(row.get("id")): row for row in rows}
    if any(_terminal_row_errors(row, rows_by_id, as_of=as_of) for row in rows):
        return False
    for field in ("p1", "p2", "unclassified"):
        counts = [_finding_count(row, field) for row in rows]
        if any(value is None for value in counts) or sum(value for value in counts if value is not None) != 0:
            return False
    if _completion_gate_errors(completion_gates, as_of=as_of):
        return False
    return all(completion_gates[key].get("status") == "passed" for key in COMPLETION_GATE_KEYS)


def _summary_for(
    rows: list[dict[str, Any]],
    completion_gates: Any,
    *,
    refreshed_at: str,
) -> dict[str, Any]:
    as_of = _parse_timestamp(refreshed_at)
    valid_rows = [row for row in rows if isinstance(row, dict)]
    counts = {
        field: sum((_finding_count(row, field) or 0) for row in valid_rows) for field in ("p1", "p2", "unclassified")
    }
    return {
        "accepted": sum(row.get("disposition") == "accepted" for row in valid_rows),
        "repair_required": sum(row.get("disposition") == "repair_required" for row in valid_rows),
        "reverted": sum(row.get("disposition") == "reverted" for row in valid_rows),
        "superseded": sum(row.get("disposition") == "superseded" for row in valid_rows),
        "current_p1": counts["p1"],
        "current_p2": counts["p2"],
        "current_unclassified": counts["unclassified"],
        "release_ready": _release_ready(rows, completion_gates, as_of=as_of),
    }


def _gh_graphql(repository: str, number: int) -> dict[str, Any]:
    owner, name = repository.split("/", 1)
    command = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"owner={owner}",
        "-f",
        f"name={name}",
        "-F",
        f"number={number}",
        "-f",
        f"query={GRAPHQL}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise LedgerError(f"GitHub read failed for {repository}#{number}: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
        if payload.get("errors"):
            raise LedgerError(f"GitHub GraphQL returned errors for {repository}#{number}")
        pr = payload["data"]["repository"]["pullRequest"]
    except LedgerError:
        raise
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LedgerError(f"invalid GitHub response for {repository}#{number}") from exc
    if not pr:
        raise LedgerError(f"pull request not found: {repository}#{number}")
    return pr


def _severity(body: str) -> str | None:
    if re.search(r"(?:P1 Badge|\[P1\]|\bP1\b)", body, re.IGNORECASE):
        return "p1"
    if re.search(r"(?:P2 Badge|\[P2\]|\bP2\b)", body, re.IGNORECASE):
        return "p2"
    return None


def _complete_connection(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise LedgerError(f"{label} connection is unavailable")
    page_info = value.get("pageInfo")
    nodes = value.get("nodes")
    if not isinstance(page_info, dict) or page_info.get("hasNextPage") is not False:
        raise LedgerError(f"{label} pagination is incomplete")
    if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
        raise LedgerError(f"{label} nodes are unavailable or malformed")
    return nodes


def _current_findings(pr: dict[str, Any]) -> dict[str, Any]:
    p1: list[str] = []
    p2: list[str] = []
    unclassified: list[str] = []
    threads = _complete_connection(pr.get("reviewThreads"), label="reviewThreads")
    for index, thread in enumerate(threads):
        comments = _complete_connection(thread.get("comments"), label=f"reviewThreads[{index}].comments")
        if thread.get("isResolved") or thread.get("isOutdated"):
            continue
        body = "\n".join(str(comment.get("body") or "") for comment in comments)
        url = next((str(comment.get("url")) for comment in comments if comment.get("url")), "")
        severity = _severity(body)
        if severity == "p1":
            p1.append(url)
        elif severity == "p2":
            p2.append(url)
        else:
            unclassified.append(url)
    return {
        "status": "current_remote_snapshot",
        "p1": len(p1),
        "p2": len(p2),
        "unclassified": len(unclassified),
        "unresolved_current": len(p1) + len(p2) + len(unclassified),
        "urls": p1 + p2 + unclassified,
    }


def _pr_row(item: tuple[str, int]) -> dict[str, Any]:
    repository, number = item
    pr = _gh_graphql(repository, number)
    findings = _current_findings(pr)
    author = (pr.get("author") or {}).get("login")
    return {
        "id": f"pull_request:{repository}#{number}",
        "kind": "pull_request",
        "source_ask": _redacted_ask(f"private_prompt_corpus:pr:{repository}#{number}:unreconciled"),
        "session": None,
        "spend": _unreconciled_spend(),
        "exact_head": pr.get("headRefOid"),
        "side_effects": {
            "status": "observed" if SIDE_EFFECTS.get(item) else "none_identified_yet",
            "observed": SIDE_EFFECTS.get(item, []),
            "replay_authorized": False,
        },
        "review_findings": findings,
        "predicate": {
            "status": "not_verified",
            "command": None,
            "requirement": (
                "deployed scoped predicate passes; zero current findings; limen.pr_review_gate.v1 accepts exact head"
            ),
        },
        "receipt": {
            "status": str(pr.get("state") or "UNKNOWN").lower(),
            "url": pr.get("url"),
            "merge_commit": (pr.get("mergeCommit") or {}).get("oid"),
            "review_decision": pr.get("reviewDecision"),
            "draft": bool(pr.get("isDraft")),
            "merged_at": pr.get("mergedAt"),
            "closed_at": pr.get("closedAt"),
        },
        "keeper": {
            "executing_keeper": "claude",
            "reviewing_keeper": None,
            "provider_route": "claude",
            "github_author": author,
            "owner_surface": repository,
        },
        "disposition": "repair_required",
    }


def _row_has_adjudication(row: dict[str, Any]) -> bool:
    if row.get("disposition") in TERMINAL_DISPOSITIONS:
        return True
    predicate = row.get("predicate")
    if isinstance(predicate, dict) and predicate.get("status") == "verified":
        return True
    receipt = row.get("receipt")
    adjudication = receipt.get("adjudication") if isinstance(receipt, dict) else None
    return isinstance(adjudication, dict) and adjudication.get("status") == "verified"


def _merge_side_effects(fresh: Any, previous: Any) -> Any:
    if not isinstance(fresh, dict) or not isinstance(previous, dict):
        return copy.deepcopy(previous)
    merged = copy.deepcopy(previous)
    old_observed = previous.get("observed") if isinstance(previous.get("observed"), list) else []
    fresh_observed = fresh.get("observed") if isinstance(fresh.get("observed"), list) else []
    merged["observed"] = list(dict.fromkeys([*old_observed, *fresh_observed]))
    if fresh_observed and previous.get("status") in {None, "unreconciled", "none_identified_yet"}:
        merged["status"] = fresh.get("status")
    return merged


def _merge_refreshed_row(fresh: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    identifier = fresh.get("id")
    if identifier != previous.get("id") or fresh.get("kind") != previous.get("kind"):
        raise LedgerError(f"stable row identity conflict for {identifier}")
    if fresh.get("session") != previous.get("session"):
        raise LedgerError(f"stable row session conflict for {identifier}")

    old_head = previous.get("exact_head")
    new_head = fresh.get("exact_head")
    if fresh.get("kind") == "pull_request" and old_head != new_head and _row_has_adjudication(previous):
        raise LedgerError(f"adjudicated row {identifier} is stale: exact head changed from {old_head} to {new_head}")
    if fresh.get("kind") == "pull_request" and previous.get("disposition") == "accepted":
        fresh_debt = [_finding_count(fresh, field) for field in ("p1", "p2", "unclassified")]
        if any(value is None or value != 0 for value in fresh_debt):
            raise LedgerError(f"accepted row {identifier} is stale: current review debt changed")
        fresh_receipt = fresh.get("receipt")
        if isinstance(fresh_receipt, dict) and (
            fresh_receipt.get("draft") is True or fresh_receipt.get("review_decision") == "CHANGES_REQUESTED"
        ):
            raise LedgerError(f"accepted row {identifier} is stale: current PR review state no longer accepts it")
    predicate = previous.get("predicate")
    predicate_head = predicate.get("exact_head") if isinstance(predicate, dict) else None
    receipt = previous.get("receipt")
    adjudication = receipt.get("adjudication") if isinstance(receipt, dict) else None
    receipt_head = adjudication.get("exact_head") if isinstance(adjudication, dict) else None
    if fresh.get("kind") == "pull_request" and predicate_head not in {None, new_head}:
        raise LedgerError(f"row {identifier} predicate is stale for refreshed exact head {new_head}")
    if fresh.get("kind") == "pull_request" and receipt_head not in {None, new_head}:
        raise LedgerError(f"row {identifier} receipt is stale for refreshed exact head {new_head}")
    old_effects = previous.get("side_effects")
    fresh_effects = fresh.get("side_effects")
    old_observed = set(old_effects.get("observed") or []) if isinstance(old_effects, dict) else set()
    fresh_observed = set(fresh_effects.get("observed") or []) if isinstance(fresh_effects, dict) else set()
    if fresh_observed - old_observed and previous.get("disposition") in TERMINAL_DISPOSITIONS:
        raise LedgerError(f"terminal row {identifier} is stale: refresh discovered new side effects")

    merged = copy.deepcopy(fresh)
    for field in ("source_ask", "spend", "predicate", "disposition"):
        merged[field] = copy.deepcopy(previous.get(field))
    merged["side_effects"] = _merge_side_effects(fresh.get("side_effects"), previous.get("side_effects"))
    if fresh.get("kind") != "pull_request":
        merged["exact_head"] = copy.deepcopy(old_head)
        merged["receipt"] = copy.deepcopy(previous.get("receipt"))
        merged["keeper"] = copy.deepcopy(previous.get("keeper"))
    else:
        fresh_receipt = fresh.get("receipt") if isinstance(fresh.get("receipt"), dict) else {}
        old_receipt = previous.get("receipt") if isinstance(previous.get("receipt"), dict) else {}
        merged_receipt = copy.deepcopy(fresh_receipt)
        merged_receipt.update(
            {key: copy.deepcopy(value) for key, value in old_receipt.items() if key not in REMOTE_RECEIPT_KEYS}
        )
        merged["receipt"] = merged_receipt
        old_keeper = previous.get("keeper") if isinstance(previous.get("keeper"), dict) else {}
        fresh_keeper = fresh.get("keeper") if isinstance(fresh.get("keeper"), dict) else {}
        merged_keeper = copy.deepcopy(old_keeper)
        merged_keeper.update(
            {
                key: copy.deepcopy(value)
                for key, value in fresh_keeper.items()
                if key in {"github_author", "owner_surface"}
            }
        )
        merged["keeper"] = merged_keeper
    for key, value in previous.items():
        if key not in merged:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_previous_rows(
    fresh_rows: list[dict[str, Any]],
    previous_document: dict[str, Any],
    scope: dict[str, Any],
) -> list[dict[str, Any]]:
    previous_errors = validate_document(previous_document, scope)
    if previous_errors:
        raise LedgerError("cannot refresh from invalid prior ledger: " + "; ".join(previous_errors))
    previous_time = _parse_timestamp(previous_document.get("refreshed_at"))
    if previous_time is None:
        raise LedgerError("prior ledger refreshed_at is invalid")
    if previous_time > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise LedgerError("prior ledger refreshed_at is in the future")
    previous_rows = previous_document.get("rows")
    assert isinstance(previous_rows, list)  # proven by validate_document
    by_id = {str(row["id"]): row for row in previous_rows}
    fresh_ids = {str(row.get("id")) for row in fresh_rows}
    if set(by_id) != fresh_ids:
        raise LedgerError("prior ledger row IDs conflict with the frozen refresh denominator")
    return [_merge_refreshed_row(row, by_id[str(row["id"])]) for row in fresh_rows]


def build_document(
    scope: dict[str, Any],
    workers: int = 8,
    *,
    previous_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sessions = sorted(set(scope.get("sessions", [])))
    workflows = sorted(set(scope.get("workflows", [])))
    prs = expand_prs(scope)
    rows = [_base_row("session", identifier) for identifier in sessions]
    rows.extend(_base_row("workflow", identifier) for identifier in workflows)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        rows.extend(executor.map(_pr_row, prs))
    rows.sort(key=lambda row: row["id"])
    completion_gates = _default_completion_gates()
    if previous_document is not None:
        rows = _merge_previous_rows(rows, previous_document, scope)
        completion_gates = copy.deepcopy(previous_document.get("completion_gates"))
    refreshed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema": SCHEMA,
        "refreshed_at": refreshed_at,
        "scope": {
            "starts_at": scope["boundary"]["starts_at"],
            "sessions": len(sessions),
            "workflows": len(workflows),
            "pull_requests": len(prs),
            "rows": len(rows),
        },
        "completion_gates": completion_gates,
        "summary": _summary_for(rows, completion_gates, refreshed_at=refreshed_at),
        "rows": rows,
    }


def validate_document(document: dict[str, Any], scope: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    refreshed_at = _parse_timestamp(document.get("refreshed_at"))
    if refreshed_at is None:
        errors.append("refreshed_at must be an ISO-8601 timestamp with timezone")
    rows = document.get("rows")
    if not isinstance(rows, list):
        return errors + ["rows must be a list"]
    expected_counts = {
        "session": len(set(scope.get("sessions", []))),
        "workflow": len(set(scope.get("workflows", []))),
        "pull_request": len(expand_prs(scope)),
    }
    expected_scope = {
        "starts_at": scope["boundary"]["starts_at"],
        "sessions": expected_counts["session"],
        "workflows": expected_counts["workflow"],
        "pull_requests": expected_counts["pull_request"],
        "rows": sum(expected_counts.values()),
    }
    if document.get("scope") != expected_scope:
        errors.append(f"document scope mismatch: expected {expected_scope}, got {document.get('scope')}")
    actual_counts = {
        kind: sum(isinstance(row, dict) and row.get("kind") == kind for row in rows) for kind in expected_counts
    }
    if actual_counts != expected_counts:
        errors.append(f"row denominator mismatch: expected {expected_counts}, got {actual_counts}")
    ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
    if any(not isinstance(identifier, str) for identifier in ids):
        errors.append("row ids must be strings")
        actual_ids: set[str] = set()
    else:
        actual_ids = set(ids)
    if len(ids) != len(actual_ids):
        errors.append("row ids must be unique")
    expected_ids = {
        *(f"session:{identifier}" for identifier in scope.get("sessions", [])),
        *(f"workflow:{identifier}" for identifier in scope.get("workflows", [])),
        *(f"pull_request:{repository}#{number}" for repository, number in expand_prs(scope)),
    }
    if actual_ids != expected_ids:
        errors.append("row ids do not match the frozen scope denominator")
    rows_by_id = {str(row.get("id")): row for row in rows if isinstance(row, dict)}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {index} must be an object")
            continue
        missing = sorted(REQUIRED_ROW_KEYS - set(row))
        if missing:
            errors.append(f"row {index} missing keys: {', '.join(missing)}")
        if row.get("disposition") not in ALLOWED_DISPOSITIONS:
            errors.append(f"row {index} has invalid disposition {row.get('disposition')!r}")
        if row.get("kind") == "pull_request" and (
            not isinstance(row.get("exact_head"), str) or not FULL_HEAD.fullmatch(row["exact_head"])
        ):
            errors.append(f"row {index} pull request has no full exact_head")
        source_ask = row.get("source_ask") or {}
        if source_ask.get("status") != "redacted" or not source_ask.get("reference"):
            errors.append(f"row {index} source ask is not a redacted reference")
        findings = row.get("review_findings")
        if not isinstance(findings, dict):
            errors.append(f"row {index} review_findings must be an object")
            continue
        for field in ("p1", "p2", "unclassified"):
            value = findings.get(field)
            if field == "unclassified" and row.get("kind") != "pull_request" and value is None:
                value = 0
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"row {index} review_findings.{field} must be a non-negative integer")
        if row.get("kind") == "pull_request":
            counts = [_finding_count(row, field) for field in ("p1", "p2", "unclassified")]
            unresolved = findings.get("unresolved_current")
            if all(value is not None for value in counts) and unresolved != sum(
                value for value in counts if value is not None
            ):
                errors.append(f"row {index} review_findings.unresolved_current does not match classified debt")
        errors.extend(_terminal_row_errors(row, rows_by_id, as_of=refreshed_at))

    completion_gates = document.get("completion_gates")
    errors.extend(_completion_gate_errors(completion_gates, as_of=refreshed_at))
    summary = document.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        expected_summary = _summary_for(
            rows,
            completion_gates,
            refreshed_at=str(document.get("refreshed_at") or ""),
        )
        if summary != expected_summary:
            errors.append(f"summary must be derived from rows and completion gates: expected {expected_summary}")
    return errors


def _write_atomic(path: Path, document: dict[str, Any], *, expected_digest: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if expected_digest is not None:
            try:
                current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                raise LedgerError(f"cannot verify refresh destination before replace: {exc}") from exc
            if current_digest != expected_digest:
                raise LedgerError(
                    "refresh destination changed after the prior ledger snapshot; refusing stale overwrite"
                )
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="read current PR state from GitHub")
    mode.add_argument(
        "--check",
        nargs="?",
        const=str(LEDGER_PATH),
        metavar="PATH",
        help="validate a ledger (default: tracked ledger); performs no writes",
    )
    parser.add_argument("--output", type=Path, help="refresh output path; omitted means stdout")
    parser.add_argument("--write", action="store_true", help="explicitly write refresh output")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--scope", type=Path, default=SCOPE_PATH)
    parser.add_argument(
        "--previous",
        type=Path,
        help="prior adjudicated ledger to preserve by stable row ID (default: tracked ledger when present)",
    )
    args = parser.parse_args(argv)

    try:
        scope = load_scope(args.scope)
        if args.refresh:
            previous_path = args.previous
            if previous_path is None and LEDGER_PATH.exists():
                previous_path = LEDGER_PATH
            previous_document = None
            previous_digest = None
            if previous_path is not None:
                if not previous_path.exists():
                    raise LedgerError(f"prior adjudicated ledger does not exist: {previous_path}")
                previous_document, previous_digest = load_json_snapshot(previous_path)
            document = build_document(
                scope,
                workers=args.workers,
                previous_document=previous_document,
            )
            errors = validate_document(document, scope)
            if errors:
                raise LedgerError("; ".join(errors))
            if args.write:
                destination = args.output or LEDGER_PATH
                compare_digest = None
                if previous_path is not None and previous_digest is not None:
                    try:
                        same_path = destination.resolve() == previous_path.resolve()
                    except OSError:
                        same_path = False
                    if same_path:
                        compare_digest = previous_digest
                _write_atomic(destination, document, expected_digest=compare_digest)
                print(f"reacceptance-ledger: wrote {destination}")
            else:
                payload = json.dumps(document, indent=2) + "\n"
                if args.output:
                    raise LedgerError("--output requires --write; omit it for stdout")
                sys.stdout.write(payload)
            return 0

        if args.write or args.output or args.previous:
            raise LedgerError("--write/--output/--previous require --refresh")
        target = Path(args.check) if args.check else LEDGER_PATH
        document = load_json(target)
        errors = validate_document(document, scope)
        if errors:
            for error in errors:
                print(f"reacceptance-ledger: {error}", file=sys.stderr)
            return 1
        print(
            "reacceptance-ledger: valid "
            f"sessions={document['scope']['sessions']} workflows={document['scope']['workflows']} "
            f"pull_requests={document['scope']['pull_requests']} rows={document['scope']['rows']}"
        )
        return 0
    except LedgerError as exc:
        print(f"reacceptance-ledger: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
