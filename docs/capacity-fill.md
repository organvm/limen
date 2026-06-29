# Capacity Fill Ledger

Generated: `2026-06-29T23:45:46Z`
Dispatch health status: `blocked`

## Summary
- up: codex, claude, opencode, agy, gemini, jules, github_actions
- down: ollama, copilot, warp, oz

## OpenCode slot
- reachable: yes
- remaining: 99/100
- detail: /opt/homebrew/bin/opencode

## Capacity census
```
-- capacity census
  up   codex          local-cli      remaining=99/100 - /opt/homebrew/bin/codex
  up   claude         local-cli      remaining=100/100 - /Users/4jp/.local/bin/claude
  up   opencode       local-cli      remaining=99/100 - /opt/homebrew/bin/opencode
  up   agy            local-cli      remaining=95/100 - /opt/homebrew/bin/agy
  up   gemini         local-cli      remaining=10/10 - /opt/homebrew/bin/gemini
  down ollama         local-cli      remaining=543/600 - /usr/local/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane
  up   jules          cloud-cli      remaining=50/100 - /opt/homebrew/bin/jules
  down copilot        github-issue   remaining=543/600 - /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent)
  down warp           paid-service   remaining=543/600 - WARP_API_KEY not set (set env var + add as org/repo Actions secret)
  down oz             paid-service   remaining=543/600 - WARP_API_KEY not set (set env var + add as org/repo Actions secret)
  up   github_actions github-actions remaining=543/600 - /opt/homebrew/bin/gh; workflow=limen-agent.yml
```

## Commands
- Re-run this ledger: `python3 scripts/capacity-fill-ledger.py --write`
- Re-check routing pressure: `PYTHONPATH=cli/src python3 scripts/route.py --tasks tasks.yaml`
