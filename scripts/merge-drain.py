#!/usr/bin/env python3
"""merge-drain.py — the receipt-bound merge executor and preview classifier.

The loop may publish PRs every beat (dispatch + jules-land), while merge authorization remains
a separate signed boundary. Default invocations preview genuinely READY candidates
(mergeable + CI-green + exact-head review accepted). An explicit receipt-bound apply
attempts only its named exact heads and NEVER force-merges. Bounded per run so it never
dominates a beat.
Idempotent and concurrency-safe: if another agent already merged a PR, gh reports it and
we count it, no error. It preserves source branches; branch cleanup is a separate accepted reap.
Touches only GitHub — not tasks.yaml ownership or agent worktrees — so it cannot race the
dispatcher.

It also REFUSES stale-base PRs (the #111 guard): a mergeable+green PR that branched from an old
base can silently REVERT work that landed since — self-heal reroutes those to a rebase-onto-current
task instead of letting them clobber the body. ([[pr111-daemon-regression-healed]])

  --scan N      assess WINDOW per run — PRs classified this beat, rotating over the full backlog
  --scan-max N  cap on the cheap full-fleet enumeration the window draws from (default 500)
  --limit N     max receipts/PRs to attempt this run (default 10)
  --apply       enable exact-target merge attempts; default is zero-write preview
  --authorization-receipt PATH
               short-lived signed limen.merge_authorization.v1 receipt; repeat per target
  --allowed-signers PATH
               Domus-owned OpenSSH trust owner (or LIMEN_REVIEW_ALLOWED_SIGNERS)
  --target-repo/--target-pr/--target-head
               optional delegated-call constraint; all three must match the sole receipt target

An authorization receipt only authorizes attempting one exact-head merge.  It
cannot replace the live ``limen.pr_review_gate.v1`` receipt or merge policy,
which are both re-run immediately before every mutation.
"""

import sys

# Dry-run is a literal zero-write contract.  Prevent importing the sibling scan module from
# materializing a local __pycache__ as an incidental filesystem mutation.
sys.dont_write_bytecode = True

import argparse
import concurrent.futures as cf
import datetime
import json
import os
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts/ for _pr_scan
from _pr_scan import enumerate_open_prs, rotating_window, stale_base_verdict  # noqa: E402
from _merge_authorization import (  # noqa: E402
    AuthorizationError,
    MergeAuthorization,
    load_authorization,
    materialize_allowed_signers,
)

# DERIVED from env (derive-not-pin) so the conductor survives relocation; same default + classifier
# as self-heal.py — the two organs are two halves of one verdict and must agree on the PR universe.
OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))


