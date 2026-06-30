# Dispatch Health

Generated: `2026-06-30T01:23:43+00:00`

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
- Loaded launchd state: `running` pid `59116`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `0`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-06-30T01:23:44.243278+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: would reap 0 dead ; would harvest 0 ; 0 still running ; would launch 1 (cap 12) -> ['CAPFILL-gemini-20260629-09']`.

## Capacity Fill

- Capacity fill status: `blocked`.
- Productive means task-board spend/reservation. Attempts alone do not satisfy a lane's fill contract.

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active |
|---|---|---:|---:|---:|---:|---:|---:|
| `jules` | `underfilled` | 77 | 77 | 81 | 100 | 1 | 69 |
| `claude` | `blocked` | 0 | 0 | 9 | 15 | 0 | 0 |
| `opencode` | `no_work` | 1 | 9 | 86 | 100 | 0 | 3 |
| `agy` | `blocked` | 5 | 19 | 86 | 100 | 18 | 0 |
| `gemini` | `unproductive` | 0 | 15 | 8 | 10 | 0 | 7 |
| `codex` | `depleted` | 15 | 10 | 59 | 100 | 0 | 1 |

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 15]`.
- HEAD: `3035140c1deab43a665eb2905a5e272cb3d16044`.
- origin/main: `7ecdd65a529802a581d173b4cb390d19bcb20e55`.
- Matches origin/main: `False`; ahead `23` behind `0`.
- Dirty entries: `17`.
  - `cli/src/limen/dispatch.py`
  - `cli/tests/test_async_dispatch.py`
  - `cli/tests/test_dispatch_engine.py`
  - `cli/tests/test_generate_capacity_fill.py`
  - `cli/tests/test_rebalance.py`
  - `cli/tests/test_usage_gate.py`
  - `docs/capacity-fill.md`
  - `docs/consolidation/GATES.md`
  - `docs/dispatch-health.md`
  - `docs/live-root-gate.md`
  - `ianva/scripts/ianva-serve.sh`
  - `scripts/dispatch-async.py`
  - `scripts/generate-capacity-fill.py`
  - `tasks.yaml`
  - `docs/lane-checkups/`
  - `scripts/photos-universe-bootstrap.sh`
  - `tasks.yaml.bak`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 15]`.
- HEAD matches origin/main: `False`.

## Blockers

- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head 3035140c1dea differs from origin/main 7ecdd65a5298.
- `live-root-dirty`: live root has 17 dirty entries.
- `lane-fill-jules`: jules: productive 77/81; attempts 77/81
- `lane-fill-claude`: claude: lane is down by the live dispatch gate
- `lane-fill-opencode`: opencode: productive 1/86, but no open/any work is available
- `lane-fill-agy`: agy: lane is down by the live dispatch gate
- `lane-fill-gemini`: gemini: attempted 15/8, but productive board spend is 0/8

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
