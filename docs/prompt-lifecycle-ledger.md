# Prompt Lifecycle Ledger

Generated: `2026-07-04T18:38:30+00:00`
Horizon: `all local history`

## Canonical Decision

- A human prompt/session is a lifecycle seed. Work that starts from it must end in a named outcome: merged, pushed PR, preserved branch, owner-recorded blocker, named supersession, archived task, or documented non-source residue.
- Raw personal/session material belongs in `.limen-private/session-corpus/`; tracked ledgers must stay redacted and receipt-oriented.
- Screenshots are coverage hints. The canonical absorptive layer is the local app/session filesystem plus private cartridge materialization.
- Worktree cleanup is subordinate to prompt lifecycle: no unique work is removed just because a directory is inconvenient.

## Redacted Prompt Coverage

Indexed `14911` app/session files, `4.2 GiB`, with `128730` prompt-like user events hashed into the private index.
Normalized task-body payload covered `256.1 MiB` after stripping recognized scaffold-only prompt frames.

| Source | Files/Sessions | Prompt Events | Prompt Bytes | Task Body Bytes | Event Records | Size | Newest |
|---|---:|---:|---:|---:|---:|---:|---|
| `claude-projects` | 6483 | 118285 | 241.7 MiB | 237.1 MiB | 449661 | 1.9 GiB | `2026-07-04T18:36:38+00:00` |
| `codex-sessions` | 1361 | 7427 | 18.7 MiB | 13.2 MiB | 482034 | 1.4 GiB | `2026-07-04T18:36:51+00:00` |
| `opencode-db` | 1320 | 1327 | 3.2 MiB | 3.2 MiB | 75666 | 0 B | `2026-07-04T18:33:45+00:00` |
| `codex-history` | 1 | 999 | 701.7 KiB | 701.6 KiB | 999 | 801.2 KiB | `2026-07-04T18:11:56+00:00` |
| `agy-cli-conversations` | 501 | 480 | 2.0 MiB | 2.0 MiB | 28565 | 851.5 MiB | `2026-07-04T18:28:41+00:00` |
| `claude-tasks` | 206 | 138 | 32.2 KiB | 32.2 KiB | 138 | 59.9 KiB | `2026-07-03T15:47:52+00:00` |
| `agy-cli-history` | 1 | 44 | 10.7 KiB | 10.7 KiB | 44 | 16.4 KiB | `2026-07-03T11:53:18+00:00` |
| `gemini-tmp-agy` | 15 | 30 | 267.0 KiB | 9.9 KiB | 60 | 280.8 KiB | `2026-06-30T14:29:59+00:00` |
| `claude-file-history` | 4976 | 0 | 0 B | 0 B | 0 | 63.6 MiB | `2026-07-04T18:36:05+00:00` |
| `claude-plans` | 43 | 0 | 0 B | 0 B | 0 | 369.8 KiB | `2026-07-03T15:08:54+00:00` |
| `codex-attachments` | 4 | 0 | 0 B | 0 B | 0 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Prompt Body Mix

| Body Kind | Prompt Events |
|---|---:|
| `direct` | 124401 |
| `flame_scaffold` | 2343 |
| `flame_with_task_body` | 1971 |
| `session_context` | 15 |

## Prompt To Worktree Crosswalk

- Current `.limen-worktrees` roots scanned: `81`; debt roots: `41`.
- Current worktree roots with at least one local session/prompt receipt: `63`.
- Current worktree roots without a local session receipt in this index: `18`.

