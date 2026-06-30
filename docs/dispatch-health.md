# Dispatch Health

Generated: `2026-06-29T23:15:16+00:00`

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
- Loaded launchd state: `running` pid `1656`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `0`.
- Watchdog dry-run healthy: `False`; `[watchdog] 2026-06-29T23:15:16.928156+00:00 UNHEALTHY sig=beating+daemon-up`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `False`; timed out `False`.
- Async dry-run summary: `PermissionError: [Errno 1] Operation not permitted: '/Users/4jp/Workspace/limen/logs/.queue.lock.d'`.

## Capacity Fill

- Capacity fill status: `blocked`.
- Productive means task-board spend/reservation. Attempts alone do not satisfy a lane's fill contract.

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active |
|---|---|---:|---:|---:|---:|---:|---:|
| `jules` | `no_work` | 50 | 48 | 72 | 100 | 0 | 46 |
| `claude` | `no_work` | 0 | 5 | 8 | 15 | 0 | 0 |
| `opencode` | `no_work` | 1 | 6 | 72 | 100 | 0 | 1 |
| `agy` | `blocked` | 5 | 6 | 72 | 100 | 0 | 0 |
| `gemini` | `no_work` | 0 | 5 | 7 | 10 | 0 | 0 |
| `codex` | `no_work` | 1 | 15 | 51 | 100 | 0 | 0 |

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 10]`.
- HEAD: `59b124f70b8694525d3100c87fe725b0d56276b9`.
- origin/main: `7ecdd65a529802a581d173b4cb390d19bcb20e55`.
- Matches origin/main: `False`; ahead `18` behind `0`.
- Dirty entries: `19`.
  - `cli/src/limen/dispatch.py`
  - `cli/tests/test_dispatch_engine.py`
  - `cli/tests/test_rebalance.py`
  - `cli/tests/test_usage_gate.py`
  - `docs/capacity-fill.md`
  - `docs/conductor-tranche.md`
  - `docs/consolidation/GATES.md`
  - `docs/dispatch-health.md`
  - `docs/live-root-gate.md`
  - `docs/session-attack-paths.md`
  - `docs/session-lifecycle-blockers.md`
  - `docs/worktree-lifecycle-ledger.md`
  - `docs/worktree-preservation-receipts.json`
  - `scripts/generate-capacity-fill.py`
  - `tasks.yaml`
  - `docs/lane-checkups/`
  - `output.txt`
  - `photos-universe-bootstrap.sh`
  - `test.txt`

## Verified Worktree

- Verified worktree: `~/Workspace/.limen-worktrees/capfill-agy-20260629-11-a3b7`.
- Branch: `limen/capfill-agy-20260629-11-a3b7`; status `## limen/capfill-agy-20260629-11-a3b7...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `heartbeat-watchdog-unhealthy`:   ok  not-wedged: {"reason": "no PARALLEL beats in window", "recent_pr_counts": [], "max_fails_threshold": 3}
- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head 59b124f70b86 differs from origin/main 7ecdd65a5298.
- `live-root-dirty`: live root has 19 dirty entries.
- `async-dry-run-unhealthy`: PermissionError: [Errno 1] Operation not permitted: '/Users/4jp/Workspace/limen/logs/.queue.lock.d'
- `lane-fill-jules`: jules: productive 50/72, but no open/any work is available
- `lane-fill-claude`: claude: productive 0/8, but no open/any work is available
- `lane-fill-opencode`: opencode: productive 1/72, but no open/any work is available
- `lane-fill-agy`: agy: lane is down by the live dispatch gate
- `lane-fill-gemini`: gemini: productive 0/7, but no open/any work is available
- `lane-fill-codex`: codex: productive 1/51, but no open/any work is available

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
