# Prompt Priority Map

Generated: `2026-06-29T21:23:49+00:00`

## Canonical Decision

- The long-running unit is a review batch, not a chat-length mega-prompt.
- Every prompt-like event is represented by a hash in the private map; tracked docs show only counts, session keys, lanes, and routes.
- A batch becomes dispatchable only after it has an owner repo or owner ledger, bounded next action, no raw-secret dependency, and a verification or blocker receipt.
- Credential/auth/secret lanes stay parked unless a scoped task directly requires non-secret preparation.

## Coverage

- Prompt lifecycle source files: `9706`.
- Prompt-like events from source ledger: `97985`.
- Prioritized session receipts: `3629`.
- Prioritized prompt events: `97985`.
- Unique prompt hashes: `58444`.
- Review batches: `157`.
- Codex classified sessions: `887`.
- Attack paths / blockers / capability items: `31` / `7` / `30`.
- Source mix: `claude-projects` 2512, `codex-sessions` 983, `claude-tasks` 133.
- Band mix: `low` 1438, `medium` 1374, `parked` 405, `high` 277, `critical` 135.
- Lane mix: `legacy-session-review` 1737, `historical-worktree-review` 980, `family` 419, `parked-secret` 405, `stalled-review` 59, `hash-review` 16.

## Priority Model

- Highest: stalled or active receipts tied to high-ranked attack paths, worktree preservation risk, repeated prompt hashes, and recent activity.
- Middle: legacy Claude/Codex sessions that need private sampling and owner-ledger promotion.
- Lowest: closed, already-parked, or credential/auth work unless directly blocking a selected path.
- The private JSON keeps the complete sorted hash/session map; this Markdown intentionally shows a bounded operator slice.

## Review Batches

