# Merge-ready — 2026-07-05 21:58

Scanned **80** open PRs (authored by you, across `organvm` + `4444J99`). **2 are CLEAN** (mergeable + CI-green + non-trivial) and ranked revenue-first below.

> This is a **candidate view**, not merge authorization. Each merge attempt requires explicit `merge-drain.py --apply` plus a short-lived signed `limen.merge_authorization.v1` receipt bound to the exact repository, PR, and head. The signature is verified against the explicit Domus-owned allowed-signers path; the executor then re-runs the live review gate and merge policy before a head-pinned squash merge.

## ✅ READY — clean, ranked revenue-first

| # | PR | revenue rank | value-repo |
|---|---|---|---|
| 1 | `organvm/a-i--skills#32` | — |  |
| 2 | `organvm/a-mavs-olevm#105` | — |  |

## ⏳ Blocked (not yours to fix — the fleet heals these)

- **merge conflict (rebase needed)** (5): `organvm/universal-mail--automation#134`, `organvm/portfolio#169`, `organvm/dot-github--logos#37`, `organvm/peer-audited--behavioral-blockchain#757`, `organvm/writelens#9`
- **CI failing** (58): `organvm/universal-mail--automation#135`, `organvm/universal-mail--automation#138`, `organvm/mirror-mirror#100`, `organvm/mirror-mirror#102`, `organvm/mirror-mirror#103`, `organvm/mirror-mirror#104`, `organvm/domus-genoma#162`, `organvm/domus-genoma#163`, `organvm/domus-genoma#172`, `organvm/domus-genoma#173`, `organvm/domus-genoma#174`, `organvm/domus-genoma#175` … (+46 more)

---
*Generated read-only by `scripts/merge-ready.py` — reuses `merge-drain.py`'s classifier. Re-run any time. Nothing merges without explicit apply plus an exact-target receipt.*
