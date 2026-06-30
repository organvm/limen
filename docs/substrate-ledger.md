# Substrate Ledger

Generated: `2026-06-30T11:48:50+00:00`
Status: `ready`

## Counts

- `active`: 4
- `full`: 6
- `read_only`: 4

## Roots

| Root | Status | Sources | Detail |
|---|---|---|---|
| `/Volumes/Archive4T` | `active` | `mounted-volume` | exists and is usable |
| `/Volumes/Ingress` | `active` | `mounted-volume` | exists and is usable |
| `/Volumes/Scratch` | `active` | `mounted-volume` | exists and is usable |
| `/Volumes/T7Recovery` | `active` | `mounted-volume` | exists and is usable |
| `/` | `read_only` | `mounted-volume` | exists but is not writable |
| `/Volumes/.timemachine` | `read_only` | `mounted-volume` | exists but is not writable |
| `/Volumes/Antigravity` | `read_only` | `mounted-volume` | exists but is not writable |
| `/Volumes/TM-Mac` | `read_only` | `mounted-volume` | exists but is not writable |
| `~/.claude/projects` | `full` | `prompt-default` | usage 95.4% above 95.0% ceiling |
| `~/.codex/history.jsonl` | `full` | `prompt-default` | usage 95.4% above 95.0% ceiling |
| `~/.codex/sessions` | `full` | `prompt-default` | usage 95.4% above 95.0% ceiling |
| `~/Workspace` | `full` | `repo-default`, `repo-default` | usage 95.4% above 95.0% ceiling |
| `~/Workspace/limen` | `full` | `repo-default` | usage 95.4% above 95.0% ceiling |
| `~/Workspace/limen/.limen-private/session-corpus` | `full` | `private-default` | usage 95.4% above 95.0% ceiling |

## Contract

- Configured roots are classified with receipts; stale or missing roots do not become global blockers by name.
- Raw prompt bodies and private indexes stay under `.limen-private/`.
