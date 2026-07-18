#!/usr/bin/env bash
set -euo pipefail

root="/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717"
capsule_dir="$root/.limen-workstream"
contract="$capsule_dir/workstream.json"
contract_helper="$root/cli/src/limen/workstream_contract.py"
capsule_lock="$capsule_dir/.capsule.lock"
expected_branch="fix/codex-runaway-prevention-20260717-v2"
tracked_rel=(
  ".limen-workstream/README.md"
  ".limen-workstream/manifest.md"
  ".limen-workstream/workstream.json"
  ".limen-workstream/intent.md"
  ".limen-workstream/runtime.md"
  ".limen-workstream/closeout.md"
  ".limen-workstream/kickstart.sh"
  "cli/src/limen/workstream_contract.py"
)

if [[ -L "$root" || ! -d "$root" || "$(cd "$root" && pwd -P)" != "$root" ]]; then
  printf 'invalid capsule: worktree root is not the expected real directory\n' >&2
  exit 2
fi
if [[ -L "$capsule_dir" || ! -d "$capsule_dir" \
  || "$(cd "$capsule_dir" && pwd -P)" != "$capsule_dir" ]]; then
  printf 'invalid capsule: capsule root is not the expected real directory\n' >&2
  exit 2
fi
if [[ -L "$capsule_lock" || ( -e "$capsule_lock" && ! -f "$capsule_lock" ) ]]; then
  printf 'invalid capsule: lock path is unsafe\n' >&2
  exit 2
fi

cd "$root"
exec 9>> "$capsule_lock"
lock_status=0
python3 -c \
  'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)' \
  9>&9 || lock_status=$?
if [[ "$lock_status" -ne 0 ]]; then
  printf 'invalid capsule: another launch holds the capsule lock\n' >&2
  exit 2
fi

validate_tracked_capsule() {
  local relative="" module=""
  if [[ "$(git branch --show-current 9>&-)" != "$expected_branch" ]]; then
    printf 'invalid capsule: worktree branch identity mismatch\n' >&2
    return 1
  fi
  for relative in "${tracked_rel[@]}"; do
    module="$root/$relative"
    if [[ -L "$module" || ! -s "$module" ]]; then
      printf 'invalid capsule: missing, empty, or symlinked module %s\n' "$module" >&2
      return 1
    fi
    if ! git ls-files --error-unmatch -- "$relative" >/dev/null 2>&1 9>&-; then
      printf 'invalid capsule: module is not tracked %s\n' "$module" >&2
      return 1
    fi
  done
  if ! git diff --quiet HEAD -- "${tracked_rel[@]}" 9>&-; then
    printf 'invalid capsule: tracked module or helper differs from HEAD\n' >&2
    return 1
  fi
}

validate_tracked_capsule

refresh_workstream_runway() {
  local runway_fields=""
  if runway_fields="$(python3 "$contract_helper" admit --path "$contract" 9>&-)"; then
    :
  else
    return $?
  fi
  IFS=: read -r LIMEN_WORKSTREAM_REQUESTED LIMEN_WORKSTREAM_RUNWAY_SECONDS LIMEN_WORKSTREAM_STARTED_EPOCH LIMEN_WORKSTREAM_DEADLINE_EPOCH LIMEN_WORKSTREAM_REMAINING_SECONDS <<< "$runway_fields"
  export LIMEN_WORKSTREAM_REQUESTED LIMEN_WORKSTREAM_RUNWAY_SECONDS LIMEN_WORKSTREAM_STARTED_EPOCH LIMEN_WORKSTREAM_DEADLINE_EPOCH LIMEN_WORKSTREAM_REMAINING_SECONDS
}

refresh_workstream_runway
preflight_timeout="${LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS:-120}"
case "$preflight_timeout" in
  ""|*[!0-9]*)
    printf 'invalid capsule preflight timeout: %s\n' "$preflight_timeout" >&2
    exit 2
    ;;
esac
if (( preflight_timeout < 1 || preflight_timeout > 300 )); then
  printf 'capsule preflight timeout must be between 1 and 300 seconds\n' >&2
  exit 2
fi
if git remote get-url origin >/dev/null 2>&1 9>&-; then
  GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
    --timeout-seconds "$preflight_timeout" -- git fetch --prune 9>&-
fi
python3 "$contract_helper" run-bounded \
  --timeout-seconds "$preflight_timeout" -- git status --short --branch 9>&-

validate_tracked_capsule
if command -v codex >/dev/null 2>&1; then
  capsule_prompt=""
  IFS= read -r -d '' capsule_prompt < "$capsule_dir/README.md" || true
  refresh_workstream_runway
  validate_tracked_capsule
  exec 9>&-
  exec codex --ask-for-approval never --sandbox workspace-write "$capsule_prompt"
fi
refresh_workstream_runway
validate_tracked_capsule
exec 9>&-
exec "${SHELL:-/bin/zsh}" -l
