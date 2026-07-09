#!/usr/bin/env bash
# session-lifecycle-pressure.sh — SessionEnd hook for local/remote lifecycle pressure.
#
# Refreshes ignored logs/session-lifecycle-pressure.{json,md} so the next session's
# orientation can show whether local disk pressure is returning to lean after work
# has been preserved remotely. Fail-open and non-blocking by construction.
set -u

SCRIPT_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")/../.." rev-parse --show-toplevel 2>/dev/null || true)"
ROOT="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/session-lifecycle-pressure.py" ]; then
  ROOT="$SCRIPT_ROOT"
fi
[ -z "$ROOT" ] && exit 0
GEN="$ROOT/scripts/session-lifecycle-pressure.py"
[ -f "$GEN" ] || exit 0
LOCK_DIR="${TMPDIR:-/tmp}/limen-session-lifecycle-pressure.lock"
HOOK_TIMEOUT="${LIMEN_SESSION_LIFECYCLE_TIMEOUT:-45}"
DEBT_TIMEOUT="${LIMEN_SESSION_WORKTREE_DEBT_TIMEOUT:-30}"

run_pressure() {
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$HOOK_TIMEOUT" "$@"
  elif command -v timeout >/dev/null 2>&1; then
    timeout "$HOOK_TIMEOUT" "$@"
  else
    "$@"
  fi
}

(
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
  fi
  trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
  if command -v python3 >/dev/null 2>&1; then
    export LIMEN_WORKTREE_DEBT_TIMEOUT="$DEBT_TIMEOUT"
    run_pressure nice -n 10 python3 "$GEN" --write || true
  fi
) >/dev/null 2>&1 </dev/null &

exit 0
