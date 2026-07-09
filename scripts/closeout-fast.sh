#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AMBIENT_PYTHONPATH="${PYTHONPATH:-}"
PYTHONPATH_VALUE="$ROOT/cli/src${AMBIENT_PYTHONPATH:+:$AMBIENT_PYTHONPATH}"
export LIMEN_ROOT="${LIMEN_ROOT:-$ROOT}"
export PYTHONPATH="$PYTHONPATH_VALUE"

TMP_FILES=()
QUEUE_LOCK_HELD=0
GATE_NAMES=()
GATE_STATUSES=()

cleanup() {
  if ((${#TMP_FILES[@]})); then
    rm -f "${TMP_FILES[@]}"
  fi
  release_queue_lock
}

record_gate() {
  GATE_NAMES+=("$1")
  GATE_STATUSES+=("$2")
}

write_receipt() {
  local code="$1"
  local status="fail"
  if [[ "$code" == "0" ]]; then
    status="pass"
  fi
  local receipt_json="$ROOT/logs/closeout-fast.json"
  local receipt_md="$ROOT/logs/closeout-fast.md"
  local gate_args=()
  local i
  for ((i = 0; i < ${#GATE_NAMES[@]}; i++)); do
    gate_args+=("${GATE_NAMES[$i]}=${GATE_STATUSES[$i]}")
  done
  python3 - "$status" "$receipt_json" "$receipt_md" "${gate_args[@]}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

status, receipt_json, receipt_md, *pairs = sys.argv[1:]
gates = []
for pair in pairs:
    name, _, gate_status = pair.rpartition("=")
    gates.append({"name": name, "status": gate_status or "unknown"})

receipt = {
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": status,
    "gates": gates,
    "safe_alternative": "focused lane predicates plus remote CI verify receipt",
}

json_path = Path(receipt_json)
md_path = Path(receipt_md)
json_path.parent.mkdir(parents=True, exist_ok=True)
json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

lines = [f"# closeout-fast receipt", "", f"Status: `{status}`", ""]
for gate in gates:
    lines.append(f"- {gate['name']}: `{gate['status']}`")
lines.extend(["", "Whole-repo proof remains the guarded full verifier or remote CI verify receipt."])
md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\nCloseout-fast receipt")
print(f"status: {status}")
for gate in gates:
    print(f"- {gate['name']}: {gate['status']}")
print(f"wrote: {json_path}")
print(f"wrote: {md_path}")
PY
}

closeout_exit() {
  local code="$1"
  trap - EXIT
  set +e
  write_receipt "$code"
  cleanup
  exit "$code"
}
trap 'closeout_exit "$?"' EXIT

step() {
  printf '\n==> %s\n' "$*"
}

run_gate() {
  local label="$1"
  shift
  step "$label"
  if "$@"; then
    record_gate "$label" "pass"
  else
    local rc="$?"
    record_gate "$label" "fail"
    return "$rc"
  fi
}

report_live_root_gate() {
  local label="$1"
  shift
  local receipt
  receipt="$(mktemp "${TMPDIR:-/tmp}/limen-closeout-fast.XXXXXX")"
  TMP_FILES+=("$receipt")
  if ! "$@" | tee "$receipt"; then
    record_gate "$label" "fail"
    return 1
  fi
  if grep -Fq 'Status: `ready`' "$receipt"; then
    record_gate "$label" "ready"
  else
    record_gate "$label" "blocked-report"
    return 1
  fi
  return 0
}

acquire_queue_lock() {
  local lockd="$ROOT/logs/.queue.lock.d"
  local waited
  for waited in $(seq 1 "${LIMEN_CLOSEOUT_QUEUE_LOCK_TIMEOUT:-30}"); do
    if mkdir "$lockd" 2>/dev/null; then
      printf '%s\n' "$$" > "$lockd/pid" 2>/dev/null || true
      date -u '+%Y-%m-%dT%H:%M:%SZ' > "$lockd/created_at" 2>/dev/null || true
      QUEUE_LOCK_HELD=1
      return 0
    fi
    sleep 1
  done
  printf 'closeout-fast: queue lock unavailable after %ss\n' "${LIMEN_CLOSEOUT_QUEUE_LOCK_TIMEOUT:-30}" >&2
  return 1
}

release_queue_lock() {
  local lockd="$ROOT/logs/.queue.lock.d"
  if [[ "$QUEUE_LOCK_HELD" == "1" ]]; then
    if [[ "$(cat "$lockd/pid" 2>/dev/null || true)" == "$$" ]]; then
      rm -f "$lockd/pid" "$lockd/created_at" 2>/dev/null || true
      rmdir "$lockd" 2>/dev/null || true
    fi
    QUEUE_LOCK_HELD=0
  fi
}

closeout_smoke_tests() {
  python3 -m py_compile cli/src/limen/worktree_debt.py scripts/session-lifecycle-pressure.py scripts/closeout-resource-guard.py
  python3 -m pytest \
    cli/tests/test_worktree_debt.py::test_reachable_from_remote_uses_single_contains_query \
    -q
}

run_with_timeout() {
  local seconds="$1"
  shift
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$seconds" "$@"
  elif command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  else
    "$@"
  fi
}

cd "$ROOT"

run_gate "Resource guard" python3 scripts/closeout-resource-guard.py --mode closeout-fast --warn-only

acquire_queue_lock

run_gate "Validate task board" python3 scripts/validate-task-board.py --tasks tasks.yaml

run_gate "Check TABVLARIVS ticket inbox" python3 scripts/tabularius-organ.py --check

step "Report live-root gate"
if ! report_live_root_gate "Report live-root gate" python3 scripts/live-root-gate.py; then
  printf 'live-root gate is report-only in closeout-fast; use its owner receipt for daemon/live-root blockers\n'
fi

run_gate "Probe dispatch health" python3 scripts/dispatch-health.py --probe-async

run_gate "Check branch reap debt" python3 scripts/reap-branches.py --check

run_gate "Check parameter registry" python3 scripts/check-params.py

run_gate "Run closeout smoke tests" closeout_smoke_tests

if [[ "${LIMEN_CLOSEOUT_RUN_LIFECYCLE_TESTS:-0}" == "1" ]]; then
  run_gate "Run opt-in lifecycle regression tests" \
    run_with_timeout "${LIMEN_CLOSEOUT_LIFECYCLE_TEST_TIMEOUT:-90}" \
    python3 -m pytest cli/tests/test_worktree_debt.py cli/tests/test_session_lifecycle_pressure.py -q
else
  step "Skip opt-in lifecycle regression tests"
  printf 'set LIMEN_CLOSEOUT_RUN_LIFECYCLE_TESTS=1 to run the slower lifecycle pytest tranche\n'
  record_gate "Run opt-in lifecycle regression tests" "skipped"
fi

step "Reconcile closeout claims (claimed-done vs ground truth)"
if [[ "${LIMEN_SESSION_CLOSEOUT:-0}" == "1" ]]; then
  python3 scripts/reconcile-closeouts.py --check
else
  python3 scripts/reconcile-closeouts.py --doctor >/dev/null \
    && printf '  (closeout-reconcile dark; classifier OK — set LIMEN_SESSION_CLOSEOUT=1 to enforce --check)\n'
fi

printf '\nFast closeout verification passed\n'
