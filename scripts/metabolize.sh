#!/usr/bin/env bash
# metabolize.sh — one full metabolism cycle of the conductor (the heartbeat).
#
#   drain (close completed) → mine (refill queue) → route (assign cheapest
#   vendor) → [dispatch] → board.
#
# This is the body the local cron AND the remote 4-hourly auto-scaler run to keep
# idle multi-vendor capacity producing. Idempotent + bounded.
#
# SAFE BY DEFAULT: without LIMEN_DISPATCH=1 it only drains/mines/routes/reports —
# all reversible local writes, nothing outward. With LIMEN_DISPATCH=1 it also
# walks every paid lane in the router census. Local lanes use worktree
# isolation and produce reviewable PRs; cloud/service lanes use their explicit
# dispatch adapters and each lane remains budget-gated.
#
# Knobs: LIMEN_MINE_LIMIT (15)  LIMEN_LOCAL_LIMIT (3)  LIMEN_JULES_LIMIT (10)
#        LIMEN_SERVICE_LIMIT (3)  LIMEN_ACTIONS_LIMIT (3)
#        LIMEN_PAID_AGENTS (defaults to the full paid-lane catalog)
set -uo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
export LIMEN_WORKDIR="${LIMEN_WORKDIR:-$HOME/Workspace}"
export LIMEN_ISOLATION="${LIMEN_ISOLATION:-worktree}"
export PYTHONPATH="$LIMEN_ROOT/cli/src"
cd "$LIMEN_ROOT" || exit 1

echo "═══ metabolize $(date '+%F %T') — dispatch=${LIMEN_DISPATCH:-0} isolation=$LIMEN_ISOLATION ═══"

echo "── 1. drain (close completed Jules) ──"
bash "$LIMEN_ROOT/scripts/drain.sh" || echo "  (drain skipped/failed — continuing)"

echo "── 2. mine (refill queue from GitHub backlog) ──"
python3 "$LIMEN_ROOT/scripts/mine-backlog.py" --limit "${LIMEN_MINE_LIMIT:-15}" --apply || echo "  (mine skipped)"

echo "── 3. route (assign cheapest-capable vendor) ──"
python3 "$LIMEN_ROOT/scripts/route.py" --apply || echo "  (route skipped)"

if [ "${LIMEN_DISPATCH:-0}" = "1" ]; then
  echo "── 4. dispatch paid lanes (full census order, budget-gated) ──"
  for v in ${LIMEN_PAID_AGENTS:-codex claude opencode agy gemini jules copilot warp oz github_actions}; do
    case "$v" in
      codex|claude|opencode|agy|gemini) limit="${LIMEN_LOCAL_LIMIT:-3}" ;;
      jules) limit="${LIMEN_JULES_LIMIT:-10}" ;;
      github_actions) limit="${LIMEN_ACTIONS_LIMIT:-3}" ;;
      *) limit="${LIMEN_SERVICE_LIMIT:-3}" ;;
    esac
    python3 -m limen dispatch --agent "$v" --live --limit "$limit" || true
  done
else
  echo "── 4. dispatch SKIPPED (set LIMEN_DISPATCH=1 to enable outward dispatch) ──"
fi

echo "── 5. board ──"
python3 -m limen doctor 2>&1 | head -12
echo "═══ metabolize done $(date '+%F %T') ═══"
