#!/usr/bin/env python3
"""merge-ready.py — turn the merge gate into ONE go/no-go.

The fleet BUILDS faster than it SHIPS: merge-ready PRs pile up because merging is outward +
irreversible, so the classifier holds the whole batch behind a single human gate. But "open the merge
gate" is currently a *hunt* — nobody can see, at a glance, which PRs are actually clean and which
matter most. This builds that view.

READ-ONLY by default. It reuses merge-drain.py's EXACT assessment (`assess`: READY / REVIEW-HOLD /
CI-RED / CI-PENDING / CONFLICT / TRIVIAL / SKIP) so the surface can never disagree with what the merge
organ would actually do — then ranks the READY set REVENUE-FIRST (revenue-ladder.json rank, then
value-repos membership). `--write` explicitly publishes docs/MERGE-READY.md + logs/merge-ready.json;
the default preview performs zero writes. It NEVER merges anything.

Derive-don't-pin: ranks come from revenue-ladder.json + value-repos.json at run time, never hardcoded.
Unreadable ranking inputs yield an empty section; merge acceptance itself remains fail-closed.
"""

from __future__ import annotations

import sys

# The default mode promises zero writes, including incidental bytecode from dynamically importing
# merge-drain.py and its sibling modules.
sys.dont_write_bytecode = True

import argparse
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
DOCS = ROOT / "docs"


