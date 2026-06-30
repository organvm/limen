# Capacity Fill Ledger

Generated: `2026-06-30T03:17:03+00:00`

Status: `blocked`

## Agy lane

- Reachable: `False`
- Detail: `agy not found`
- Remaining: `95` / `100`
- Down reason: `agy unreachable: agy not found`

## Capacity snapshot

- Up lanes:
  - none

- Down lanes:
  - `agy`
  - `claude`
  - `codex`
  - `copilot`
  - `gemini`
  - `github_actions`
  - `jules`
  - `ollama`
  - `opencode`
  - `oz`
  - `warp`

## Focus

- If Agy remains `down` for multiple beats, run:
  - `python3 scripts/dispatch-health.py --write --probe-async`
  - `python3 scripts/capacity-fill-ledger.py --write`
  - and check manual entries in `logs/lanes-down.txt` if present.
