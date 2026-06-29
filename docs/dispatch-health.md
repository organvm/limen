# Dispatch Health

Generated: `2026-06-29T22:15:31+00:00`

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
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-06-29T22:15:31.254563+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 0 ; 0 still running ; would launch 12 (cap 12) -> ['CAPFILL-opencode-20260629-01', 'CAPFILL-opencode-20260629-02', 'CAPFILL-opencode-20260629-03', 'CAPFILL-agy-20260629-01', 'CAPFILL-agy-20260629-02', 'CAPFILL-agy-20260629-03', 'CAPFILL-claude-20260629-01', 'CAPFILL-claude-20260629-02', 'CAPFILL-claude-20260629-03', 'CAPFILL-gemini-20260629-01', 'CAPFILL-gemini-20260629-02', 'CAPFILL-gemini-20260629-03']`.

## Capacity Fill

- Capacity fill status: `blocked`.
- Productive means task-board spend/reservation. Attempts alone do not satisfy a lane's fill contract.

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active |
|---|---|---:|---:|---:|---:|---:|---:|
| `jules` | `underfilled` | 51 | 51 | 68 | 100 | 15 | 44 |
| `claude` | `underfilled` | 0 | 5 | 15 | 15 | 15 | 0 |
| `opencode` | `underfilled` | 1 | 10 | 100 | 100 | 15 | 1 |
| `agy` | `underfilled` | 5 | 11 | 100 | 100 | 15 | 0 |
| `gemini` | `blocked` | 0 | 5 | 7 | 10 | 7 | 0 |
| `codex` | `depleted` | 1 | 17 | 100 | 100 | 0 | 0 |

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 2]`.
- HEAD: `e61656ef2a15fab12ed7500f80559b59c92325f0`.
- origin/main: `7ecdd65a529802a581d173b4cb390d19bcb20e55`.
- Matches origin/main: `False`; ahead `10` behind `0`.
- Dirty entries: `17`.
  - `cli/src/limen/capacity.py`
  - `docs/corpus-command-center.md`
  - `docs/dispatch-health.md`
  - `docs/prompt-acceptance-ledger.md`
  - `docs/prompt-batch-review-ledger.md`
  - `docs/prompt-lifecycle-ledger.md`
  - `docs/prompt-packet-ledger.md`
  - `docs/prompt-priority-map.md`
  - `scripts/dispatch-health.py`
  - `scripts/heartbeat-loop.sh`
  - `scripts/verify-whole.sh`
  - `tasks.yaml`
  - `cli/tests/test_capacity_fill.py`
  - `cli/tests/test_generate_capacity_fill.py`
  - `docs/capacity-fill.md`
  - `scripts/capacity-fill-ledger.py`
  - `scripts/generate-capacity-fill.py`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 2]`.
- HEAD matches origin/main: `False`.

## Blockers

- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head e61656ef2a15 differs from origin/main 7ecdd65a5298.
- `live-root-dirty`: live root has 17 dirty entries.
- `lane-fill-jules`: jules: productive 51/68; attempts 51/68
- `lane-fill-claude`: claude: productive 0/15; attempts 5/15
- `lane-fill-opencode`: opencode: productive 1/100; attempts 10/100
- `lane-fill-agy`: agy: productive 5/100; attempts 11/100
- `lane-fill-gemini`: gemini: productive 0/7, but the lane is not reachable

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