def _pause_active() -> bool:
    """Treat any pause marker, including an unreadable or dangling one, as binding."""

    try:
        (ROOT / "logs" / "AUTONOMY_PAUSED").lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _load_merge_drain():
    """Load the sibling merge-drain.py (hyphenated -> can't `import`) so we reuse its EXACT
    open_prs/assess classifier instead of forking a second, drifting copy."""
    path = Path(__file__).resolve().parent / "merge-drain.py"
    spec = importlib.util.spec_from_file_location("merge_drain", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ladder_ranks() -> dict[str, int]:
    """repo -> revenue rank (lower = closer to a dollar). {} on any error."""
    try:
        data = json.loads((ROOT / "revenue-ladder.json").read_text())
    except (OSError, ValueError):
        return {}
    return {p["repo"]: p.get("rank", 99) for p in (data.get("products") or []) if isinstance(p, dict) and p.get("repo")}


def _value_repos() -> set[str]:
    try:
        data = json.loads((ROOT / "value-repos.json").read_text())
    except (OSError, ValueError):
        return set()
    if isinstance(data, dict):
        repos = data.get("repos") or []
    elif isinstance(data, list):
        repos = data
    else:
        repos = []
    return {str(repo) for repo in repos if repo}


def _open_prs(md, scan: int) -> list[tuple[str, int]]:
    if hasattr(md, "enumerate_open_prs"):
        return md.enumerate_open_prs(md.OWNERS, md.gh, max_total=scan, want_url=False)
    if hasattr(md, "open_prs"):
        return md.open_prs(scan)
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", type=int, default=80, help="max open PRs to assess")
    ap.add_argument("--write", action="store_true", help="publish the Markdown and JSON projections")
    args = ap.parse_args(argv)

    if args.write and _pause_active():
        print("merge-ready: REFUSED-PAUSED — --write disabled while logs/AUTONOMY_PAUSED exists")
        return 3

    md = _load_merge_drain()
    ranks = _ladder_ranks()
    value = _value_repos()

    prs = _open_prs(md, args.scan)
    rows = []
    if prs:
        import concurrent.futures as cf

        with cf.ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(md.assess, prs))

    buckets: dict[str, list] = {}
    for repo, num, status in rows:
        buckets.setdefault(status, []).append((repo, num))

    def rank_key(item):
        repo, num = item
        return (ranks.get(repo, 500), 0 if repo in value else 1, repo, num)

    ready = sorted(buckets.get("READY", []), key=rank_key)

    surface = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scanned": len(prs),
        "counts": {k: len(v) for k, v in sorted(buckets.items())},
        "ready": [
            {
                "ref": f"{repo}#{num}",
                "repo": repo,
                "number": num,
                "revenue_rank": ranks.get(repo),
                "value_repo": repo in value,
            }
            for repo, num in ready
        ],
        "blocked": {
            k: [f"{r}#{n}" for r, n in sorted(buckets.get(k, []), key=rank_key)]
            for k in ("REVIEW-HOLD", "CONFLICT", "CI-RED", "CI-PENDING", "TRIVIAL", "ERR")
            if buckets.get(k)
        },
    }

    # logs/merge-ready.json (machine) -------------------------------------------------------------
    if args.write:
        try:
            LOGS.mkdir(parents=True, exist_ok=True)
            (LOGS / "merge-ready.json").write_text(json.dumps(surface, indent=2))
        except OSError:
            pass

    # docs/MERGE-READY.md (his one go/no-go) ------------------------------------------------------
    c = surface["counts"]
    lines = [
        f"# Merge-ready — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Scanned **{surface['scanned']}** open PRs (authored by you, across `organvm` + `4444J99`). "
        f"**{c.get('READY', 0)} are CLEAN** (mergeable + CI-green + exact-head review accepted + non-trivial) "
        "and ranked revenue-first below.",
        "",
        "> This is the **candidate view**, not merge authorization. Each merge attempt requires an "
        "explicit `merge-drain.py --apply` plus a short-lived signed `limen.merge_authorization.v1` "
        "receipt bound to that exact repository, PR, and head. The executor re-runs review and policy gates, "
        "preserves source branches, and never force-merges.",
        "",
        "## ✅ READY — clean, ranked revenue-first",
        "",
    ]
    if ready:
        lines += ["| # | PR | revenue rank | value-repo |", "|---|---|---|---|"]
        for i, (repo, num) in enumerate(ready, 1):
            rr = ranks.get(repo)
            lines.append(f"| {i} | `{repo}#{num}` | {rr if rr is not None else '—'} | {'✓' if repo in value else ''} |")
    else:
        lines.append("_No clean-ready PRs in this scan._")

    lines += ["", "## ⏳ Held (not mergeable yet)", ""]
    label = {
        "REVIEW-HOLD": "exact-head review not accepted",
        "CONFLICT": "merge conflict (rebase needed)",
        "CI-RED": "CI failing",
        "CI-PENDING": "CI still running",
        "TRIVIAL": "no-op/reformat (value gate refuses)",
        "ERR": "assessment error",
    }
    for k in ("REVIEW-HOLD", "CONFLICT", "CI-RED", "CI-PENDING", "TRIVIAL", "ERR"):
        refs = surface["blocked"].get(k)
        if refs:
            shown = ", ".join(f"`{r}`" for r in refs[:12])
            more = f" … (+{len(refs) - 12} more)" if len(refs) > 12 else ""
            lines.append(f"- **{label[k]}** ({len(refs)}): {shown}{more}")
    if not surface["blocked"]:
        lines.append("_None._")
    lines += [
        "",
        "---",
        "*Generated without merge mutation by `scripts/merge-ready.py` — reuses `merge-drain.py`'s "
        "classifier. Re-run any time. Nothing merges without explicit apply plus an exact-target receipt.*",
        "",
    ]

    if args.write:
        try:
            DOCS.mkdir(parents=True, exist_ok=True)
            (DOCS / "MERGE-READY.md").write_text("\n".join(lines))
        except OSError:
            pass

    destination = "docs/MERGE-READY.md + logs/merge-ready.json" if args.write else "preview (zero-write)"
    print(
        f"merge-ready: scanned {surface['scanned']} -> READY {c.get('READY', 0)} "
        f"(conflict {c.get('CONFLICT', 0)}, ci-red {c.get('CI-RED', 0)}, "
        f"ci-pending {c.get('CI-PENDING', 0)}, review-hold {c.get('REVIEW-HOLD', 0)}, "
        f"trivial {c.get('TRIVIAL', 0)}) -> {destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
