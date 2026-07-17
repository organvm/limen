"""Bounded GitHub evidence collection and CheckRun publication."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Sequence
from urllib.parse import quote

from .model import (
    CHECK_RECEIPT_SCHEMA,
    DIAGNOSTIC_SCHEMA,
    GENERIC_ACTIONS_APP_SLUG,
    HEAD_SHA,
    SCHEMA,
    GateError,
    check_receipt_summary,
    configured_review_gate_app_id,
    configured_review_gate_app_slug,
    make_check_receipt,
    validate_check_run_receipt,
)


MAX_GRAPHQL_PAGES = 100
MAX_CONNECTION_NODES = 10_000
MAX_REST_PAGES = 100
MAX_GH_RESPONSE_BYTES = 5 * 1024 * 1024

BASE_QUERY = r"""
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      url
      state
      isDraft
      headRefOid
      baseRefName
      author { login }
      commits(last: 1) {
        nodes {
          commit {
            oid
            author { user { login } }
            committer { user { login } }
          }
        }
      }
    }
  }
}
"""

CHECKS_QUERY = r"""
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      statusCheckRollup {
        contexts(first: 100, after: $cursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            __typename
            ... on CheckRun {
              databaseId
              name
              headSha
              status
              conclusion
              externalId
              startedAt
              completedAt
              output { title summary }
              checkSuite {
                app { id slug }
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
    }
  }
}
"""

THREADS_QUERY = r"""
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id isResolved isOutdated }
      }
    }
  }
}
"""

COMMENTS_QUERY = r"""
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      comments(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id createdAt updatedAt url author { login } }
      }
    }
  }
}
"""

REVIEWS_QUERY = r"""
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      reviews(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
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

FILES_QUERY = r"""
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      files(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { path changeType additions deletions }
      }
    }
  }
}
"""


def run_gh(args: Sequence[str], *, timeout: int = 45, input_text: str | None = None) -> Any:
    """Run one bounded ``gh`` JSON command."""

    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            input=input_text,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GateError(f"GitHub command unavailable: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown GitHub error").strip()
        raise GateError(f"GitHub command failed: {detail}")
    if len(proc.stdout.encode("utf-8")) > MAX_GH_RESPONSE_BYTES:
        raise GateError(f"GitHub response exceeds the {MAX_GH_RESPONSE_BYTES}-byte bound")
    try:
        return json.loads(proc.stdout or "{}")
    except ValueError as exc:
        raise GateError("GitHub returned invalid JSON") from exc


def split_repo(repo: str) -> tuple[str, str]:
    parts = repo.strip().split("/")
    if len(parts) != 2 or not all(parts):
        raise GateError("--repo must be OWNER/NAME")
    return parts[0], parts[1]


def resolve_repo() -> str:
    value = run_gh(["repo", "view", "--json", "nameWithOwner"])
    if not isinstance(value, dict):
        raise GateError("GitHub returned a non-object repository response")
    repo = str(value.get("nameWithOwner") or "")
    split_repo(repo)
    return repo


def _graphql(repo: str, number: int, query: str, cursor: str | None = None) -> dict[str, Any]:
    owner, name = split_repo(repo)
    args = [
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
    if cursor is not None:
        args.extend(["-f", f"cursor={cursor}"])
    value = run_gh(args)
    if not isinstance(value, dict):
        raise GateError("GitHub GraphQL response is not an object")
    if value.get("errors"):
        raise GateError(f"GitHub GraphQL returned errors: {json.dumps(value['errors'], sort_keys=True)[:500]}")
    return value


def _pull_request(value: dict[str, Any]) -> dict[str, Any]:
    try:
        pull = value["data"]["repository"]["pullRequest"]
    except (KeyError, TypeError) as exc:
        raise GateError("GitHub response omitted the pull request") from exc
    if not isinstance(pull, dict):
        raise GateError("pull request does not exist or is not readable")
    return pull


def _fetch_connection(
    repo: str,
    number: int,
    *,
    head: str,
    query: str,
    key: str,
    nested: str | None = None,
) -> dict[str, Any]:
    cursor: str | None = None
    seen_cursors: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for _page in range(MAX_GRAPHQL_PAGES):
        pull = _pull_request(_graphql(repo, number, query, cursor))
        if str(pull.get("headRefOid") or "") != head:
            raise GateError(f"PR head changed while paginating {key}")
        parent = pull.get(nested) if nested else pull
        connection = parent.get(key) if isinstance(parent, dict) else None
        if connection is None and key == "contexts":
            # A null rollup is a complete empty check connection, not an
            # unavailable page that can be silently accepted.
            return {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}
        if not isinstance(connection, dict):
            raise GateError(f"GitHub response omitted {key} connection")
        page_nodes = connection.get("nodes")
        page_info = connection.get("pageInfo")
        if (
            not isinstance(page_nodes, list)
            or any(not isinstance(node, dict) for node in page_nodes)
            or not isinstance(page_info, dict)
            or not isinstance(page_info.get("hasNextPage"), bool)
        ):
            raise GateError(f"GitHub returned an invalid {key} page")
        nodes.extend(page_nodes)
        if len(nodes) > MAX_CONNECTION_NODES:
            raise GateError(f"{key} exceeds the {MAX_CONNECTION_NODES}-node bound")
        if page_info["hasNextPage"] is False:
            return {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
            raise GateError(f"{key} pagination cursor is missing or did not advance")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    raise GateError(f"{key} exceeds the {MAX_GRAPHQL_PAGES}-page bound")


def fetch_pull_request(repo: str, number: int) -> dict[str, Any]:
    """Fetch one complete, bounded PR snapshot across every acceptance input."""

    pull = _pull_request(_graphql(repo, number, BASE_QUERY))
    head = str(pull.get("headRefOid") or "")
    if not HEAD_SHA.fullmatch(head):
        raise GateError("GitHub did not return a full current head SHA")
    commits = pull.pop("commits", None)
    commit_nodes = commits.get("nodes") if isinstance(commits, dict) else None
    commit = commit_nodes[-1].get("commit") if isinstance(commit_nodes, list) and commit_nodes else None
    author = commit.get("author") if isinstance(commit, dict) else None
    committer = commit.get("committer") if isinstance(commit, dict) else None
    author_user = author.get("user") if isinstance(author, dict) else None
    committer_user = committer.get("user") if isinstance(committer, dict) else None
    pull["headCommitIdentity"] = {
        "oid": str(commit.get("oid") or "") if isinstance(commit, dict) else "",
        "author": str(author_user.get("login") or "") if isinstance(author_user, dict) else "",
        "committer": str(committer_user.get("login") or "") if isinstance(committer_user, dict) else "",
    }
    branch = str(pull.get("baseRefName") or "")
    if not branch:
        raise GateError("GitHub did not return the pull request base branch")
    try:
        protection = run_gh(
            [
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{repo}/branches/{quote(branch, safe='')}/protection",
            ]
        )
    except GateError as exc:
        # Protection absence/plan denial is acceptance evidence, not permission
        # to skip the gate. Preserve the bounded failure so a dedicated App can
        # publish an honest rejected bootstrap receipt.
        pull["baseBranchProtection"] = None
        pull["baseBranchProtectionError"] = str(exc)[:500]
    else:
        if not isinstance(protection, dict):
            pull["baseBranchProtection"] = None
            pull["baseBranchProtectionError"] = "GitHub returned a non-object base-branch protection response"
        else:
            pull["baseBranchProtection"] = protection
            pull["baseBranchProtectionError"] = None
    pull["statusCheckRollup"] = {
        "contexts": _fetch_connection(
            repo,
            number,
            head=head,
            query=CHECKS_QUERY,
            key="contexts",
            nested="statusCheckRollup",
        )
    }
    pull["reviewThreads"] = _fetch_connection(repo, number, head=head, query=THREADS_QUERY, key="reviewThreads")
    pull["comments"] = _fetch_connection(repo, number, head=head, query=COMMENTS_QUERY, key="comments")
    pull["reviews"] = _fetch_connection(repo, number, head=head, query=REVIEWS_QUERY, key="reviews")
    pull["files"] = _fetch_connection(repo, number, head=head, query=FILES_QUERY, key="files")
    return pull


def _rest_pages(path: str, *, key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    separator = "&" if "?" in path else "?"
    for page in range(1, MAX_REST_PAGES + 1):
        value = run_gh(
            [
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"{path}{separator}per_page=100&page={page}",
            ]
        )
        page_rows = value.get(key) if isinstance(value, dict) else value
        if not isinstance(page_rows, list) or any(not isinstance(row, dict) for row in page_rows):
            raise GateError(f"GitHub returned an invalid paginated {key} response")
        rows.extend(page_rows)
        if len(rows) > MAX_CONNECTION_NODES:
            raise GateError(f"{key} exceeds the {MAX_CONNECTION_NODES}-row bound")
        if len(page_rows) < 100:
            return rows
    raise GateError(f"{key} exceeds the {MAX_REST_PAGES}-page bound")


def list_check_runs(repo: str, head: str) -> list[dict[str, Any]]:
    split_repo(repo)
    if not HEAD_SHA.fullmatch(head):
        raise GateError("check-run inventory requires a full head SHA")
    return _rest_pages(f"repos/{repo}/commits/{head}/check-runs", key="check_runs")


def app_preflight(
    expected_app_id: int | str | None = None,
    expected_app_slug: str | None = None,
) -> tuple[str, int]:
    """Derive the live App identity and optionally bind it to branch protection."""

    app_id = configured_review_gate_app_id(expected_app_id)
    expected_slug = configured_review_gate_app_slug(expected_app_slug)
    value = run_gh(["api", "-H", "Accept: application/vnd.github+json", "installation"])
    live_app_id = value.get("app_id") if isinstance(value, dict) else None
    live_slug = value.get("app_slug") if isinstance(value, dict) else None
    slug = configured_review_gate_app_slug(str(live_slug or ""))
    if slug is None or not isinstance(live_app_id, int) or isinstance(live_app_id, bool) or live_app_id <= 0:
        raise GateError("current credentials do not expose a dedicated App installation identity")
    if app_id is not None and live_app_id != app_id:
        raise GateError(f"current credentials are not installation credentials for protected App id {app_id}")
    if expected_slug is not None and slug != expected_slug:
        raise GateError(f"current credentials are not installation credentials for protected App slug {expected_slug}")
    return slug, live_app_id


def _check_run_payload(report: dict[str, Any], *, check_name: str) -> dict[str, Any]:
    accepted = report.get("status") == "accepted"
    envelope = make_check_receipt(report)
    summary = check_receipt_summary(report)
    if len(summary.encode("utf-8")) > 65_535:
        raise GateError("complete review-gate receipt exceeds GitHub's bounded CheckRun summary")
    return {
        "name": check_name,
        "head_sha": report["head_sha"],
        "status": "completed",
        "conclusion": "success" if accepted else "failure",
        "external_id": f"{CHECK_RECEIPT_SCHEMA}:{envelope['digest']}",
        "details_url": report.get("url") or None,
        "output": {
            "title": check_name,
            "summary": summary,
        },
    }


def _get_check_run(repo: str, check_id: int) -> dict[str, Any]:
    value = run_gh(
        [
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repo}/check-runs/{check_id}",
        ]
    )
    if not isinstance(value, dict):
        raise GateError("GitHub returned a non-object CheckRun")
    return value


def _authoritative_runs(
    runs: list[dict[str, Any]],
    *,
    app_slug: str,
    app_id: int,
) -> list[dict[str, Any]]:
    # Authenticate before inspecting marker payloads or imposing any cardinality
    # bound. Caller-created lookalikes cannot exhaust the App's publication path.
    authenticated = []
    for run in runs:
        app = run.get("app")
        if (
            run.get("name") == SCHEMA
            and isinstance(app, dict)
            and app.get("slug") == app_slug
            and app.get("id") == app_id
        ):
            authenticated.append(run)
    return authenticated


def publish_status(
    report: dict[str, Any],
    *,
    check_name: str = SCHEMA,
) -> None:
    """Publish, read back, and authenticate one exact-head CheckRun receipt."""

    repo = str(report.get("repository") or "")
    head = str(report.get("head_sha") or "")
    split_repo(repo)
    if not HEAD_SHA.fullmatch(head):
        raise GateError("cannot publish without a full exact head SHA")
    if check_name not in {SCHEMA, DIAGNOSTIC_SCHEMA}:
        raise GateError("refusing to publish an unknown review-gate check name")
    payload = _check_run_payload(report, check_name=check_name)

    if check_name == DIAGNOSTIC_SCHEMA:
        created = run_gh(
            ["api", "--method", "POST", f"repos/{repo}/check-runs", "--input", "-"],
            input_text=json.dumps(payload),
        )
        app = created.get("app") if isinstance(created, dict) else None
        if not isinstance(app, dict) or app.get("slug") != GENERIC_ACTIONS_APP_SLUG:
            raise GateError("diagnostic CheckRun was not published by github-actions")
        report["publication"]["check_id"] = created.get("id")
        report["publication"]["receipt_digest"] = make_check_receipt(report)["digest"]
        return

    authority = report.get("last_push_authority")
    review_gate = authority.get("review_gate") if isinstance(authority, dict) else None
    protected_app_id = review_gate.get("app_id") if isinstance(review_gate, dict) else None
    protected_app_slug = review_gate.get("app_slug") if isinstance(review_gate, dict) else None
    # A rejected bootstrap receipt may be published before protection exists so
    # setup-rulesets can discover the installed App.  An accepted report always
    # carries live protection and therefore pins this preflight to its App id.
    app_slug, app_id = app_preflight(protected_app_id, protected_app_slug)
    authenticated = _authoritative_runs(list_check_runs(repo, head), app_slug=app_slug, app_id=app_id)
    authenticated.sort(key=lambda run: (str(run.get("updated_at") or ""), int(run.get("id") or 0)))
    current = authenticated[-1] if authenticated else None
    if current is None:
        written = run_gh(
            ["api", "--method", "POST", f"repos/{repo}/check-runs", "--input", "-"],
            input_text=json.dumps(payload),
        )
    else:
        check_id = current.get("id")
        if not isinstance(check_id, int) or isinstance(check_id, bool) or check_id <= 0:
            raise GateError("existing App CheckRun has no stable id")
        # Application-level compare-and-swap: re-read the chosen record and make
        # sure its version token still matches before updating that same id.
        before = _get_check_run(repo, check_id)
        for field in ("id", "updated_at", "external_id"):
            if before.get(field) != current.get(field):
                raise GateError("review-gate CheckRun changed before stable update")
        update_payload = {key: value for key, value in payload.items() if key != "head_sha"}
        written = run_gh(
            [
                "api",
                "--method",
                "PATCH",
                f"repos/{repo}/check-runs/{check_id}",
                "--input",
                "-",
            ],
            input_text=json.dumps(update_payload),
        )
    if not isinstance(written, dict):
        raise GateError("GitHub returned a non-object publication response")
    check_id = written.get("id")
    app = written.get("app")
    if (
        not isinstance(check_id, int)
        or isinstance(check_id, bool)
        or not isinstance(app, dict)
        or app.get("slug") != app_slug
        or app.get("id") != app_id
    ):
        raise GateError("published CheckRun does not belong to the configured dedicated App")
    readback = _get_check_run(repo, check_id)
    valid, detail = validate_check_run_receipt(
        readback,
        repo=repo,
        number=int(report["pull_request"]),
        head=head,
        app_id=app_id,
        app_slug=app_slug,
        require_success=report.get("status") == "accepted",
    )
    if not valid:
        raise GateError(f"published CheckRun readback failed: {detail}")
    report["publication"]["check_id"] = check_id
    report["publication"]["receipt_digest"] = make_check_receipt(report)["digest"]
