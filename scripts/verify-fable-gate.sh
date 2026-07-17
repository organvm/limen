#!/usr/bin/env bash
# verify-fable-gate.sh — executable predicate for provider-neutral Fable planning.
#
# Exit 0 means:
#   1. acceptance + fresh balance authority fails closed and honors the reserve band;
#   2. the interactive hook is report-only and emits no model/session control;
#   3. workflow metadata is plan-only and hands building back to provider Auto;
#   4. focused contract/allotment/session/workflow tests pass; and
#   5. balance publication reaches a no-op fixed point on unchanged evidence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PY=("$ROOT/.venv/bin/python")
elif [ -x "$HOME/Workspace/limen/.venv/bin/python" ]; then
  PY=("$HOME/Workspace/limen/.venv/bin/python")
else
  PY=(python3)
fi
export PYTHONPATH="$ROOT/cli/src${PYTHONPATH:+:$PYTHONPATH}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "verify-fable-gate: FAIL — $1" >&2; exit 1; }
pass() { echo "  ok — $1"; }

TMP="$TMP" "${PY[@]}" - <<'PYEOF'
import datetime as dt
import json
import os
from pathlib import Path
from limen import fable_contract as C

root = Path(os.environ["TMP"])
now = dt.datetime.now(dt.timezone.utc)

def acceptance(category="governance"):
    return {
        "schema": C.ACCEPTANCE_SCHEMA,
        "created_at": now.isoformat(),
        "week": C.current_week(now),
        "category": category,
        "percent": 5,
        "sources": ["docs/fable-allotment.md"],
        "redacted_packets": [],
        "verification": ["scripts/verify-fable-gate.sh"],
        "reserve_unlocked": category == "reserve",
        "mode": "plan-only",
        "deliverable": "continuation-capsule",
        "builder_handoff": C.builder_handoff(),
        "motion_receipt_deadline_seconds": C.MOTION_RECEIPT_DEADLINE_SECONDS,
    }

def balance(spent_pct):
    return {
        "schema": C.BALANCE_SCHEMA,
        "observed_at": now.isoformat(),
        "week": C.current_week(now),
        "spent_tokens": int(spent_pct),
        "spent_pct": spent_pct,
        "deliberate_cap": 40,
        "hard_cap": 50,
        "over_cap": spent_pct >= 50,
        "source": "predicate-owner-adapter",
        "meter_ready": True,
        "measurement": {
            "method": "owner-used-percent",
            "owner_observed_pct": spent_pct,
        },
    }

(root / "fable-acceptance.json").write_text(json.dumps(acceptance()))
(root / "fable-reserve.json").write_text(json.dumps(acceptance("reserve")))
(root / "fable-open.json").write_text(json.dumps(balance(5)))
(root / "fable-band.json").write_text(json.dumps(balance(45)))
(root / "fable-over.json").write_text(json.dumps(balance(50)))
PYEOF

echo "── 1. receipt authority is fresh, reconciled, and fail-closed ──"
TMP="$TMP" "${PY[@]}" - <<'PYEOF' || fail "authority/cap contract"
import os
from pathlib import Path
from limen import fable_contract as C

root = Path(os.environ["TMP"])
authority, reason = C.authorization_status(
    acceptance_path=root / "fable-acceptance.json",
    balance_path=root / "fable-band.json",
)
assert authority is None and reason == "reserve-required", (authority, reason)
authority, reason = C.authorization_status(
    acceptance_path=root / "fable-reserve.json",
    balance_path=root / "fable-band.json",
)
assert authority is not None and reason == "ok", (authority, reason)
authority, reason = C.authorization_status(
    acceptance_path=root / "fable-reserve.json",
    balance_path=root / "fable-over.json",
)
assert authority is None and reason == "hard-cap", (authority, reason)
PYEOF
pass "ordinary acceptance closes in reserve band; exact reserve opens; hard cap closes"

