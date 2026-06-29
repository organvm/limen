# Root-To-Leaf Acceptance Packet - 2026-06-29

> Implementation is done. The next move is root-to-leaf acceptance: use the Corpus Command Center to decide what work matters, clean the active worktree surface, then convert the public scraper into the inbound asset that starts the August pipeline.

## Build Acceptance

Corpus Command Center is accepted as built. It is not waiting on more tooling.

Evidence from the current generated surface:

- `docs/corpus-command-center.md` was generated at `2026-06-29T17:42:28+00:00`.
- Corpus coverage: `353277` units, `219803` unique hashes, `202168` clusters, `24` side-by-side comparisons.
- Private bodies stay under `.limen-private/session-corpus/corpus-command-center/objects`; tracked output is redacted.
- Inbound panel is present: `12` value repos, `9` seeded repos, front door present, discoverability present, scraper model present.
- Aug-1 gate is still false: `0/5` legs, `0` received dollars, `0` signed engagements.

Acceptance rule: do not extend the Command Center until an operator acceptance pass has used it to decide, clean, and publish.

## Warp Crash Triage

Crash receipt: Warp Stable `0.2026.06.24.09.19.02` crashed on 2026-06-29 at 15:53:20 -0400 with `EXC_CRASH (SIGABRT)`.

The crash stack is native Warp/AppKit window handling, not a Limen shell predicate:

- AppKit was entering or ordering a fullscreen window (`_NSEnterFullScreenTransitionController`, `NSWindow _doOrderWindow`).
- Warp was handling a tab/window transfer (`Workspace.on_tab_drag`, `create_transferred_window`, `schedule_synthetic_drag`).
- Background file watchers and code indexing were present, but the aborting path is the main-thread window transition.

Recovery rule: continue from git state and logs, avoid dragging/transferring Warp tabs while in fullscreen during long runs, and use a plain window for sustained autonomous work. If this recurs, treat it as a Warp native crash receipt unless a shell process, hook, or Limen predicate is in the crashing stack.

## First Work Clusters That Matter

These are the first clusters to accept from root to leaf. Raw repeated tool-call clusters are noise; the meaningful clusters are the ranked work families and blockers tied to prompt recurrence, worktree state, preservation risk, and August value.

| Order | Cluster | Corpus Evidence | Acceptance Decision | Next Move |
|---:|---|---|---|---|
| 1 | `session_lifecycle` | Score `72`; `159` sessions; `636` prompt events; recency `<=7d`. | Matters because it decides whether the corpus becomes durable memory or repeated chat residue. | Keep the ledgers current, collapse repeats into owner receipts, and stop re-answering old prompts as new work. |
| 2 | `dispatch-heartbeat-substrate-unhealthy` | Score `64`; blocker lane `human-gate`; status `needs_human_gate`. | Matters because a bad substrate makes every downstream agent misread auth, GitHub, launchd, and runtime symptoms. | Use `docs/live-root-gate.md`; do not reload launchd, switch branches, mutate the task board, or enable async work without explicit operator gate. |
| 3 | `worktree_lifecycle` | Score `63`; `77` sessions; `289` prompt events; current scan reports `25` roots and `0` debt. | Matters because worktree sprawl is now an acceptance queue, not a hidden backlog. | Use the disposition table below; merge open PRs, keep active roots visible, delete only after acceptance, and route blockers to human decisions. |
| 4 | `github_review` | Score `61`; `158` sessions; `615` prompt events. | Matters only after owner repo, branch, predicate, and receipt are explicit. | Review or merge named PRs; do not dispatch broad GitHub review prompts. |
| 5 | `public-record-data-scrapper` inbound asset | Command Center inbound panel says scraper model present; positioning page exists; merged worktree receipt is preserved. | Matters because this is the August pipeline artifact, not an internal tooling problem. | Publish the proof page, sample output, case study, and contact path; start counting visits, qualified inbound, replies, calls, paid trials, and cash. |

## Worktree Disposition

Read-only scan used for this table: `python3 scripts/worktree-debt.py --json` on 2026-06-29. Result: `25` roots, `0` debt, class mix `10 active(<24h)`, `5 remote-pr-open`, `3 remote-merged`, `3 documented-residue`, `2 remote-superseded`, `2 owner-blocker`.

| Disposition | Roots | Reason | Acceptance Action |
|---|---|---|---|
| merge | `bld-my--father-mother-harden-44b2`, `bld-promptscope-next-rev-3fde`, `cifix-organvm-i-theoria-conversation-corpus-engine-f02e`, `discover-organvm-kerygma-profiles-6c74`, `the-invisible-ledger` | Remote PRs preserve local heads. | Review and merge, or name a successor PR. Do not keep local checkouts as the source of truth. |
| keep | `warp-agent-routing-20260629`, `workstream-kickstart-20260629`, `limen-main-trench-20260628`, `limen-network-substrate-20260628`, `limen-rob-game-lane-20260628` | Active Limen roots inside the grace window. | Keep visible; do not reclaim during this acceptance pass. |
| defer | `triptych-media-offload-20260629`, `maddie-boundary-20260629`, `student-email-d2l-support-20260629`, `domus-quarantine-retire-20260629`, `universal-entry-20260629` | Active non-Limen or owner-specific roots inside the grace window. | Defer to their owner packets; do not sweep from the Limen acceptance pass. |
| delete | `bld-mirror-mirror-harden-350f`, `mirror-mirror`, `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f`, `cifix-organvm-i-theoria-hierarchia-mundi-3145`, `triptych-story`, `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38`, `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2`, `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | Remote merged, remote superseded, or documented non-source residue. | Reclaim only after operator acceptance; no new PR or implementation work remains. |
| needs_human | `gen-organvm-universal-mail--automation-test-coverage-0625-151e`, `resolve-organvm-i-theoria-.github-459-1ade` | Owner-blocker roots with preserved private patch evidence. | Decide whether to reclaim, recreate from current default, or cherry-pick a narrow idea into a new owner packet. |

## Public Scraper Inbound Asset

Public-safe August artifact set:

- Proof page: `docs/positioning/public-record-data-scrapper-proof-page.md`
- Sample output: `docs/positioning/public-record-data-scrapper-sample-output.json`
- Case study: `docs/positioning/public-record-data-scrapper-case-study.md`
- Contact path: `docs/positioning/public-record-data-scrapper-contact-path.md`

Acceptance rule: the repo proves form publicly; the paid operation is the fresh, fed, tuned instance. The public artifact should sell the buyer on a call without exposing private data, premium keys, live prospects, or customer contact data.

## August Scoreboard

Source of truth:

- Pipeline event ledger: `state/aug1/pipeline-scoreboard.json`
- Cleared cash ledger: `state/aug1/revenue-received.json`
- Signed engagement ledger: `state/aug1/engagements.json`
- Board renderer: `scripts/aug1-view.py`

The six visible metrics are fixed: visits, qualified inbound, replies, calls, paid trials, cash. Cash is cleared money only and comes from `state/aug1/revenue-received.json`; the other five come from `state/aug1/pipeline-scoreboard.json`.
