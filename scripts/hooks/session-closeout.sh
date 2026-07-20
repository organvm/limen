#!/usr/bin/env bash
# session-closeout.sh — constant-time SessionEnd signal hook.
#
# Claude supplies the authoritative session_id and cwd as JSON on stdin. This hook
# records only the worktree-closeout breadcrumb consumed by quicken.py. Handoff
# rebuilds and watcher/transcript audits belong to their heartbeat/metabolize owners;
# none may delay or prevent this signal.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || exit 0
if command -v python3 >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/session-closeout.py" ]; then
  python3 "$SCRIPT_DIR/session-closeout.py" || true
fi
exit 0
