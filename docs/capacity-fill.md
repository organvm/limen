# Capacity Fill Ledger

Generated: `2026-06-29T23:47:11+00:00`

Status: `healthy`

## Agy lane

- Reachable: `True`
- Detail: `/opt/homebrew/bin/agy`
- Remaining: `95` / `100`
- Down reason: `none`

## Capacity snapshot

- Up lanes:
  - `agy`
  - `claude`
  - `codex`
  - `gemini`
  - `github_actions`
  - `jules`
  - `opencode`

- Down lanes:
  - `copilot`
  - `ollama`
  - `oz`
  - `warp`

## Focus

- If Agy remains `down` for multiple beats, run:
  - `python3 scripts/dispatch-health.py --write --probe-async`
  - `python3 scripts/capacity-fill-ledger.py --write`
  - and check manual entries in `logs/lanes-down.txt` if present.
