#!/usr/bin/env bash
# omega.test.sh — regression test for scripts/omega.sh (the autonomic fixed-point predicate).
#
# omega.sh is the CONJUNCTION of every gate's --check; its own contract is the tally logic:
#   • a rung that cannot be checked here is SKIP, never a silent PASS (the curl-000 lesson);
#   • exit 0 ⟺ zero FAIL rungs (SKIPs allowed);
#   • --strict exits non-zero on either FAIL or SKIP;
#   • it stamps a versioned, content-addressed logs/omega.json with one row per rung.
# Deterministic: omega.sh derives ROOT from its own path and calls children by "$ROOT/scripts/X",
# so we run a COPY in a temp ROOT stubbed with fake predicates — no live board, handoff, or network.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
real_omega="$here/../omega.sh"
real_watch="$here/../overnight-watch.py"
[ -f "$real_omega" ] || { echo "FAIL: cannot find omega.sh at $real_omega" >&2; exit 1; }
[ -f "$real_watch" ] || { echo "FAIL: cannot find overnight-watch.py at $real_watch" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# A stub ROOT: omega.sh + a scripts/ dir of fake predicates whose exit codes we control per case.
mkdir -p "$work/scripts" "$work/cli/src" "$work/logs"
cp "$real_omega" "$work/scripts/omega.sh"

# write_stubs <ask_gate_rc> — all det children exit 0 except ask-gate.py, whose rc is the argument.
# (In --offline the live children are SKIPped without running. Registry-owned checks are discovered
# through a generic stub whose sensor id is intentionally unrelated to its command/label.)
write_stubs() {
  local ask_rc="$1"
  for py in enactment-audit armed-valve-audit handoff-relay; do
    printf '#!/usr/bin/env python3\nimport sys; sys.exit(0)\n' > "$work/scripts/$py.py"
    chmod +x "$work/scripts/$py.py"
  done
  printf '#!/usr/bin/env python3\nimport sys; sys.exit(%s)\n' "$ask_rc" > "$work/scripts/ask-gate.py"
  chmod +x "$work/scripts/ask-gate.py"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$work/scripts/no-tasks-on-me.sh"
  chmod +x "$work/scripts/no-tasks-on-me.sh"
  cat > "$work/scripts/beat-sensors.py" <<'PY'
#!/usr/bin/env python3
import sys
import os
if "--list-omega" in sys.argv:
    rows = [
        "arbitrary.future.id\t0\tdet\tarbitrary registry parity\tpython3 scripts/future.py --check\t30",
        "arbitrary.future.id\t1\tlive\tarbitrary registry posture\tpython3 scripts/future.py --live\t45",
    ]
    mode = os.environ.get("OMEGA_TEST_SENSOR_MODE")
    if mode == "reverse":
        rows.reverse()
    elif mode == "added":
        rows.append("new.sensor.id\t0\tdet\tnew registry contract\tpython3 scripts/new.py\t60")
    elif mode == "command":
        rows[0] = "arbitrary.future.id\t0\tdet\tarbitrary registry parity\tpython3 scripts/renamed.py --check\t30"
    print("\n".join(rows))
    raise SystemExit(0)
if "--run-omega" in sys.argv:
    raise SystemExit(0)
raise SystemExit(2)
PY
  chmod +x "$work/scripts/beat-sensors.py"
}

pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else echo "  MISMATCH ($3): want '$2' got '$1'"; fail=$((fail+1)); fi; }

# ── Case 1: every det child green → OMEGA HOLDS, exit 0 ──────────────────────────
write_stubs 0
set +e
out="$(bash "$work/scripts/omega.sh" --offline --quiet 2>&1)"; rc=$?
set -e
check "$rc" "0" "case1 exit"
echo "$out" | grep -q "OMEGA HOLDS" && check "holds" "holds" "case1 verdict" || check "missing" "holds" "case1 verdict"
python3 - "$work/logs/omega.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["schema_version"] == 1, d
assert d["generated_at"] == d["generated"], d
assert len(d["contract_hash"]) == 64, d
assert d["verdict"] == "HOLDS", d["verdict"]
assert d["strict"] is False, d
assert d["fail"] == 0, d
assert all({"rung", "tier", "status"} <= set(r) for r in d["rungs"]), "rung shape"
# every live rung must be SKIP in offline mode (never a silent PASS)
live = [r for r in d["rungs"] if r["tier"] == "live"]
assert live and all(r["status"] == "SKIP" for r in live), [r["status"] for r in live]
rows = {r["rung"]: r for r in d["rungs"]}
assert rows["ask-lineage convergence"]["status"] == "SKIP", rows
assert rows["arbitrary registry parity"]["status"] == "PASS", rows
assert rows["arbitrary registry posture"]["status"] == "SKIP", rows
print("  case1 stamp OK")
PY
base_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_hash"])' "$work/logs/omega.json")"

