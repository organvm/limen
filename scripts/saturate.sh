#!/usr/bin/env bash
# saturate.sh — use ALL available multi-vendor capacity in one safe pass.
#
#   route open work across every reachable paid lane -> release stale claims ->
#   dispatch each paid lane.
#
# SEQUENTIAL by design: tasks.yaml is the single source of truth and the dispatcher
# is NOT concurrency-safe on it, so lanes run one after another (never racing the
# file). A flock guard makes this safe to also run from launchd/cron without overlap.
#
# Every local dispatch is worktree-isolated -> produces a reviewable PR, never touches
# a live checkout. Knobs: LIMEN_LOCAL_LIMIT (50) LIMEN_JULES_LIMIT (100)
# LIMEN_LANES defaults to the complete paid fleet.
set -uo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
export LIMEN_WORKDIR="${LIMEN_WORKDIR:-$HOME/Workspace}"
export LIMEN_ISOLATION="${LIMEN_ISOLATION:-worktree}"
export PYTHONPATH="$LIMEN_ROOT/cli/src"
export GEMINI_CLI_TRUST_WORKSPACE="${GEMINI_CLI_TRUST_WORKSPACE:-true}"  # gemini runs headless in throwaway worktrees
cd "$LIMEN_ROOT" || exit 1

# load local secrets (gemini key, etc.) from the single un-committed secrets file
[ -f "$HOME/.limen.env" ] && { set -a; . "$HOME/.limen.env"; set +a; }

LANES="${LIMEN_LANES:-codex,claude,opencode,agy,gemini,jules,copilot,warp,oz,github_actions}"
LOCAL_LIMIT="${LIMEN_LOCAL_LIMIT:-50}"
JULES_LIMIT="${LIMEN_JULES_LIMIT:-100}"
mkdir -p "$LIMEN_ROOT/logs"
LOCK="$LIMEN_ROOT/logs/.saturate.lock"

# single-instance guard (flock if available; mkdir fallback)
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK"
  flock -n 9 || { echo "another saturate/metabolize is running — exiting"; exit 0; }
else
  mkdir "$LOCK.d" 2>/dev/null || { echo "another run holds the lock — exiting"; exit 0; }
  trap 'rmdir "$LOCK.d" 2>/dev/null' EXIT
fi

echo "═══ saturate $(date '+%F %T') lanes=$LANES local_limit=$LOCAL_LIMIT jules_limit=$JULES_LIMIT ═══"

echo "── 0. refresh usage telemetry / lane health ──"
python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" 2>&1 | tail -2 || true

echo "── 0a. drain (pull + close completed/awaiting jules) ──"
bash "$LIMEN_ROOT/scripts/drain.sh" 2>&1 | tail -4 || echo "  (drain skipped)"

echo "── 0b. release stale claims (after drain, so completed work closes first) ──"
python3 -m limen release-stale --hours 24 --apply 2>&1 | tail -3

echo "── 1. route open work across all reachable paid lanes ──"
python3 "$LIMEN_ROOT/scripts/route.py" --apply 2>&1

IFS=',' read -ra LANE_ARR <<< "$LANES"
for v in "${LANE_ARR[@]}"; do
  LIMIT="$LOCAL_LIMIT"
  [ "$v" = "jules" ] && LIMIT="$JULES_LIMIT"
  echo "── 2. dispatch lane: $v (--live, limit $LIMIT) ──"
  python3 -m limen dispatch --agent "$v" --live --limit "$LIMIT" 2>&1 | tail -12
done

echo "── 4. board ──"
python3 -m limen doctor 2>&1 | head -12
echo "═══ saturate done $(date '+%F %T') ═══"