| Rank | Batch | Band | Lane | Sessions | Prompt Events | Unique Prompts | Dominant Mix | Route |
|---:|---|---|---|---:|---:|---:|---|---|
| 1 | `prompt-batch-critical-historical-worktree-review-001` | `critical` | `historical-worktree-review` | 25 | 4143 | 2574 | sources claude-projects 24, codex-sessions 1; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 2 | `prompt-batch-critical-human-gate-001` | `critical` | `human-gate` | 2 | 167 | 113 | sources claude-projects 2; families uncategorized 2 | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| 3 | `prompt-batch-critical-stalled-review-001` | `critical` | `stalled-review` | 25 | 110 | 72 | sources codex-sessions 25; families session_lifecycle 17, worktree_lifecycle 7, github_review 1 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 4 | `prompt-batch-critical-hash-review-001` | `critical` | `hash-review` | 2 | 280 | 127 | sources codex-sessions 2; families uncategorized 2 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 5 | `prompt-batch-critical-legacy-session-review-001` | `critical` | `legacy-session-review` | 25 | 17163 | 8807 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 6 | `prompt-batch-critical-stalled-review-002` | `critical` | `stalled-review` | 18 | 80 | 48 | sources codex-sessions 18; families github_review 11, worktree_lifecycle 7 | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 7 | `prompt-batch-critical-legacy-session-review-002` | `critical` | `legacy-session-review` | 14 | 4353 | 2570 | sources claude-projects 14; families uncategorized 14 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 8 | `prompt-batch-critical-historical-worktree-review-002` | `critical` | `historical-worktree-review` | 24 | 2249 | 1502 | sources claude-projects 23, codex-sessions 1; families uncategorized 24 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 9 | `prompt-batch-high-legacy-session-review-001` | `high` | `legacy-session-review` | 25 | 9190 | 5595 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 10 | `prompt-batch-high-historical-worktree-review-001` | `high` | `historical-worktree-review` | 25 | 2102 | 1314 | sources claude-projects 24, codex-sessions 1; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 11 | `prompt-batch-high-stalled-review-001` | `high` | `stalled-review` | 16 | 67 | 35 | sources codex-sessions 16; families agent_coordination 9, technical_debt_ci 3, session_lifecycle 2, uncategorized 2 | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 12 | `prompt-batch-high-human-gate-001` | `high` | `human-gate` | 6 | 258 | 182 | sources claude-projects 4, codex-sessions 2; families uncategorized 4, worktree_lifecycle 1, session_lifecycle 1 | No local source preservation action remains. Local HEAD, origin/main, and closed PR #22 head/base OIDs all equal 745a1baa57874b4e819a0eba4b983246f72e5539; git cherry origin/main HEAD and git diff --check origin/main..HEAD are empty. Reclaim the local checkout only after normal operator acceptance. |
| 13 | `prompt-batch-high-historical-worktree-review-002` | `high` | `historical-worktree-review` | 25 | 1895 | 1216 | sources claude-projects 24, codex-sessions 1; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 14 | `prompt-batch-high-legacy-session-review-002` | `high` | `legacy-session-review` | 24 | 2795 | 2152 | sources claude-projects 24; families uncategorized 24 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 15 | `prompt-batch-high-historical-worktree-review-003` | `high` | `historical-worktree-review` | 25 | 1717 | 1107 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 16 | `prompt-batch-high-hash-review-001` | `high` | `hash-review` | 3 | 913 | 586 | sources codex-sessions 2, codex-history 1; families uncategorized 3 | Review the redacted `codex-history` receipt privately and assign an owner route before delegation. |
| 17 | `prompt-batch-high-historical-worktree-review-004` | `high` | `historical-worktree-review` | 25 | 1582 | 1046 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 18 | `prompt-batch-high-historical-worktree-review-005` | `high` | `historical-worktree-review` | 25 | 1529 | 967 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 19 | `prompt-batch-high-historical-worktree-review-006` | `high` | `historical-worktree-review` | 25 | 1380 | 869 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 20 | `prompt-batch-high-historical-worktree-review-007` | `high` | `historical-worktree-review` | 25 | 1340 | 875 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 21 | `prompt-batch-high-historical-worktree-review-008` | `high` | `historical-worktree-review` | 25 | 1295 | 826 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 22 | `prompt-batch-high-historical-worktree-review-009` | `high` | `historical-worktree-review` | 3 | 140 | 115 | sources claude-projects 3; families uncategorized 3 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 23 | `prompt-batch-medium-legacy-session-review-001` | `medium` | `legacy-session-review` | 25 | 1578 | 1344 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 24 | `prompt-batch-medium-historical-worktree-review-001` | `medium` | `historical-worktree-review` | 25 | 1154 | 740 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 25 | `prompt-batch-medium-historical-worktree-review-002` | `medium` | `historical-worktree-review` | 25 | 1086 | 764 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 26 | `prompt-batch-medium-historical-worktree-review-003` | `medium` | `historical-worktree-review` | 25 | 905 | 633 | sources claude-projects 22, codex-sessions 3; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 27 | `prompt-batch-medium-family-001` | `medium` | `family` | 25 | 137 | 80 | sources codex-sessions 25; families worktree_lifecycle 16, session_lifecycle 9 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 28 | `prompt-batch-medium-historical-worktree-review-004` | `medium` | `historical-worktree-review` | 25 | 939 | 615 | sources claude-projects 23, codex-sessions 2; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 29 | `prompt-batch-medium-hash-review-001` | `medium` | `hash-review` | 9 | 96 | 40 | sources codex-sessions 9; families uncategorized 9 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 30 | `prompt-batch-medium-human-gate-001` | `medium` | `human-gate` | 4 | 93 | 61 | sources claude-projects 2, codex-sessions 2; families uncategorized 2, github_review 1, agent_coordination 1 | No local-only source preservation remains. GitHub PR #60 is OPEN/DRAFT, all reported checks passed, and its head OID equals the local worktree HEAD. Review and merge or supersede the PR; reclaim the local checkout only after normal operator acceptance. |

## Top Session Receipts

