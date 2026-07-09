#!/usr/bin/env bash
# session-lifecycle-pressure.sh — SessionEnd hook for local/remote lifecycle pressure.
#
# Refreshes ignored logs/session-lifecycle-pressure.{json,md} so the next session's
# orientation can show whether local disk pressure is returning to lean after work
# has been preserved remotely. Fail-open and non-blocking by construction.
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P || true)"
SCRIPT_ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd -P || true)"
LIVE_ROOT="${LIMEN_LIVE_ROOT:-${LIMEN_ROOT:-$SCRIPT_ROOT}}"
LIVE_ROOT="$(cd "$LIVE_ROOT" >/dev/null 2>&1 && pwd -P || printf '%s' "$LIVE_ROOT")"

resolve_session_root() {
  local candidate
  for candidate in \
    "${LIMEN_SESSION_ROOT:-}" \
    "$(git rev-parse --show-toplevel 2>/dev/null || true)" \
    "${CLAUDE_PROJECT_DIR:-}" \
    "${CODEX_PROJECT_DIR:-}" \
    "${PWD:-}"; do
    if [ -n "$candidate" ] && [ -d "$candidate" ]; then
      (cd "$candidate" >/dev/null 2>&1 && pwd -P) && return 0
    fi
  done
  return 1
}

SESSION_ROOT="$(resolve_session_root || true)"
same_root=0
if [ -n "$SESSION_ROOT" ] && [ -n "$LIVE_ROOT" ] && [ "$SESSION_ROOT" = "$LIVE_ROOT" ]; then
  same_root=1
fi
MODE="${LIMEN_SESSION_MODE:-}"
if [ -z "$MODE" ]; then
  if [ "$same_root" -eq 1 ]; then
    MODE="control-plane"
  else
    MODE="task"
  fi
fi
case "$MODE" in
  task|control-plane) ;;
  *) MODE="task" ;;
esac

if [ "$MODE" = "task" ]; then
  exit 0
fi

[ -z "$LIVE_ROOT" ] && exit 0
GEN="$LIVE_ROOT/scripts/session-lifecycle-pressure.py"
[ -f "$GEN" ] || exit 0

(
  if command -v python3 >/dev/null 2>&1; then
    LIMEN_LIVE_ROOT="$LIVE_ROOT" LIMEN_SESSION_ROOT="${SESSION_ROOT:-$LIVE_ROOT}" LIMEN_SESSION_MODE="control-plane" \
      python3 "$GEN" --mode control-plane --session-root "${SESSION_ROOT:-$LIVE_ROOT}" --live-root "$LIVE_ROOT" --write || true
  fi
) >/dev/null 2>&1 </dev/null &

exit 0
