# Corpus Command Center

Generated: `2026-06-29T21:35:01+00:00`

## Canonical Decision

- Prompts, replies, artifacts, tasks, Aug-1 state, and inbound positioning are one corpus surface.
- Raw bodies stay in `.limen-private/session-corpus/corpus-command-center/objects`; tracked output is redacted.
- The dashboard surfaces work candidates and pressure; it does not claim tasks or mutate `tasks.yaml`.

## Coverage

- Units indexed: `408766`.
- Unique hashes: `250706`.
- Clusters: `228966`.
- Side-by-side comparisons: `24`.
- Private body objects: `250706`.

## Kind Mix

| Kind | Units |
|---|---:|
| `tool` | 202567 |
| `response` | 99303 |
| `prompt` | 97863 |
| `system` | 4658 |
| `artifact` | 2875 |
| `task` | 1500 |

## Goal Panels

- Aug-1 gate: `false`; legs `0` / `5`; deadline `2026-08-01`.
- Acceptance panel: prompt packets `9` closed / `0` open; Aug-1 gate `false`; Aug-1 remains the operational checkpoint; late-August unemployment remains the hard runway premise.
- Outward reciprocity: `staged` 1.
- Inbound magnet: value repos `12`, seeded repos `9`, scraper model present `True`.

## Private Outputs

- Private index: `.limen-private/session-corpus/lifecycle/corpus-command-center.private.json`.
- Private local explorer: `.limen-private/session-corpus/lifecycle/corpus-command-center.private.html`.
- Public/redacted index: `.limen-private/session-corpus/lifecycle/corpus-command-center.public.json`.

## Commands

- Refresh the command center: `python3 scripts/corpus-command-center.py --write`
- Run the full local corpus intentionally: `python3 scripts/corpus-command-center.py --write --all-sessions`
- Refresh upstream ledgers first when needed: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/prompt-priority-map.py --write`
