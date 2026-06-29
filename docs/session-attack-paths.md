# Session Attack Paths

Generated: `2026-06-29T22:17:32+00:00`

## Canonical Decision

- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.
- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.
- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.
- Local substrate incidents such as network/LaunchAgent failures are not lane-local noise: patch once, record a reusable receipt, then make the blocker visible to every lane.
- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.

## Coverage

- Redacted prompt corpus: `9711` files, `98045` prompt-like events.
- Codex classified sessions: `887`.
- Worktree debt roots: `0`.
- Worktree preservation receipts: `17`.
- Parked blockers: `8`.
- Local lifecycle footprint: `17.2 GiB`.
- Candidate lanes: `blocker` 1, `family` 7, `human-gate` 18, `parked` 5, `remote-close` 1, `remote-proof` 9.

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
| 1 | `session_lifecycle` | `family` | `family` | 72 | sessions 159; states CLOSED 139, STALLED 20; prompts 636 | codex | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 2 | `dispatch-heartbeat-substrate-unhealthy` | `blocker` | `human-gate` | 64 | category `dispatch_lifecycle`; status `needs_human_gate` | human/codex-prep | Use `docs/live-root-gate.md` to preserve/reconcile the live Limen root and reload launchd only under an explicit operator gate; stop before reset, branch switch, task-board edits, or async enablement. |
| 3 | `worktree_lifecycle` | `family` | `family` | 63 | sessions 77; states CLOSED 62, STALLED 15; prompts 289 | codex/openCode | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 4 | `github_review` | `family` | `family` | 61 | sessions 158; states CLOSED 145, STALLED 13; prompts 615 | opencode/jules | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 5 | `github-app-limen-bot-not-wired` | `blocker` | `human-gate` | 58 | category `github_app_identity`; status `needs_human_gate` | human/codex-prep | Create/install the org GitHub App and hydrate credentials via `scripts/set-credential.sh`; verify `bash scripts/gh-app-token.sh --which` reports the App path. |
| 6 | `triptych-media-offload-20260629` | `worktree` | `remote-proof` | 58 | reason `active(<24h)`; prompts 123; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 7 | `github-consolidation-collisions` | `blocker` | `human-gate` | 52 | category `github_consolidation`; status `needs_human_gate` | human/codex-prep | Collision packet is complete; await an explicit human GitHub mutation gate to run `docs/consolidation/COLLISION-RENAMES.md`, then re-run the consolidation dry-run and require 0 collisions before transfer. |
| 8 | `maddie-boundary-20260629` | `worktree` | `remote-proof` | 52 | reason `active(<24h)`; prompts 68; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 9 | `student-email-d2l-support-20260629` | `worktree` | `remote-proof` | 52 | reason `active(<24h)`; prompts 67; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 10 | `capability-substrate-not-resurfaced` | `blocker` | `blocker` | 48 | category `capability_substrate`; status `needs_refresh` | codex | Run `python3 scripts/capability-substrate-ledger.py --write` to index names/counts and choose activation order; do not read private skill bodies, install plugins, or repair MCP/ACP auth inside session lifecycle closeout. |
| 11 | `limen-network-substrate-20260628` | `worktree` | `remote-proof` | 48 | reason `active(<24h)`; prompts 21; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 12 | `limen-main-trench-20260628` | `worktree` | `remote-proof` | 47 | reason `active(<24h)`; prompts 14; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 13 | `warp-agent-routing-20260629` | `worktree` | `remote-proof` | 47 | reason `active(<24h)`; prompts 15; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 14 | `agent_coordination` | `family` | `family` | 46 | sessions 40; states CLOSED 30, STALLED 10; prompts 133 | codex | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 15 | `technical_debt_ci` | `family` | `family` | 40 | sessions 36; states CLOSED 33, STALLED 3; prompts 128 | opencode/jules | Run narrow predicates and preserve failures in owner repos. |
| 16 | `mirror-mirror` | `worktree` | `human-gate` | 35 | reason `remote-merged`; prompts 2275; remote `missing`; open PRs 0; receipt `merged_pr_preserved` | human/codex-prep | No local-only source preservation remains. GitHub PR #87 is MERGED, its head OID equals the preserved worktree HEAD, local tests/build/lint passed, and GitHub CI Lint/build/test passed before merge. Reclaim local checkout only after normal operator acceptance. |
| 17 | `the-invisible-ledger` | `worktree` | `human-gate` | 35 | reason `remote-pr-open`; prompts 2919; remote `missing`; open PRs 0; receipt `open_pr_preserved` | human/codex-prep | No local-only source preservation remains. GitHub PR #76 is OPEN and preserves the two unmerged follow-up commits from the old feat/trial-signup-flow worktree plus the current-main clamp and typecheck fixes. Local typecheck/tests/build/lint passed; GitHub CI docker, build/test/lint, and Node 20/22 matrix checks passed. Review and merge or supersede the PR; reclaim local checkout only after normal operator acceptance. |
| 18 | `local-lifecycle-disk-pressure` | `blocker` | `parked` | 34 | category `local_lean`; status `parked` | codex | Drain only after remote/default preservation proof or non-source residue receipt; keep pressure visible in SessionStart. |
| 19 | `domus-quarantine-retire-20260629` | `worktree` | `remote-close` | 34 | reason `active(<24h)`; prompts 63; remote `present`; open PRs 1 | codex first; opencode/jules after packetization | Review PR state/checks, then merge or name supersession before local reclaim. |
| 20 | `convergence_corpus` | `family` | `family` | 32 | sessions 10; states CLOSED 10; prompts 37 | codex | Promote durable atoms through session-meta and knowledge-corpus. |
| 21 | `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `worktree` | `human-gate` | 32 | reason `owner-blocker`; prompts 100; remote `missing`; open PRs 0; receipt `private_patch_preserved` | human/codex-prep | Do not PR or delegate this deletion patch. The branch has no unique commits, no remote branch, no PR, no sparse-checkout configuration, and 167 tracked files deleted from disk while HEAD is an ancestor of origin/main. Treat as stale broken checkout/deletion artifact; reclaim only after operator acceptance, and recreate from origin/main if owner work is needed. |
| 22 | `limen-rob-game-lane-20260628` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 23 | `universal-entry-20260629` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 24 | `workstream-kickstart-20260629` | `worktree` | `remote-proof` | 28 | reason `active(<24h)`; prompts 0; remote `present`; open PRs 0 | codex first; opencode/jules after packetization | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 25 | `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `worktree` | `human-gate` | 24 | reason `remote-merged`; prompts 79; remote `missing`; open PRs 0; receipt `merged_pr_preserved` | human/codex-prep | No local PR or branch preservation action remains. GitHub PR #328 is MERGED and its head OID equals the local worktree HEAD. Reclaim the local checkout only after normal operator acceptance. |

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
