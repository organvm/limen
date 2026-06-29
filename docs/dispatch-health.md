# Dispatch Health

Generated: `2026-06-29T22:43:46+00:00`

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
- Watchdog dry-run healthy: `False`; `[watchdog] 2026-06-29T22:43:49.847113+00:00 UNHEALTHY sig=beating+daemon-up`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 0 ; 0 still running ; would launch 9 (cap 12) -> ['CAPFILL-opencode-20260629-08', 'CAPFILL-agy-20260629-11', 'CAPFILL-agy-20260629-13', 'CAPFILL-opencode-20260629-09', 'CAPFILL-opencode-20260629-12', 'CAPFILL-opencode-20260629-14', 'CAPFILL-jules-20260629-04', 'CAPFILL-jules-20260629-05', 'CAPFILL-jules-20260629-06']`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 5]`.
- HEAD: `893b1f93eef06219bcea8ebfa73760954e478f1b`.
- origin/main: `7ecdd65a529802a581d173b4cb390d19bcb20e55`.
- Matches origin/main: `False`; ahead `13` behind `0`.
- Dirty entries: `10`.
  - `cli/src/limen/dispatch.py`
  - `docs/capacity-fill.md`
  - `docs/consolidation/GATES.md`
  - `docs/dispatch-health.md`
  - `docs/live-root-gate.md`
  - `docs/worktree-preservation-receipts.json`
  - `tasks.yaml`
  - `docs/lane-checkups/`
  - `output.txt`
  - `photos-universe-bootstrap.sh`

## Verified Worktree

- Verified worktree: `~/Workspace/.limen-worktrees/capfill-claude-20260629-01-278a`.
- Branch: `limen/capfill-claude-20260629-01-278a`; status `## limen/capfill-claude-20260629-01-278a...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `heartbeat-watchdog-unhealthy`:   ok  not-wedged: {"reason": "no PARALLEL beats in window", "recent_pr_counts": [], "max_fails_threshold": 3}
- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head 893b1f93eef0 differs from origin/main 7ecdd65a5298.
- `live-root-dirty`: live root has 10 dirty entries.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