| Worktree Root | Session Files | Prompt Events | Debt Reason |
|---|---:|---:|---|
| `GEN-organvm-limen-ci-green-0702` | 0 | 0 | `unpushed-commits` |
| `agent-aefc63d95daa3131b` | 2 | 31 | `not-merged-to-default` |
| `agent-code-review-0704-113` | 0 | 0 | `active(<6h)` |
| `bld-my--father-mother-harden-44b2` | 1 | 5 | `remote-pr-open` |
| `bld-promptscope-next-rev-3fde` | 1 | 4 | `remote-pr-open` |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | 3 | 79 | `remote-pr-open` |
| `discover-organvm-kerygma-profiles-6c74` | 1 | 24 | `remote-pr-open` |
| `docs-file-fleet-dispatch-lever` | 1 | 1149 | `active(<24h)` |
| `domus-quarantine-retire-20260629` | 10 | 84 | `remote-pr-open` |
| `fable-adjudication-followup-0704` | 0 | 0 | `active(<6h)` |
| `fable-backlog-resume-0704` | 0 | 0 | `active(<6h)` |
| `feat+workstream-channels` | 2 | 47 | `not-merged-to-default` |
| `feat-codex-skill-slim` | 20 | 415 | `clean+merged+idle` |
| `feat-gcp-sa-organ` | 13 | 727 | `owner-blocker` |
| `financial-codex-finish-0704` | 0 | 0 | `active(<6h)` |
| `gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec` | 1 | 5 | `owner-blocker` |
| `gen-organvm-limen-test-coverage-0703-3a17` | 1 | 3 | `not-a-git-dir` |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 3 | 100 | `owner-blocker` |
| `gh-organvm-domus-genoma-170-bbbc` | 0 | 0 | `dirty` |
| `heal+jules-revive-census-converge` | 20 | 988 | `active(<24h)` |
| `heal-cifix-organvm-limen-449-25ce` | 1 | 3 | `not-a-git-dir` |
| `heal-cifix-organvm-limen-450-ed38` | 1 | 3 | `not-a-git-dir` |
| `heal-cifix-organvm-limen-450-fc3a` | 1 | 3 | `not-a-git-dir` |
| `heal-cifix-organvm-limen-451-0b29` | 1 | 3 | `not-a-git-dir` |
| `heal-cifix-organvm-limen-451-1cc7` | 1 | 3 | `not-a-git-dir` |
| `heal-cifix-organvm-limen-453-7f81` | 1 | 3 | `not-a-git-dir` |
| `heal-cifix-organvm-limen-456-07d7` | 1 | 3 | `not-a-git-dir` |
| `iterative-coalescing-wilkinson` | 15 | 234 | `active(<24h)` |
| `limen-main-trench-20260628` | 1 | 14 | `remote-pr-open` |
| `limen-network-substrate-20260628` | 2 | 21 | `remote-pr-open` |
| `limen_jules-org-health-organ-kernel-0630-ba5c` | 0 | 0 | `active(<6h)` |
| `linear-conjuring-bear` | 43 | 2136 | `active(<24h)` |
| `maddie-boundary-20260629` | 2 | 68 | `remote-pr-open` |
| `org-governance-organ-selffeed-0703-028a` | 1 | 3 | `not-a-git-dir` |
| `org-governance-organ-selffeed-0703-ae8d` | 1 | 3 | `not-a-git-dir` |
| `org-health-organ-firstslice-0703-9ab8` | 1 | 3 | `not-a-git-dir` |
| `org-health-organ-kernel-0704-1496` | 1 | 3 | `not-a-git-dir` |
| `org-health-organ-kernel-0704-457e` | 1 | 3 | `not-a-git-dir` |
| `org-health-organ-kernel-0704-efd2` | 1 | 3 | `not-a-git-dir` |
| `org-hr-organ-charter-0704-2089` | 0 | 0 | `active(<6h)` |
| `org-legal-organ-charter-0703-0149` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0703-3131` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0703-37ce` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0703-4f38` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0703-8eef` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0703-d5af` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0703-dcc8` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0703-fb48` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0704-55ad` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-firstslice-0703-8242` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-firstslice-0703-bdce` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-charter-0704-39f1` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-156a` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-3636` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-3dcb` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-562f` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-5b59` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-7556` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-c117` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-c80d` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-e618` | 0 | 0 | `active(<6h)` |
| `partitioned-beaming-cosmos` | 41 | 754 | `active(<24h)` |
| `peer-audited--behavioral-blockchain` | 95 | 650 | `unpushed-commits` |
| `photos-universe-20260629-182431` | 4 | 20 | `remote-pr-open` |
| `polymorphic-popping-phoenix` | 2 | 329 | `active(<24h)` |
| `pr-463` | 0 | 0 | `remote-merged` |
| `pr-466` | 0 | 0 | `remote-merged` |
| `pr-467` | 0 | 0 | `remote-merged` |
| `pr-468` | 0 | 0 | `remote-merged` |
| `pr-471` | 0 | 0 | `remote-merged` |
| `pr-475` | 0 | 0 | `remote-merged` |
| `resolve-organvm-i-theoria-.github-459-1ade` | 1 | 5 | `owner-blocker` |
| `review-avditor-billing-pr43` | 0 | 0 | `unpushed-commits` |
| `student-email-d2l-support-20260629` | 2 | 67 | `remote-pr-open` |
| `the-invisible-ledger` | 106 | 3036 | `remote-pr-open` |
| `ticklish-bubbling-robin` | 69 | 2085 | `active(<24h)` |
| `triptych-story` | 3 | 212 | `remote-pr-open` |
| `universal-entry-20260629` | 0 | 0 | `remote-pr-open` |
| `unpark-live-checkout` | 0 | 0 | `active(<24h)` |
| `warp-agent-routing-20260629` | 2 | 15 | `remote-pr-open` |
| `wf_29a15be5-9f8-2` | 1 | 33 | `unpushed-commits` |

