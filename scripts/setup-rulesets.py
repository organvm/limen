#!/usr/bin/env python3
"""setup-rulesets — contain merge effects, then install exact-head acceptance.

Containment is deliberately independent from branch protection and its account/App prerequisites:
  • ``--contain`` previews every active auto-merge request and both repository merge settings
  • ``--contain apply`` cancels every active auto-merge request, sets ``allow_auto_merge=false``
    and ``delete_branch_on_merge=false``, then reads both surfaces back and fails on any mismatch

After containment is verified, ``--apply`` installs protected rules only for repos that already
publish the trusted review-gate workflow from their default branch:
  • required_status_checks = current-head CI plus an app-bound ``limen.pr_review_gate.v1``
  • required_pull_request_reviews = stale dismissal without a native-login approval count
  • required_conversation_resolution = true
  • enforce_admins = true

The protected gate identifies its live GitHub App producer dynamically; an actor-agnostic status with
the same name cannot satisfy it. Administrator actions are subject to the same acceptance boundary.

SAFE: both operations preview by default and execute NOTHING. Mutations are explicit and separate.

  python3 scripts/setup-rulesets.py --contain          # containment preview (read-only)
  python3 scripts/setup-rulesets.py --contain apply    # ⚠ cancel auto-merge + lock settings
  python3 scripts/setup-rulesets.py                    # protection preview (read-only)
  python3 scripts/setup-rulesets.py --apply --review-app-slug keeper-gate  # ⚠ install protection
  python3 scripts/setup-rulesets.py --repo owner/name [...]   # limit to specific repos
  python3 scripts/setup-rulesets.py --contexts pr-gate,python,web   # force CI names; review gate remains
"""

import json
import re
import subprocess
import sys
from collections import OrderedDict


def _parse_contain_mode(argv):
    positions = [index for index, value in enumerate(argv) if value == "--contain"]
    if not positions:
        return None, ""
    if len(positions) != 1:
        return None, "--contain may be supplied only once"
    if "--apply" in argv:
        return None, "--contain and --apply are separate operations"
    index = positions[0]
    mode = "preview"
    if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
        mode = argv[index + 1]
    if mode not in {"preview", "apply"}:
        return None, "--contain accepts only 'preview' or 'apply'"
    return mode, ""


