#!/usr/bin/env bash
# heal-claude-update-marker.sh — clear Claude Code's BENIGN "install_failed" update marker.
#
# The native updater writes ~/.claude/.last-update-result.json with
# status=install_failed and version_to=null whenever it checks for an update while
# already on the latest version — there is no target to install, so "failed" is a
# mislabel of "nothing to do". That cosmetic marker surfaces as a ⚠ on the /doctor
# startup screen: a scary-looking false alarm for nothing.
#
# This clears ONLY that exact benign signature (install_failed + null target + no
# error code). A REAL failure — an actual newer version that didn't install, i.e.
# version_to is set — is LEFT untouched so it still surfaces. Absent file == "no
# prior failure" == the known-good state, so removal is the fix. Idempotent + lockless.
#
# This is the BEAT layer of a defense-in-depth cascade ([[cascade-fallback-principle]]):
# an independent launchd WatchPaths agent clears it the instant it is written; this
# beat step is the periodic net (every C_HYGIENE beats); a manual run is the floor.
# No single point of failure ever lets the false alarm reach him ([[no-never-happens-again]]).
set -uo pipefail
M="${HOME:-/Users/4jp}/.claude/.last-update-result.json"

if [ ! -f "$M" ]; then
  echo "claude-marker-heal: clean (no marker)"; exit 0
fi
# Benign false-positive signature (whitespace-tolerant):
#   "status":"install_failed"  AND  "version_to":null  AND  "error_code":null
if grep -Eq '"status"[[:space:]]*:[[:space:]]*"install_failed"' "$M" \
   && grep -Eq '"version_to"[[:space:]]*:[[:space:]]*null' "$M" \
   && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*null' "$M"; then
  rm -f "$M" && echo "claude-marker-heal: cleared benign install_failed marker (false ⚠)"
else
  echo "claude-marker-heal: marker present but NOT the benign signature — left to surface"
fi
exit 0
