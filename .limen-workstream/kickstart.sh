#!/usr/bin/env bash
set -euo pipefail
cd "/Users/4jp/Workspace/limen/.worktrees/next-autonomous-epoch-20260714"
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --prune
fi
git status --short --branch
if command -v codex >/dev/null 2>&1; then
  exec codex "$(cat "/Users/4jp/Workspace/limen/.worktrees/next-autonomous-epoch-20260714/.limen-workstream/README.md")"
fi
exec "${SHELL:-/bin/zsh}" -l
