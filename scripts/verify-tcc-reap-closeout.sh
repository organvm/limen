#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
common_dir="$(git rev-parse --git-common-dir)"
case "$common_dir" in
  /*) ;;
  *) common_dir="$repo_root/$common_dir" ;;
esac
runtime_root="$(cd "$(dirname "$common_dir")" && pwd -P)"

target_path_client="$runtime_root/.worktrees/tcc-path-client-cleanup-successor-20260731"
target_automatic="$runtime_root/.worktrees/tcc-automatic-worktree-reap-20260731"
registered="$(git -C "$repo_root" worktree list --porcelain | sed -n 's/^worktree //p')"

for target in "$target_path_client" "$target_automatic"; do
  if [ -e "$target" ] || [ -L "$target" ]; then
    echo "FAIL: target still exists: $target" >&2
    exit 1
  fi
  if printf '%s\n' "$registered" | grep -Fqx -- "$target"; then
    echo "FAIL: target remains registered: $target" >&2
    exit 1
  fi
done

python3 - "$runtime_root" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
targets = {
    "tcc-path-client-cleanup-successor-20260731": (
        "b5867c73bd13467baa9c22ff917d90e75d09143d5e46afa4c7230b5b6803bc01.json"
    ),
    "tcc-automatic-worktree-reap-20260731": (
        "3b27913fb5b4999892042ca20d4bdd533031811d3840f64886d1db34758ac089.json"
    ),
}

for name, receipt_name in targets.items():
    receipt_path = root / "logs" / "worktree-abandonment" / receipt_name
    try:
        receipt = json.loads(receipt_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: unreadable typed receipt {receipt_path}: {exc}") from exc
    expected_target = str(root / ".worktrees" / name)
    checks = {
        "schema": receipt.get("schema") == "limen.worktree_abandonment.v1",
        "target": receipt.get("target") == expected_target,
        "state": receipt.get("state") == "completed",
        "phase": receipt.get("phase") == "verify-final",
        "detached": receipt.get("result", {}).get("detached") is True,
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise SystemExit(f"FAIL: typed receipt {receipt_path} failed: {', '.join(failed)}")

aggregate_path = root / "logs" / "reclaim-worktrees.jsonl"
expected_removed = set(targets)
matched = False
try:
    for line in aggregate_path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        removed = record.get("removed")
        if (
            record.get("apply") is True
            and record.get("scanned") == 2
            and isinstance(removed, list)
            and len(removed) == 2
            and set(removed) == expected_removed
            and record.get("failed") == {}
        ):
            matched = True
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"FAIL: unreadable aggregate receipt {aggregate_path}: {exc}") from exc

if not matched:
    raise SystemExit("FAIL: no exact successful two-target aggregate apply receipt")

print("PASS: both TCC worktrees are absent, unregistered, and terminally receipted")
PY
