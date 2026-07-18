#!/usr/bin/env bash
set -euo pipefail
cd "/Users/4jp/Workspace/limen/.worktrees/governance-organ-recovery-next"
for module in "/Users/4jp/Workspace/limen/.worktrees/governance-organ-recovery-next/.limen-workstream/manifest.md" "/Users/4jp/Workspace/limen/.worktrees/governance-organ-recovery-next/.limen-workstream/intent.md" "/Users/4jp/Workspace/limen/.worktrees/governance-organ-recovery-next/.limen-workstream/evidence.md" "/Users/4jp/Workspace/limen/.worktrees/governance-organ-recovery-next/.limen-workstream/runtime.md" "/Users/4jp/Workspace/limen/.worktrees/governance-organ-recovery-next/.limen-workstream/closeout.md"; do
  if [[ ! -s "$module" ]]; then
    printf 'invalid capsule: missing or empty module %s\n' "$module" >&2
    exit 2
  fi
done
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --prune
fi
git status --short --branch
if command -v codex >/dev/null 2>&1; then
  if [[ "1" -eq 1 ]]; then
    capsule_prompt=""
    IFS= read -r -d '' capsule_prompt < "/Users/4jp/Workspace/limen/.worktrees/governance-organ-recovery-next/.limen-workstream/README.md" || true
    exec codex "$capsule_prompt"
  fi
  exec codex
fi
exec "${SHELL:-/bin/zsh}" -l
