#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

# Test fixtures must derive behavior from their local setup, never from the
# operator's credentials, active workstream identity, signing helpers, ignore
# files, or interactive editor. Scrub the namespace dynamically so a newly
# introduced Limen runtime variable cannot silently become test input.
while IFS= read -r name; do
  unset "$name"
done < <(compgen -A variable LIMEN_)
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
# Git's default global ignore lives under XDG independently of gitconfig.
export XDG_CONFIG_HOME=/dev/null
export GIT_EDITOR=true
export GIT_SEQUENCE_EDITOR=true
export VISUAL=true
export EDITOR=true
export PYTHONPATH="$ROOT/cli/src${PYTHONPATH:+:$PYTHONPATH}"

exec python3 -m pytest "$@"