def pause_active() -> bool:
    """The drain is an effector: any pause marker blocks every write or remote mutation."""

    try:
        (ROOT / "logs" / "AUTONOMY_PAUSED").lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def review_accepted(
    repo: str,
    num: int,
    expected_head: str,
    allowed_signers: Path | None = None,
) -> bool:
    """Require the dedicated App's authenticated current-head receipt.

    ``allowed_signers`` remains in the caller signature because it owns merge
    authorization custody. It is deliberately not forwarded to the review gate:
    an executor-controlled local file is not peer-review authority.
    """

    if not repo or not expected_head:
        return False
    gate = Path(os.environ.get("LIMEN_PR_REVIEW_GATE") or ROOT / "scripts" / "pr-review-gate.py")
    try:
        command = [
            sys.executable,
            str(gate),
            str(num),
            "--repo",
            repo,
            "--expected-head",
            expected_head,
            "--require-published-result",
            "--quiet",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def merge_policy_cleared(
    repo: str,
    num: int,
    expected_head: str,
    allowed_signers: Path | None = None,
) -> bool:
    """Run the shared merge predicate on one exact head, failing closed."""

    if not repo or not expected_head:
        return False
    policy = ROOT / "scripts" / "merge-policy.sh"
    try:
        environment = os.environ.copy()
        if allowed_signers is not None:
            environment["LIMEN_REVIEW_ALLOWED_SIGNERS"] = str(allowed_signers)
        result = subprocess.run(
            [
                str(policy),
                str(num),
                "--repo",
                repo,
                "--expected-head",
                expected_head,
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def gh(args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


def _is_trivial(repo, num):
    """True if the PR diff is a no-op / pure reformat (whitespace or line-ending only) or empty — the
    'green-checkmark noise' class (e.g. a CIFIX that only normalized CRLF->LF, showing 436/436 lines).
    A VALUE gate ON TOP of the CI gate: refuse to attempt these. Conservative + fail-open: any real
    content change, or any error fetching the diff, -> NOT trivial (defer to the existing CI gate)."""
    r = gh(["pr", "diff", str(num), "-R", repo], timeout=60)
    if r.returncode != 0:
        return False
    added, removed = [], []
    for ln in r.stdout.splitlines():
        if ln.startswith(
            (
                "+++",
                "---",
                "diff ",
                "index ",
                "@@",
                "old mode",
                "new mode",
                "similarity",
                "rename",
                "deleted file",
                "new file",
                "Binary",
            )
        ):
            continue
        if ln.startswith("+"):
            added.append(ln[1:].strip())
        elif ln.startswith("-"):
            removed.append(ln[1:].strip())
    if not added and not removed:
        return True  # empty diff
    # added==removed after stripping whitespace/EOL -> no net content change -> pure reformat no-op
    return sorted(x for x in added if x) == sorted(x for x in removed if x)


def assess(rn, *, allowed_signers: Path | None = None):
    repo, num = rn
    try:
        r = gh(
            [
                "pr",
                "view",
                str(num),
                "-R",
                repo,
                "--json",
                "mergeable,mergeStateStatus,state,statusCheckRollup,isDraft,files,baseRefName,headRefOid",
            ],
            timeout=40,
        )
        if r.returncode != 0:
            return (repo, num, "ERR")
        d = json.loads(r.stdout)
        if d.get("state") != "OPEN" or d.get("isDraft"):
            return (repo, num, "SKIP")
        if d.get("mergeable") == "CONFLICTING":
            return (repo, num, "CONFLICT")
        states = [(c.get("conclusion") or c.get("state") or "") for c in (d.get("statusCheckRollup") or [])]
        if any(s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED") for s in states):
            return (repo, num, "CI-RED")
        if any(s in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "") for s in states):
            return (repo, num, "CI-PENDING")
        if d.get("mergeable") == "MERGEABLE":
            # STALE-BASE GATE (kept identical to self-heal.assess — one verdict): a green+mergeable
            # PR off an OLD base can silently revert work it never meant to touch (#111). Refuse it
            # here; self-heal reroutes it to a rebase-onto-current task. One bounded compare call.
            paths = [f.get("path", "") for f in (d.get("files") or [])]
            sb = stale_base_verdict(repo, paths, d.get("baseRefName"), d.get("headRefOid"), gh)
            if sb:
                return (repo, num, sb)  # STALE-CORE / STALE-BASE — do NOT attempt; rebase first
            if _is_trivial(repo, num):
                return (repo, num, "TRIVIAL")  # CI-green but no-op/reformat — value gate refuses it
            if not review_accepted(
                repo,
                num,
                str(d.get("headRefOid") or ""),
                allowed_signers,
            ):
                return (repo, num, "REVIEW-HOLD")
            return (repo, num, "READY")
        return (repo, num, "BLOCKED")
    except Exception:
        return (repo, num, "ERR")


def current_head(repo: str, num: int) -> str:
    """Read the head immediately before the acceptance recheck and merge."""

    try:
        result = gh(["pr", "view", str(num), "-R", repo, "--json", "headRefOid"], timeout=40)
        if result.returncode != 0:
            return ""
        return str(json.loads(result.stdout).get("headRefOid") or "")
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return ""


def ready_head_for_merge(
    repo: str,
    num: int,
    allowed_signers: Path | None = None,
) -> str:
    """Re-run the complete READY predicate inside a stable exact-head bracket.

    The rotating assessment is only a candidate census.  Files, base ancestry, mergeability,
    CI, review threads, or head identity can change before the effector runs.  Bracketing a fresh
    assessment with two head reads proves that the READY verdict covered the same immutable commit
    passed to ``--match-head-commit``.  Any movement or uncertainty fails closed.
    """

    before = current_head(repo, num)
    if not before:
        return ""
    verdict = assess((repo, num), allowed_signers=allowed_signers)
    after = current_head(repo, num)
    if before != after or verdict != (repo, num, "READY"):
        return ""
    return after


def merge(
    repo: str,
    num: int,
    expected_head: str,
    authorization: MergeAuthorization | None,
) -> bool:
    """Attempt one receipt-bound, exact-head squash merge after live predicates pass."""

    if pause_active() or not expected_head or authorization is None:
        return False
    original_authorization = authorization

    def refresh_authorization() -> MergeAuthorization | None:
        """Re-read the same receipt and trust owner, including current expiry."""

        try:
            current = load_authorization(
                original_authorization.source,
                allowed_signers=original_authorization.allowed_signers,
            )
        except AuthorizationError:
            return None
        if (
            current.authorization_id != original_authorization.authorization_id
            or current.receipt_sha256 != original_authorization.receipt_sha256
            or current.allowed_signers_sha256 != original_authorization.allowed_signers_sha256
            or not current.permits(repo, num, expected_head)
        ):
            return None
        return current

    authorization = refresh_authorization()
    if authorization is None:
        return False
    try:
        with materialize_allowed_signers(authorization) as trusted_signers:
            if not review_accepted(repo, num, expected_head, trusted_signers):
                return False
            if not merge_policy_cleared(repo, num, expected_head, trusted_signers):
                return False
    except AuthorizationError:
        return False
    if pause_active():
        return False
    # Predicates may consume most of a short authorization window. Re-read and re-verify the
    # immutable receipt immediately before the remote effect so expiry cannot race the merge.
    authorization = refresh_authorization()
    if authorization is None or pause_active():
        return False
    r = gh(
        ["pr", "merge", str(num), "-R", repo, "--squash", "--match-head-commit", expected_head],
        timeout=90,
    )
    if r.returncode == 0:
        return True
    # A concurrent keeper may have completed the same exact merge between the final
    # policy check and this command. Treat that idempotent race as success only when
    # GitHub reports the PR's current state as MERGED.
    try:
        state = gh(
            ["pr", "view", str(num), "-R", repo, "--json", "state,headRefOid"],
            timeout=40,
        )
        if state.returncode == 0:
            observed = json.loads(state.stdout)
            if observed.get("state") == "MERGED" and observed.get("headRefOid") == expected_head:
                return True
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        pass
    return False


def exact_target_already_merged(repo: str, num: int, expected_head: str) -> bool:
    """Confirm an idempotent concurrent completion of the authorized exact head."""

    try:
        result = gh(
            ["pr", "view", str(num), "-R", repo, "--json", "state,headRefOid"],
            timeout=40,
        )
        if result.returncode != 0:
            return False
        value = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return False
    return value.get("state") == "MERGED" and value.get("headRefOid") == expected_head


def _load_authorizations(
    paths: list[Path],
    *,
    allowed_signers: Path,
) -> dict[tuple[str, int, str], MergeAuthorization]:
    """Load a non-ambiguous set of exact-target authorization receipts."""

    result: dict[tuple[str, int, str], MergeAuthorization] = {}
    ids: set[str] = set()
    pull_requests: set[tuple[str, int]] = set()
    for path in paths:
        authorization = load_authorization(path, allowed_signers=allowed_signers)
        key = (
            authorization.repository,
            authorization.pull_request,
            authorization.head_sha,
        )
        pull_request = (authorization.repository, authorization.pull_request)
        if authorization.authorization_id in ids:
            raise AuthorizationError(f"duplicate authorization_id: {authorization.authorization_id}")
        if key in result:
            raise AuthorizationError(
                f"duplicate exact merge target: {authorization.repository}#{authorization.pull_request}"
            )
        if pull_request in pull_requests:
            raise AuthorizationError(
                f"multiple authorized heads for one pull request: "
                f"{authorization.repository}#{authorization.pull_request}"
            )
        ids.add(authorization.authorization_id)
        pull_requests.add(pull_request)
        result[key] = authorization
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scan",
        type=int,
        default=int(os.environ.get("LIMEN_MERGE_SCAN", "30")),
        help="assess WINDOW per run — PRs classified this beat, rotating",
    )
    ap.add_argument(
        "--scan-max",
        type=int,
        default=int(os.environ.get("LIMEN_MERGE_SCAN_MAX", "500")),
        help="cap on the cheap full-fleet enumeration the window draws from",
    )
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_MERGE_LIMIT", "10")))
    ap.add_argument(
        "--apply",
        action="store_true",
        help="attempt receipt-bound merges; default is zero-write preview",
    )
    ap.add_argument(
        "--authorization-receipt",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help="short-lived limen.merge_authorization.v1 receipt; repeat per exact target",
    )
    ap.add_argument(
        "--allowed-signers",
        type=Path,
        help=("Domus-owned OpenSSH allowed-signers file; defaults to LIMEN_REVIEW_ALLOWED_SIGNERS when set"),
    )
    ap.add_argument("--target-repo", help="optional exact OWNER/REPO constraint for a delegated apply")
    ap.add_argument("--target-pr", type=int, help="optional exact PR-number constraint for a delegated apply")
    ap.add_argument("--target-head", help="optional exact 40-character head constraint for a delegated apply")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="deprecated explicit spelling of the default zero-write preview",
    )
    a = ap.parse_args(argv)
    if a.apply and a.dry_run:
        ap.error("--apply and --dry-run are mutually exclusive")
    if a.limit < 0:
        ap.error("--limit must be non-negative")
    target_values = (a.target_repo, a.target_pr, a.target_head)
    if any(value is not None for value in target_values) and not all(value is not None for value in target_values):
        ap.error("--target-repo, --target-pr, and --target-head must be supplied together")
    if any(value is not None for value in target_values) and not a.apply:
        ap.error("exact target constraints require --apply")
    if a.apply and a.limit <= 0:
        ap.error("--apply requires a positive --limit")
    if a.target_pr is not None and a.target_pr <= 0:
        ap.error("--target-pr must be positive")
    if a.target_head is not None and (
        len(a.target_head) != 40 or any(character not in "0123456789abcdefABCDEF" for character in a.target_head)
    ):
        ap.error("--target-head must be a full 40-character Git commit SHA")
    if a.authorization_receipt and not a.apply:
        ap.error("--authorization-receipt requires --apply")
    if a.allowed_signers is not None and not a.apply:
        ap.error("--allowed-signers requires --apply")
    if a.apply and not a.authorization_receipt:
        print(
            "[merge-drain] REFUSED: --apply requires at least one limen.merge_authorization.v1 --authorization-receipt"
        )
        return 2
    allowed_signers = a.allowed_signers
    if allowed_signers is None and os.environ.get("LIMEN_REVIEW_ALLOWED_SIGNERS"):
        allowed_signers = Path(os.environ["LIMEN_REVIEW_ALLOWED_SIGNERS"])
    if a.apply and allowed_signers is None:
        print("[merge-drain] REFUSED: --apply requires --allowed-signers or LIMEN_REVIEW_ALLOWED_SIGNERS")
        return 2
    if a.apply and pause_active():
        print("[merge-drain] REFUSED-PAUSED: logs/AUTONOMY_PAUSED is present; zero side effects")
        return 3

    authorizations: dict[tuple[str, int, str], MergeAuthorization] = {}
    if a.apply:
        try:
            assert allowed_signers is not None
            authorizations = _load_authorizations(
                a.authorization_receipt,
                allowed_signers=allowed_signers,
            )
        except AuthorizationError as exc:
            print(f"[merge-drain] REFUSED: invalid authorization receipt: {exc}")
            return 2
        if a.target_repo is not None:
            target = (a.target_repo, a.target_pr, a.target_head)
            if set(authorizations) != {target}:
                print("[merge-drain] REFUSED: authorization receipt does not match the delegated exact target")
                return 2
        # Apply mode is deliberately exact-target rather than fleet-scanning: a receipt for one
        # head must never authorize a different READY PR discovered nearby in the queue.
        allprs = list(dict.fromkeys((repo, number) for repo, number, _head in authorizations))
        prs = allprs[: a.limit]
    else:
        # Preview the full-fleet rotating window without advancing its cursor. Default invocation
        # performs no filesystem or GitHub mutation.
        allprs = enumerate_open_prs(OWNERS, gh, max_total=a.scan_max, want_url=False)
        cursor_path = str(ROOT / "logs" / ".pr-scan-cursor.merge")
        prs = rotating_window(allprs, a.scan, cursor_path, persist=False) if allprs else []
    if not allprs:
        print("[merge-drain] no open PRs (or gh unavailable)")
        return 0
    assessor = (lambda item: assess(item, allowed_signers=allowed_signers)) if a.apply else assess
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(assessor, prs))
    import collections

    b = collections.Counter(r[2] for r in rows)
    ready = [(r[0], r[1]) for r in rows if r[2] == "READY"][: a.limit]
    merged = []
    completed_targets: set[tuple[str, int, str]] = set()
    if a.apply:
        for repo, num in ready:
            if pause_active():
                break
            head = ready_head_for_merge(repo, num, allowed_signers)
            authorization = authorizations.get((repo, num, head))
            if merge(repo, num, head, authorization):
                merged.append(f"{repo}#{num}")
                completed_targets.add((repo, num, head))
        # A second keeper may have completed an authorized exact target between
        # census and effect. Count that race only when GitHub binds MERGED to the
        # same receipt head; a different merged head remains a failure.
        selected_targets = list(authorizations)[: a.limit]
        for repo, num, head in selected_targets:
            key = (repo, num, head)
            if key in completed_targets:
                continue
            if exact_target_already_merged(repo, num, head):
                completed_targets.add(key)
                merged.append(f"{repo}#{num}")
    ts = datetime.datetime.now().strftime("%F %T")
    summary = (
        f"[merge-drain] {ts} mode={'apply' if a.apply else 'preview'} "
        f"window={len(prs)}/{len(allprs)} authorized={len(authorizations)} ready={b['READY']} "
        f"merged={len(merged)} trivial-skipped={b['TRIVIAL']} | blocked: conflict={b['CONFLICT']} "
        f"ci-red={b['CI-RED']} ci-pending={b['CI-PENDING']} "
        f"review-hold={b['REVIEW-HOLD']} "
        f"stale-core={b['STALE-CORE']} stale-base={b['STALE-BASE']}"
    )
    print(summary)
    if a.apply and not pause_active():
        try:
            log_path = ROOT / "logs" / "merge-drain.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(summary + (("  " + " ".join(merged)) if merged else "") + "\n")
        except Exception:
            pass
    if a.apply and len(completed_targets) != len(list(authorizations)[: a.limit]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
