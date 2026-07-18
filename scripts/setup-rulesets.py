#!/usr/bin/env python3
"""setup-rulesets — configure self-draining, concurrency-safe merge gates.

For each repo that currently has open author PRs, configure the default branch so that:
  • required_status_checks = the repo's actual CI checks (strict:false)
  • required_pull_request_reviews = NONE  (there is no human reviewer team — requiring one is the
    faulty old element that forced the admin-bypass; we gate on CI instead)
  • allow_auto_merge = true  (so a PR armed with --auto merges itself the instant CI is green)
  • delete_branch_on_merge = false  (source branches are retained for receipt-backed reaping)

For organvm/limen only, keep the classic required check to `pr-gate` with
strict:false/enforce_admins:false, and idempotently ensure a default-branch ruleset whose only rule
is the native merge queue. The queue tests GitHub's synthetic integration commit instead of asking
every concurrent PR to merge a moving main and restart its already-green full CI.

SAFE: dry-run by default — prints the exact per-repo plan and executes NOTHING. Reversible:
branch protection can be removed. `--apply` is GATED on the user.

  python3 scripts/setup-rulesets.py            # dry-run plan (read-only)
  python3 scripts/setup-rulesets.py --apply     # ⚠ GATED: configure protection + auto-merge
  python3 scripts/setup-rulesets.py --repo owner/name [...]   # limit to specific repos
  python3 scripts/setup-rulesets.py --contexts pr-gate,python,web   # force these check names (skip detection)
"""

import json
import re
import subprocess
import sys
from collections import OrderedDict

MERGE_QUEUE_REPO = "organvm/limen"
MERGE_QUEUE_RULESET_NAME = "limen-default-merge-queue"
MERGE_QUEUE_PARAMETERS = {
    "check_response_timeout_minutes": 60,
    "grouping_strategy": "HEADGREEN",
    "max_entries_to_build": 4,
    "max_entries_to_merge": 1,
    "merge_method": "SQUASH",
    "min_entries_to_merge": 1,
    "min_entries_to_merge_wait_minutes": 0,
}

APPLY = "--apply" in sys.argv
EXPLICIT = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--repo" and i + 1 < len(sys.argv)]
# --contexts a,b,c overrides auto-detection entirely — the explicit fallback for any repo whose job
# names the heuristic can't classify. Applied to every targeted repo.
FORCED = next(
    (sys.argv[i + 1].split(",") for i, a in enumerate(sys.argv) if a == "--contexts" and i + 1 < len(sys.argv)), None
)
FORCED = [c.strip() for c in FORCED if c.strip()] if FORCED else None


def gh(args, t=45):
    return subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=t)


def gh_json(args, t=45, default=None):
    try:
        return json.loads(gh(args, t).stdout or "null") or default
    except json.JSONDecodeError:
        return default


def gh_input(method, path, body, t=45):
    """Call a mutating GitHub endpoint once with an explicit JSON body."""
    return subprocess.run(
        ["gh", "api", "-X", method, path, "--input", "-"],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        timeout=t,
    )


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


def checks_for_repo(repo):
    """Return the classic required checks; Limen's queue has one stable required context."""
    if repo == MERGE_QUEUE_REPO:
        return ["pr-gate"]
    return detect_checks(repo)


def classic_protection_body(checks):
    """Classic CI protection stays non-strict and admin-bypassable for direct data writers."""
    return {
        # strict:false — gate on checks passing, NOT on branch-up-to-date, else auto-merge
        # deadlocks (nothing auto-updates behind branches) and we're back on the treadmill.
        "required_status_checks": {"strict": False, "contexts": checks},
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
    }


def merge_queue_ruleset_body():
    """The targeted Limen queue rule; no pull-request or direct-push restriction is added."""
    return {
        "name": MERGE_QUEUE_RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {
                "type": "merge_queue",
                "parameters": dict(MERGE_QUEUE_PARAMETERS),
            }
        ],
    }


def ensure_merge_queue(repo):
    """Idempotently create/update Limen's dedicated default-branch merge-queue ruleset."""
    if repo != MERGE_QUEUE_REPO:
        return None
    existing = gh_json(["api", f"/repos/{repo}/rulesets"], default=[]) or []
    rid = next((r.get("id") for r in existing if r.get("name") == MERGE_QUEUE_RULESET_NAME), None)
    method, path = ("PUT", f"/repos/{repo}/rulesets/{rid}") if rid else ("POST", f"/repos/{repo}/rulesets")
    result = gh_input(method, path, merge_queue_ruleset_body())
    ok = result.returncode == 0
    print(
        "      "
        + (
            "✓ limen merge-queue ruleset ensured"
            if ok
            else "✗ limen merge-queue ruleset: " + result.stderr.strip()[:60]
        )
    )
    return ok


_COPILOT_AVAILABLE = {}


