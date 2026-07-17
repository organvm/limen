#!/usr/bin/env bash
# merge-policy.sh — the executable predicate for "may this peer-authored PR merge?"
#
# Every canonical agent is a co-equal peer keeper. Executor identity is attribution, not
# ownership or merge authority. This predicate applies the same exact-head acceptance boundary
# to every PR regardless of which peer authored it. A merge to `main` auto-deploys the site/API
# only when the diff touches a deploy-trigger path, so that path receives an additional live-
# deployment check.
#
#   exit 0  CLEARED — exact head is an accepted merge candidate. This predicate never grants
#                     mutation authority; the signed receipt-bound merge executor is separate.
#   exit 2  HOLD    — website-sensitive AND CI not yet green/complete, or the PR is a draft,
#                     or a non-deploy PR still has checks running. Wait for green; never
#                     blind-merge a live deploy.
#   exit 3  BLOCKED — GitHub itself refuses the merge right now: conflicts (DIRTY), stale base
#                     (BEHIND), or a branch-protection gate not satisfied (BLOCKED — e.g. the
#                     required `pr-gate` check hasn't run on a pre-existing PR). Rebase onto
#                     current main (the PR#111 silent-revert guard; also retriggers required
#                     checks), then re-run. Distinct from HOLD: HOLD means GitHub would allow
#                     the merge but the website-safety policy says wait; BLOCKED means it can't.
#
# Usage:  scripts/merge-policy.sh [PR_NUMBER] [--repo OWNER/NAME] [--expected-head SHA]
#         (no PR number → resolves the PR open for the current branch)
set -euo pipefail

PR=""; REPO=""; EXPECTED_HEAD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --repo=*) REPO="${1#*=}"; shift ;;
    --expected-head) EXPECTED_HEAD="${2:-}"; shift 2 ;;
    --expected-head=*) EXPECTED_HEAD="${1#*=}"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) PR="$1"; shift ;;
  esac
done

repo_args=(); [ -n "$REPO" ] && repo_args=(--repo "$REPO")
# bash 3.2 (macOS /bin/bash) errors on a bare empty-array expansion under `set -u`. Use the
# array-plus idiom at each call site below, which expands to nothing for an empty array and to
# the elements otherwise — safe in bash 3.2 and 4+.

# Deploy-trigger classification — DERIVED from the GATES registry (institutio/governance/
# gates.yaml). check-gates.py holds the registry in exact set-parity with the deploy*.yml
# `on.push.paths` on every PR, so the old hardcoded regexes and their awk staleness guard
# are gone: one source of truth, one drift predicate. A push/merge to `main` touching a
# derived path auto-deploys the live public site/API.
#
# Fail toward caution: if derivation fails (missing python3/PyYAML/registry), STALE=1
# forces website-sensitive — a broken environment can only HOLD, never blind-deploy.
STALE=0
_root="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
REVIEW_GATE="${LIMEN_PR_REVIEW_GATE:-$_root/scripts/pr-review-gate.py}"
DEPLOY_RE="$(python3 "$_root/scripts/verify.py" --deploy-regex 2>/dev/null || true)"
if [ -z "$DEPLOY_RE" ]; then
  echo "merge-policy: cannot derive the deploy regex from the GATES registry — treating the PR as website-sensitive (fail toward caution)." >&2
  STALE=1
  DEPLOY_RE='^$'
fi

# Resolve the PR for the current branch when not given.
if [ -z "$PR" ]; then
  PR="$(gh pr view "${repo_args[@]+"${repo_args[@]}"}" --json number -q .number 2>/dev/null || true)"
  [ -z "$PR" ] && { echo "merge-policy: no PR number given and none open for the current branch." >&2; exit 3; }
fi

# Keep the check path zero-write: hold the bounded GitHub response in memory instead of creating
# a temporary file. `--apply` does not exist here; this command is a predicate only.
j="$(gh pr view "$PR" "${repo_args[@]+"${repo_args[@]}"}" \
  --json number,title,url,state,isDraft,mergeStateStatus,baseRefName,headRefName,headRefOid,files,statusCheckRollup \
  2>/dev/null)" || { echo "merge-policy: cannot read PR #$PR (wrong repo?)." >&2; exit 3; }

