# Prompt Packet Ledger

Generated: `2026-06-29T22:00:40+00:00`

## Canonical Decision

- Packets are bounded owner/task units derived from redacted batch/session hashes.
- Packetization is not dispatch by itself; a packet needs an owner repo or owner ledger, a narrow predicate, no secret dependency, and an expected receipt before external delegation.
- Stalled-review packets default to Codex because they require lifecycle judgment before cheaper lanes can safely execute.
- This ledger contains no raw prompt or session text.

## Coverage

- Source review batches: `159`.
- Batches needing packetization: `0`.
- Packets emitted: `9`.
- Recorded packets: `9`.
- Open packets: `0`.
- Session receipts packetized: `52`.
- Prompt events packetized: `225`.
- Unique prompt hash refs in packets: `142`.
- Packet resolution receipts: `10`.
- Packet status mix: `owner-recorded` 8, `non-source-recorded` 1.
- Dispatchability mix: `recorded-owner-receipt` 9.
- Family mix: `session_lifecycle` 2, `worktree_lifecycle` 2, `github_review` 2, `agent_coordination` 1, `technical_debt_ci` 1, `uncategorized` 1.

## Recorded Packets

| Rank | Packet | Status | Family | Sessions | Events | Root Evidence | Gate |
|---:|---|---|---|---:|---:|---|---|
| 1 | `packet-prompt-batch-critical-stalled-review-001-session_lifecycle` | `owner-recorded` | `session_lifecycle` | 14 | 59 | `session_ledger_recorded_absent_root` 11 | No live local session/worktree cleanup remains for this packet. Continue with the next open packet; rehydrate any owner repo only if a later packet names a current branch, PR, predicate, and expected receipt. |
| 2 | `packet-prompt-batch-critical-stalled-review-001-worktree_lifecycle` | `owner-recorded` | `worktree_lifecycle` | 9 | 40 | `historical_absent_reference` 13, `remote_pr_preserved` 1 | No broad worktree cleanup or delegation remains for this packet. Rehydrate a root only if a later owner-repo review explicitly names the repo, branch, predicate, and expected receipt. |
| 3 | `packet-prompt-batch-critical-stalled-review-002-github_review` | `owner-recorded` | `github_review` | 8 | 38 | `owner_repo_routed_absent_branch` 11, `remote_pr_preserved` 1 | Only bld2-a-i-chat--exporter-integration-tests-a00b has a current PR receipt. For all other roots, do not delegate until an owner packet recreates or names a live branch/PR and a narrow predicate. |
| 4 | `packet-prompt-batch-critical-stalled-review-002-worktree_lifecycle` | `owner-recorded` | `worktree_lifecycle` | 3 | 11 | `historical_absent_reference` 5, `remote_pr_preserved` 1, `merged_pr_preserved` 1 | No broad worktree cleanup or delegation remains for this refreshed packet. Rehydrate a root only if a later owner-repo review explicitly names the repo, branch, predicate, and expected receipt. |
| 5 | `packet-prompt-batch-critical-stalled-review-001-github_review` | `owner-recorded` | `github_review` | 2 | 10 | `owner_repo_routed_absent_branch` 1 | Do not delegate or rehydrate this broad historical GitHub-review root unless a later owner packet identifies the missing hardening delta, live branch or PR, predicate, and expected receipt. |
| 6 | `packet-prompt-batch-high-stalled-review-001-agent_coordination` | `owner-recorded` | `agent_coordination` | 9 | 35 | `agent_router_recorded_absent_root` 9 | No broad agent-coordination dispatch remains for this packet. Rehydrate or delegate only if a later owner packet names a live repo, branch or PR, narrow predicate, and expected receipt. |
| 7 | `packet-prompt-batch-high-stalled-review-001-session_lifecycle` | `owner-recorded` | `session_lifecycle` | 2 | 9 | `session_ledger_recorded_no_root` 2 | No live local session/worktree cleanup remains for this packet. Continue with the next open packet; rehydrate only if a later owner packet names a current repo, branch or PR, narrow predicate, and expected receipt. |
| 8 | `packet-prompt-batch-high-stalled-review-001-technical_debt_ci` | `owner-recorded` | `technical_debt_ci` | 3 | 13 | `superseded_by_owner_pr` 1, `remote_pr_preserved` 1, `owner_repo_routed_absent_branch` 1 | Only bld-media-ark-tests-2698 has a current same-root PR receipt. bld-essay-pipeline-readme-94ce is superseded by the active essay README PR, and bld-media-ark-tests-795d should not be delegated unless a later packet proves a delta not covered by the preserved media-ark tests PR. |
| 9 | `packet-prompt-batch-high-stalled-review-001-uncategorized` | `non-source-recorded` | `uncategorized` | 2 | 10 | `local_recovery_context_recorded` 2 | No repo dispatch remains for this packet. Retain as operational continuity context; create a new explicit infrastructure task only if machine restarts recur and need a fresh diagnostic packet. |

## Packet Queue

| Rank | Packet | Source Batch | Family | Dispatch Gate | Sessions | Events | Worktrees | Agent Fit | Predicate |
|---:|---|---|---|---|---:|---:|---|---|---|
| 0 | none | n/a | n/a | n/a | 0 | 0 | none | n/a | n/a |

## Packet Routes

| Packet | Owner | Route |
|---|---|---|
| none | n/a | n/a |

## Private Output

- Prompt packet private index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-packet-ledger.json`.
- The private index keeps packet membership, prompt hashes, session keys, worktree slugs, and attack-path evidence; it contains no prompt text.
- Public packet resolution receipts: `docs/prompt-packet-resolution-receipts.json`.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-batch-review-ledger.py --write && python3 scripts/prompt-priority-map.py --write`
- Refresh this packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Show a wider tracked slice: `python3 scripts/prompt-packet-ledger.py --write --limit 60`
