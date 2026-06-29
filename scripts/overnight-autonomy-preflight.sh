#!/usr/bin/env bash
# Refresh the receipts needed before any overnight autonomous Limen run.
# This script is intentionally dry-run only: it does not dispatch, edit tasks.yaml,
# change the autonomy policy, mutate GitHub, or touch credentials.
set -euo pipefail

ROOT="${LIMEN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export LIMEN_ROOT="$ROOT"
export LIMEN_TASKS="${LIMEN_TASKS:-$ROOT/tasks.yaml}"
export PYTHONPATH="$ROOT/cli/src${PYTHONPATH:+:$PYTHONPATH}"

cd "$ROOT"
mkdir -p logs

PREFLIGHT_LOG="${LIMEN_OVERNIGHT_PREFLIGHT_LOG:-logs/overnight-preflight.log}"
exec > >(tee -a "$PREFLIGHT_LOG") 2>&1

tasks_sha() {
  shasum -a 256 "$LIMEN_TASKS" | awk '{print $1}'
}

TASKS_SHA_BEFORE="$(tasks_sha)"

echo "== overnight autonomy preflight =="
echo "root: $LIMEN_ROOT"
echo "tasks: $LIMEN_TASKS"
echo "log: $PREFLIGHT_LOG"
date -u +"utc: %Y-%m-%dT%H:%M:%SZ"

python3 scripts/validate-task-board.py --tasks "$LIMEN_TASKS"
python3 scripts/usage-telemetry.py
python3 scripts/autonomy-governor.py explain

python3 scripts/session-lifecycle-pressure.py --write
python3 scripts/live-root-gate.py --write
python3 scripts/session-blockers-ledger.py --write
python3 scripts/session-attack-paths.py --write
python3 scripts/conductor-tranche.py --write

echo "== router plan =="
python3 scripts/route.py \
  --tasks "$LIMEN_TASKS" \
  --workdir "${LIMEN_WORKDIR:-$HOME/Workspace}" \
  | tee logs/overnight-route-plan.log

echo "== dispatch dry-run =="
python3 scripts/dispatch-parallel.py \
  --tasks "$LIMEN_TASKS" \
  --lanes "${LIMEN_OVERNIGHT_LANES:-github_actions,jules,claude,opencode,agy}" \
  --per-lane "${LIMEN_OVERNIGHT_PER_LANE:-1}" \
  --workers "${LIMEN_OVERNIGHT_WORKERS:-3}" \
  --dry-run \
  | tee logs/overnight-dispatch-dry-run.log

TASKS_SHA_AFTER="$(tasks_sha)"
if [[ "$TASKS_SHA_BEFORE" != "$TASKS_SHA_AFTER" ]]; then
  echo "ERROR: dry-run preflight changed $LIMEN_TASKS" >&2
  exit 1
fi

echo "== done =="
echo "tasks.yaml unchanged: $TASKS_SHA_AFTER"
echo "Review docs/overnight-autonomy.md before enabling dispatch."
