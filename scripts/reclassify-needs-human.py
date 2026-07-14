#!/usr/bin/env python3
"""reclassify-needs-human.py — separate the REAL human atoms from the mislabeled ones.

The `needs_human` queue regressed to 37 undifferentiated entries, but most are NOT human-blocked:
they're fleet-buildable code/docs (READMEs, landing pages, "is-LIVE" verifications) that got parked
in `needs_human` and now sit idle behind a false gate while the fleet has the capacity to do them.
This separates them so the human surface is only what genuinely needs his hand.

Classification is DERIVED from signals, never a pinned id list:
  * KEEP (real human atom): needs a secret/credential/account, admin/branch-protection, the merge
    gate, or an irreversible/backup-gated cutover. Also the `BLD2-*` deploy batch (blocked on the
    Cloudflare wrangler credential — his hand).
  * DEBT -> failed_chronic: FLEET debt masquerading as a human gate — a chronic (reopened ≥3×, no PR)
    or repeated-no-op task the count-based escalators (heal-dispatch/recover) dumped in `needs_human`.
    It is a fleet failure, not a human decision, so it parks in `failed_chronic` (terminal, not
    re-dispatched). NEVER flipped to `open`: flipping chronic->open is exactly what ping-ponged
    252/290 tasks straight back to needs_human within a day.
  * FLIP -> open: a code/docs task in a repo with NO human-only signal and NOT chronic — fleet does it.
  * STALE: its precondition is already satisfied (e.g. "live-dispatch across vendors" while the
    daemon is already dispatching) -> recommend close, don't re-queue.
  * REVIEW: an `ACTIVATION AUDIT: skip|kill` decision — "kill" is irreversible, so NEVER auto-flip;
    a one-pass human/triage call.

Dry-run by default: prints the buckets so every decision is visible. With --apply it moves the DEBT
bucket `needs_human -> failed_chronic` and (unless --debt-only) the FLIP bucket `needs_human -> open`,
lockless + atomic (re-read fresh under the limen save path, exactly like generate-revenue-backlog),
and never touches KEEP / STALE / REVIEW. Fully reversible. `--apply --debt-only` is the beat guard:
it keeps `needs_human` meaning ONLY his hand by auto-parking any chronic straggler in failed_chronic.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file, save_limen_file  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))

# Completing one of these needs something the fleet structurally CANNOT do.
# Substring (not \b) on the credential cluster on purpose: "JWT_SECRET" / "org_id" have no word
# boundary before the keyword, and erring toward KEEP (leaving a task surfaced) is the safe direction.
_HUMAN_SIGNALS = re.compile(
    r"secret|credential|token|jwt|oauth|password|api[ _-]?key|org_id|org id|"
    r"branch protection|launchd|launchagent|gh (cli )?auth|merge gate|wrangler|cloudflare|"
    r"container/migrate|cutover|relocate bulky|backup|"
    r"ko-?fi|sponsor|stripe|lemonsqueeze|billing|\bkyc\b|account",
    re.IGNORECASE,
)
# Structural class (not pinned individuals): the *-deploy batch is gated on the Cloudflare credential.
_HUMAN_ID_PREFIXES = ("BLD2-",)
# Precondition-already-met: "live-dispatch / dispatch-drain" while the daemon is already dispatching.
_STALE_SIGNAL = re.compile(r"live-dispatch|dispatch.drain|set autonomy.*dispatch", re.IGNORECASE)
# Irreversible triage decision — surface, never auto-act.
_REVIEW_SIGNAL = re.compile(r"activation audit:\s*(skip|kill)\b", re.IGNORECASE)


def _lever_ids() -> set[str]:
    """The owned human-gate registry — a task naming any of these is his hand BY DEFINITION.

    Derived, never pinned: a `needs_human` task tagged to a lever (`needs-human (L-…)`, `[his-hand]`,
    or naming a registered lever id) must stay KEEP even absent a credential keyword — else the drain
    would flip a real lever (e.g. L-ENC1101-GOLIVE "take the course live", L-SOCIAL-SEND) to `open`
    and hand a human-gated, sometimes IRREVERSIBLE act to the autonomous fleet.
    """
    try:
        raw = json.loads((ROOT / "his-hand-levers.json").read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    levers = raw.get("levers") if isinstance(raw, dict) else raw
    return {lv["id"] for lv in (levers or []) if isinstance(lv, dict) and lv.get("id")}


_LEVER_IDS = _lever_ids()
# Explicit lever tag on a task — the surest human-atom signal, independent of the credential cluster.
_LEVER_MARKER = re.compile(r"needs-human \(L-|\[his-hand\]", re.IGNORECASE)

# FLEET DEBT masquerading as a human gate: a needs_human task carrying a chronic/no-op escalation
# receipt in its dispatch_log, or the structural chronic signature (reopened ≥3× with no PR ever).
# The count-based escalators (heal-dispatch/recover) dumped ~333 of these here — fleet failure, not a
# human decision. They move to failed_chronic (terminal), NEVER flip to `open`.
_DEBT_RECEIPT = re.compile(r"chronic \(reopened|repeated no-op failures|parked as fleet-debt", re.IGNORECASE)


def _is_fleet_debt(task) -> bool:
    log = getattr(task, "dispatch_log", None) or []
    for e in log:
        if _DEBT_RECEIPT.search(str(getattr(e, "output", "") or "")):
            return True
    reopens = sum(1 for e in log if str(getattr(e, "status", "")) == "open")
    ever_pr = any("/pull/" in str(u) for u in (getattr(task, "urls", None) or []))
    return reopens >= 3 and not ever_pr


def _live_root() -> Path:
    """The live checkout, even when run from a worktree (whose logs/ are stale): strip a trailing
    .claude/worktrees/<name>. Falls back to ROOT."""
    parts = ROOT.parts
    if ".claude" in parts:
        i = parts.index(".claude")
        if parts[i:i + 2] == (".claude", "worktrees"):
            return Path(*parts[:i])
    return ROOT


def _dispatch_is_live() -> bool:
    """True if a recent tick shows the daemon dispatching (ASK-7's precondition). Reads ROOT then the
    live checkout (so it's correct from a worktree too). Fail-open False."""
    for base in (ROOT, _live_root()):
        try:
            lines = (base / "logs" / "ticks.jsonl").read_text().splitlines()
            for ln in reversed(lines[-5:]):
                t = json.loads(ln)
                if (t.get("dispatched") or 0) > 0:
                    return True
        except Exception:
            continue
    return False


def classify(task, dispatch_live: bool) -> str:
    blob = " ".join(str(x) for x in (task.id, task.title, task.context, task.description) if x)
    # A lever-tagged task is his hand by definition — checked FIRST so a real lever can never leak
    # into FLIP for lack of a credential keyword. Derived from the registry, not a pinned id list.
    if _LEVER_MARKER.search(blob) or any(lv in blob for lv in _LEVER_IDS):
        return "KEEP"
    if task.id.startswith(_HUMAN_ID_PREFIXES):
        return "KEEP"
    if _REVIEW_SIGNAL.search(blob):
        return "REVIEW"
    if _HUMAN_SIGNALS.search(blob):
        return "KEEP"
    # Fleet debt is checked AFTER every KEEP/REVIEW signal (a real lever that happens to be chronic
    # stays his hand) but BEFORE FLIP — so a chronic code/docs task parks in failed_chronic instead of
    # ping-ponging back to needs_human via open.
    if _is_fleet_debt(task):
        return "DEBT"
    if _STALE_SIGNAL.search(blob) and dispatch_live:
        return "STALE"
    if task.type in ("code", "docs") and task.repo:
        return "FLIP"
    return "REVIEW"  # unknown shape -> surface, never auto-flip


_REASON = {
    "KEEP": "real human atom (secret/account/admin/merge-gate/cutover/credential-gated deploy)",
    "DEBT": "fleet debt (chronic reopen / repeated no-op) — park in failed_chronic, NOT his hand",
    "FLIP": "fleet-buildable code/docs — no human-only signal",
    "STALE": "precondition already satisfied (daemon already dispatching) — recommend close",
    "REVIEW": "irreversible/ambiguous (skip-vs-kill) — one human triage pass",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--apply", action="store_true",
                    help="apply: DEBT->failed_chronic and (unless --debt-only) FLIP->open (lockless, atomic, reversible)")
    ap.add_argument("--debt-only", action="store_true",
                    help="with --apply, move ONLY the DEBT bucket needs_human->failed_chronic (the beat guard)")
    args = ap.parse_args()

    path = Path(args.tasks)
    lf = load_limen_file(path)
    dispatch_live = _dispatch_is_live()
    nh = [t for t in lf.tasks if t.status == "needs_human"]

    buckets: dict[str, list] = {"KEEP": [], "DEBT": [], "FLIP": [], "STALE": [], "REVIEW": []}
    for t in nh:
        buckets[classify(t, dispatch_live)].append(t)

    # docs/RECLASSIFY-PROPOSAL.md ------------------------------------------------------------------
    md = [
        f"# Reclassify needs_human — {date.today().isoformat()}",
        "",
        f"`needs_human` holds **{len(nh)}** tasks. By signal (not by hand-picked id) they split into:",
        "",
        f"- **KEEP — {len(buckets['KEEP'])}** genuinely need your hand (secret / account / admin / "
        "merge gate / irreversible cutover / Cloudflare-credential-gated deploy).",
        f"- **DEBT — {len(buckets['DEBT'])}** are FLEET debt (chronic reopen / repeated no-op) the "
        "escalators dumped in `needs_human`. `--apply` parks them in `failed_chronic` (terminal), "
        "NOT `open`. This is why the count lied. Reversible.",
        f"- **FLIP — {len(buckets['FLIP'])}** are fleet-buildable code/docs parked behind a false gate. "
        "`--apply` flips these to `open` so the fleet does them. Reversible.",
        f"- **STALE — {len(buckets['STALE'])}** precondition already met — recommend close, don't re-queue.",
        f"- **REVIEW — {len(buckets['REVIEW'])}** one quick triage call (skip vs *kill* — kill is "
        "irreversible, never auto-flipped).",
        "",
        "> `--apply` changes ONLY DEBT (`->failed_chronic`) and FLIP (`->open`); KEEP / STALE / REVIEW "
        "are never auto-touched. Both moves are reversible.",
        "",
    ]
    for b in ("DEBT", "FLIP", "STALE", "REVIEW", "KEEP"):
        md += [f"## {b} — {_REASON[b]}", "", "| id | type | repo | title |", "|---|---|---|---|"]
        for t in buckets[b]:
            md.append(f"| `{t.id}` | {t.type} | {t.repo or '—'} | {(t.title or '')[:70]} |")
        md.append("")
    md += ["---", "*Generated by `scripts/reclassify-needs-human.py`. Re-run `--apply` to flip the "
           "FLIP bucket, or say the word and I will.*", ""]
    try:
        (ROOT / "docs").mkdir(parents=True, exist_ok=True)
        (ROOT / "docs" / "RECLASSIFY-PROPOSAL.md").write_text("\n".join(md))
    except OSError:
        pass

    # console -------------------------------------------------------------------------------------
    print(f"# reclassify-needs-human: {len(nh)} needs_human  (dispatch_live={dispatch_live})")
    for b in ("KEEP", "DEBT", "FLIP", "STALE", "REVIEW"):
        print(f"  {b:6} {len(buckets[b]):2}  — {_REASON[b]}")
    flip_ids = [t.id for t in buckets["FLIP"]]
    debt_ids = [t.id for t in buckets["DEBT"]]
    print("\nDEBT -> failed_chronic:")
    for t in buckets["DEBT"]:
        print(f"  {t.id:52.52} {(t.title or '')[:50]}")
    if not args.debt_only:
        print("\nFLIP -> open:")
        for t in buckets["FLIP"]:
            print(f"  {t.id:52.52} {(t.title or '')[:50]}")

    if not args.apply:
        moves = f"{len(debt_ids)} DEBT->failed_chronic" + ("" if args.debt_only else f" + {len(flip_ids)} FLIP->open")
        print(f"\ndry-run — re-run with --apply to move {moves}.")
        print("wrote docs/RECLASSIFY-PROPOSAL.md")
        return 0

    # Apply lockless + atomic: re-read fresh so we never clobber a concurrent dispatch write; the
    # set-of-ids makes this idempotent (re-running flips nothing already flipped). Never skip on
    # contention — next run simply re-applies (self-healing), mirroring generate-revenue-backlog.
    fresh = load_limen_file(path)
    flip_set = set(flip_ids)
    debt_set = set(debt_ids)
    stamp = date.today().isoformat()
    parked = flipped = 0
    for t in fresh.tasks:
        if t.status != "needs_human":
            continue
        if t.id in debt_set:
            t.status = "failed_chronic"
            t.updated = stamp
            if "reclassified-fleet-debt" not in (t.labels or []):
                t.labels = list(t.labels or []) + ["reclassified-fleet-debt"]
            parked += 1
        elif t.id in flip_set and not args.debt_only:
            t.status = "open"
            t.updated = stamp
            if "reclassified-from-needs-human" not in (t.labels or []):
                t.labels = list(t.labels or []) + ["reclassified-from-needs-human"]
            flipped += 1
    if not (parked or flipped):
        print("\n(nothing to reclassify after fresh re-read — already applied.)")
        return 0
    save_limen_file(path, fresh)
    print(f"\napplied: {parked} needs_human->failed_chronic (fleet debt), "
          f"{flipped} needs_human->open (buildable) -> {path} (route+dispatch separately).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
