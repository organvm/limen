# Corpus Command Center

Generated: `2026-06-29T17:35:46+00:00`

## Canonical Decision

- Prompts, replies, artifacts, tasks, Aug-1 state, and inbound positioning are one corpus surface.
- Raw bodies stay in `.limen-private/session-corpus/corpus-command-center/objects`; tracked output is redacted.
- The dashboard surfaces work candidates and pressure; it does not claim tasks or mutate `tasks.yaml`.

## Coverage

- Units indexed: `63827`.
- Unique hashes: `38153`.
- Clusters: `34852`.
- Side-by-side comparisons: `24`.
- Private body objects: `38153`.

## Kind Mix

| Kind | Units |
|---|---:|
| `tool` | 30246 |
| `prompt` | 16033 |
| `response` | 15083 |
| `task` | 1500 |
| `system` | 524 |
| `artifact` | 441 |

## Goal Panels

- Aug-1 gate: `false`; legs `0` / `5`; deadline `2026-08-01`.
- Inbound magnet: value repos `12`, seeded repos `9`, scraper model present `True`.

## Private Outputs

- Private index: `.limen-private/session-corpus/lifecycle/corpus-command-center.private.json`.
- Private local explorer: `.limen-private/session-corpus/lifecycle/corpus-command-center.private.html`.
- Public/redacted index: `.limen-private/session-corpus/lifecycle/corpus-command-center.public.json`.

## Commands

- Refresh the command center: `python3 scripts/corpus-command-center.py --write` (default `500`-session bounded snapshot).
- Run the full local corpus intentionally: `python3 scripts/corpus-command-center.py --write --all-sessions`
- Refresh upstream ledgers first when needed: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/prompt-priority-map.py --write`