APPLY = "--apply" in sys.argv
CONTAIN_MODE, ARGUMENT_ERROR = _parse_contain_mode(sys.argv)
EXPLICIT = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--repo" and i + 1 < len(sys.argv)]
# --contexts a,b,c overrides auto-detection entirely — the explicit fallback for any repo whose job
# names the heuristic can't classify. Applied to every targeted repo.
FORCED = next(
    (sys.argv[i + 1].split(",") for i, a in enumerate(sys.argv) if a == "--contexts" and i + 1 < len(sys.argv)), None
)
FORCED = [c.strip() for c in FORCED if c.strip()] if FORCED else None
REVIEW_GATE_APP_SLUG = next(
    (
        sys.argv[i + 1]
        for i, argument in enumerate(sys.argv)
        if argument == "--review-app-slug" and i + 1 < len(sys.argv)
    ),
    None,
)
REVIEW_GATE_CONTEXT = "limen.pr_review_gate.v1"
REVIEW_GATE_WORKFLOW = ".github/workflows/pr-review-gate.yml"
RECOVERY_COHORT_REPOS = (
    "organvm/limen",
    "organvm/domus-genoma",
    "organvm/universal-mail--automation",
    "organvm/daily-engine",
    "organvm/application-pipeline",
    "organvm/public-record-data-scrapper",
    "organvm/_agent",
)
MAX_PULL_REQUEST_PAGES = 1000
AUTO_MERGE_QUERY = """
query RecoveryAutoMergeRequests($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      nodes {
        id
        number
        url
        autoMergeRequest {
          enabledAt
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""
DISABLE_AUTO_MERGE_MUTATION = """
mutation DisableRecoveryAutoMerge($pullRequestId: ID!) {
  disablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId}) {
    pullRequest {
      id
      number
      autoMergeRequest {
        enabledAt
      }
    }
  }
}
"""


def gh(args, t=45, *, input_text=None):
    return subprocess.run(
        ["gh"] + args,
        capture_output=True,
        input=input_text,
        text=True,
        timeout=t,
    )


def gh_json(args, t=45, default=None):
    result = gh(args, t)
    if result.returncode != 0:
        return default
    try:
        return json.loads(result.stdout or "null") or default
    except json.JSONDecodeError:
        return default


def checked_gh_json(args, t=45):
    """Read one API object without turning transport or JSON failures into false state."""

    result = gh(args, t)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"gh exited {result.returncode}"
        return None, detail
    try:
        return json.loads(result.stdout or "null"), ""
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON response: {exc.msg}"


def target_repos():
    if EXPLICIT:
        return EXPLICIT
    prs = (
        gh_json(
            ["search", "prs", "--author", "@me", "--state", "open", "--limit", "200", "--json", "repository"],
            default=[],
        )
        or []
    )
    seen = OrderedDict()
    for p in prs:
        seen[p["repository"]["nameWithOwner"]] = True
    return list(seen.keys())


def containment_repos():
    """Return the frozen recovery cohort unless an explicit bounded cohort is supplied."""

    return list(OrderedDict.fromkeys(EXPLICIT or RECOVERY_COHORT_REPOS))


def _repository_parts(repo: str):
    owner, separator, name = repo.partition("/")
    if not separator or not owner or not name or "/" in name:
        return None
    return owner, name


def _graphql_error(value) -> str:
    if not isinstance(value, dict):
        return "GraphQL response is not an object"
    errors = value.get("errors")
    if errors:
        return f"GraphQL returned errors: {json.dumps(errors, sort_keys=True)[:300]}"
    return ""


def list_active_auto_merges(repo: str):
    """Read every open PR page and return only current auto-merge requests."""

    parts = _repository_parts(repo)
    if parts is None:
        return None, f"invalid repository name: {repo!r}"
    owner, name = parts
    cursor = None
    seen_cursors = set()
    seen_pull_ids = set()
    active = []
    for _page in range(1, MAX_PULL_REQUEST_PAGES + 1):
        args = [
            "api",
            "graphql",
            "-f",
            f"query={AUTO_MERGE_QUERY}",
            "-f",
            f"owner={owner}",
            "-f",
            f"name={name}",
        ]
        if cursor is not None:
            args.extend(["-f", f"cursor={cursor}"])
        value, error = checked_gh_json(args)
        if error:
            return None, f"auto-merge inventory failed: {error}"
        graphql_error = _graphql_error(value)
        if graphql_error:
            return None, graphql_error
        data = value.get("data")
        repository = data.get("repository") if isinstance(data, dict) else None
        pulls = repository.get("pullRequests") if isinstance(repository, dict) else None
        if not isinstance(pulls, dict):
            return None, "GraphQL response omitted repository pull requests"
        nodes = pulls.get("nodes")
        page_info = pulls.get("pageInfo")
        if not isinstance(nodes, list) or not isinstance(page_info, dict):
            return None, "GraphQL response omitted pull-request nodes or page information"
        for node in nodes:
            if not isinstance(node, dict):
                return None, "GraphQL pull-request node is not an object"
            if node.get("autoMergeRequest") is None:
                continue
            pull_id = node.get("id")
            number = node.get("number")
            if (
                not isinstance(pull_id, str)
                or not pull_id
                or pull_id in seen_pull_ids
                or not isinstance(number, int)
                or isinstance(number, bool)
                or number <= 0
            ):
                return None, "GraphQL returned an invalid or duplicate active pull request"
            seen_pull_ids.add(pull_id)
            active.append(
                {
                    "id": pull_id,
                    "number": number,
                    "url": node.get("url") if isinstance(node.get("url"), str) else "",
                }
            )
        has_next_page = page_info.get("hasNextPage")
        if not isinstance(has_next_page, bool):
            return None, "GraphQL pageInfo.hasNextPage is not boolean"
        if not has_next_page:
            return active, ""
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
            return None, "GraphQL pagination cursor is missing or did not advance"
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return None, f"auto-merge inventory exceeded {MAX_PULL_REQUEST_PAGES} pages"


def cancel_auto_merge(pull):
    """Cancel one active request and verify the mutation response is fail closed."""

    pull_id = pull.get("id") if isinstance(pull, dict) else None
    if not isinstance(pull_id, str) or not pull_id:
        return False, "active auto-merge request has no pull-request node id"
    value, error = checked_gh_json(
        [
            "api",
            "graphql",
            "-f",
            f"query={DISABLE_AUTO_MERGE_MUTATION}",
            "-f",
            f"pullRequestId={pull_id}",
        ]
    )
    if error:
        return False, f"cancel failed: {error}"
    graphql_error = _graphql_error(value)
    if graphql_error:
        return False, graphql_error
    data = value.get("data")
    disabled = data.get("disablePullRequestAutoMerge") if isinstance(data, dict) else None
    returned_pull = disabled.get("pullRequest") if isinstance(disabled, dict) else None
    if (
        not isinstance(returned_pull, dict)
        or returned_pull.get("id") != pull_id
        or returned_pull.get("autoMergeRequest") is not None
    ):
        return False, "cancel response did not confirm autoMergeRequest=null for the exact pull request"
    return True, ""


# A genuine merge gate is the test/build/lint suite — NOT bots, scanners, release-drafters, or CLA.
# Requiring the latter (strict) would permanently block merges (they never reliably "pass" per-PR).
# The token list includes this estate's own CI job names (derived from .github/workflows): the
# always-on `pr-gate` workflow (matched by `gate`, the `-` is a word boundary) plus ci.yml's
# `python` / `web` / `worker` jobs — without these the limen-style repos report "no checks detected".
_GATE = re.compile(
    r"\b(test|build|lint|typecheck|type-check|e2e|tox|matrix|smoke|unit|compile|gate|gates|pytest|jest|vitest|doctor|python|web|worker)\b",
    re.I,
)
_NOISE = re.compile(
    r"(cla|dependabot|release[_-]?draft|sourcery|coderabbit|gitguardian|semgrep|secret|codeql|analyze|advisory|scan|pr title|pr comment|^release$)",
    re.I,
)


def is_real_gate(name):
    return bool(_GATE.search(name)) and not _NOISE.search(name)


def detect_checks(repo):
    """genuine CI gate names from the newest open PR's rollup (filtered: real test/build/lint only)."""
    if FORCED:
        return list(FORCED)
    prs = (
        gh_json(["pr", "list", "--repo", repo, "--state", "open", "--limit", "1", "--json", "number"], default=[]) or []
    )
    if not prs:
        return []
    d = gh_json(["pr", "view", str(prs[0]["number"]), "--repo", repo, "--json", "statusCheckRollup"], default={}) or {}
    names = []
    for c in d.get("statusCheckRollup") or []:
        n = c.get("name") or c.get("context")
        if n and n not in names and is_real_gate(n):
            names.append(n)
    return names