| Rank | Session Key | Band | Lane | Score | Source | Family / State | Worktree | Prompt Events | Next Action |
|---:|---|---|---|---:|---|---|---|---:|---|
| 1 | `de2567892435fc602bf0` | `critical` | `historical-worktree-review` | 113 | `codex-sessions` | `uncategorized` / `unclassified` | `triptych-story` | 192 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 2 | `cad7d3bad2068e8d3d75` | `critical` | `historical-worktree-review` | 105 | `claude-projects` | `uncategorized` / `unclassified` | `heal-192-regression` | 782 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 3 | `32b3b0fa9e485d2f895f` | `critical` | `human-gate` | 103 | `claude-projects` | `uncategorized` / `unclassified` | `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | 94 | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| 4 | `67f2241d792c23af0a4e` | `critical` | `historical-worktree-review` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `the-invisible-ledger` | 317 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 5 | `9491f01ba49706d8bca5` | `critical` | `historical-worktree-review` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `the-invisible-ledger` | 301 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 6 | `a7441461de8ac4b716c1` | `critical` | `historical-worktree-review` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `rev-organvm-universal-mail--automation-revenue-ship-0629-14ea` | 95 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 7 | `25db5ecad5a24d2052ef` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `bld2-peer-audited--behavioral-blockchain-integration-tests-c82f` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 8 | `49c3236f515814e83ed0` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-conversation-corpus-engine-2e73` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 9 | `73a15948cbe81d81ce53` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `the-invisible-ledger` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 10 | `7bc21d2319c0becc8dc0` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `rev-styx-stripe-subscription-719b` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 11 | `9e95b555d72c21e03223` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `bld-peer-audited--behavioral-blockchain-ci-706e` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 12 | `30430506c7f63f021904` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `rev-organvm-public-record-data-scrapper-revenue-readiness-0626-6d93` | 137 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 13 | `6f85af70c8b7c2aa59d4` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-a-i-chat--exporter-typing-0624-5bd9` | 125 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 14 | `82b6bf7f5cf6c4f5c517` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-domus-genoma-security-0626-5961` | 166 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 15 | `8cdf7b189043e65a730c` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-public-record-data-scrapper-ci-green-0625-ec9e` | 118 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 16 | `c54a97d270a56014657e` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-public-record-data-scrapper-security-0626-6c09` | 197 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 17 | `0da770169830d2e25a55` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `resolve-a-organvm-peer-audited--behavioral-blockchain-714-6648` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 18 | `0f1862fbac5e43c4ebcf` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `the-invisible-ledger` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 19 | `1e91bfdf2d9519aa4343` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `the-invisible-ledger` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 20 | `21b24f831030fdd82fb5` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-conversation-corpus-engine-ee1d` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 21 | `27c92b31ca08bc9bd700` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `resolve-organvm-i-theoria-.github-459-cd2f` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 22 | `49d1c148af42651fc860` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-099` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 23 | `58c20119ea3d81efc71e` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-a-organvm-peer-audited--behavioral-blockchain-3887` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 24 | `6cf13afbcf7cb2d144f4` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-084-8712` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 25 | `6e9ffdf3b05b2aea3284` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-054` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 26 | `7385a82f1cbd54d7c08c` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `gh-a-organvm-organvm-corpvs-testamentvm-494-0388` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 27 | `bfdf703ed5b6281a5aac` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `gh-4444j99-domus-genoma-86-8188` | 3 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 28 | `c1d088d3f3cd46bc6053` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-a-organvm-peer-audited--behavioral-blockchain-6f84` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 29 | `176ec660a51377584f49` | `critical` | `historical-worktree-review` | 97 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-session-meta-ci-green-0628-a6ac` | 127 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 30 | `691e6660bee9a00cdf40` | `critical` | `historical-worktree-review` | 97 | `claude-projects` | `uncategorized` / `unclassified` | `rev-organvm-universal-mail--automation-revenue-ship-0625-56e9` | 125 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |

## Lane Task Map

| Lane | Top Band | Sessions | Prompt Events | Batches | Dominant Source | Dominant Family | Route |
|---|---|---:|---:|---:|---|---|---|
| `historical-worktree-review` | `critical` | 980 | 34039 | 41 | `claude-projects` | `uncategorized` | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| `human-gate` | `critical` | 13 | 538 | 4 | `claude-projects` | `uncategorized` | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| `stalled-review` | `critical` | 59 | 257 | 3 | `codex-sessions` | `session_lifecycle` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| `hash-review` | `critical` | 16 | 1309 | 4 | `codex-sessions` | `uncategorized` | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| `legacy-session-review` | `critical` | 1737 | 57769 | 71 | `claude-projects` | `uncategorized` | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| `family` | `medium` | 419 | 1573 | 17 | `codex-sessions` | `github_review` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| `parked-secret` | `parked` | 405 | 2500 | 17 | `codex-sessions` | `auth_credentials` | Keep parked unless a scoped account/setup task directly requires non-secret prep. |

## Private Output

- Prompt priority private map: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-priority-map.json`.
- The private map contains prompt hashes, session keys, source paths, lanes, scores, and batch membership; it contains no prompt text.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/session-attack-paths.py --write`
- Refresh this priority map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Show a wider tracked slice: `python3 scripts/prompt-priority-map.py --write --limit 60`
