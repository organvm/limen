from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GUARD_SCRIPT = ROOT / "scripts" / "closeout-resource-guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("closeout_resource_guard", GUARD_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_closeout_fast_keeps_lifecycle_regressions_opt_in():
    script = (ROOT / "scripts" / "closeout-fast.sh").read_text(encoding="utf-8")

    assert "LIMEN_CLOSEOUT_RUN_LIFECYCLE_TESTS" in script
    assert "LIMEN_CLOSEOUT_LIFECYCLE_TEST_TIMEOUT" in script
    default_path, _opt_in = script.split('if [[ "${LIMEN_CLOSEOUT_RUN_LIFECYCLE_TESTS:-0}" == "1" ]]', 1)
    assert "test_session_lifecycle_pressure.py" not in default_path


def test_closeout_fast_default_path_includes_resource_guard_and_excludes_full_gates():
    script = (ROOT / "scripts" / "closeout-fast.sh").read_text(encoding="utf-8")

    assert "closeout-resource-guard.py --mode closeout-fast --warn-only" in script
    assert "scripts/verify-whole.sh" not in script
    assert "python3 -m pytest \\" in script
    assert "python3 -m pytest web/api/tests cli/tests" not in script
    assert "cli/tests/test_worktree_debt.py::test_reachable_from_remote_uses_single_contains_query" in script


def test_closeout_fast_reports_live_root_status_without_failing_fast_closeout():
    script = (ROOT / "scripts" / "closeout-fast.sh").read_text(encoding="utf-8")

    assert "report_live_root_gate" in script
    assert 'record_gate "$label" "blocked-report"' in script
    assert '"Report live-root gate" python3 scripts/live-root-gate.py' in script
    assert "live-root gate is report-only in closeout-fast" in script
    assert "Status: `ready`" in script


def test_closeout_fast_receipt_records_gate_statuses():
    script = (ROOT / "scripts" / "closeout-fast.sh").read_text(encoding="utf-8")

    assert "Closeout-fast receipt" in script
    assert "GATE_NAMES" in script
    assert "GATE_STATUSES" in script
    assert '"status": status' in script
    assert "logs/closeout-fast.json" in script
    assert "logs/closeout-fast.md" in script


def test_verify_whole_runs_resource_guard_only_outside_ci():
    script = (ROOT / "scripts" / "verify-whole.sh").read_text(encoding="utf-8")
    guard = GUARD_SCRIPT.read_text(encoding="utf-8")

    assert 'if [[ -z "${CI:-}" ]]' in script
    assert "python3 scripts/closeout-resource-guard.py --mode verify-whole" in script
    assert "Skip local closeout resource guard in CI" in script
    assert "LIMEN_VERIFY_ALLOW_CONCURRENT" in guard


def test_resource_guard_verify_mode_blocks_active_heavy_work():
    guard = _load_guard()
    processes = [
        guard.ProcessInfo(101, "bash scripts/verify-whole.sh"),
        guard.ProcessInfo(102, "python3 -m pytest cli/tests -q"),
        guard.ProcessInfo(103, "python3 scripts/worktree-debt.py --json"),
        guard.ProcessInfo(104, "du -sh /Users/4jp/Workspace"),
        guard.ProcessInfo(105, "claude agents run verifier"),
    ]
    launchd = [guard.LaunchdInfo("com.limen.heartbeat", 4242, True)]

    hazards = guard.hazards_from_snapshots(processes, launchd)
    result = guard.evaluate(mode="verify-whole", warn_only=False, allow_override=False, hazards=hazards)

    hazard_ids = {hazard["id"] for hazard in result["hazards"]}
    assert result["status"] == "blocked"
    assert result["exit_code"] == 12
    assert "verify-whole-active" in hazard_ids
    assert "full-pytest-active" in hazard_ids
    assert "worktree-debt-active" in hazard_ids
    assert "broad-du-active" in hazard_ids
    assert "claude-agents-active" in hazard_ids
    assert "heartbeat-active" in hazard_ids


def test_resource_guard_closeout_fast_warn_mode_reports_without_failing():
    guard = _load_guard()
    hazards = guard.hazards_from_snapshots(
        [guard.ProcessInfo(201, "python3 scripts/session-lifecycle-pressure.py --write")],
        [guard.LaunchdInfo("com.limen.watchdog", 999, True)],
    )

    result = guard.evaluate(mode="closeout-fast", warn_only=True, allow_override=False, hazards=hazards)
    text = guard.render_text(result)

    assert result["status"] == "warn"
    assert result["exit_code"] == 0
    assert "bash scripts/closeout-fast.sh" in text
    assert "remote CI verify receipt" in text
    for forbidden in ("kill", "pkill", "launchctl bootout", "launchctl kickstart"):
        assert forbidden not in text


def test_resource_guard_override_allows_verify_mode():
    guard = _load_guard()
    hazards = guard.hazards_from_snapshots(
        [guard.ProcessInfo(301, "python3 scripts/generate-backlog.py --apply")],
        [],
    )

    result = guard.evaluate(mode="verify-whole", warn_only=False, allow_override=True, hazards=hazards)

    assert result["status"] == "override"
    assert result["exit_code"] == 0
