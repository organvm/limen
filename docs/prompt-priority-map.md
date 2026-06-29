# Prompt Priority Map

Generated: `2026-06-29T00:03:17+00:00`

## Canonical Decision

- The long-running unit is a review batch, not a chat-length mega-prompt.
- Every prompt-like event is represented by a hash in the private map; tracked docs show only counts, session keys, lanes, and routes.
- A batch becomes dispatchable only after it has an owner repo or owner ledger, bounded next action, no raw-secret dependency, and a verification or blocker receipt.
- Credential/auth/secret lanes stay parked unless a scoped task directly requires non-secret preparation.

## Coverage

- Prompt lifecycle source files: `9614`.
- Prompt-like events from source ledger: `96001`.
- Prioritized session receipts: `3539`.
- Prioritized prompt events: `96001`.
- Unique prompt hashes: `57579`.
- Review batches: `152`.
- Codex classified sessions: `931`.
- Attack paths / blockers / capability items: `32` / `10` / `30`.
- Source mix: `claude-projects` 2474, `codex-sessions` 931, `claude-tasks` 133.
- Band mix: `low` 1360, `medium` 1324, `parked` 446, `high` 272, `critical` 137.
- Lane mix: `legacy-session-review` 1720, `historical-worktree-review` 878, `parked-secret` 446, `family` 422, `stalled-review` 59, `human-gate` 14.

## Priority Model

- Highest: stalled or active receipts tied to high-ranked attack paths, worktree preservation risk, repeated prompt hashes, and recent activity.
- Middle: legacy Claude/Codex sessions that need private sampling and owner-ledger promotion.
- Lowest: closed, already-parked, or credential/auth work unless directly blocking a selected path.
- The private JSON keeps the complete sorted hash/session map; this Markdown intentionally shows a bounded operator slice.

## Review Batches

