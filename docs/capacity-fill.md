# Capacity Fill Ledger

Generated: `2026-06-30T01:12:31+00:00`
Packet: `20260629-16`

## Scope

- target lane: `agy`
- objective: close one lane-fill gap check for Agy productivity

## Capacity Census

| lane | state | remaining | limit | detail |
|---|---|---|---|---|
| codex | up | 99 | 100 | /opt/homebrew/bin/codex |
| claude | up | 100 | 100 | /Users/4jp/.local/bin/claude |
| opencode | up | 99 | 100 | /opt/homebrew/bin/opencode |
| agy | up | 95 | 100 | /opt/homebrew/bin/agy |
| gemini | down | 10 | 10 | gemini auth not configured |
| ollama | down | 543 | 600 | /usr/local/bin/ollama; no model pulled ? run `ollama pull qwen2.5-coder:7b` to light the floor lane |
| jules | up | 50 | 100 | /opt/homebrew/bin/jules |
| copilot | down | 543 | 600 | /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent) |
| warp | down | 543 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| oz | down | 543 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| github_actions | up | 543 | 600 | /opt/homebrew/bin/gh; workflow=limen-agent.yml |

## Down Lanes

agy, antigravity

## Commands

- `python3 scripts/dispatch-health.py --write --probe-async`
- `python3 scripts/capacity-fill-ledger.py --write`