def review_gate_publisher_available(repo: str, branch: str) -> bool:
    """Prove the required status has a base-controlled producer before requiring it.

    Installing a required context in a repository that cannot publish it would deadlock every PR.
    The workflow must already exist on the live default branch; a copy present only in a local or PR
    branch is deliberately insufficient.
    """

    value = (
        gh_json(
            [
                "api",
                "--method",
                "GET",
                f"repos/{repo}/contents/{REVIEW_GATE_WORKFLOW}",
                "-f",
                f"ref={branch}",
            ],
            default={},
        )
        or {}
    )
    return isinstance(value, dict) and value.get("type") == "file" and bool(value.get("sha"))


def configured_review_gate_app_slug() -> str | None:
    """Return the explicitly trusted dedicated review-gate App slug, never generic Actions."""

    slug = REVIEW_GATE_APP_SLUG.strip() if isinstance(REVIEW_GATE_APP_SLUG, str) else ""
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?", slug):
        return None
    # GitHub's generic Actions App is shared by every workflow in the repository. Binding a
    # context to it does not bind that context to this workflow or event, so it is not an
    # independent acceptance principal.
    if slug == "github-actions":
        return None
    return slug


def review_gate_app_id(repo: str, expected_slug: str) -> int | None:
    """Derive the unique live App id for the explicitly trusted dedicated App slug.

    The id is never stored in code.  A current check run must prove the mapping from the configured
    slug to one live id. Generic ``github-actions`` runs and runs from every other App are ignored.
    """

    if expected_slug == "github-actions" or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?", expected_slug):
        return None

    pulls = (
        gh_json(
            ["api", f"repos/{repo}/pulls?state=open&per_page=20"],
            default=[],
        )
        or []
    )
    app_ids: set[int] = set()
    for pull in pulls:
        if not isinstance(pull, dict):
            continue
        head = pull.get("head")
        sha = str(head.get("sha") or "") if isinstance(head, dict) else ""
        if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
            continue
        result = (
            gh_json(
                [
                    "api",
                    "-H",
                    "Accept: application/vnd.github+json",
                    f"repos/{repo}/commits/{sha}/check-runs?per_page=100",
                ],
                default={},
            )
            or {}
        )
        for run in result.get("check_runs") or []:
            if not isinstance(run, dict) or run.get("name") != REVIEW_GATE_CONTEXT:
                continue
            app = run.get("app")
            app_id = app.get("id") if isinstance(app, dict) and app.get("slug") == expected_slug else None
            if isinstance(app_id, int) and not isinstance(app_id, bool) and app_id > 0:
                app_ids.add(app_id)
    return next(iter(app_ids)) if len(app_ids) == 1 else None