title=$(printf '%s\n' "$j" | jq -r '.title')
url=$(printf '%s\n' "$j" | jq -r '.url')
state=$(printf '%s\n' "$j" | jq -r '.state')
base=$(printf '%s\n' "$j" | jq -r '.baseRefName')
mss=$(printf '%s\n' "$j" | jq -r '.mergeStateStatus')
draft=$(printf '%s\n' "$j" | jq -r '.isDraft')
head=$(printf '%s\n' "$j" | jq -r '.headRefOid // empty')

# Only an OPEN PR can be merged — guard against a false CLEARED on an already-merged/closed PR.
if [ "$state" != "OPEN" ]; then
  echo "PR #$PR — $title"
  echo "  $url"
  echo "VERDICT: BLOCKED — PR is $state, nothing to merge."
  exit 3
fi

# Bind the rollup above to one exact PR head. A push racing this predicate invalidates the
# association between the checks we inspected and the code GitHub would merge; fail closed and let
# the next invocation inspect the new head. Missing head identity is equally non-authoritative.
if [ -z "$head" ]; then
  echo "VERDICT: HOLD — PR head identity is unavailable; cannot associate checks with exact code."
  exit 2
fi
if [ -n "$EXPECTED_HEAD" ] && [ "$head" != "$EXPECTED_HEAD" ]; then
  echo "VERDICT: HOLD — expected PR head $EXPECTED_HEAD but GitHub reports $head; re-run on the new head."
  exit 2
fi
head_now=$(gh pr view "$PR" "${repo_args[@]+"${repo_args[@]}"}" --json headRefOid -q .headRefOid 2>/dev/null || true)
if [ -z "$head_now" ] || [ "$head_now" != "$head" ]; then
  echo "VERDICT: HOLD — PR head changed while checks were inspected; re-run on the new exact head."
  exit 2
fi

# The review acceptance receipt is a separate exact-head predicate from CI. Resolve the repository
# from the explicit argument when present, otherwise from GitHub's canonical PR URL. Ambiguity can
# only HOLD: never let a missing owner/repo silently bypass the shared review gate.
review_repo="$REPO"
if [ -z "$review_repo" ]; then
  case "$url" in
    https://github.com/*/pull/*) review_repo="${url#https://github.com/}"; review_repo="${review_repo%/pull/*}" ;;
  esac
fi
if [ -z "$review_repo" ]; then
  echo "VERDICT: HOLD — cannot derive OWNER/REPO for the exact-head review gate."
  exit 2
fi

deploy_hits=$(printf '%s\n' "$j" | jq -r '.files[].path' | grep -E "$DEPLOY_RE" || true)
sensitive=0
[ -n "$deploy_hits" ] && sensitive=1
[ "$STALE" = 1 ] && sensitive=1   # fail-safe: uncertain classification ⇒ treat as a live deploy

# CI rollup: count failing / pending across CheckRuns (conclusion/status) and StatusContexts (state).
failing=$(printf '%s\n' "$j" | jq '[.statusCheckRollup[]? | (.conclusion // .state // "" | ascii_upcase)
             | select(.=="FAILURE" or . =="CANCELLED" or . =="TIMED_OUT" or . =="ERROR"
                      or . =="ACTION_REQUIRED" or . =="STARTUP_FAILURE")] | length')
