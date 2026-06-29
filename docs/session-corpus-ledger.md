# Session Corpus Ledger

Generated: `2026-06-29T03:25:55+00:00`
Horizon: `all local history`

## Canonical Decision

- Limen is the control plane and visible ledger for session/corpus lifecycle.
- `session-meta` remains the producer for redacted, deduped, multi-provider atoms.
- `knowledge-corpus` remains the distillation target consumed by `corpus-converge.py`.
- `prompt-lifecycle-ledger.py` is the redacted crosswalk from local prompts/sessions to worktrees, tasks, GitHub receipts, and cloud probes.
- Raw personal/session data is private local material. It belongs under `./.limen-private/session-corpus/` when materialized, never in public Git history.
- The app screenshots are coverage hints, not canonical input. Canonical input is the local Claude/Codex/session-meta filesystem state.

## Local Session Sources

Total seen: `9869` files, `2.3 GiB`.

| Source | Root | Files | Size | Newest |
|---|---:|---:|---:|---|
| `claude-projects` | `~/.claude/projects` | 4941 | 1.4 GiB | `2026-06-29T02:14:45+00:00` |
| `codex-sessions` | `~/.codex/sessions` | 934 | 839.6 MiB | `2026-06-29T03:25:50+00:00` |
| `claude-file-history` | `~/.claude/file-history` | 3519 | 42.2 MiB | `2026-06-27T00:26:28+00:00` |
| `codex-goals-state` | `~/.codex` | 6 | 15.6 MiB | `2026-06-29T03:25:50+00:00` |
| `claude-plans` | `~/.claude/plans` | 34 | 289.3 KiB | `2026-06-25T03:22:45+00:00` |
| `codex-history` | `~/.codex` | 1 | 260.5 KiB | `2026-06-29T03:23:12+00:00` |
| `claude-usage-session-meta` | `~/.claude/usage-data/session-meta` | 197 | 221.4 KiB | `2026-06-23T19:06:40+00:00` |
| `codex-app-sqlite` | `~/.codex/sqlite` | 1 | 68.0 KiB | `2026-06-27T13:58:29+00:00` |
| `claude-tasks` | `~/.claude/tasks` | 188 | 57.7 KiB | `2026-06-26T00:08:52+00:00` |
| `claude-usage-facets` | `~/.claude/usage-data/facets` | 32 | 29.1 KiB | `2026-06-23T19:06:55+00:00` |
| `codex-shell-snapshots` | `~/.codex/shell_snapshots` | 12 | 16.3 KiB | `2026-06-29T03:12:00+00:00` |
| `codex-attachments` | `~/.codex/attachments` | 4 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Existing Organs

| Organ | Role | Path | Git state |
|---|---|---|---|
| `session-meta` | producer: redacted, deduped multi-provider atoms | `~/Workspace/session-meta` | `## codex/preserve-session-meta-owner-state-20260627` |
| `knowledge-corpus` | distillation target: collection, reduced faces, THE ONE | `~/Workspace/knowledge-corpus` | `## codex/preserve-knowledge-corpus-owner-state-20260627...origin/codex/preserve-knowledge-corpus-owner-state-20260627 [ahead 1]` |
| `conversation-corpus-engine` | product/research engine: provider import and corpus promotion | `~/Workspace/conversation-corpus-engine` | `## discover-latent-value-corpus-engine...origin/discover-latent-value-corpus-engine` |

## Substrate Counts

- `session-meta/ingest/manifest.jsonl`: 23,672 records, mtime `2026-06-29T03:22:56+00:00`.
- `session-meta/ingest/atoms.jsonl`: 120,412 atoms, mtime `2026-06-29T03:25:53+00:00`.
- `knowledge-corpus`: `13` reduced faces; `00-THE-ONE.md` present: `True`.
- Top manifest sources: `gemini` 4,592, `claude` 3,961, `chatgpt` 2,709, `claude-projects` 2,539, `cowork-sessions` 2,047, `antigravity` 1,893, `downloads` 1,717, `intake` 1,569.

## Session Lifecycle

- No `quicken.py` journal found yet.
- Last `codex-quicken.py` journal: `2026-06-29T00:01:47+00:00`.
- Codex sessions classified: `931` total; `ALIVE` 4, `CLOSED` 822, `PARKED` 40, `STALLED` 65.
- Top Codex lifecycle families: `auth_credentials` 445, `github_review` 161, `session_lifecycle` 159, `worktree_lifecycle` 77, `agent_coordination` 40, `technical_debt_ci` 37.

## Private Cartridge

- Private root: `~/Workspace/limen-main-trench-20260628/.limen-private/session-corpus`.
- Private inventory: `~/Workspace/limen-main-trench-20260628/.limen-private/session-corpus/inventory/session-corpus-ledger.json`.
- `.limen-private/` is ignored by Git; it is the local raw/private landing zone.
- Materialized objects this run: copied `9`, already present `9860`, bytes copied `89.9 MiB`.
- Private object store now holds `7503` unique objects, `2.4 GiB`.
- Private screenshot evidence: none recorded yet.

## Tracked Intake Receipts

- Screenshot intake: `docs/session-screenshot-intake-2026-06-27.md`.
- Session lifecycle drain queue: `docs/session-lifecycle-drain-queue-2026-06-27.md`.
- Session lifecycle blockers: `docs/session-lifecycle-blockers.md`.
- Session attack paths: `docs/session-attack-paths.md`.
- Prompt priority map: `docs/prompt-priority-map.md`.
- Prompt batch review ledger: `docs/prompt-batch-review-ledger.md`.
- Prompt packet ledger: `docs/prompt-packet-ledger.md`.
- Prompt packet resolution receipts: `docs/prompt-packet-resolution-receipts.json`.
- Capability substrate ledger: `docs/capability-substrate-ledger.md`.

## Roadblocks And Potholes

- Local Claude/Codex app stores are live private data; screenshots are only UI evidence. Canonical ingestion must come from the filesystem stores, not from the screenshots.
- Claude has a lifecycle organ (`scripts/quicken.py`), but no recent journal was found; refresh it before treating Claude FleetView lifecycle as current.

## Commands

- Refresh the visible all-history ledger: `python3 scripts/session-corpus-ledger.py --write --all`
- Refresh a bounded ledger: `python3 scripts/session-corpus-ledger.py --write --days 7`
- Absorb raw local objects into the ignored cartridge: `python3 scripts/session-corpus-ledger.py --write --all --materialize`
- Refresh local/remote/cloud prompt lifecycle: `python3 scripts/prompt-lifecycle-ledger.py --write --all`
- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`
- Refresh parked blockers: `python3 scripts/session-blockers-ledger.py --write`
- Refresh ranked attack paths: `python3 scripts/session-attack-paths.py --write`
- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Rebuild session-meta atoms after preserving its dirty work: `cd ~/Workspace/session-meta && ./ingest/refresh-atoms.sh`
- Refresh Limen coverage view: `python3 scripts/ingest-coverage.py`
- Classify Codex app/session lifecycle: `python3 scripts/codex-quicken.py --all --apply`
