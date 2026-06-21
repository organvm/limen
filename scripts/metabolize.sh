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
# all reversible local writes, nothing outward. With LIMEN_DISPATCH=1 it also:
#   - dispatches every reachable paid lane in the shared fleet catalog:
#     codex, claude, opencode, agy, gemini, jules, copilot, warp, oz, and
#     github_actions. Local CLI lanes use worktree isolation and only ever
#     produce reviewable PRs — never touch a live tree.
#
# Knobs: LIMEN_MINE_LIMIT (15)  LIMEN_FLEET_LIMIT (3 per reachable lane)
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
  echo "── 4. dispatch paid fleet (capacity-census gated, per-lane bounded) ──"
  python3 -m limen dispatch --agent fleet --live --limit "${LIMEN_FLEET_LIMIT:-${LIMEN_LOCAL_LIMIT:-3}}" || true
else
  echo "── 4. dispatch SKIPPED (set LIMEN_DISPATCH=1 to enable outward dispatch) ──"
fi

echo "── 5. board ──"
python3 -m limen doctor 2>&1 | head -12
echo "═══ metabolize done $(date '+%F %T') ═══"