pending=$(printf '%s\n' "$j" | jq '[.statusCheckRollup[]?
             | ((.status // "" | ascii_upcase) as $s | (.state // "" | ascii_upcase) as $st
                | select($s=="QUEUED" or $s=="IN_PROGRESS" or $s=="PENDING" or $st=="PENDING" or $st=="EXPECTED"))]
             | length')
total_checks=$(printf '%s\n' "$j" | jq '[.statusCheckRollup[]?] | length')

echo "PR #$PR — $title"
echo "  $url"
echo "  base=$base  head=${head:0:12}  mergeState=$mss  draft=$draft"
if [ "$sensitive" = 1 ]; then
  if [ -n "$deploy_hits" ]; then
    echo "  WEBSITE-SENSITIVE — diff touches deploy-trigger paths:"
    printf '%s\n' "$deploy_hits" | sed 's/^/      /'
  else
    echo "  WEBSITE-SENSITIVE — forced: deploy classification could not be derived from the GATES registry"
  fi
else
  echo "  non-deploy — merging will NOT trigger a live website/API deploy"
fi
echo "  checks: total=$total_checks failing=$failing pending=$pending"

# --- verdict ---
# GitHub's mergeStateStatus is authoritative on whether a merge is even POSSIBLE. Handle every
# not-mergeable / indeterminate state explicitly; NEVER fall through to CLEARED on an unhandled
# state (an UNKNOWN-during-recompute or a future enum value must not read as "safe to merge").
case "$mss" in
  DIRTY)  echo "VERDICT: BLOCKED — merge conflicts. Rebase onto origin/$base, then re-run."; exit 3 ;;
  BEHIND) echo "VERDICT: BLOCKED — stale base (branch is behind $base). Rebase onto current $base first (PR#111 silent-revert guard), then re-run."; exit 3 ;;
  BLOCKED)
    # BLOCKED means branch protection won't merge yet — but it covers two cases. If a required
    # check is still RUNNING, the remedy is simply to wait (HOLD); only when nothing is pending is
    # it genuinely stuck (required check never ran, or a required review is missing → action needed).
    if [ "$pending" -gt 0 ]; then
      echo "VERDICT: HOLD — branch protection is waiting on $pending required check(s) still running. Wait for green, then re-run."; exit 2
    fi
    echo "VERDICT: BLOCKED — branch protection won't allow the merge: a required check never ran, or a required review is missing. For a PR opened before a required check was added this is almost always the missing 'pr-gate' context, which only runs after the head is pushed/rebased — rebase onto origin/$base to retrigger it, then re-run. If it persists after a rebase with green checks, a required review or admin merge is needed: surface to human, don't force it."; exit 3 ;;
  UNKNOWN) echo "VERDICT: HOLD — GitHub is still computing mergeability (mergeState=UNKNOWN); this is transient. Re-run in a few seconds."; exit 2 ;;
esac
if [ "$draft" = "true" ]; then
  echo "VERDICT: HOLD — PR is a draft. Mark ready, then re-run."; exit 2
fi
if [ "$failing" -gt 0 ]; then
  echo "VERDICT: HOLD — $failing CI check(s) failing. Fix before merge."; exit 2
fi
# Past the not-mergeable states: only an explicitly mergeable state may proceed toward CLEARED.
case "$mss" in
  CLEAN|UNSTABLE|HAS_HOOKS) : ;;  # GitHub will permit the merge
  *) echo "VERDICT: HOLD — unrecognized merge state '$mss'; refusing to clear on an unhandled state. Re-run, or inspect the PR manually."; exit 2 ;;
esac
if [ "$sensitive" = 1 ]; then
  if [ "$pending" -gt 0 ] || [ "$total_checks" -eq 0 ]; then
    echo "VERDICT: HOLD — website-sensitive: a live deploy fires on merge and CI is not GREEN+COMPLETE (${pending} pending, ${total_checks} total). Wait for green; never blind-merge a deploy."
    exit 2
  fi
elif [ "$pending" -gt 0 ]; then
  echo "VERDICT: HOLD — ${pending} non-deploy check(s) still running. Merge once green."; exit 2
fi

if ! python3 "$REVIEW_GATE" "$PR" --repo "$review_repo" --expected-head "$head" --quiet; then
  echo "VERDICT: HOLD — exact-head review gate has not accepted $review_repo#$PR at $head."
  exit 2
fi

if [ "$sensitive" = 1 ]; then
  echo "VERDICT: CLEARED — website-sensitive, CI is fully green, and exact-head review is accepted."
else
  echo "VERDICT: CLEARED — non-deploy PR, mergeable, no failing checks, and exact-head review is accepted."
fi
echo "MERGE-REPO: $review_repo"
echo "MERGE-HEAD: $head"
echo "MERGE-AUTHORITY: separate signed limen.merge_authorization.v1 receipt required"
exit 0
