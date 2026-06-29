# Prompt Lifecycle Ledger

Generated: `2026-06-29T22:00:16+00:00`
Horizon: `all local history`

## Canonical Decision

- A human prompt/session is a lifecycle seed. Work that starts from it must end in a named outcome: merged, pushed PR, preserved branch, owner-recorded blocker, named supersession, archived task, or documented non-source residue.
- Raw personal/session material belongs in `.limen-private/session-corpus/`; tracked ledgers must stay redacted and receipt-oriented.
- Screenshots are coverage hints. The canonical absorptive layer is the local app/session filesystem plus private cartridge materialization.
- Worktree cleanup is subordinate to prompt lifecycle: no unique work is removed just because a directory is inconvenient.

## Redacted Prompt Coverage

Indexed `9711` app/session files, `2.5 GiB`, with `98045` prompt-like user events hashed into the private index.

| Source | Files | Prompt Events | Event Records | Size | Newest |
|---|---:|---:|---:|---:|---|
| `claude-projects` | 4979 | 91418 | 322331 | 1.4 GiB | `2026-06-29T21:27:16+00:00` |
| `codex-sessions` | 986 | 5677 | 309024 | 1.0 GiB | `2026-06-29T21:59:16+00:00` |
| `codex-history` | 1 | 817 | 817 | 639.5 KiB | `2026-06-29T21:59:07+00:00` |
| `claude-tasks` | 188 | 133 | 133 | 57.7 KiB | `2026-06-26T00:08:52+00:00` |
| `claude-file-history` | 3519 | 0 | 0 | 42.2 MiB | `2026-06-27T00:26:28+00:00` |
| `claude-plans` | 34 | 0 | 0 | 289.3 KiB | `2026-06-25T03:22:45+00:00` |
| `codex-attachments` | 4 | 0 | 0 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Prompt To Worktree Crosswalk

- Current `.limen-worktrees` roots scanned: `25`; debt roots: `0`.
- Current worktree roots with at least one local session/prompt receipt: `22`.
- Current worktree roots without a local session receipt in this index: `3`.

| Worktree Root | Session Files | Prompt Events | Debt Reason |
|---|---:|---:|---|
| `bld-mirror-mirror-harden-350f` | 1 | 5 | `remote-merged` |
| `bld-my--father-mother-harden-44b2` | 1 | 5 | `remote-pr-open` |
| `bld-promptscope-next-rev-3fde` | 1 | 4 | `remote-pr-open` |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | 3 | 79 | `remote-pr-open` |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | 1 | 71 | `remote-superseded` |
| `discover-organvm-kerygma-profiles-6c74` | 1 | 24 | `remote-pr-open` |
| `domus-quarantine-retire-20260629` | 7 | 63 | `active(<24h)` |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | 1 | 3 | `documented-residue` |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | 1 | 4 | `documented-residue` |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 3 | 100 | `owner-blocker` |
| `limen-main-trench-20260628` | 1 | 14 | `active(<24h)` |
| `limen-network-substrate-20260628` | 2 | 21 | `active(<24h)` |
| `limen-rob-game-lane-20260628` | 0 | 0 | `active(<24h)` |
| `maddie-boundary-20260629` | 2 | 68 | `active(<24h)` |
| `mirror-mirror` | 85 | 2275 | `remote-merged` |
| `resolve-organvm-i-theoria-.github-459-1ade` | 1 | 5 | `owner-blocker` |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | 1 | 79 | `remote-merged` |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | 1 | 94 | `documented-residue` |
| `student-email-d2l-support-20260629` | 2 | 67 | `active(<24h)` |
| `the-invisible-ledger` | 99 | 2919 | `remote-pr-open` |
| `triptych-media-offload-20260629` | 4 | 123 | `active(<24h)` |
| `triptych-story` | 3 | 212 | `remote-superseded` |
| `universal-entry-20260629` | 0 | 0 | `active(<24h)` |
| `warp-agent-routing-20260629` | 2 | 15 | `active(<24h)` |
| `workstream-kickstart-20260629` | 0 | 0 | `active(<24h)` |

## Task Board Crosswalk

- Task records: `1500`.
- Status distribution: `archived` 439, `dispatched` 34, `done` 869, `in_progress` 1, `needs_human` 78, `open` 79.
- Invalid statuses outside canonical set: `0`.
- Current worktree root slugs mentioned exactly in `tasks.yaml`: `2` / `25`.
- Chronic reopen-loop candidates: `0`.
- Dispatched tasks with PR receipt: `0`.
- Dispatched Jules async tasks without PR yet: `34`.
- Dispatched local tasks still inside running grace/no-op guard: `0`.
- Dispatched local tasks stranded without PR receipt: `0`.
- Done tasks with PR receipt still visible in dispatch log/URLs: `690`.

## Remote Receipts

- GitHub worktree repos seen: `14`.
- Git worktree roots with remote branch present: `15`; missing: `7`.
- Branch-linked PR states: `OPEN` 5, `MERGED` 5, `CLOSED` 0.
- Task-board GitHub PR refs seen: `713`; checked: `713`; states: `CLOSED` 50, `MERGED` 473, `OPEN` 190.

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
