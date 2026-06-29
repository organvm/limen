# Overnight Autonomy Runbook

Generated for the night of Sunday, 2026-06-28 EDT into Monday, 2026-06-29 UTC.

## Active Goal

`/goal`: Prepare the Limen network-substrate project for overnight autonomous work by verifying the current gates, selecting only bounded safe lanes, preserving dry-run receipts, and stopping before queue, credential, GitHub, live-root, or spend mutations unless a human opens those gates explicitly.

## Current Decision

Default mode tonight is observe-mode maintenance, not live spend or broad dispatch.

Reasons:

- Verified preflight at `2026-06-29T03:16:03Z` reported this checkout's governor as `mode: observe`, `dispatchAllowed: false`, and `dispatchReason: autonomy mode is observe`.
- `docs/conductor-tranche.md` selects `tranche-no-autonomous-actionable-path`.
- `docs/session-attack-paths.md` ranks all current paths as human-gated or parked.
- `docs/live-root-gate.md` says the live Limen root is blocked and requires an operator gate before branch reconcile, task-board writes, launchd reload, or async enablement.
- Router dry-run found reachable lanes `jules`, `github_actions`, `agy`, `opencode`, `claude`, and `codex`; unavailable lanes were `gemini`, `ollama`, `copilot`, `warp`, and `oz`.
- Router dry-run would re-route `79` open items if `--apply` were used, but the safe preflight does not apply that plan.
- Dispatch dry-run against the current board would dispatch `1` task, `GEN-a-organvm-my-knowledge-base-ci-green-0620`, on `github_actions`.

## Preflight

Run:

```bash
LIMEN_ROOT="$PWD" LIMEN_TASKS="$PWD/tasks.yaml" bash scripts/overnight-autonomy-preflight.sh
```

This refreshes receipts and writes:

- `docs/live-root-gate.md`
- `docs/session-lifecycle-blockers.md`
- `docs/session-attack-paths.md`
- `docs/conductor-tranche.md`
- `logs/session-lifecycle-pressure.md`
- `logs/overnight-preflight.log`
- `logs/overnight-route-plan.log`
- `logs/overnight-dispatch-dry-run.log`

It does not dispatch, change autonomy policy, edit `tasks.yaml`, mutate GitHub, or touch credentials. It also checks the `tasks.yaml` SHA before and after the run and exits nonzero if the dry-run path changes it.

For observe-only overnight monitoring, run the preflight loop from this checkout:

```bash
while true; do
  LIMEN_ROOT="$PWD" LIMEN_TASKS="$PWD/tasks.yaml" bash scripts/overnight-autonomy-preflight.sh
  sleep "${LIMEN_OVERNIGHT_OBSERVE_SLEEP:-1800}"
done
```

This loop is receipt refresh only. It is not a dispatcher.

## Allowed Overnight Work Without A Spend Gate

- Refresh lifecycle receipts.
- Refresh live-root and blocker gates.
- Refresh route and dispatch dry-runs.
- Keep the heartbeat in observe mode.
- Preserve logs and receipts for morning review.
- Keep `tasks.yaml` byte-identical during preflight.

Stop before:

- `tasks.yaml` mutation.
- `git push`.
- GitHub rename, transfer, close, merge, or App install.
- Credential writes.
- Local worktree deletion/reclaim.
- Broad queue dispatch.
- Starting a second heartbeat writer against the same task board while the live LaunchAgent is still running.

## Live Dispatch Gate

Only use this if a human explicitly opens the spend gate for the night.

First satisfy the single-writer gate:

- Review `docs/live-root-gate.md`.
- Preserve or intentionally resolve the dirty live root state in `/Users/4jp/Workspace/limen`.
- Ensure only one process writes the selected `tasks.yaml`.
- Do not bootout, bootstrap, kickstart, branch-switch, reset, stash-drop, or enable async without the live-root operator gate.

1. Re-route the open queue to reachable lanes:

```bash
LIMEN_ROOT="$PWD" LIMEN_TASKS="$PWD/tasks.yaml" python3 scripts/route.py --tasks tasks.yaml --apply
```

2. Enable dispatch policy in the same checkout that will own the single writer:

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("logs/autonomy-policy.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({
    "mode": "dispatch",
    "dispatch_enabled": True,
    "reason": "Explicit overnight operator gate for 2026-06-28 EDT, capped lanes and per-lane limit."
}, indent=2) + "\n")
PY
```

3. Start capped live dispatch:

```bash
LIMEN_ROOT="$PWD" \
LIMEN_TASKS="$PWD/tasks.yaml" \
LIMEN_LANES="github_actions,claude,opencode,agy" \
LIMEN_LOCAL_LIMIT=1 \
LIMEN_WORKERS=3 \
LIMEN_LOOP_MIN=600 \
LIMEN_LOOP_MAX=1800 \
bash scripts/heartbeat-loop.sh
```

Live dispatch remains blocked by this checkout's governor unless step 2 is done. `heartbeat-loop.sh` appends `jules` to `LIMEN_LANES` internally. If the live LaunchAgent in `/Users/4jp/Workspace/limen` remains active, run live dispatch there instead of starting a second writer here.

## Monitoring

Use:

```bash
LIMEN_ROOT="$PWD" python3 scripts/autonomy-governor.py explain
LIMEN_ROOT="$PWD" LIMEN_TASKS="$PWD/tasks.yaml" python3 scripts/board.py
tail -n 80 logs/overnight-preflight.log
tail -n 80 logs/overnight-dispatch-dry-run.log
tail -n 80 logs/heartbeat.out.log
```

Watch for:

- `dispatchAllowed: false` when live dispatch was expected.
- Down lanes in the capacity census.
- Repeated authentication or browser-login failures.
- No dispatched tasks after route apply.
- Any task-state change without a matching `dispatch_log` entry.
- `ERROR: dry-run preflight changed ...` from the checksum guard.

## Rollback

Return to observe mode:

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("logs/autonomy-policy.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({
    "mode": "observe",
    "dispatch_enabled": False,
    "reason": "Overnight dispatch closed; observe only."
}, indent=2) + "\n")
PY
```

If the heartbeat was started manually, stop that shell with `Ctrl-C`.

If launchd was used, inspect before changing it:

```bash
launchctl print "gui/$(id -u)/com.limen.heartbeat"
```

Do not unload or kickstart launchd during rollback unless the live-root gate has been reviewed and the operator explicitly opened that gate.