echo "── 2. interactive observer reports but never controls ──"
NON_FABLE="$(printf '%s\n' '{"model":"arbitrarily-renamed-provider-id"}' | \
  "${PY[@]}" scripts/fable-session-guard.py 2>&1)"
[ -z "$NON_FABLE" ] || fail "non-Fable context was not a clean no-op"
REPORT="$(printf '%s\n' '{"model":"arbitrarily-renamed-provider-id","execution_role":"fable-planner"}' | \
  LIMEN_FABLE_ACCEPTANCE="$TMP/fable-acceptance.json" \
  LIMEN_FABLE_BALANCE_PATH="$TMP/fable-over.json" \
  "${PY[@]}" scripts/fable-session-guard.py 2>&1)"
grep -q "CONTRACT RED" <<<"$REPORT" || fail "red contract was not reported"
grep -q "report-only" <<<"$REPORT" || fail "report-only boundary is absent"
if grep -Eq '/model|kill|signal|terminate|retune' <<<"$REPORT"; then
  fail "interactive observer emitted a control action"
fi
pass "current invocation is observed without model or peer-session control"

echo "── 3. workflow receipt is plan-only and provider-neutral ──"
TMP="$TMP" "${PY[@]}" - <<'PYEOF'
import json
import os
from pathlib import Path
from limen import fable_contract as C

root = Path(os.environ["TMP"])
workflow = {
    "workflowName": "bounded-fable-plan",
    "status": "completed",
    "fableAcceptance": str(root / "fable-acceptance.json"),
    "executionProfile": {
        "execution_role": "fable-planner",
        "planning_only": True,
        "build_allowed": False,
        "fanout_allowed": False,
    },
    "fablePacket": {
        "schema": C.PACKET_SCHEMA,
        "mode": "plan-only",
        "implementation_by_fable": "prohibited",
        "builder_handoff": C.builder_handoff(),
        "path": "docs/continuations/fable/predicate.md",
    },
    "workflowProgress": [{"model": "fable-role-observation", "state": "done"}],
}
(root / "workflow.json").write_text(json.dumps(workflow))
PYEOF
LIMEN_FABLE_BALANCE_PATH="$TMP/fable-open.json" \
  "${PY[@]}" scripts/claude-workflow-guard.py audit-workflow "$TMP/workflow.json" \
  >/dev/null || fail "valid plan-only workflow was rejected"
pass "workflow profile and build packet contain no model/tier pin"

echo "── 4. focused contract tests ──"
"${PY[@]}" -m pytest \
  cli/tests/test_fable_contract.py \
  cli/tests/test_fable_allotment.py \
  cli/tests/test_fable_session_guard.py \
  cli/tests/test_claude_workflow_guard.py \
  -q >/dev/null || fail "focused Fable/workflow suite"
pass "focused Fable/workflow pytest suite green"

echo "── 5. unchanged balance evidence reaches a fixed point ──"
BAL_ROOT="$TMP/balance-root"
EMPTY="$TMP/empty-transcripts"
mkdir -p "$BAL_ROOT/logs" "$EMPTY"
LIMEN_ROOT="$BAL_ROOT" LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR="$EMPTY" \
  LIMEN_FABLE_WEEKLY_TOKENS=1000000 \
  "${PY[@]}" scripts/fable-allotment.py balance >/dev/null
H1="$(shasum "$BAL_ROOT/logs/fable-allotment.json" | awk '{print $1}')"
LIMEN_ROOT="$BAL_ROOT" LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR="$EMPTY" \
  LIMEN_FABLE_WEEKLY_TOKENS=1000000 \
  "${PY[@]}" scripts/fable-allotment.py balance >/dev/null
H2="$(shasum "$BAL_ROOT/logs/fable-allotment.json" | awk '{print $1}')"
[ "$H1" = "$H2" ] || fail "balance publication changed on identical evidence"
pass "balance publication is idempotent"

echo "verify-fable-gate: PASS"