| Rank | Batch | Band | Lane | Sessions | Prompt Events | Unique Prompts | Dominant Mix | Route |
|---:|---|---|---|---:|---:|---:|---|---|
| 1 | `prompt-batch-critical-stalled-review-001` | `critical` | `stalled-review` | 25 | 110 | 69 | sources codex-sessions 25; families worktree_lifecycle 14, session_lifecycle 9, github_review 2 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 2 | `prompt-batch-critical-historical-worktree-review-001` | `critical` | `historical-worktree-review` | 25 | 3856 | 2554 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 3 | `prompt-batch-critical-human-gate-001` | `critical` | `human-gate` | 3 | 246 | 172 | sources claude-projects 3; families uncategorized 3 | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| 4 | `prompt-batch-critical-stalled-review-002` | `critical` | `stalled-review` | 18 | 82 | 52 | sources codex-sessions 18; families github_review 10, session_lifecycle 7, technical_debt_ci 1 | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 5 | `prompt-batch-critical-legacy-session-review-001` | `critical` | `legacy-session-review` | 25 | 17950 | 9285 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 6 | `prompt-batch-critical-historical-worktree-review-002` | `critical` | `historical-worktree-review` | 25 | 2292 | 1531 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 7 | `prompt-batch-critical-legacy-session-review-002` | `critical` | `legacy-session-review` | 15 | 4731 | 2759 | sources claude-projects 15; families uncategorized 15 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 8 | `prompt-batch-critical-historical-worktree-review-003` | `critical` | `historical-worktree-review` | 1 | 71 | 50 | sources claude-projects 1; families uncategorized 1 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 9 | `prompt-batch-high-legacy-session-review-001` | `high` | `legacy-session-review` | 25 | 8281 | 5044 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 10 | `prompt-batch-high-historical-worktree-review-001` | `high` | `historical-worktree-review` | 25 | 2082 | 1303 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 11 | `prompt-batch-high-stalled-review-001` | `high` | `stalled-review` | 16 | 67 | 35 | sources codex-sessions 16; families agent_coordination 9, technical_debt_ci 3, session_lifecycle 2, uncategorized 2 | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 12 | `prompt-batch-high-human-gate-001` | `high` | `human-gate` | 7 | 189 | 129 | sources codex-sessions 4, claude-projects 3; families uncategorized 3, session_lifecycle 2, github_review 1, worktree_lifecycle 1 | No local source preservation action remains. Local HEAD, origin/main, and closed PR #22 head/base OIDs all equal 745a1baa57874b4e819a0eba4b983246f72e5539; git cherry origin/main HEAD and git diff --check origin/main..HEAD are empty. Reclaim the local checkout only after normal operator acceptance. |
| 13 | `prompt-batch-high-historical-worktree-review-002` | `high` | `historical-worktree-review` | 25 | 1773 | 1160 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 14 | `prompt-batch-high-legacy-session-review-002` | `high` | `legacy-session-review` | 25 | 2909 | 2128 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 15 | `prompt-batch-high-historical-worktree-review-003` | `high` | `historical-worktree-review` | 25 | 1646 | 1080 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 16 | `prompt-batch-high-historical-worktree-review-004` | `high` | `historical-worktree-review` | 25 | 1571 | 1023 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 17 | `prompt-batch-high-historical-worktree-review-005` | `high` | `historical-worktree-review` | 25 | 1496 | 933 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 18 | `prompt-batch-high-historical-worktree-review-006` | `high` | `historical-worktree-review` | 25 | 1343 | 844 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 19 | `prompt-batch-high-historical-worktree-review-007` | `high` | `historical-worktree-review` | 25 | 1289 | 882 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 20 | `prompt-batch-high-historical-worktree-review-008` | `high` | `historical-worktree-review` | 21 | 1067 | 696 | sources claude-projects 21; families uncategorized 21 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 21 | `prompt-batch-high-legacy-session-review-003` | `high` | `legacy-session-review` | 3 | 224 | 205 | sources claude-projects 3; families uncategorized 3 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 22 | `prompt-batch-medium-legacy-session-review-001` | `medium` | `legacy-session-review` | 25 | 1530 | 1316 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 23 | `prompt-batch-medium-historical-worktree-review-001` | `medium` | `historical-worktree-review` | 25 | 1160 | 736 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 24 | `prompt-batch-medium-historical-worktree-review-002` | `medium` | `historical-worktree-review` | 25 | 1039 | 736 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 25 | `prompt-batch-medium-historical-worktree-review-003` | `medium` | `historical-worktree-review` | 25 | 951 | 666 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 26 | `prompt-batch-medium-family-001` | `medium` | `family` | 25 | 135 | 78 | sources codex-sessions 25; families worktree_lifecycle 22, session_lifecycle 3 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 27 | `prompt-batch-medium-historical-worktree-review-004` | `medium` | `historical-worktree-review` | 25 | 996 | 679 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 28 | `prompt-batch-medium-human-gate-001` | `medium` | `human-gate` | 3 | 88 | 58 | sources claude-projects 2, codex-sessions 1; families uncategorized 2, agent_coordination 1 | No local-only source preservation remains. GitHub PR #60 is OPEN/DRAFT, all reported checks passed, and its head OID equals the local worktree HEAD. Review and merge or supersede the PR; reclaim the local checkout only after normal operator acceptance. |
| 29 | `prompt-batch-medium-historical-worktree-review-005` | `medium` | `historical-worktree-review` | 25 | 927 | 696 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 30 | `prompt-batch-medium-historical-worktree-review-006` | `medium` | `historical-worktree-review` | 25 | 859 | 627 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |

## Top Session Receipts

