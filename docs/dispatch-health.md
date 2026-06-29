# Dispatch Health

Generated: `2026-06-29T03:28:08+00:00`

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
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-06-29T03:28:08.871460+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 0 ; 0 still running ; would launch 0 (cap 12) -> []`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `feature/ORG-artist-organ-face-0628`; status `## feature/ORG-artist-organ-face-0628...origin/feature/ORG-artist-organ-face-0628`.
- HEAD: `838af6a9468d406c79c5a4cf5976bbf64bfa9dbe`.
- origin/main: `a6fcb51ffd9d4c1ffb0f165c6b76bf6b564fddbe`.
- Matches origin/main: `False`; ahead `3` behind `17`.
- Dirty entries: `4`.
  - `ianva/scripts/ianva-serve.sh`
  - `institutio/governance/parameters.yaml`
  - `scripts/route.py`
  - `tasks.yaml`

## Verified Worktree

- Verified worktree: `~/Workspace/limen-main-trench-20260628`.
- Branch: `codex/limen-main-trench-20260628`; status `## codex/limen-main-trench-20260628...origin/codex/limen-main-trench-20260628`.
- HEAD matches origin/main: `False`.

## Blockers

- `live-root-not-at-origin-main`: live root branch feature/ORG-artist-organ-face-0628 head 838af6a9468d differs from origin/main a6fcb51ffd9d.
- `live-root-dirty`: live root has 4 dirty entries.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