def project_contexts(detected_checks):
    """Keep project CI separate from the one dedicated-App-bound acceptance context."""

    return [context for context in OrderedDict.fromkeys(detected_checks) if context != REVIEW_GATE_CONTEXT]


def required_contexts(detected_checks):
    """Return stable project CI contexts with exactly one review receipt gate."""

    return [*project_contexts(detected_checks), REVIEW_GATE_CONTEXT]


def protection_body(detected_checks, review_app_id: int):
    """Build the fail-closed branch-protection contract for one default branch."""
    if not isinstance(review_app_id, int) or isinstance(review_app_id, bool) or review_app_id <= 0:
        raise ValueError("review_app_id must be a positive live GitHub App id")
    return {
        "required_status_checks": {
            "strict": True,
            "checks": [
                *({"context": context} for context in project_contexts(detected_checks)),
                {"context": REVIEW_GATE_CONTEXT, "app_id": review_app_id},
            ],
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            # The custom exact-head status accepts either a distinct GitHub login or a
            # separately custodied SSH keeper principal. Requiring one native approval here
            # would deadlock co-equal keepers that share the operator's GitHub credential.
            "required_approving_review_count": 0,
            "require_last_push_approval": False,
        },
        "required_conversation_resolution": True,
        "restrictions": None,
    }


def _enabled(value):
    """Normalize GitHub's boolean and ``{"enabled": bool}`` response shapes."""

    if isinstance(value, bool):
        return value
    if isinstance(value, dict) and isinstance(value.get("enabled"), bool):
        return value["enabled"]
    return None


def repository_settings_match(value) -> tuple[bool, str]:
    if not isinstance(value, dict):
        return False, "repository settings response is not an object"
    mismatches = []
    if value.get("allow_auto_merge") is not False:
        mismatches.append("allow_auto_merge is not false")
    if value.get("delete_branch_on_merge") is not False:
        mismatches.append("delete_branch_on_merge is not false")
    return not mismatches, "; ".join(mismatches)


def repository_settings_state(value):
    if not isinstance(value, dict):
        return None, "repository settings response is not an object"
    allow_auto_merge = value.get("allow_auto_merge")
    delete_branch_on_merge = value.get("delete_branch_on_merge")
    if not isinstance(allow_auto_merge, bool) or not isinstance(delete_branch_on_merge, bool):
        return None, "repository settings response omitted boolean merge settings"
    return {
        "allow_auto_merge": allow_auto_merge,
        "delete_branch_on_merge": delete_branch_on_merge,
    }, ""


