# Live Root Gate

Generated: `2026-06-29T03:16:10+00:00`

Status: `blocked`

## Rule

- This is an operator gate for the live Limen checkout and heartbeat LaunchAgent.
- It does not switch branches, reset, stash, commit, edit tasks.yaml, or reload launchd.
- Treat tasks.yaml as daemon-owned live state; preserve it before release convergence.

## Gate State

- Operator gate required: `True`.
- Release reconcile allowed without human: `False`.
- Launchd reload allowed without human: `False`.
- Blocking gates: `live-root-not-release-branch`, `live-root-not-at-release`, `live-root-unique-commits`, `live-root-dirty`, `live-root-task-board-dirty`.

## Live Root

- Path: `~/Workspace/limen`.
- Branch: `feature/ORG-artist-organ-face-0628`; release branch `main`.
- HEAD: `838af6a9468d406c79c5a4cf5976bbf64bfa9dbe`.
- Release head: `a6fcb51ffd9d4c1ffb0f165c6b76bf6b564fddbe`.
- Matches release: `False`; ahead `3` behind `17`.
- Unique local commits: `3`; patch-equivalent commits: `0`.
- Dirty entries: `2`.

### Local Commits

- `838af6a capture: autonomic off-disk sync 2026-06-29T01:55:56Z`
- `f347c4d feat(artist): polish macro + micro face for A-MAVS-OLEVM`
- `84a3288 feat(artist): author KERNEL and CHARTER for A-MAVS-OLEVM`

### Dirty Paths

- `ianva/scripts/ianva-serve.sh`
- `tasks.yaml`

## Heartbeat

- Plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Loaded launchd state: `running` pid `1656`.
- Loaded env matches plist for tracked LIMEN_* keys.

## Verified Worktree

- Path: `~/Workspace/limen-network-substrate-20260628`.
- Branch: `codex/network-substrate-healing-20260628`.
- Matches release: `False`.

## Stop Conditions

- Stop before `git reset`, branch switch, stash drop, task-board write, launchd bootout/bootstrap/kickstart, or async enablement.
- Stop if `git cherry origin/main HEAD` reports any `+` commits until the operator decides whether to preserve, cherry-pick, or abandon them.
- Stop if `tasks.yaml` is dirty until the daemon-owned queue has been explicitly preserved.
- Stop if heartbeat has live child work; reload only between beats.

## Human-Gated Command Packet

Run these only after operator approval, in order, stopping on any mismatch:

```bash
LIVE_ROOT='/Users/4jp/Workspace/limen'
HEARTBEAT_LABEL='com.limen.heartbeat'
git -C "$LIVE_ROOT" status --branch --short
git -C "$LIVE_ROOT" cherry origin/main HEAD
git -C "$LIVE_ROOT" diff --name-status
git -C "$LIVE_ROOT" ls-files --others --exclude-standard
python3 scripts/dispatch-health.py --write --probe-async
python3 scripts/live-root-gate.py --write
# After preserving or intentionally discarding live-root-only state:
# launchctl kickstart -k "gui/$(id -u)/$HEARTBEAT_LABEL"
# Then require dispatch-health status healthy before enabling async.
```

## Refresh Commands

- Refresh this gate: `python3 scripts/live-root-gate.py --write`
- Refresh with remote tracking update: `python3 scripts/live-root-gate.py --write --fetch`
- Refresh dispatch health: `python3 scripts/dispatch-health.py --write --probe-async`
- Verify watchdog: `python3 scripts/watchdog.py --dry-run`
