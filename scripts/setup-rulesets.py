#!/usr/bin/env python3
"""setup-rulesets — install fail-closed, exact-head merge acceptance.

For each repo that currently has open author PRs and already publishes the trusted review-gate
workflow from its default branch, configure that branch so that:
  • required_status_checks = current-head CI plus an app-bound ``limen.pr_review_gate.v1``
  • required_pull_request_reviews = stale dismissal without a native-login approval count
  • required_conversation_resolution = true
  • enforce_admins = true
  • allow_auto_merge = false (merge effects require a short-lived signed authorization receipt)
  • delete_branch_on_merge = false  (source branches are retained for receipt-backed reaping)

The protected gate identifies its live GitHub App producer dynamically; an actor-agnostic status with
the same name cannot satisfy it. Administrator actions are subject to the same acceptance boundary.

SAFE: dry-run by default — prints the exact per-repo plan and executes NOTHING. Reversible:
branch protection can be removed. `--apply` is GATED on the user.

  python3 scripts/setup-rulesets.py            # dry-run plan (read-only)
  python3 scripts/setup-rulesets.py --apply     # ⚠ GATED: configure protection; disable auto-merge
  python3 scripts/setup-rulesets.py --repo owner/name [...]   # limit to specific repos
  python3 scripts/setup-rulesets.py --contexts pr-gate,python,web   # force CI names; review gate remains
"""

import json
import os
import re
import subprocess
import sys
from collections import OrderedDict

APPLY = "--apply" in sys.argv
EXPLICIT = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--repo" and i + 1 < len(sys.argv)]
# --contexts a,b,c overrides auto-detection entirely — the explicit fallback for any repo whose job
# names the heuristic can't classify. Applied to every targeted repo.
FORCED = next(
    (sys.argv[i + 1].split(",") for i, a in enumerate(sys.argv) if a == "--contexts" and i + 1 < len(sys.argv)), None
)
FORCED = [c.strip() for c in FORCED if c.strip()] if FORCED else None
REVIEW_GATE_CONTEXT = "limen.pr_review_gate.v1"
REVIEW_GATE_WORKFLOW = ".github/workflows/pr-review-gate.yml"
REVIEW_GATE_APP_SLUG_ENV = "LIMEN_REVIEW_GATE_APP_SLUG"


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

    slug = os.environ.get(REVIEW_GATE_APP_SLUG_ENV, "").strip()
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


def _read_repository_settings(repo: str) -> tuple[bool, str]:
    value, error = checked_gh_json(["api", "--method", "GET", f"repos/{repo}"])
    if error:
        return False, f"repository settings read failed: {error}"
    return repository_settings_match(value)


def _read_protection(repo: str, branch: str, expected) -> tuple[bool, str]:
    value, error = checked_gh_json(["api", "--method", "GET", f"repos/{repo}/branches/{branch}/protection"])
    if error:
        return False, f"branch protection read failed: {error}"
    return protection_matches(value, expected)


def apply_fail_closed_contract(repo: str, branch: str, body) -> tuple[bool, list[str]]:
    """Apply in safe order and verify live state; every partial result leaves auto-merge off."""

    messages = []
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
        return False, [f"repository fail-closed settings update failed: {detail}"]

    settings_ok, settings_detail = _read_repository_settings(repo)
    if not settings_ok:
        return False, [f"repository fail-closed settings not confirmed: {settings_detail}"]

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


def main():
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
            f"    trust blocker: {REVIEW_GATE_APP_SLUG_ENV} must name a dedicated GitHub App "
            "(generic github-actions is rejected)"
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
        accepted, messages = apply_fail_closed_contract(repo, branch, body)
        if accepted:
            configured += 1
            print("      ✓ dedicated-app protection and fail-closed repository settings verified live")
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
        print("After --apply, auto-merge remains disabled; signed merge-drain owns merge effects.")
    elif failed:
        print(f"\nFAILED — {failed} repo transaction(s) were blocked or not verified.", file=sys.stderr)
    return 1 if APPLY and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
