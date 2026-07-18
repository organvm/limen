#!/usr/bin/env python3
"""profile-bio-sync.py — give the GitHub sidebar bio an owner so it stops rotting.

The profile README self-heals every build (every number is recomputed from the live API). The
GitHub *bio* did not: it was hand-set once and froze at stale daily counts ("91 repos, 3,586 code
files, ...") because nothing owned it. This makes positioning-seeds.json `frontdoor.bio` the single
source of truth — STABLE identity only, never a count that changes daily — and applies it.

    python scripts/profile-bio-sync.py            # apply canonical bio (needs the gh `user` scope)
    python scripts/profile-bio-sync.py --check     # report drift only; exit 1 if live != canonical

Writing the bio needs the OAuth `user` scope (repo/workflow tokens can't). When absent, this reports
the exact one-command remediation and exits 0 (non-fatal) — the drift is surfaced, never silently
swallowed, and never blocks a build.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SEEDS = ROOT / "positioning-seeds.json"
REFRESH_HINT = "gh auth refresh -h github.com -s user"


def canonical_bio() -> str:
    try:
        seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
        return str(seeds.get("frontdoor", {}).get("bio") or "").strip()
    except Exception as exc:
        print(f"profile-bio-sync: cannot read {SEEDS}: {exc}", file=sys.stderr)
        return ""


def live_bio() -> str:
    proc = subprocess.run(
        ["gh", "api", "user", "--jq", ".bio"], capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Own + apply the GitHub sidebar bio from positioning-seeds.json.")
    ap.add_argument("--check", action="store_true", help="report drift only; exit 1 if live != canonical")
    args = ap.parse_args(argv)

    want = canonical_bio()
    if not want:
        print("profile-bio-sync: no frontdoor.bio in positioning-seeds.json — nothing to own.")
        return 0
    if len(want) > 160:
        print(
            f"profile-bio-sync: canonical bio is {len(want)} chars (>160, GitHub's limit) — trim it.", file=sys.stderr
        )
        return 2

    have = live_bio()
    if have == want:
        print("profile-bio-sync: sidebar bio in sync with canonical.")
        return 0

    if args.check:
        print(f"profile-bio-sync: DRIFT — live bio differs from canonical.\n  live: {have!r}\n  want: {want!r}")
        return 1

    proc = subprocess.run(
        ["gh", "api", "-X", "PATCH", "user", "-f", f"bio={want}", "--jq", ".bio"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode == 0:
        print(f"profile-bio-sync: applied canonical bio -> {(proc.stdout or '').strip()!r}")
        return 0
    # write blocked — almost always the missing `user` scope. Surface the atom, never fail the build.
    print(
        "profile-bio-sync: could not write the bio (the GitHub `user` OAuth scope is required; "
        "repo/workflow tokens cannot set it)."
    )
    print(f"  one-time fix, then re-run this script:  {REFRESH_HINT}")
    print(f"  intended bio: {want!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
