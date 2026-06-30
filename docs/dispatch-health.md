# Dispatch Health

Generated: `2026-06-30T10:32:44+00:00`

Status: `blocked`

## Incident Class

- Dispatch/heartbeat health is not proven by tests in a detached worktree alone.
- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.
- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.

## Heartbeat

- LaunchAgent plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Plist KeepAlive: `True`; RunAtLoad: `True`.
- Plist LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Plist LIMEN_DISPATCH_ASYNC: `0`.
- Loaded launchd state: `running` pid `92588`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `0`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-06-30T10:32:44.238232+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: would reap 0 dead ; would harvest 0 ; 0 still running ; would launch 6 (cap 12) -> ['GEN-organvm-fetch-familiar-friends-test-coverage-0620', 'GEN-organvm-classroom-rpg-aetheria-test-coverage-0620', 'GEN-organvm-dot-github--poiesis-test-coverage-0620', 'GEN-a-organvm-the-actual-news-ci-green-0620', 'GEN-a-organvm-example-theatre-dialogue-ci-green-0620', 'GEN-meta-organvm-_agent-health-ci-green-0620']`.

## Fleet Classification

| Lane | Kind | Status | Detail |
|---|---|---|---|
| `codex` | `local-cli` | `active` | /opt/homebrew/bin/codex |
| `claude` | `local-cli` | `down` | live dispatch gate marked lane down; /Users/4jp/.local/bin/claude |
| `opencode` | `local-cli` | `active` | /opt/homebrew/bin/opencode |
| `agy` | `local-cli` | `active` | /opt/homebrew/bin/agy |
| `gemini` | `local-cli` | `active` | /opt/homebrew/bin/gemini |
| `ollama` | `local-cli` | `human-gated` | /usr/local/bin/ollama; no model pulled - run `ollama pull qwen2.5-coder:7b` to light the floor lane |
| `jules` | `cloud-cli` | `active` | /opt/homebrew/bin/jules |
| `copilot` | `github-issue` | `human-gated` | /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent) |
| `warp` | `paid-service` | `human-gated` | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `oz` | `paid-service` | `human-gated` | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `github_actions` | `github-actions` | `active` | /opt/homebrew/bin/gh; workflow=limen-agent.yml |

## Capacity Fill

- Capacity fill status: `blocked`.
- Productive means task-board spend/reservation. Attempts alone do not satisfy a lane's fill contract.

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active |
|---|---|---:|---:|---:|---:|---:|---:|
| `codex` | `no_work` | 0 | 29 | 34 | 100 | 0 | 0 |
| `claude` | `blocked` | 0 | 17 | 5 | 15 | 1 | 0 |
| `opencode` | `unproductive` | 0 | 40 | 32 | 100 | 0 | 1 |
| `agy` | `unproductive` | 0 | 42 | 32 | 100 | 0 | 0 |
| `gemini` | `unproductive` | 0 | 46 | 2 | 10 | 0 | 0 |
| `ollama` | `blocked` | 0 | 0 | 1 | 1 | 0 | 0 |
| `jules` | `healthy` | 73 | 92 | 18 | 100 | 28 | 73 |
| `copilot` | `blocked` | 0 | 0 | 1 | 1 | 0 | 0 |
| `warp` | `blocked` | 0 | 0 | 1 | 1 | 0 | 0 |
| `oz` | `blocked` | 0 | 0 | 1 | 1 | 0 | 0 |
| `github_actions` | `underfilled` | 0 | 0 | 1 | 1 | 31 | 0 |

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 18]`.
- HEAD: `23cda6ea3deef8065b6e3b2e6c490454bdcd2043`.
- origin/main: `7ecdd65a529802a581d173b4cb390d19bcb20e55`.
- Matches origin/main: `False`; ahead `26` behind `0`.
- Dirty entries: `33`.
  - `.coverage`
  - `AGENTS.md`
  - `cli/src/limen/capacity.py`
  - `cli/src/limen/dispatch.py`
  - `cli/tests/test_async_dispatch.py`
  - `cli/tests/test_dispatch.py`
  - `cli/tests/test_generate_capacity_fill.py`
  - `cli/tests/test_session_lifecycle_pressure.py`
  - `container/launchd/com.limen.heartbeat.plist`
  - `docs/DISPATCH-ARCHITECTURE.md`
  - `docs/capacity-fill.md`
  - `docs/dispatch-health.md`
  - `docs/lane-checkups/agy/20260629-23.md`
  - `mcp/src/limen_mcp/server.py`
  - `scripts/conductor-tranche.py`
  - `scripts/dispatch-async.py`
  - `scripts/dispatch-health.py`
  - `scripts/dispatch-parallel.py`
  - `scripts/gen-launchd-plist.sh`
  - `scripts/generate-capacity-fill.py`
  - `scripts/heartbeat-loop.sh`
  - `scripts/heartbeat.sh`
  - `scripts/route.py`
  - `scripts/saturate.sh`
  - `tasks.yaml`
  - `web/api/main.py`
  - `web/worker/src/index.js`
  - `cli/tests/test_session_blockers_ledger.py`
  - `docs/lane-checkups/agy/20260629-24.md`
  - `scripts/full-fleet-lanes.py`
  - `<truncated>`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 18]`.
- HEAD matches origin/main: `False`.

## Blockers

- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head 23cda6ea3dee differs from origin/main 7ecdd65a5298.
- `live-root-dirty`: live root has 33 dirty entries.
- `lane-fill-codex`: codex: productive 0/34, but no open/any work is available
- `lane-fill-claude`: claude: lane is down by the live dispatch gate
- `lane-fill-opencode`: opencode: attempted 40/32, but productive board spend is 0/32
- `lane-fill-agy`: agy: attempted 42/32, but productive board spend is 0/32
- `lane-fill-gemini`: gemini: attempted 46/2, but productive board spend is 0/2
- `lane-fill-ollama`: ollama: productive 0/1, but the lane is not reachable
- `lane-fill-copilot`: copilot: productive 0/1, but the lane is not reachable
- `lane-fill-warp`: warp: productive 0/1, but the lane is not reachable
- `lane-fill-oz`: oz: productive 0/1, but the lane is not reachable
- `lane-fill-github_actions`: github_actions: productive 0/1; attempts 0/1

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 12 --dry-run`
