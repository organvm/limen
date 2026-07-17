#!/usr/bin/env bash
set -euo pipefail
cd "/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717"
contract="/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717/.limen-workstream/workstream.json"
contract_helper="/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717/cli/src/limen/workstream_contract.py"
for module in "/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717/.limen-workstream/manifest.md" "$contract" "$contract_helper" "/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717/.limen-workstream/intent.md" "/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717/.limen-workstream/runtime.md" "/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717/.limen-workstream/closeout.md"; do
  if [[ ! -s "$module" ]]; then
    printf 'invalid capsule: missing or empty module %s\n' "$module" >&2
    exit 2
  fi
done
runway_fields="$(python3 "$contract_helper" admit --path "$contract")"
IFS=: read -r LIMEN_WORKSTREAM_REQUESTED LIMEN_WORKSTREAM_RUNWAY_SECONDS LIMEN_WORKSTREAM_STARTED_EPOCH LIMEN_WORKSTREAM_DEADLINE_EPOCH LIMEN_WORKSTREAM_REMAINING_SECONDS <<< "$runway_fields"
export LIMEN_WORKSTREAM_REQUESTED LIMEN_WORKSTREAM_RUNWAY_SECONDS LIMEN_WORKSTREAM_STARTED_EPOCH LIMEN_WORKSTREAM_DEADLINE_EPOCH LIMEN_WORKSTREAM_REMAINING_SECONDS
if git remote get-url origin >/dev/null 2>&1; then
  GIT_TERMINAL_PROMPT=0 git fetch --prune
fi
git status --short --branch
if command -v codex >/dev/null 2>&1; then
  if [[ "1" -eq 1 ]]; then
    capsule_prompt=""
    IFS= read -r -d '' capsule_prompt < "/Users/4jp/Workspace/limen/.worktrees/codex-runaway-prevention-20260717/.limen-workstream/README.md" || true
    exec codex --ask-for-approval never --sandbox workspace-write "$capsule_prompt"
  fi
  exec codex --ask-for-approval never --sandbox workspace-write
fi
exec "${SHELL:-/bin/zsh}" -l