| Rank | Session Key | Band | Lane | Score | Source | Family / State | Worktree | Prompt Events | Next Action |
|---:|---|---|---|---:|---|---|---|---:|---|
| 1 | `5bceb564a24c59faf63c` | `critical` | `stalled-review` | 106 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-a-organvm-a-i-chat--exporter-ci-green-0620-492b` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 2 | `975fcc5c2f1e78cb30c5` | `critical` | `stalled-review` | 106 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-organvm-mirror-mirror-ci-green-0622-98c1` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 3 | `cad7d3bad2068e8d3d75` | `critical` | `historical-worktree-review` | 105 | `claude-projects` | `uncategorized` / `unclassified` | `heal-192-regression` | 782 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 4 | `6319eb873eb2ed878896` | `critical` | `stalled-review` | 105 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-organvm-a-i-chat--exporter-ci-green-0622-4a4f` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 5 | `176ec660a51377584f49` | `critical` | `historical-worktree-review` | 103 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-session-meta-ci-green-0628-a6ac` | 127 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 6 | `32b3b0fa9e485d2f895f` | `critical` | `human-gate` | 103 | `claude-projects` | `uncategorized` / `unclassified` | `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | 94 | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| 7 | `3cbfa9b3a9253f440a97` | `critical` | `historical-worktree-review` | 102 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-limen-ci-green-0628-cdb4` | 111 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 8 | `f91b96362bf17d3fe7d4` | `critical` | `historical-worktree-review` | 102 | `claude-projects` | `uncategorized` / `unclassified` | `rev-organvm-mirror-mirror-revenue-ship-0628-e60a` | 161 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 9 | `2d87d3d6120e585dcf99` | `critical` | `stalled-review` | 100 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-organvm-iii-ergon--github-6819` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 10 | `97936cf112edd566fab1` | `critical` | `stalled-review` | 100 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-organvm-v-logos--github-3b0e` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 11 | `efefc12afc137f75455b` | `critical` | `stalled-review` | 100 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `rev-mirror-deploy-3927` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 12 | `7698335b6e7a81ce795e` | `critical` | `historical-worktree-review` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `org-governance-organ-deepen-0628-0e39` | 100 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 13 | `9491f01ba49706d8bca5` | `critical` | `historical-worktree-review` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-the-invisible-ledger-typing-0626-fb12` | 301 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 14 | `051401e0b765e77fbb04` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `bld-writelens-ci-9c3b` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 15 | `0f80a8b2fff6c2b0990d` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-a-organvm-public-record-data-scrapper-a5c1` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 16 | `25db5ecad5a24d2052ef` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `bld2-peer-audited--behavioral-blockchain-integration-tests-c82f` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 17 | `3e61b3a42462f291efa7` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-4444j99-domus-genoma-07e2` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 18 | `49c3236f515814e83ed0` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-conversation-corpus-engine-2e73` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 19 | `52a3197f95915d0262a9` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `bld-domus-genoma-ci-23a9` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 20 | `7bc21d2319c0becc8dc0` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `rev-styx-stripe-subscription-719b` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 21 | `86af038939f541f0cc00` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-4444j99-media-ark-ci-green-0620-0bc1` | 3 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 22 | `88d1c646b67a6ef82218` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-a-organvm-mirror-mirror-4473` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 23 | `9e3302db88293f94a488` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-sovereign--ground-34de` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 24 | `9e95b555d72c21e03223` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `bld-peer-audited--behavioral-blockchain-ci-706e` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 25 | `a7b42860bf42f8fb791f` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `bld-domus-genoma-ci-ec4f` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 26 | `30430506c7f63f021904` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `rev-organvm-public-record-data-scrapper-revenue-readiness-0626-6d93` | 137 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 27 | `6f85af70c8b7c2aa59d4` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-a-i-chat--exporter-typing-0624-5bd9` | 125 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 28 | `82b6bf7f5cf6c4f5c517` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-domus-genoma-security-0626-5961` | 166 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 29 | `8cdf7b189043e65a730c` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-public-record-data-scrapper-ci-green-0625-ec9e` | 118 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 30 | `c54a97d270a56014657e` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-public-record-data-scrapper-security-0626-6c09` | 197 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |

## Lane Task Map

| Lane | Top Band | Sessions | Prompt Events | Batches | Dominant Source | Dominant Family | Route |
|---|---|---:|---:|---:|---|---|---|
| `stalled-review` | `critical` | 59 | 259 | 3 | `codex-sessions` | `session_lifecycle` | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| `historical-worktree-review` | `critical` | 878 | 32043 | 38 | `claude-projects` | `uncategorized` | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| `human-gate` | `critical` | 14 | 543 | 4 | `claude-projects` | `uncategorized` | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| `legacy-session-review` | `critical` | 1720 | 58009 | 71 | `claude-projects` | `uncategorized` | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| `family` | `medium` | 422 | 1582 | 18 | `codex-sessions` | `github_review` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| `parked-secret` | `parked` | 446 | 3565 | 18 | `codex-sessions` | `auth_credentials` | Keep parked unless a scoped account/setup task directly requires non-secret prep. |

## Private Output

- Prompt priority private map: `~/Workspace/limen-main-trench-20260628/.limen-private/session-corpus/lifecycle/prompt-priority-map.json`.
- The private map contains prompt hashes, session keys, source paths, lanes, scores, and batch membership; it contains no prompt text.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/session-attack-paths.py --write`
- Refresh this priority map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Show a wider tracked slice: `python3 scripts/prompt-priority-map.py --write --limit 60`
