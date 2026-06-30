# Capacity Fill

Generated: `2026-06-30T00:36:00Z`

## Opencode Lens

- Status: `up`
- Capacity remaining: `99/100`
- Detail: `/opt/homebrew/bin/opencode`
- Dispatch-health status: `blocked`

## Capacity census

```text
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

- Refresh this receipt: `python3 scripts/capacity-fill-ledger.py --write`
- Check async proof: `python3 scripts/dispatch-health.py --write --probe-async`
- Verify async dispatch: `pytest -q cli/tests/test_async_dispatch.py`

## Human Gates

- No implicit gate changes are made by this script.

## Dispatch-Health Blockers

- `live-root-not-at-origin-main`: live root branch main head d6757d3d21fc differs from origin/main 9f7af24dcb75.
- `live-root-dirty`: live root has 2 dirty entries.
