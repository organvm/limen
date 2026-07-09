#!/usr/bin/env bash
# Codex/Claude hook wrapper for repo-local hook scripts.
#
# Resolves the Limen root without assuming CLAUDE_PROJECT_DIR is set, then
# exports both CLAUDE_PROJECT_DIR and CODEX_PROJECT_DIR for the legacy scripts.
# Missing targets are diagnostic no-ops so startup/edit hooks stay fail-open.
set -uo pipefail

hook_name="${1:-}"
shift 2>/dev/null || true

log() {
  printf 'limen-hook[%s]: %s\n' "${hook_name:-unknown}" "$*" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
script_root="$(cd -- "$script_dir/../.." >/dev/null 2>&1 && pwd -P)"
live_root="${LIMEN_LIVE_ROOT:-${LIMEN_ROOT:-$script_root}}"
live_root="$(cd "$live_root" >/dev/null 2>&1 && pwd -P || printf '%s' "$live_root")"

resolve_session_root() {
  local candidate
  for candidate in \
    "${LIMEN_SESSION_ROOT:-}" \
    "$(git rev-parse --show-toplevel 2>/dev/null || true)" \
    "${CLAUDE_PROJECT_DIR:-}" \
    "${CODEX_PROJECT_DIR:-}" \
    "${PWD:-}"; do
    if [[ -n "$candidate" && -d "$candidate" ]]; then
      (cd "$candidate" >/dev/null 2>&1 && pwd -P)
      return 0
    fi
  done
  return 1
}

session_root="$(resolve_session_root)" || {
  session_root=""
}
mode="${LIMEN_SESSION_MODE:-}"
if [[ -z "$mode" ]]; then
  if [[ -n "$session_root" && "$session_root" == "$live_root" ]]; then
    mode="control-plane"
  else
    mode="task"
  fi
fi
case "$mode" in
  task|control-plane) ;;
  *) mode="task" ;;
esac

if [[ "$mode" == "task" && -z "$session_root" ]]; then
  log "no task session root resolved; skipping"
  exit 0
fi
if [[ "$mode" == "control-plane" && -z "$session_root" ]]; then
  session_root="$live_root"
fi

case "$hook_name" in
  session-orient)
    if [[ "$mode" == "task" && -f "$session_root/scripts/hooks/session-orient.sh" ]]; then
      target="$session_root/scripts/hooks/session-orient.sh"
    else
      target="$live_root/scripts/hooks/session-orient.sh"
    fi
    ;;
  lint-edited-file)
    if [[ "$mode" == "task" && -f "$session_root/scripts/hooks/lint-edited-file.sh" ]]; then
      target="$session_root/scripts/hooks/lint-edited-file.sh"
    else
      target="$live_root/scripts/hooks/lint-edited-file.sh"
    fi
    ;;
  *)
    log "unknown hook target; skipping"
    exit 0
    ;;
esac

if [[ ! -f "$target" ]]; then
  log "missing script: $target"
  exit 0
fi

export LIMEN_LIVE_ROOT="$live_root"
export LIMEN_SESSION_ROOT="$session_root"
export LIMEN_SESSION_MODE="$mode"
if [[ "$mode" == "task" ]]; then
  export LIMEN_ROOT="$session_root"
else
  export LIMEN_ROOT="$live_root"
fi
export CLAUDE_PROJECT_DIR="$session_root"
export CODEX_PROJECT_DIR="$session_root"

if [[ -x "$target" ]]; then
  exec "$target" "$@"
fi

log "script is not executable, running with bash: $target"
exec bash "$target" "$@"
