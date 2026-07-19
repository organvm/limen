# Substrate Storage Pressure

Generated: `2026-07-19T23:24:52Z`
Status: `partial`
Scope status: `partial`
Inventory: `cheap`; fresh: `False`; unknown buckets: `3`
Internal free: `18.1 GiB`
Target free: `200.0 GiB`
Shortfall: `181.9 GiB`
Free-space trend: `falling` (`-97.0 GiB` over `809800.483802s`)

## Host and Backup Admission

- Backblaze CPU: `98.4%`; RSS: `2354511872` bytes.
- Swap fraction: `0.305328369140625`; host admission allowed: `False`.
- Exclusion coverage: `missing`; complete: `False`; missing: `2`; unknown pools: `0`.

## Safe Reclaim Already Run

- `generated-state`: `26.6 GiB` over `5` apply event(s); latest `2026-07-10T11:55:58Z`.
- `ollama-models`: `9.3 GiB` over `4` apply event(s); latest `2026-07-10T11:56:09Z`.
- `tool-cache`: `5.6 GiB` over `4` apply event(s); latest `2026-07-10T11:56:04Z`.

## Scratch / Worktree Lifecycle

- Cached stale summary: `404 debt roots / 701 scanned; 0 reapable roots`.
- Inventory age: `809800.483802s`; fresh: `False`.
- Debt target: `0`; complete: `False`; reapable cap: `0`.

| Reason | Roots |
|---|---:|
| `not-merged-to-default` | `210` |
| `dirty` | `110` |
| `active(<6h)` | `104` |
| `unpushed-commits` | `84` |
| `remote-pr-open` | `77` |
| `antigravity-scratch-managed` | `48` |
| `owner-blocker` | `35` |
| `active(<24h)` | `25` |
| `remote-merged` | `5` |
| `documented-residue` | `2` |
| `remote-superseded` | `1` |

## Remaining Large Buckets

| Bucket | Size | Class | Owner | Gate |
|---|---:|---|---|---|
| `~/.local/share/opencode/opencode.db` | `17.5 GiB` | `protected-agent-state` | `aw-opencode-db-corpus-intake-0709` | external archive and private intake verified; local retention decision remains; never delete outright |
| `~/Workspace/limen/.limen-private/session-corpus` | `10.2 GiB` | `protected-private-corpus` | `docs/session-corpus-ledger.md` | two-copy/restore archive gate before move or purge |
| `~/Pictures/Photos Library.photoslibrary` | `8.6 GiB` | `personal-media` | `media/photos custody` | personal-data human gate plus two-copy restore proof |
| `~/Workspace/.limen-worktrees` | `7.4 GiB` | `worktree-cache` | `docs/worktree-reclaim-acceptance.md` | clean+merged+idle or explicit acceptance; current worktree-debt gate reports zero reapable |
| `~/Library/Messages` | `7.3 GiB` | `personal-communications` | `communications custody` | personal-data human gate plus two-copy restore proof |
| `~/.gemini/antigravity-cli` | `6.5 GiB` | `protected-agent-state` | `agy conductor` | preserve conversations/brain before eviction; scratch handled separately |
| `~/Workspace/session-meta` | `5.1 GiB` | `repo-corpus-state` | `organvm/session-meta` | repo/archive custody proof before local cache eviction |
| `~/.gemini/antigravity-cli/scratch` | `4.2 GiB` | `agy-scratch` | `docs/antigravity-scratch-bridge.md` | antigravity scratch archive/redaction acceptance ledger before removal |
| `~/Workspace/limen/.claude/worktrees` | `unknown` | `regenerable-fleet-state` | `organvm/domus-genoma#306` | live Domus exclusion coverage before growth is tolerated; worktree-debt owns deletion |
| `~/Workspace/limen/.worktrees` | `unknown` | `regenerable-fleet-state` | `organvm/domus-genoma#306` | live Domus exclusion coverage before growth is tolerated; preserve dirty or unpushed roots before deletion |
| `~/Workspace/limen/.codex/worktrees` | `unknown` | `regenerable-fleet-state` | `organvm/domus-genoma#306` | live Domus exclusion coverage before growth is tolerated; preserve dirty or unpushed roots before deletion |

## OpenCode DB Intake

- Status: `archived_private_intake`.
- Archive status: `verified`.
- Receipt: `~/Workspace/limen/docs/opencode-db-corpus-intake.md`.
- Private manifest: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/opencode-db-intake/20260710T094811Z/manifest.json`.

## Contract

- A stale, partial, or unknown inventory can never report `clear`.
- Under red host admission, auto mode reads cheap sensors and cached bounded inventories; it does not run broad bucket or worktree scans.
- Bucket inventory is bounded by an aggregate scan budget and a per-bucket timeout; unknown sizes remain explicit.
- Do not delete personal communications, photos, private corpus, or agent session databases as cache.
- Worktree and Agy scratch removal stay behind their acceptance ledgers.
- More disk reduction now requires owner gates, archive/restore proof, or explicit product decision to lower the hot-cache target.