# ── Case 1b: normalized contract identity ignores row order, but changes on a new rung ────────────
OMEGA_TEST_SENSOR_MODE=reverse bash "$work/scripts/omega.sh" --offline --quiet >/dev/null
reverse_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_hash"])' "$work/logs/omega.json")"
check "$reverse_hash" "$base_hash" "case1b normalized sensor order"
OMEGA_TEST_SENSOR_MODE=added bash "$work/scripts/omega.sh" --offline --quiet >/dev/null
added_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_hash"])' "$work/logs/omega.json")"
if [ "$added_hash" != "$base_hash" ]; then
  check "changed" "changed" "case1b added sensor changes hash"
else
  check "unchanged" "changed" "case1b added sensor changes hash"
fi
OMEGA_TEST_SENSOR_MODE=command bash "$work/scripts/omega.sh" --offline --quiet >/dev/null
command_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_hash"])' "$work/logs/omega.json")"
if [ "$command_hash" != "$base_hash" ]; then
  check "changed" "changed" "case1b command changes hash"
else
  check "unchanged" "changed" "case1b command changes hash"
fi

# ── Case 1c: strict rejects the same otherwise-green offline run because live rungs SKIP ──────────
set +e
out="$(bash "$work/scripts/omega.sh" --offline --strict --quiet 2>&1)"; rc=$?
set -e
check "$rc" "1" "case1c strict exit"
echo "$out" | grep -q "OMEGA INCOMPLETE" && check "incomplete" "incomplete" "case1c verdict" || check "missing" "incomplete" "case1c verdict"
python3 - "$work/logs/omega.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["strict"] is True and d["verdict"] == "INCOMPLETE" and d["skip"] > 0, d
print("  case1c strict stamp OK")
PY

# ── Case 2: one det child red → OMEGA BROKEN, exit 1 ─────────────────────────────
write_stubs 1
set +e
out="$(bash "$work/scripts/omega.sh" --offline --quiet 2>&1)"; rc=$?
set -e
check "$rc" "1" "case2 exit"
echo "$out" | grep -q "OMEGA BROKEN" && check "broken" "broken" "case2 verdict" || check "missing" "broken" "case2 verdict"
python3 - "$work/logs/omega.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["verdict"] == "BROKEN" and d["fail"] >= 1, d
print("  case2 stamp OK")
PY

# ── Case 3: overnight-trial receipt is content-addressed, not a bare pass boolean ────────────────
cp "$real_watch" "$work/scripts/overnight-watch.py"
python3 - "$work/scripts/overnight-watch.py" "$work/logs/overnight-trial.json" <<'PY'
import datetime as dt
import hashlib, json, sys
script, output = sys.argv[1:]
start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
window_starts = [0, 90, 180, 270, 360, 390]
windows = [
    {"index": i, "start": (start + dt.timedelta(minutes=offset)).isoformat(),
     "end": (start + dt.timedelta(minutes=offset + 90)).isoformat(),
     "sample_count": 18, "value_receipts": 1, "owner_blockers": 0, "pass": True}
    for i, offset in enumerate(window_starts, start=1)
]
d = {
    "schema_version": "overnight-trial.v1", "window_start": "2026-07-01T00:00:00+00:00",
    "window_end": "2026-07-01T08:00:00+00:00", "duration_seconds": 28800, "hours": 8,
    "value_window_seconds": 5400, "window_count": 6, "windows": windows, "sample_count": 97,
    "value_receipts": 6, "owner_blockers": 0, "seam_count": 1, "vendor_seams": 1,
    "handoff_fresh": True, "operator_prompts": 0, "operator_prompt_samples_complete": True,
    "watch_alerts": 0, "coverage_ok": True, "duration_ok": True, "windows_ok": True,
    "evaluator_hash": hashlib.sha256(open(script, "rb").read()).hexdigest(), "input_hash": "0" * 64,
    "pass": True,
}
d["content_hash"] = hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
d["generated_at"] = "2026-07-01T08:00:00+00:00"
json.dump(d, open(output, "w"), indent=2, sort_keys=True)
PY
set +e
LIMEN_ROOT="$work" python3 "$work/scripts/overnight-watch.py" --check-trial >/dev/null 2>&1; rc=$?
set -e
check "$rc" "0" "case3 content-addressed trial"
python3 - "$work/logs/overnight-trial.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["input_hash"] = "f" * 64
json.dump(d, open(p, "w"), indent=2, sort_keys=True)
PY
set +e
LIMEN_ROOT="$work" python3 "$work/scripts/overnight-watch.py" --check-trial >/dev/null 2>&1; rc=$?
set -e
check "$rc" "1" "case3 tamper rejected"

echo
if [ "$fail" -eq 0 ]; then
  echo "omega.test.sh: PASS ($pass checks)"
else
  echo "omega.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
