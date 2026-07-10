#!/usr/bin/env python3
"""trunk-ci-health.py — sensor + alarm for a RED trunk / wedged PR queue.

The 2026-07-10 blind spot: `main`'s required `pr-gate` check went red on pre-existing failures (4
unformatted files + 5 assertion failures) and EVERY open PR silently could not merge — dozens of
BLOCKED/DIRTY PRs — with nothing raising an alarm that TRUNK ITSELF was broken. The existing
`omega.sh` main-green rung probes `gh run list --branch main`, which sees `fleet-gate`/`ci.yml`
(neither runs the full test suite) but NEVER `pr-gate` — pr-gate fires on `pull_request` only, so it
never appears on a pushed-to-main commit. The queue wedged in silence.

The robust, cheap signal is the QUEUE-WEDGE FINGERPRINT: when >= K open PRs all fail the SAME
required check, the cause is the shared base (trunk), not N independent PR problems. This is exactly
what `merge-policy.sh` (a per-PR predicate) structurally cannot see.

  Predicate — queue-wedge: group open PRs by each failing REQUIRED check; if any required check
  fails on >= K PRs (K = LIMEN_TRUNK_CI_WEDGE_K, default 5), trunk is presumed red on that check.

Effector: a single self-owned GitHub issue (marker `<!-- trunk-ci-alarm -->`, label `trunk-health`)
opened when wedged and auto-closed when the queue clears — the sibling of sync-censor-issues.py, but
on its own marker so it never contends with the censor residual file. DARK by default
(observable-before-autonomous): the probe + state file + beat log always run; the issue mutation
needs `--apply` AND `LIMEN_TRUNK_CI_APPLY=1`.

  python3 scripts/trunk-ci-health.py           # probe; write logs/trunk-ci-health.json; exit 1 if wedged
  python3 scripts/trunk-ci-health.py --json     # machine output
  python3 scripts/trunk-ci-health.py --apply    # also open/close the alarm issue (gated by env)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
STATE_PATH = ROOT / "logs" / "trunk-ci-health.json"
REPO = os.environ.get("LIMEN_TRUNK_CI_REPO", "organvm/limen")
WEDGE_K = int(os.environ.get("LIMEN_TRUNK_CI_WEDGE_K", "5"))
# Only RECENTLY-ACTIVE PRs count toward the wedge: a pile of stale fleet PRs each failing pr-gate on
# its own stale base is chronic backlog, NOT an acute trunk break. A cluster of FRESH PRs sharing one
# failing required check is the "trunk just went red" fingerprint. Default 36h.
FRESH_HOURS = int(os.environ.get("LIMEN_TRUNK_CI_FRESH_HOURS", "36"))
APPLY_ARMED = os.environ.get("LIMEN_TRUNK_CI_APPLY", "0") == "1"
MARKER = "<!-- trunk-ci-alarm -->"
LABEL = "trunk-health"


def _gh(args: list[str], timeout: int = 45) -> str | None:
    """Run gh, return stdout or None (fail-open — a probe outage must never wedge the beat)."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def required_checks() -> set[str]:
    """The required status-check contexts on main's branch protection (fallback: pr-gate)."""
    out = _gh(["api", f"repos/{REPO}/branches/main/protection/required_status_checks"])
    if out:
        try:
            return set(json.loads(out).get("contexts") or []) or {"pr-gate"}
        except (ValueError, TypeError):
            pass
    return {"pr-gate"}


def open_prs() -> list[dict]:
    """Open PRs with their check rollup. Returns [] on probe failure (fail-open)."""
    out = _gh(
        [
            "pr",
            "list",
            "--repo",
            REPO,
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,statusCheckRollup,isDraft,updatedAt",
        ]
    )
    if not out:
        return []
    try:
        return json.loads(out)
    except ValueError:
        return []


def failing_required_checks(pr: dict, required: set[str]) -> set[str]:
    """The required checks that are FAILING/errored on this PR."""
    bad = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE"}
    out: set[str] = set()
    for c in pr.get("statusCheckRollup") or []:
        name = c.get("name") or c.get("context") or ""
        # check-runs use `conclusion`; legacy statuses use `state`
        concl = (c.get("conclusion") or c.get("state") or "").upper()
        if name in required and concl in bad:
            out.add(name)
    return out


