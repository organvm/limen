#!/usr/bin/env bash
# Open full-fleet overnight autonomy through one operator surface.
set -euo pipefail

ROOT="${LIMEN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export LIMEN_ROOT="$ROOT"
export PYTHONPATH="$ROOT/cli/src:${PYTHONPATH:-}"
MODE="${1:---dry-run}"

usage() {
  echo "usage: $0 [--dry-run | --apply]" >&2
}

case "$MODE" in
  --dry-run|--apply) ;;
  *) usage; exit 2 ;;
esac

cd "$ROOT"

if [ "$MODE" = "--dry-run" ]; then
  python3 scripts/overnight-doctor.py
  echo
  python3 scripts/full-fleet-lanes.py --format shell
  echo
  LIMEN_LANES=auto LIMEN_DISPATCH_ASYNC=1 bash scripts/gen-launchd-plist.sh --stdout >/tmp/limen-full-fleet-overnight.plist
  if command -v plutil >/dev/null 2>&1; then
    plutil -lint /tmp/limen-full-fleet-overnight.plist
  else
    echo "plutil not found; rendered /tmp/limen-full-fleet-overnight.plist"
  fi
  exit 0
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
python3 scripts/overnight-doctor.py --json >"$tmp"

python3 - "$tmp" <<'PY'
import json
import sys

snapshot = json.load(open(sys.argv[1]))
hard_ids = {
    "live-root-dirty-unpreserved",
    "queue-lock-unhealthy",
    "lane-classification-missing",
    "lane-classification-invalid",
    "capacity-fill-silent-lanes",
}
hard = [b for b in snapshot.get("blockers", []) if b.get("id") in hard_ids]
if hard:
    print("open-full-fleet-overnight: preservation/readiness blockers stop --apply:", file=sys.stderr)
    for blocker in hard:
        print(f"  - {blocker.get('id')}: {blocker.get('evidence')}", file=sys.stderr)
    sys.exit(2)
PY

mkdir -p "$ROOT/logs"
python3 - <<'PY'
import datetime as dt
import json
import os
from pathlib import Path

root = Path(os.environ["LIMEN_ROOT"])
policy = {
    "mode": "dispatch",
    "dispatch_enabled": True,
    "reason": "Full-fleet overnight opener: all reachable registered lanes through LIMEN_LANES=auto and async dispatch.",
    "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
}
(root / "logs").mkdir(parents=True, exist_ok=True)
(root / "logs" / "autonomy-policy.json").write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n")
(root / "logs" / "AUTONOMY_PAUSED").unlink(missing_ok=True)
PY

LIMEN_LANES=auto LIMEN_DISPATCH_ASYNC=1 bash scripts/gen-launchd-plist.sh --install
plist="$HOME/Library/LaunchAgents/com.limen.heartbeat.plist"

if ! command -v launchctl >/dev/null 2>&1; then
  echo "launchctl not found; wrote policy and plist but did not load heartbeat"
  exit 0
fi

launchctl bootout "gui/$(id -u)/com.limen.heartbeat" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
launchctl kickstart -k "gui/$(id -u)/com.limen.heartbeat" || true
python3 scripts/full-fleet-lanes.py --format shell
echo "full-fleet overnight opened: policy dispatch_enabled=true, LIMEN_LANES=auto, LIMEN_DISPATCH_ASYNC=1"