def _normalized_checks(value):
    if not isinstance(value, list):
        return None
    normalized = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("context"), str):
            return None
        app_id = item.get("app_id")
        if app_id is not None and (not isinstance(app_id, int) or isinstance(app_id, bool) or app_id <= 0):
            return None
        normalized.append((item["context"], app_id))
    return sorted(normalized, key=lambda pair: (pair[0], pair[1] or 0))


def protection_matches(value, expected) -> tuple[bool, str]:
    """Verify the material live branch-protection contract after GitHub accepted the PUT."""

    if not isinstance(value, dict):
        return False, "branch protection response is not an object"
    mismatches = []
    actual_status = value.get("required_status_checks")
    expected_status = expected["required_status_checks"]
    if not isinstance(actual_status, dict):
        mismatches.append("required_status_checks missing")
    else:
        if actual_status.get("strict") is not True:
            mismatches.append("strict current-head checks are not enabled")
        actual_checks = _normalized_checks(actual_status.get("checks"))
        expected_checks = _normalized_checks(expected_status.get("checks"))
        if actual_checks is None or actual_checks != expected_checks:
            mismatches.append("required checks or App bindings differ")

    if _enabled(value.get("enforce_admins")) is not True:
        mismatches.append("administrator enforcement is not enabled")
    if _enabled(value.get("required_conversation_resolution")) is not True:
        mismatches.append("conversation resolution is not required")

    actual_reviews = value.get("required_pull_request_reviews")
    expected_reviews = expected["required_pull_request_reviews"]
    if not isinstance(actual_reviews, dict):
        mismatches.append("pull-request review policy missing")
    else:
        for field, expected_value in expected_reviews.items():
            if actual_reviews.get(field) != expected_value:
                mismatches.append(f"review policy {field} differs")

    if value.get("restrictions", object()) is not None:
        mismatches.append("push restrictions differ")
    return not mismatches, "; ".join(mismatches)


def _current_repository_settings(repo: str):
    value, error = checked_gh_json(["api", "--method", "GET", f"repos/{repo}"])
    if error:
        return None, f"repository settings read failed: {error}"
    state, state_error = repository_settings_state(value)
    if state_error:
        return None, state_error
    return state, ""


def _read_repository_settings(repo: str) -> tuple[bool, str]:
    value, error = _current_repository_settings(repo)
    if error:
        return False, error
    return repository_settings_match(value)


def _read_protection(repo: str, branch: str, expected) -> tuple[bool, str]:
    value, error = checked_gh_json(["api", "--method", "GET", f"repos/{repo}/branches/{branch}/protection"])
    if error:
        return False, f"branch protection read failed: {error}"
    return protection_matches(value, expected)


def apply_protection_contract(repo: str, branch: str, body) -> tuple[bool, list[str]]:
    """Install protection only after the independent containment state is live."""

    messages = []
    settings_ok, settings_detail = _read_repository_settings(repo)
    if not settings_ok:
        return False, [
            f"repository containment prerequisite not confirmed: {settings_detail}; run --contain apply first"
        ]

    protection = gh(
        [
            "api",
            "--method",
            "PUT",
            f"repos/{repo}/branches/{branch}/protection",
            "--input",
            "-",
        ],
        input_text=json.dumps(body),
    )
    if protection.returncode != 0:
        detail = protection.stderr.strip() or f"gh exited {protection.returncode}"
        return False, [f"branch protection update failed with auto-merge off: {detail}"]

    # Re-read both surfaces after the protection mutation. This catches API normalization,
    # insufficient permissions, and a concurrent settings flip. Run both reads so a partial remote
    # transaction returns every observable mismatch while remaining fail closed.
    final_settings_ok, final_settings_detail = _read_repository_settings(repo)
    if not final_settings_ok:
        messages.append(f"repository fail-closed settings changed: {final_settings_detail}")
    protection_ok, protection_detail = _read_protection(repo, branch, body)
    if not protection_ok:
        messages.append(f"branch protection not confirmed: {protection_detail}")
    return not messages, messages