def classify(prs: list[dict], required: set[str], k: int = WEDGE_K, fresh_since: str | None = None) -> dict:
    """Pure: among FRESH non-draft open PRs, count those failing each required check; >= k is a wedge.

    `fresh_since`: ISO-8601 UTC cutoff (e.g. "2026-07-09T00:00:00Z"). PRs whose updatedAt is older
    are chronic backlog, excluded. UTC 'Z' timestamps compare lexicographically, so no parsing.
    This isolates the acute trunk-red fingerprint (many RECENTLY-touched PRs, one shared failing
    required check) from the repo's chronic stale-PR pile.
    """
    counts: Counter[str] = Counter()
    considered = 0
    for pr in prs:
        if pr.get("isDraft"):
            continue
        if fresh_since and str(pr.get("updatedAt", "")) < fresh_since:
            continue
        considered += 1
        for chk in failing_required_checks(pr, required):
            counts[chk] += 1
    wedged = {chk: n for chk, n in counts.items() if n >= k}
    return {
        "considered_prs": considered,
        "failing_by_check": dict(counts),
        "wedged_checks": wedged,
        "healthy": not wedged,
        "k": k,
        "fresh_since": fresh_since,
    }


def render_issue_body(verdict: dict) -> str:
    lines = [
        MARKER,
        "## Trunk CI health — the PR queue is WEDGED",
        "",
        f"{len(verdict['wedged_checks'])} required check(s) are failing across a cluster of open PRs — "
        "the fingerprint of a broken TRUNK, not independent PR problems. Rebasing individual PRs will "
        "not clear this; the base (`main`) must be healed.",
        "",
        f"- PRs considered (open, non-draft): **{verdict['considered_prs']}**",
        f"- Wedge threshold K: **{verdict['k']}**",
        "",
        "| required check | open PRs failing it |",
        "|---|---|",
    ]
    for chk, n in sorted(verdict["wedged_checks"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{chk}` | {n} |")
    lines += ["", "Heal trunk (green the check on `main`), then this issue auto-closes."]
    return "\n".join(lines)


def find_alarm_issue() -> dict | None:
    out = _gh(
        [
            "issue",
            "list",
            "--repo",
            REPO,
            "--state",
            "open",
            "--label",
            LABEL,
            "--search",
            "trunk-ci-alarm in:body",
            "--json",
            "number,body",
            "--limit",
            "20",
        ]
    )
    if not out:
        return None
    try:
        for it in json.loads(out):
            if MARKER in (it.get("body") or ""):
                return it
    except ValueError:
        return None
    return None


def apply_issue(verdict: dict) -> str:
    """Open the alarm when wedged, close it when healthy. Gated: needs --apply AND LIMEN_TRUNK_CI_APPLY=1."""
    if not APPLY_ARMED:
        return "dark (LIMEN_TRUNK_CI_APPLY!=1) — issue mirror not armed"
    existing = find_alarm_issue()
    if not verdict["healthy"]:
        body = render_issue_body(verdict)
        if existing:
            _gh(["issue", "edit", str(existing["number"]), "--repo", REPO, "--body", body])
            return f"updated alarm issue #{existing['number']}"
        out = _gh(
            [
                "issue",
                "create",
                "--repo",
                REPO,
                "--label",
                LABEL,
                "--title",
                "Trunk CI wedged — required check red across the PR queue",
                "--body",
                body,
            ]
        )
        return f"opened alarm issue ({(out or '').strip().splitlines()[-1:] or ['?'][0]})"
    if existing:
        _gh(
            [
                "issue",
                "close",
                str(existing["number"]),
                "--repo",
                REPO,
                "--comment",
                "Trunk CI recovered — queue no longer wedged. Auto-closed.",
            ]
        )
        return f"closed alarm issue #{existing['number']}"
    return "healthy — no alarm"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    required = required_checks()
    fresh_since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=FRESH_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    verdict = classify(open_prs(), required, fresh_since=fresh_since)
    verdict["required_checks"] = sorted(required)
    verdict["effector"] = apply_issue(verdict) if "--apply" in argv else "not applied (probe only)"

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")

    if "--json" in argv:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    elif verdict["healthy"]:
        print(f"trunk-ci-health: OK — no required check wedged across {verdict['considered_prs']} open PRs.")
    else:
        wl = ", ".join(f"{c}×{n}" for c, n in verdict["wedged_checks"].items())
        print(f"trunk-ci-health: WEDGED — {wl} (K={verdict['k']}); {verdict['effector']}")

    return 0 if verdict["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
