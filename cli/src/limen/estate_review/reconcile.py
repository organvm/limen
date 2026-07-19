"""Dynamic estate census and frozen exact-head receipt reconciliation."""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from .config import ReviewConfig
from .model import (
    AGENTS,
    OUTCOMES,
    TOKEN_KEYS,
    canonical_repository,
    classify_receipt,
    iso_z,
    outcome_rank,
    parse_pr_url,
    parse_ts,
    semantic_receipt_link,
    union_seconds,
)


class ReconciliationError(RuntimeError):
    """Remote or lineage evidence could not support a safe reconciliation."""


def copilot_ask_id(repository: str, number: int) -> tuple[str, str]:
    """Return a collision-safe stable ID and canonical repository/PR key."""

    safe_repository = canonical_repository(repository)
    key = f"{safe_repository.lower()}#{int(number)}"
    return "ask-copilot-" + hashlib.sha256(key.encode()).hexdigest()[:16], key


def _run_json(
    args: list[str],
    *,
    attempts: int = 3,
    timeout: int = 60,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Any:
    """Run one bounded gh command with finite transient retries."""

    failures: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            result = runner(
                ["gh", *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"attempt-{attempt}:{type(exc).__name__}")
        else:
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except ValueError as exc:
                    failures.append(f"attempt-{attempt}:{type(exc).__name__}")
            else:
                failures.append(f"attempt-{attempt}:exit-{result.returncode}")
        if attempt < attempts:
            time.sleep(min(0.2 * attempt, 0.5))
    raise ReconciliationError("gh command failed after bounded retries: " + ",".join(failures))


def registry_owners(root: Path) -> list[str]:
    """Derive owner enumeration from the GitVS registry implementation."""

    script = root / "scripts" / "gitvs.py"
    spec = importlib.util.spec_from_file_location("_limen_estate_review_gitvs", script)
    if spec is None or spec.loader is None:
        raise ReconciliationError("GitVS registry loader is unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        estate = module.load_estate()
        values = module.owners(estate)
    except (AttributeError, OSError, ValueError) as exc:
        raise ReconciliationError("GitVS owner registry could not be loaded") from exc
    owners = sorted({str(value) for value in values if str(value).strip()})
    if not owners:
        raise ReconciliationError("GitVS owner registry returned no owners")
    return owners


def _owner_repositories(owner: str) -> list[dict[str, Any]]:
    profile = _run_json(["api", f"users/{owner}"])
    owner_type = str(profile.get("type") or "").lower()
    endpoint = (
        f"orgs/{owner}/repos?per_page=100&type=all"
        if owner_type == "organization"
        else f"users/{owner}/repos?per_page=100&type=owner"
    )
    pages = _run_json(["api", "--paginate", "--slurp", endpoint])
    result: list[dict[str, Any]] = []
    for page in pages if isinstance(pages, list) else []:
        for row in page if isinstance(page, list) else []:
            if isinstance(row, dict):
                result.append(row)
    return result


def estate_census(
    root: Path,
    *,
    evidence_repositories: Iterable[str] = (),
) -> tuple[dict[str, str], int, list[str]]:
    """Union registry owners with evidence-linked repositories and redirects."""

    owners = registry_owners(root)
    repos: list[dict[str, Any]] = []
    for owner in owners:
        repos.extend(_owner_repositories(owner))
    canonical: dict[str, str] = {}
    for row in repos:
        full = str(row.get("full_name") or row.get("nameWithOwner") or "")
        name = str(row.get("name") or "").lower()
        if full and name:
            canonical[full.lower()] = full
            canonical.setdefault(name, full)
    for repository in sorted(set(evidence_repositories)):
        safe = canonical_repository(repository)
        if safe == "unknown":
            continue
        try:
            row = _run_json(["repo", "view", safe, "--json", "nameWithOwner"])
        except ReconciliationError:
            continue
        full = str(row.get("nameWithOwner") or "")
        if full:
            canonical[safe.lower()] = full
            canonical[full.lower()] = full
            canonical[full.split("/", 1)[-1].lower()] = full
    count = len(
        {
            str(row.get("full_name") or row.get("nameWithOwner") or "").lower()
            for row in repos
            if row.get("full_name") or row.get("nameWithOwner")
        }
    )
    return canonical, count, owners


def coding_agent_receipts(
    owners: Iterable[str],
    *,
    start: str,
    end: str,
) -> list[str]:
    """Enumerate Copilot coding-agent PRs for every registry owner."""

    urls: set[str] = set()
    for owner in owners:
        try:
            profile = _run_json(["api", f"users/{owner}"])
        except ReconciliationError:
            continue
        owner_qualifier = "org" if str(profile.get("type") or "").lower() == "organization" else "user"
        query = f"{owner_qualifier}:{owner} is:pr author:app/copilot-swe-agent created:{start}..{end}"
        try:
            pages = _run_json(
                [
                    "api",
                    "--paginate",
                    "--slurp",
                    "--method",
                    "GET",
                    "search/issues",
                    "-f",
                    f"q={query}",
                    "-f",
                    "per_page=100",
                ]
            )
        except ReconciliationError:
            continue
        for page in pages if isinstance(pages, list) else []:
            for row in (page.get("items") or []) if isinstance(page, dict) else []:
                url = str(row.get("pull_request", {}).get("html_url") or row.get("html_url") or "")
                if parse_pr_url(url):
                    urls.add(url)
    return sorted(urls)


def _receipt_query(chunk: list[tuple[str, str, int]]) -> str:
    fields: list[str] = []
    for index, (owner, repo, number) in enumerate(chunk):
        fields.append(
            f"""r{index}: repository(owner:{json.dumps(owner)}, name:{json.dumps(repo)}) {{
              nameWithOwner isPrivate defaultBranchRef {{ name }}
              p: pullRequest(number:{number}) {{
                url title state createdAt mergedAt closedAt baseRefName headRefOid
                author {{ login }}
                mergedBy {{ login }}
                commits(last:1) {{ nodes {{ commit {{
                  committedDate oid
                  statusCheckRollup {{
                    contexts(first:100) {{
                      pageInfo {{ hasNextPage endCursor }}
                      nodes {{
                        __typename
                        ... on CheckRun {{
                          name status conclusion completedAt detailsUrl
                          checkSuite {{ app {{ slug }} }}
                        }}
                        ... on StatusContext {{
                          context state createdAt targetUrl creator {{ login }}
                        }}
                      }}
                    }}
                  }}
                }} }} }}
              }}
            }}"""
        )
    return "query {\n" + "\n".join(fields) + "\n}"


def _paginated_head_checks(
    owner: str,
    repository: str,
    head_sha: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch every exact-head check run and status context with timestamps."""

    checks: list[dict[str, Any]] = []
    try:
        check_pages = _run_json(
            [
                "api",
                "--paginate",
                "--slurp",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{owner}/{repository}/commits/{head_sha}/check-runs?per_page=100",
            ],
            timeout=90,
        )
        status_pages = _run_json(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{owner}/{repository}/commits/{head_sha}/statuses?per_page=100",
            ],
            timeout=90,
        )
    except ReconciliationError:
        return [], False
    for page in check_pages if isinstance(check_pages, list) else []:
        for row in (page.get("check_runs") or []) if isinstance(page, dict) else []:
            checks.append(
                {
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "conclusion": row.get("conclusion"),
                    "completed_at": row.get("completed_at"),
                    "url": row.get("details_url"),
                    "actor": (row.get("app") or {}).get("slug"),
                }
            )
    for page in status_pages if isinstance(status_pages, list) else []:
        for row in page if isinstance(page, list) else []:
            checks.append(
                {
                    "name": row.get("context"),
                    "status": "COMPLETED",
                    "conclusion": row.get("state"),
                    "completed_at": row.get("created_at"),
                    "url": row.get("target_url"),
                    "actor": (row.get("creator") or {}).get("login"),
                }
            )
    deduplicated: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in checks:
        key = (
            str(row.get("name") or ""),
            str(row.get("completed_at") or ""),
            str(row.get("url") or ""),
        )
        deduplicated.setdefault(key, row)
    return [deduplicated[key] for key in sorted(deduplicated)], True


def batch_receipts(
    urls: Iterable[str],
    aliases: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Fetch exact-head PR metadata and timestamped check contexts in batches."""

    normalized: dict[tuple[str, str, int], set[str]] = collections.defaultdict(set)
    for url in urls:
        parsed = parse_pr_url(url)
        if not parsed:
            continue
        owner, repo, number = parsed
        repository = canonical_repository(
            f"{owner}/{repo}",
            aliases=aliases,
        )
        if repository == "unknown":
            repository = f"{owner}/{repo}"
        current_owner, current_name = repository.split("/", 1)
        normalized[(current_owner, current_name, number)].add(url)
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    keys = sorted(normalized)
    for offset in range(0, len(keys), 20):
        chunk = keys[offset : offset + 20]
        query = _receipt_query(chunk)
        try:
            payload = _run_json(
                ["api", "graphql", "-f", f"query={query}"],
                attempts=3,
                timeout=90,
            )
        except ReconciliationError:
            errors.append(f"batch-{offset // 20 + 1}:unavailable")
            continue
        data = payload.get("data") or {}
        if payload.get("errors"):
            errors.append(f"batch-{offset // 20 + 1}:graphql-partial")
        for index, key in enumerate(chunk):
            owner, repo, number = key
            container = data.get(f"r{index}")
            if not isinstance(container, dict):
                # The repository may be private or inaccessible. Never publish its identity.
                errors.append("missing:redacted-private-or-inaccessible")
                continue
            pull = container.get("p")
            if not isinstance(pull, dict):
                error = (
                    "missing:redacted-private-or-inaccessible"
                    if container.get("isPrivate")
                    else f"missing:{owner}/{repo}#{number}"
                )
                errors.append(error)
                continue
            commit_nodes = (pull.get("commits") or {}).get("nodes") or []
            commits: list[dict[str, Any]] = []
            checks: list[dict[str, Any]] = []
            historical_complete = True
            for node in commit_nodes:
                commit = node.get("commit") or {}
                commits.append(
                    {
                        "committed_at": commit.get("committedDate"),
                        "head_sha": commit.get("oid"),
                    }
                )
                contexts = (commit.get("statusCheckRollup") or {}).get("contexts") or {}
                if (contexts.get("pageInfo") or {}).get("hasNextPage"):
                    historical_complete = False
                for context in contexts.get("nodes") or []:
                    if context.get("__typename") == "CheckRun":
                        checks.append(
                            {
                                "name": context.get("name"),
                                "status": context.get("status"),
                                "conclusion": context.get("conclusion"),
                                "completed_at": context.get("completedAt"),
                                "url": context.get("detailsUrl"),
                                "actor": ((context.get("checkSuite") or {}).get("app") or {}).get("slug"),
                            }
                        )
                    elif context.get("__typename") == "StatusContext":
                        checks.append(
                            {
                                "name": context.get("context"),
                                "status": "COMPLETED",
                                "conclusion": context.get("state"),
                                "completed_at": context.get("createdAt"),
                                "url": context.get("targetUrl"),
                                "actor": (context.get("creator") or {}).get("login"),
                            }
                        )
            head_sha = pull.get("headRefOid")
            if head_sha:
                paginated_checks, paginated_complete = _paginated_head_checks(
                    owner,
                    repo,
                    str(head_sha),
                )
                if paginated_complete:
                    checks = paginated_checks
                    historical_complete = True
                else:
                    historical_complete = False
                    errors.append(
                        "checks:redacted-private-or-inaccessible"
                        if container.get("isPrivate")
                        else f"checks:{owner}/{repo}#{number}:unavailable"
                    )
            else:
                historical_complete = False
            is_private = bool(container.get("isPrivate"))
            public_url = None if is_private else pull.get("url")
            receipt = {
                "url": public_url,
                "canonical_url": public_url,
                "title": None if is_private else pull.get("title"),
                "author": (pull.get("author") or {}).get("login"),
                "merged_by": (pull.get("mergedBy") or {}).get("login"),
                "created_at": pull.get("createdAt"),
                "merged_at": pull.get("mergedAt"),
                "closed_at": pull.get("closedAt"),
                "base_ref": pull.get("baseRefName"),
                "default_branch": (container.get("defaultBranchRef") or {}).get("name"),
                "head_sha": head_sha,
                "commits": commits,
                "checks": checks,
                "historical_check_contexts_complete": historical_complete,
                "private": is_private,
                "canonical_repo": ("remote GitHub repository" if is_private else container.get("nameWithOwner")),
            }
            for original in normalized[key]:
                found[original] = receipt
            if public_url:
                found[str(public_url)] = receipt
    return found, errors


def receipt_role_credits(receipt: dict[str, Any]) -> dict[str, Any]:
    """Keep execution, verification, integration, and landing actors distinct."""

    verifiers = sorted({str(check.get("actor")) for check in receipt.get("checks") or [] if check.get("actor")})
    return {
        "executor": receipt.get("author"),
        "verifiers": verifiers,
        # The PR-head APIs used here do not prove who composed a merge-group.
        # Keep integration unknown rather than assigning it to author/merger.
        "integrator": receipt.get("integrator"),
        "lander": receipt.get("merged_by"),
    }


def _summary(
    sessions: list[dict[str, Any]],
    asks: list[dict[str, Any]],
    config: ReviewConfig,
) -> dict[str, Any]:
    comparison: list[dict[str, Any]] = []
    review_agents = [
        *AGENTS,
        *sorted(
            {
                str(row.get("agent") or "")
                for row in [*sessions, *asks]
                if row.get("agent") and str(row.get("agent")) not in AGENTS
            }
        ),
    ]
    for window in config.windows:
        for agent in review_agents:
            matched = []
            intervals = []
            tokens: collections.Counter[str] = collections.Counter()
            for session in sessions:
                if session["agent"] != agent:
                    continue
                clipped = window.clip(
                    parse_ts(session.get("start")),
                    parse_ts(session.get("end")),
                )
                if clipped is None:
                    continue
                matched.append(session)
                if "unknown" not in str(session.get("time_basis")) and clipped[1] > clipped[0]:
                    intervals.append(clipped)
                for event in session.get("token_events") or []:
                    timestamp = parse_ts(event.get("timestamp"))
                    if window.contains(timestamp):
                        tokens.update(event.get("components") or {})
            ask_rows = [
                ask
                for ask in asks
                if ask.get("agent") == agent
                and (observed := parse_ts(ask.get("observed_at"))) is not None
                and window.contains(observed)
            ]
            comparison.append(
                {
                    "window": window.label,
                    "agent": agent,
                    "root_sessions": sum(row.get("role") == "root" for row in matched),
                    "child_sessions": sum(row.get("role") == "child" for row in matched),
                    "session_span_hours": round(
                        sum((end - start).total_seconds() for start, end in intervals) / 3600,
                        2,
                    ),
                    "union_wall_hours": round(union_seconds(intervals) / 3600, 2),
                    "asks_observed": len(ask_rows),
                    "verified_done": sum(row.get("outcome") == "verified_done" for row in ask_rows),
                    "open_or_unknown": sum(
                        row.get("outcome")
                        in {
                            "durably_homed_open",
                            "not_done_or_unverified",
                            "coverage_unknown",
                        }
                        for row in ask_rows
                    ),
                    "token_basis": (", ".join(TOKEN_KEYS[agent]) if agent in TOKEN_KEYS else "unknown"),
                    **{key: tokens[key] for key in TOKEN_KEYS.get(agent, ())},
                }
            )
    agents = sorted({row["agent"] for row in comparison})
    outcome_distribution = [
        {
            "agent": agent,
            "outcome": outcome,
            "ask_count": sum(ask.get("agent") == agent and ask.get("outcome") == outcome for ask in asks),
        }
        for agent in agents
        for outcome in OUTCOMES
    ]
    appendix = {
        agent: [
            {
                "session": f"{agent}-{index:04d}",
                "role": row["role"],
                "parent_session": (f"{agent}-parent" if row.get("parent_id") else None),
                "start": row["start"],
                "end": row["end"],
                "time_basis": row["time_basis"],
                "events": row["events"],
                "source_atom_ids": row.get("source_atom_ids") or [],
                "canonical_repo": row.get("canonical_repo") or "unknown",
                "executor_role": row.get("executor_role") or "executor",
                "outcome": row.get("outcome") or "coverage_unknown",
                "coverage_flags": row.get("coverage_flags") or [],
            }
            for index, row in enumerate(
                sorted(
                    (session for session in sessions if session["agent"] == agent),
                    key=lambda value: str(value.get("start") or ""),
                ),
                start=1,
            )
        ]
        for agent in agents
    }
    return {
        "comparison": comparison,
        "root_session_volume": [
            {
                "window": row["window"],
                "agent": row["agent"],
                "root_sessions": row["root_sessions"],
                "child_sessions": row["child_sessions"],
                "union_wall_hours": row["union_wall_hours"],
                "asks_observed": row["asks_observed"],
            }
            for row in comparison
        ],
        "outcome_distribution": outcome_distribution,
        "session_appendix": appendix,
    }


def reconcile_snapshot(
    snapshot: dict[str, Any],
    config: ReviewConfig,
    *,
    receipt_urls_by_ask: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Reconcile exact atoms to semantic receipts and rebuild derived summaries."""

    receipt_urls_by_ask = receipt_urls_by_ask or {}
    evidence_repositories = {str(ask.get("canonical_repo") or "") for ask in snapshot.get("asks") or []}
    for bindings in receipt_urls_by_ask.values():
        for binding in bindings:
            url = str(binding.get("url") or "")
            parsed = parse_pr_url(url)
            if parsed:
                evidence_repositories.add(f"{parsed[0]}/{parsed[1]}")
    aliases, repo_count, owners = estate_census(
        config.root,
        evidence_repositories=evidence_repositories,
    )
    start = iso_z(min(window.start for window in config.windows)) or ""
    end = iso_z(config.snapshot_at - dt.timedelta(seconds=1)) or ""
    copilot_urls = coding_agent_receipts(owners, start=start, end=end)
    all_urls = sorted(
        {
            url
            for bindings in receipt_urls_by_ask.values()
            for binding in bindings
            for url in [str(binding.get("url") or "")]
            if parse_pr_url(url)
        }
        | set(copilot_urls)
    )
    receipts, errors = batch_receipts(all_urls, aliases)
    public_receipts: dict[str, dict[str, Any]] = {}
    for ask in snapshot.get("asks") or []:
        linked: list[dict[str, Any]] = []
        assistance: list[str] = []
        for binding in receipt_urls_by_ask.get(str(ask.get("ask")), []):
            url = str(binding.get("url") or "")
            receipt = receipts.get(url)
            if not receipt:
                continue
            # The owner-link index is the exact atom-to-receipt authority. Carry
            # that binding into the receipt rather than inferring from text.
            bound_receipt = {
                **receipt,
                "source_atom_ids": list(ask.get("source_atom_ids") or []),
                "predicate_result": binding.get("predicate_result"),
                "predicate_checked_at": binding.get("predicate_checked_at"),
                "receipt_head_sha": binding.get("receipt_head_sha"),
            }
            semantic, reason = semantic_receipt_link(ask, bound_receipt)
            if semantic:
                linked.append(bound_receipt)
            else:
                assistance.append(reason)
        if linked:
            classified = []
            for receipt in linked:
                predicate_checked_at = parse_ts(receipt.get("predicate_checked_at"))
                predicate_result = receipt.get("predicate_result")
                predicate_signal = bool(
                    isinstance(predicate_result, dict)
                    and predicate_result.get("passed") is True
                    and predicate_checked_at is not None
                    and predicate_checked_at <= config.snapshot_at
                    and receipt.get("receipt_head_sha")
                    and receipt.get("receipt_head_sha") == receipt.get("head_sha")
                )
                outcome, reason = classify_receipt(
                    receipt,
                    snapshot_at=config.snapshot_at,
                    predicate_signal=predicate_signal,
                )
                receipt["outcome"] = outcome
                receipt["reason"] = reason
                classified.append(receipt)
            chosen = max(classified, key=lambda row: outcome_rank(row["outcome"]))
            ask.update(
                {
                    "outcome": chosen["outcome"],
                    "receipt": chosen.get("url"),
                    "receipt_head_sha": chosen.get("head_sha"),
                    "predicate_result": {
                        "passed": chosen["outcome"] == "verified_done",
                        "detail": chosen["reason"],
                    },
                    "predicate_checked_at": iso_z(config.snapshot_at),
                    "canonical_repo": canonical_repository(
                        chosen.get("canonical_repo"),
                        aliases=aliases,
                    ),
                }
            )
            if chosen.get("url"):
                public_receipts[str(chosen["url"])] = chosen
        elif assistance:
            ask["coverage_flags"] = sorted(set(ask.get("coverage_flags") or []) | {"receipt_assistance_only"})
            ask["outcome"] = "coverage_unknown"
    copilot_by_key: dict[str, dict[str, Any]] = {}
    for url in copilot_urls:
        receipt = receipts.get(url)
        parsed = parse_pr_url(url)
        if not receipt or not parsed:
            continue
        repository = (
            "remote GitHub repository"
            if receipt.get("private")
            else canonical_repository(
                receipt.get("canonical_repo"),
                aliases=aliases,
            )
        )
        ask_id, key = copilot_ask_id(repository, parsed[2])
        outcome, reason = classify_receipt(
            receipt,
            snapshot_at=config.snapshot_at,
        )
        copilot_by_key[key] = {
            "ask": ask_id,
            "copilot_key": key,
            "source_atom_ids": [],
            "agent": "copilot",
            "subject": (
                "GitHub coding-agent work item"
                if receipt.get("private")
                else receipt.get("title") or "GitHub coding-agent work item"
            ),
            "canonical_repo": repository,
            "executor_role": "executor",
            "outcome": "coverage_unknown",
            "receipt": receipt.get("url"),
            "receipt_head_sha": receipt.get("head_sha"),
            "predicate_result": {
                "passed": False,
                "detail": "coding-agent PR has no exact prompt atom binding",
            },
            "predicate_checked_at": iso_z(config.snapshot_at),
            "observed_at": receipt.get("created_at"),
            "coverage_flags": ["coverage_unknown", "missing_source_atom"],
            "receipt_classification": {"outcome": outcome, "detail": reason},
        }
        if receipt.get("url"):
            public_receipts[str(receipt["url"])] = {
                **receipt,
                "outcome": outcome,
                "reason": reason,
            }
    non_copilot = [ask for ask in snapshot.get("asks") or [] if not ask.get("copilot_key")]
    snapshot["asks"] = non_copilot + [copilot_by_key[key] for key in sorted(copilot_by_key)]
    snapshot["deliverables"] = sorted(
        [
            {
                "title": receipt.get("title"),
                "receipt": url,
                "receipt_head_sha": receipt.get("head_sha"),
                "outcome": receipt.get("outcome"),
                **receipt_role_credits(receipt),
                "predicate_result": {
                    "passed": receipt.get("outcome") == "verified_done",
                    "detail": receipt.get("reason"),
                },
                "predicate_checked_at": iso_z(config.snapshot_at),
            }
            for url, receipt in public_receipts.items()
            if receipt.get("outcome") in {"verified_done", "verified_partial"}
        ],
        key=lambda row: (
            row["outcome"] != "verified_done",
            str(row["executor"] or ""),
            str(row["title"] or ""),
        ),
    )
    snapshot["estate"] = {
        "registry": "institutio/github/estate.yaml",
        "owners": owners,
        "remote_repository_count": repo_count,
        "evidence_repository_union": True,
        "redirects_resolved": True,
    }
    snapshot["reconciliation"] = {
        "state": "complete" if not errors else "partial",
        "candidate_pr_urls": len(all_urls),
        "resolved_pr_urls": sum(url in receipts for url in all_urls),
        "batch_errors": errors,
        "remote_repository_count": repo_count,
        "copilot_coding_agent_receipts": len(copilot_urls),
        "semantic_linkage_required": True,
        "timestamped_exact_head_checks": True,
    }
    snapshot.update(
        _summary(
            snapshot.pop("_sessions", []),
            snapshot["asks"],
            config,
        )
    )
    return snapshot
