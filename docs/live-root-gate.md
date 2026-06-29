# Live Root Gate

Generated: `2026-06-29T22:18:14+00:00`

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
- Branch: `work/workstream-agent-launcher-20260629`; release branch `main`.
- HEAD: `e61656ef2a15fab12ed7500f80559b59c92325f0`.
- Release head: `7ecdd65a529802a581d173b4cb390d19bcb20e55`.
- Matches release: `False`; ahead `10` behind `0`.
- Unique local commits: `10`; patch-equivalent commits: `0`.
- Dirty entries: `21`.

### Local Commits

- `e61656e limen: add prompt acceptance checkpoint`
- `78f7de9 limen: preserve august pipeline acceptance packet`
- `61c8071 limen: refresh corpus command center snapshot`
- `65b6d23 limen: sync live task board state`
- `5252041 limen: add corpus command center`
- `e7bf044 limen: mark mirror mirror receipt merged`
- `e18b858 limen: refresh invisible ledger preservation receipt`
- `0795e13 limen: record worktree preservation receipts`
- `99dd302 limen: preserve live task board state`
- `3cd1507 limen: add agent-selectable workstream launcher`

### Dirty Paths

- `cli/src/limen/capacity.py`
- `docs/DISPATCH-ARCHITECTURE.md`
- `docs/conductor-tranche.md`
- `docs/corpus-command-center.md`
- `docs/dispatch-health.md`
- `docs/prompt-acceptance-ledger.md`
- `docs/prompt-batch-review-ledger.md`
- `docs/prompt-lifecycle-ledger.md`
- `docs/prompt-packet-ledger.md`
- `docs/prompt-priority-map.md`
- `docs/session-attack-paths.md`
- `docs/session-lifecycle-blockers.md`
- `scripts/dispatch-health.py`
- `scripts/heartbeat-loop.sh`
- `scripts/verify-whole.sh`
- `tasks.yaml`
- `cli/tests/test_capacity_fill.py`
- `cli/tests/test_generate_capacity_fill.py`
- `docs/capacity-fill.md`
- `scripts/capacity-fill-ledger.py`
- `scripts/generate-capacity-fill.py`

## Heartbeat

- Plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Loaded launchd state: `running` pid `1656`.
- Loaded env matches plist for tracked LIMEN_* keys.

## Verified Worktree

- Path: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`.
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
