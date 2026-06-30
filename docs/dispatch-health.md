# Dispatch Health

Generated: `2026-06-30T01:42:48+00:00`

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
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-06-30T01:42:48.808382+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: would reap 0 dead ; would harvest 0 ; 0 still running ; would launch 5 (cap 12) -> ['CAPFILL-claude-20260629-09', 'CAPFILL-agy-20260629-25', 'CAPFILL-claude-20260629-10', 'CAPFILL-opencode-20260629-16', 'CAPFILL-gemini-20260629-09']`.

## Capacity Fill

- Capacity fill status: `blocked`.
- Productive means task-board spend/reservation. Attempts alone do not satisfy a lane's fill contract.

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active |
|---|---|---:|---:|---:|---:|---:|---:|
| `jules` | `underfilled` | 81 | 81 | 83 | 100 | 5 | 69 |
| `claude` | `no_work` | 0 | 4 | 10 | 15 | 0 | 4 |
| `opencode` | `underfilled` | 1 | 12 | 89 | 100 | 2 | 4 |
| `agy` | `blocked` | 5 | 19 | 89 | 100 | 0 | 0 |
| `gemini` | `unproductive` | 0 | 19 | 8 | 10 | 0 | 4 |
| `codex` | `depleted` | 16 | 15 | 67 | 100 | 0 | 6 |

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 17]`.
- HEAD: `7bc979226b817269bd0872312944a68b71b13a16`.
- origin/main: `7ecdd65a529802a581d173b4cb390d19bcb20e55`.
- Matches origin/main: `False`; ahead `25` behind `0`.
- Dirty entries: `2`.
  - `docs/capacity-fill.md`
  - `tasks.yaml`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 17]`.
- HEAD matches origin/main: `False`.

## Blockers

- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head 7bc979226b81 differs from origin/main 7ecdd65a5298.
- `live-root-dirty`: live root has 2 dirty entries.
- `lane-fill-jules`: jules: productive 81/83; attempts 81/83
- `lane-fill-claude`: claude: productive 0/10, but no open/any work is available
- `lane-fill-opencode`: opencode: productive 1/89; attempts 12/89
- `lane-fill-agy`: agy: lane is down by the live dispatch gate
- `lane-fill-gemini`: gemini: attempted 19/8, but productive board spend is 0/8

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
