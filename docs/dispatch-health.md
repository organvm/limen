# Dispatch Health

Generated: `2026-06-30T14:27:25+00:00`

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
- Watchdog dry-run healthy: `False`; `[watchdog] 2026-06-30T14:27:25.614440+00:00 UNHEALTHY sig=beating+daemon-up`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `False`; timed out `False`.
- Async dry-run summary: `PermissionError: [Errno 1] Operation not permitted: '/Users/4jp/Workspace/limen/logs/.queue.lock.d'`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629`.
- HEAD: `40c428549922b04a8cda05f5809a25c062c64500`.
- origin/main: `a55e45a04653ed9b3d92339a996f47ca8cca66cd`.
- Matches origin/main: `False`; ahead `27` behind `16`.
- Dirty entries: `24`.
  - `cli/src/limen/capacity.py`
  - `cli/src/limen/dispatch.py`
  - `cli/src/limen/io.py`
  - `cli/tests/test_async_dispatch.py`
  - `cli/tests/test_dispatch.py`
  - `cli/tests/test_dispatch_engine.py`
  - `cli/tests/test_substrate_repo_product_fanout.py`
  - `docs/capacity-fill.md`
  - `docs/current-session-fanout.md`
  - `docs/dispatch-health.md`
  - `institutio/governance/parameters.yaml`
  - `scripts/current-session-fanout.py`
  - `scripts/dispatch-async.py`
  - `scripts/heal-dispatch.py`
  - `scripts/heartbeat-loop.sh`
  - `scripts/verify-dispatch.py`
  - `tasks.yaml`
  - `agy_log.txt`
  - `agy_log_big.txt`
  - `docs/lane-checkups/agy/20260630-02.md`
  - `docs/lane-checkups/gemini/20260630-02.md`
  - `docs/lane-checkups/gemini/20260630-03.md`
  - `docs/lane-checkups/oz/`
  - `docs/lane-checkups/warp/`

## Verified Worktree

- Verified worktree: `~/Workspace/.limen-worktrees/capfill-opencode-20260630-03-7cee`.
- Branch: `limen/capfill-opencode-20260630-03-7cee`; status `## limen/capfill-opencode-20260630-03-7cee...origin/main [behind 1]`.
- HEAD matches origin/main: `False`.

## Blockers

- `heartbeat-watchdog-unhealthy`:   ok  not-wedged: {"reason": "no PARALLEL beats in window", "recent_pr_counts": [], "max_fails_threshold": 3}
- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head 40c428549922 differs from origin/main a55e45a04653.
- `live-root-dirty`: live root has 24 dirty entries.
- `async-dry-run-unhealthy`: PermissionError: [Errno 1] Operation not permitted: '/Users/4jp/Workspace/limen/logs/.queue.lock.d'

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
