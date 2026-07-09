#!/usr/bin/env bash
# session-orient.sh — SessionStart context-injection hook.
#
# Emits a compact, PII-free orientation digest (north star, open his-hand levers,
# organ liveness, the board, git state, "read first" pointers) to stdout, which the
# Claude Code harness injects as session context. This is the auto-version of the
# orienting context that otherwise gets hand-pasted at the top of every session.
#
# FAIL-OPEN BY CONSTRUCTION: any error -> emit nothing -> exit 0. A SessionStart hook
# cannot block a session even on a non-zero exit (per the Claude Code hooks contract),
# and this one is read-only. Activated by a SessionStart entry in the project's
# committed .claude/settings.json (limen-scoped); a clean no-op in any other project.
set -uo pipefail

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

if [ "$MODE" = "task" ] && [ -z "$SESSION_ROOT" ]; then
  exit 0
fi
if [ "$MODE" = "control-plane" ] && [ -z "$SESSION_ROOT" ]; then
  SESSION_ROOT="$LIVE_ROOT"
fi

if [ "$MODE" = "task" ] && [ -f "$SESSION_ROOT/scripts/session-orient.py" ]; then
  GEN="$SESSION_ROOT/scripts/session-orient.py"
else
  GEN="$LIVE_ROOT/scripts/session-orient.py"
fi

if [ "$MODE" = "task" ]; then
  DIGEST="$SESSION_ROOT/logs/session-orientation.md"
else
  DIGEST="$LIVE_ROOT/logs/session-orientation.md"
fi

# Primary: regenerate fresh (lean + read-only) under a hard timeout; the generator
# prints the digest to stdout AND refreshes $DIGEST. No-op cleanly outside limen
# (no generator present -> fall through). `timeout` is absent on stock macOS, so
# guard for it and run the generator directly if it is missing.
if command -v python3 >/dev/null 2>&1 && [ -f "$GEN" ]; then
  export LIMEN_LIVE_ROOT="$LIVE_ROOT"
  export LIMEN_SESSION_ROOT="$SESSION_ROOT"
  export LIMEN_SESSION_MODE="$MODE"
  if command -v timeout >/dev/null 2>&1; then
    timeout 5 python3 "$GEN" --mode "$MODE" --session-root "$SESSION_ROOT" --live-root "$LIVE_ROOT" 2>/dev/null && exit 0
  else
    python3 "$GEN" --mode "$MODE" --session-root "$SESSION_ROOT" --live-root "$LIVE_ROOT" 2>/dev/null && exit 0
  fi
fi

# Fallback: emit the last-good digest the daemon/previous run left behind.
[ -f "$DIGEST" ] && cat "$DIGEST"
exit 0
