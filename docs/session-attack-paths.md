# Session Attack Paths

Generated: `2026-07-04T18:45:56+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local substrate incidents such as network/LaunchAgent failures are not lane-local noise: patch once, record a reusable receipt, then make the blocker visible to every lane.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `14911` files, `128730` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `4`.
- Worktree preservation receipts: `70`.
- Parked blockers: `9`.
- Local lifecycle footprint: `29.4 GiB`.
- Candidate lanes: `blocker` 3, `family` 7, `human-gate` 50, `observe` 6, `owner-blocker` 3, `parked` 5, `remote-close` 1, `remote-pr-open` 10, `remote-proof` 10.

## Ordering Model

- Highest priority: system clogs that prevent the lifecycle machine from draining: broken hooks, invalid states, missing preservation receipts, stale remote proof, or owner ledgers that make downstream cleanup unsafe.
- Network/environment substrate failures outrank ordinary repo cleanup because they can make every agent misclassify auth, dispatch, and GitHub symptoms.
- Next: dirty or non-Git local roots with prompt evidence and missing remote preservation, because they consume disk and risk unique work.
- Worktree receipts that require operator acceptance before reclaim are human-gated, not autonomous lane work.
- Then: open remote-proof lanes where local copies can become lean after PR/default evidence is checked.
- Then: repeated lifecycle/family loops that need owner packets before delegation.
- Credential/auth lanes stay parked unless they are the direct clog blocking the selected path; then prepare only the bounded non-secret setup or human handoff.

## Ranked Paths

| Rank | Path | Kind | Lane | Score | Evidence | Agent Fit | Next Action |
|---:|---|---|---|---:|---|---|---|
| 1 | `worktree-lifecycle-debt` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve or owner-record each root; no deletion of unique work. |
| 2 | `worktree-remote-branches-missing` | `blocker` | `blocker` | 70 | category `worktree_lifecycle`; status `parked` | codex | Preserve each root by branch, PR, owner blocker, or documented non-source residue before cleanup. |
| 3 | `heal+jules-revive-census-converge` | `worktree` | `remote-proof` | 70 | reason `active(<24h)`; prompts 988; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 4 | `iterative-coalescing-wilkinson` | `worktree` | `remote-proof` | 70 | reason `active(<24h)`; prompts 234; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 5 | `partitioned-beaming-cosmos` | `worktree` | `remote-proof` | 70 | reason `active(<24h)`; prompts 754; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 6 | `peer-audited--behavioral-blockchain` | `worktree` | `remote-proof` | 70 | reason `unpushed-commits`; prompts 650; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 7 | `worktree_lifecycle` | `family` | `family` | 67 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 8 | `session_lifecycle` | `family` | `family` | 66 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 9 | `github-app-limen-bot-not-wired` | `blocker` | `human-gate` | 58 | category `github_app_identity`; status `needs_human_gate` | human/codex-prep | Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path. |
| 10 | `polymorphic-popping-phoenix` | `worktree` | `remote-proof` | 58 | reason `active(<24h)`; prompts 329; remote `unknown`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 11 | `ticklish-bubbling-robin` | `worktree` | `remote-proof` | 58 | reason `active(<24h)`; prompts 2085; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 12 | `github_review` | `family` | `family` | 55 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 13 | `wf_29a15be5-9f8-2` | `worktree` | `remote-proof` | 55 | reason `unpushed-commits`; prompts 33; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 14 | `github-consolidation-collisions` | `blocker` | `human-gate` | 52 | category `github_consolidation`; status `needs_human_gate` | human/codex-prep | Collision packet is complete; await an explicit human GitHub mutation gate to run `docs/consolidation/COLLISION-RENAMES.md`, then re-run the consolidation dry-run and require 0 collisions before transfer. |
| 15 | `owner-state-dirty-session-meta` | `blocker` | `blocker` | 42 | category `owner_state`; status `parked` | codex | Preserve in that owner repo before treating corpus substrate as clean. |
| 16 | `agent_coordination` | `family` | `family` | 40 | sessions 40; states CLOSED 30, STALLED 10; prompts 133 | codex | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 17 | `GEN-organvm-limen-ci-green-0702` | `worktree` | `remote-proof` | 40 | reason `unpushed-commits`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 18 | `linear-conjuring-bear` | `worktree` | `remote-close` | 40 | reason `active(<24h)`; prompts 2136; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 19 | `review-avditor-billing-pr43` | `worktree` | `remote-proof` | 40 | reason `unpushed-commits`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 20 | `local-lifecycle-disk-pressure` | `blocker` | `parked` | 34 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 21 | `technical_debt_ci` | `family` | `family` | 34 | sessions 36; states CLOSED 33, STALLED 3; prompts 128 | opencode/jules | Run narrow predicates and preserve failures in owner repos. |
| 22 | `feat-gcp-sa-organ` | `worktree` | `owner-blocker` | 34 | reason `owner-blocker`; prompts 727; remote `missing`; open PRs 0; receipt `owner_commit_needs_packet` | codex first; opencode/jules after packetization | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 23 | `agent-code-review-0704-113` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 24 | `fable-adjudication-followup-0704` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |
| 25 | `org-hr-organ-charter-0704-2089` | `worktree` | `observe` | 32 | reason `active(<6h)`; prompts 0; remote `missing`; open PRs 0 | codex first; opencode/jules after packetization | Keep active work visible; do not interrupt unless it becomes stale. |

## Delegation Gate

- A path may be assigned only when it has an owner repo or owner ledger, a bounded next action, no raw-secret dependency, and a verification predicate or blocker receipt.
- Claude is a context source while near limit; it should not be the default executor.
- Jules/OpenCode/Agy get packets only after the ranked path is narrowed to a repo, branch, predicate, and expected receipt.
- Gemini stays parked if auth is not already repaired.

## Private Output

- Private attack-path index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/session-attack-paths.json`.
- The private index keeps structured path evidence from redacted indexes; it contains no raw prompt text.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/session-blockers-ledger.py --write`
- Refresh attack paths: `python3 scripts/session-attack-paths.py --write`
- Refresh the current conductor tranche: `python3 scripts/conductor-tranche.py --write`
- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