## Task Board Crosswalk

- Task records: `1911`.
- Status distribution: `archived` 439, `dispatched` 4, `done` 1004, `in_progress` 1, `needs_human` 160, `open` 303.
- Invalid statuses outside canonical set: `0`.
- Current worktree root slugs mentioned exactly in `tasks.yaml`: `3` / `81`.
- Chronic reopen-loop candidates: `0`.
- Dispatched tasks with PR receipt: `2`.
- Dispatched Jules async tasks without PR yet: `0`.
- Dispatched local tasks still inside running grace/no-op guard: `2`.
- Dispatched local tasks stranded without PR receipt: `0`.
- Done tasks with PR receipt still visible in dispatch log/URLs: `794`.

## Remote Receipts

- GitHub worktree repos seen: `11`.
- Git worktree roots with remote branch present: `17`; missing: `16`.
- Branch-linked PR states: `OPEN` 15, `MERGED` 9, `CLOSED` 1.
- Task-board GitHub PR refs seen: `1015`; checked: `1000`; states: `CLOSED` 54, `MERGED` 530, `OPEN` 416.
- Task PR receipt scan truncated at `1000` refs.

## Cloud Receipts

- Public site probed: `https://device-streaming-067d747a.web.app`; `4` / `4` probes passed.
- Runtime URL configured: `False`; runtime health probe ok: `False`.
- Cloudflare deploy auth present: `False`.
- Cloud env flags: `CLOUDFLARE_API_TOKEN`=absent, `GOOGLE_APPLICATION_CREDENTIALS`=absent, `LIMEN_API_TOKEN`=absent, `LIMEN_CLIENT_TOKEN`=absent, `LIMEN_WORKER_URL`=absent, `NETLIFY_AUTH_TOKEN`=absent, `NEXT_PUBLIC_API_URL`=absent, `VERCEL_TOKEN`=absent.

## Roadblocks And Potholes

- The app screenshots are partially covered by local Codex history and Claude project/task stores, but screenshots alone are not durable enough to be the corpus. The durable object is now filesystem source + private object copy + redacted hash ledger.
- Remote/cloud receipts are part of the lifecycle proof, but they are not substitutes for preserving local raw prompt/session material.
- Worktree roots still do not have first-class task-board receipt fields; exact slug references are the bridge to add before automatic drain can be trusted.
- Dispatch receipt classification must distinguish async Jules work from stranded local no-PR work; otherwise the conductor burns attention on healthy async reservations.
- Prompt/session coverage is now hashed, but lifecycle judgment still needs owner actions: dirty roots need PRs or blocker records, and open PR receipts need merge or named supersession.
- Codex now has prompt-event coverage plus `codex-quicken.py` lifecycle classification: `887` sessions; `ALIVE` 1, `CLOSED` 783, `PARKED` 40, `STALLED` 63.

## Drain Queue

- Session lifecycle drain queue: `docs/session-lifecycle-drain-queue-2026-06-27.md`.

## Private Outputs

- Prompt lifecycle private index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-lifecycle-index.json`.
- Raw object cartridge: `~/Workspace/limen/.limen-private/session-corpus/objects`.
- The private index contains source paths, session hashes, prompt hashes, CWD hashes, and worktree links; it contains no prompt text.

## Commands

- Refresh this ledger with remote/cloud receipts: `python3 scripts/prompt-lifecycle-ledger.py --write --all`
- Refresh local-only when offline: `python3 scripts/prompt-lifecycle-ledger.py --write --all --no-remote --no-cloud`
- Refresh and absorb raw session/app files: `python3 scripts/session-corpus-ledger.py --write --all --materialize`
- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Inspect lifecycle debt: `python3 scripts/worktree-debt.py --json`