def copilot_available(org):
    """One cached probe per org: does it hold ANY Copilot seat? (/orgs/{org}/copilot/billing
    .seat_breakdown.total > 0 — a 200 alone is NOT enough; the endpoint answers 200 with 0 seats
    while Copilot is unconfigured.) Gate for the copilot-review ruleset: no seat → clean no-op.
    Individual Copilot Pro (restored free 2026-07-17, #1186) is NOT an org Business seat — this
    stays a no-op unless org seats ever exist (docs/github-estate-runbook.md)."""
    if org not in _COPILOT_AVAILABLE:
        data = gh_json(["api", f"/orgs/{org}/copilot/billing"], t=20, default=None)
        total = ((data or {}).get("seat_breakdown") or {}).get("total") or 0
        _COPILOT_AVAILABLE[org] = total > 0
    return _COPILOT_AVAILABLE[org]


def ensure_copilot_review(repo):
    """Idempotently ensure the `copilot-review` repo RULESET (rulesets, not classic protection —
    automatic Copilot code review only exists there) requesting Copilot review on default-branch
    PRs. required_approving_review_count stays 0 so merge-drain is never blocked on an approval.
    Arms itself on the next --apply after the Copilot seat lands; until then a one-line skip."""
    org = repo.split("/", 1)[0]
    if not copilot_available(org):
        print(
            "      · copilot-review ruleset skipped — no org Copilot Business seat (individual Pro doesn't count; see runbook)"
        )
        return
    existing = gh_json(["api", f"/repos/{repo}/rulesets"], default=[]) or []
    rid = next((r.get("id") for r in existing if r.get("name") == "copilot-review"), None)
    body = {
        "name": "copilot-review",
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "automatic_copilot_code_review_enabled": True,
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                },
            }
        ],
    }
    method, path = ("PUT", f"/repos/{repo}/rulesets/{rid}") if rid else ("POST", f"/repos/{repo}/rulesets")
    r = gh_input(method, path, body)
    ok = r.returncode == 0
    print(f"      {'✓ copilot-review ruleset ensured' if ok else '✗ copilot-review ruleset: ' + r.stderr.strip()[:60]}")


def main():
    repos = target_repos()
    print(f"=== ruleset plan — {len(repos)} repos with open PRs ({'APPLY' if APPLY else 'DRY-RUN'}) ===")
    if FORCED:
        print(f"    contexts forced (detection skipped): {FORCED}")
    print()
    no_ci = []
    for repo in repos:
        info = gh_json(["repo", "view", repo, "--json", "defaultBranchRef"], default={}) or {}
        branch = (info.get("defaultBranchRef") or {}).get("name") or "main"
        checks = checks_for_repo(repo)
        if not checks:
            no_ci.append(repo)
            print(
                f"  {repo}@{branch}: ⚠ no CI checks detected → auto-merge N/A (PRs merge immediately); "
                f"would only set allow_auto_merge"
            )
        else:
            print(
                f"  {repo}@{branch}: require {len(checks)} check(s) {checks[:4]}"
                f"{'…' if len(checks) > 4 else ''} · no human review · allow_auto_merge=true"
            )
        if repo == MERGE_QUEUE_REPO:
            p = MERGE_QUEUE_PARAMETERS
            print(
                "      + default-branch merge queue: "
                f"{p['merge_method']} · {p['grouping_strategy']} · "
                f"timeout {p['check_response_timeout_minutes']}m · "
                f"build {p['max_entries_to_build']} · merge {p['max_entries_to_merge']} · "
                f"min {p['min_entries_to_merge']}/wait {p['min_entries_to_merge_wait_minutes']}m"
            )
        if not APPLY:
            continue
        # --- APPLY ---
        gh(
            [
                "api",
                "-X",
                "PATCH",
                f"/repos/{repo}",
                "-F",
                "allow_auto_merge=true",
                "-F",
                "delete_branch_on_merge=false",
            ]
        )
        if checks:
            body = classic_protection_body(checks)
            r = gh_input("PUT", f"/repos/{repo}/branches/{branch}/protection", body)
            ok = r.returncode == 0
            print(f"      {'✓ protected + auto-merge on' if ok else '✗ ' + r.stderr.strip()[:70]}")
        else:
            print("      ✓ allow_auto_merge set (no protection — no CI to gate on)")
        ensure_merge_queue(repo)
        # The review engine's Copilot lane — a ruleset, orthogonal to the classic protection above.
        ensure_copilot_review(repo)

    print(
        f"\n{len(repos) - len(no_ci)} repos gateable via CI; {len(no_ci)} have no CI "
        f"(auto-merge moot — they merge on creation)."
    )
    if not APPLY:
        print("\nDRY-RUN — nothing changed. Re-run with --apply (GATED) to configure.")
        if MERGE_QUEUE_REPO in repos:
            print(
                "After the Limen workflow lands and --apply succeeds: "
                "`scripts/await-pr.sh <n> --repo organvm/limen --merge` → exact-head queue rail."
            )
        if any(repo != MERGE_QUEUE_REPO for repo in repos):
            print("For non-queue repos: `gh pr merge <n> --auto --squash` on green PRs.")


if __name__ == "__main__":
    main()