def apply_repository_containment(repo: str):
    """Cancel current requests, lock both settings, and re-read every effect."""

    messages = []
    initial_active, initial_error = list_active_auto_merges(repo)
    initial_count = None if initial_active is None else len(initial_active)
    cancelled = 0
    if initial_error:
        messages.append(initial_error)
    else:
        for pull in initial_active:
            accepted, detail = cancel_auto_merge(pull)
            if accepted:
                cancelled += 1
            else:
                messages.append(f"PR #{pull['number']} auto-merge {detail}")

    settings = gh(
        [
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}",
            "-F",
            "allow_auto_merge=false",
            "-F",
            "delete_branch_on_merge=false",
        ]
    )
    if settings.returncode != 0:
        detail = settings.stderr.strip() or f"gh exited {settings.returncode}"
        messages.append(f"repository containment settings update failed: {detail}")

    settings_ok, settings_detail = _read_repository_settings(repo)
    if not settings_ok:
        messages.append(f"repository containment settings not confirmed: {settings_detail}")

    remaining, remaining_error = list_active_auto_merges(repo)
    remaining_count = None if remaining is None else len(remaining)
    if remaining_error:
        messages.append(f"post-containment {remaining_error}")
    elif remaining:
        numbers = ", ".join(f"#{pull['number']}" for pull in remaining[:10])
        suffix = "…" if len(remaining) > 10 else ""
        messages.append(f"active auto-merge requests remain: {numbers}{suffix}")

    return (
        not messages,
        {
            "initial_active": initial_count,
            "cancelled": cancelled,
            "remaining": remaining_count,
        },
        messages,
    )


def containment_main(*, apply: bool) -> int:
    repos = containment_repos()
    mode = "APPLY" if apply else "PREVIEW"
    print(f"=== recovery containment — {len(repos)} cohort repo(s) ({mode}) ===")
    failures = 0
    total_active = 0
    total_cancelled = 0
    for repo in repos:
        if apply:
            accepted, summary, messages = apply_repository_containment(repo)
            if summary["initial_active"] is not None:
                total_active += summary["initial_active"]
            total_cancelled += summary["cancelled"]
            if accepted:
                print(
                    f"  {repo}: ✓ cancelled {summary['cancelled']} active request(s); "
                    "allow_auto_merge=false; delete_branch_on_merge=false; readback verified"
                )
            else:
                failures += 1
                print(
                    f"  {repo}: ✗ containment incomplete "
                    f"(seen={summary['initial_active']}, cancelled={summary['cancelled']}, "
                    f"remaining={summary['remaining']})"
                )
                for message in messages:
                    print(f"      ✗ {message[:300]}")
            continue

        active, active_error = list_active_auto_merges(repo)
        settings, settings_error = _current_repository_settings(repo)
        if active_error or settings_error:
            failures += 1
            print(f"  {repo}: BLOCKED — containment evidence incomplete")
            if active_error:
                print(f"      ✗ {active_error[:300]}")
            if settings_error:
                print(f"      ✗ {settings_error[:300]}")
            continue
        total_active += len(active)
        print(
            f"  {repo}: {len(active)} active auto-merge request(s); "
            f"allow_auto_merge={str(settings['allow_auto_merge']).lower()}; "
            f"delete_branch_on_merge={str(settings['delete_branch_on_merge']).lower()}"
        )

    if apply:
        print(
            f"\nContainment apply: observed {total_active} active request(s), "
            f"confirmed {total_cancelled} cancellation(s), {failures} repo failure(s)."
        )
    else:
        print(
            f"\nPREVIEW — observed {total_active} active request(s); nothing changed. "
            "Re-run with --contain apply to cancel requests and lock repository settings."
        )
    return 1 if failures else 0


def protection_main():
    repos = target_repos()
    print(f"=== ruleset plan — {len(repos)} repos with open PRs ({'APPLY' if APPLY else 'DRY-RUN'}) ===")
    if FORCED:
        print(f"    contexts forced (detection skipped): {FORCED}")
    print()
    no_project_ci = []
    no_review_publisher = []
    no_review_app = []
    no_default_branch = []
    configured = 0
    failed = 0
    review_app_slug = configured_review_gate_app_slug()
    if review_app_slug is None:
        print(
            "    trust blocker: --review-app-slug must name a dedicated GitHub App (generic github-actions is rejected)"
        )
        print()
    for repo in repos:
        info = gh_json(["repo", "view", repo, "--json", "defaultBranchRef"], default={}) or {}
        branch = (info.get("defaultBranchRef") or {}).get("name")
        if not isinstance(branch, str) or not branch:
            no_default_branch.append(repo)
            print(f"  {repo}: BLOCKED — live default branch could not be read")
            if APPLY:
                failed += 1
            continue
        detected_checks = project_contexts(detect_checks(repo))
        review_publisher = review_gate_publisher_available(repo, branch)
        review_app = (
            review_gate_app_id(repo, review_app_slug) if review_publisher and review_app_slug is not None else None
        )
        checks = required_contexts(detected_checks)
        if not detected_checks:
            no_project_ci.append(repo)
            print(
                f"  {repo}@{branch}: BLOCKED — no project CI checks detected; refusing a review-only "
                "protection contract"
            )
        elif not review_publisher:
            no_review_publisher.append(repo)
            print(
                f"  {repo}@{branch}: BLOCKED — {REVIEW_GATE_WORKFLOW} is absent from the live "
                "default branch; refusing to require an unpublishable status"
            )
        elif review_app is None:
            no_review_app.append(repo)
            print(
                f"  {repo}@{branch}: BLOCKED — no unique live {review_app_slug or 'dedicated'} "
                f"GitHub App producer exists for {REVIEW_GATE_CONTEXT}; refusing generic or "
                "actor-agnostic protection"
            )
        else:
            print(
                f"  {repo}@{branch}: require {len(checks)} check(s) {checks[:4]}"
                f"{'…' if len(checks) > 4 else ''} · strict current-head · native-or-signed "
                f"peer receipt · dedicated_app={review_app_slug}:{review_app} · stale dismissal · "
                "resolved conversations · admins enforced"
            )
        if not APPLY:
            continue
        # --- APPLY ---
        if not detected_checks or not review_publisher or review_app is None:
            reason = (
                "strict current-head project CI could not be derived"
                if not detected_checks
                else (
                    "trusted review-gate publisher is not deployed on the default branch"
                    if not review_publisher
                    else "review-gate GitHub App identity could not be derived uniquely"
                )
            )
            print(f"      ✗ unchanged: {reason}")
            failed += 1
            continue
        body = protection_body(detected_checks, review_app)
        accepted, messages = apply_protection_contract(repo, branch, body)
        if accepted:
            configured += 1
            print("      ✓ dedicated-app protection installed; independent containment remains verified live")
        else:
            failed += 1
            for message in messages:
                print(f"      ✗ {message[:200]}")

    print(
        f"\n{configured if APPLY else len(repos) - len(no_project_ci) - len(no_review_publisher) - len(no_review_app) - len(no_default_branch)} "
        f"repo(s) are eligible for project CI beside {REVIEW_GATE_CONTEXT}; "
        f"{len(no_project_ci)} blocked for missing project CI; "
        f"{len(no_review_publisher)} blocked for missing trusted publisher; "
        f"{len(no_review_app)} blocked for missing unique dedicated App identity; "
        f"{len(no_default_branch)} blocked for unreadable default branch."
    )
    if not APPLY:
        print("\nDRY-RUN — nothing changed. Re-run with --apply (GATED) to configure.")
        print("Run --contain apply first; --apply never changes repository merge settings.")
    elif failed:
        print(f"\nFAILED — {failed} repo transaction(s) were blocked or not verified.", file=sys.stderr)
    return 1 if APPLY and failed else 0


def main():
    if ARGUMENT_ERROR:
        print(f"argument error: {ARGUMENT_ERROR}", file=sys.stderr)
        return 2
    if CONTAIN_MODE is not None:
        return containment_main(apply=CONTAIN_MODE == "apply")
    return protection_main()


if __name__ == "__main__":
    raise SystemExit(main())
