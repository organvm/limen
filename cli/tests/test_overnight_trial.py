"""Fail-closed prospective eight-hour unattended-trial contract tests."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "overnight-watch.py"


def _fresh_module(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_PRIVATE_SESSION_CORPUS", str(tmp_path / "private"))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks.yaml").write_text("version: 1\ntasks: []\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("overnight_trial_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def _write_prompt_authority(module, at: dt.datetime, count: int = 10, *, scope: str = "all", stale: bool = False):
    at = at.astimezone(dt.timezone.utc).replace(microsecond=0)
    cursor = {
        "version": 2,
        "scanner_version": 2,
        "scope": scope,
        "target_scope": "all",
        "all_baseline_complete": scope == "all",
        "pending_files": 0,
        "source_errors": [],
        "unsupported_source_count": 0,
        "unresolved_unit_count": 0,
        "adapter_gaps": [],
        "source_families": {"fixture": {"discovered": 1, "converged": 1, "pending": 0, "errors": 0, "unsupported": 0}},
        "files": {},
        "last_scan_at": (at - dt.timedelta(minutes=20) if stale else at).isoformat(timespec="seconds"),
    }
    source = module.PROMPT_ATOM_SNAPSHOT
    source.parent.mkdir(parents=True, exist_ok=True)
    cursor_path = source.parent / "source-cursor.json"
    cursor_path.write_text(json.dumps(cursor, sort_keys=True), encoding="utf-8")
    stat = cursor_path.stat()
    snapshot = {
        "version": 1,
        "source_cursor_digest": module._cursor_digest(cursor),
        "source_scope": {
            key: value
            for key, value in cursor.items()
            if key
            in {
                "scanner_version",
                "scope",
                "target_scope",
                "all_baseline_complete",
                "pending_files",
                "source_errors",
                "unsupported_source_count",
                "unresolved_unit_count",
                "adapter_gaps",
                "source_families",
            }
        },
        "coverage": {"operator_occurrences": count},
        "validation": {"ok": True, "errors": []},
        "journal_signatures": {"cursor": {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}},
        "semantic_digest": "1" * 64,
    }
    source.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")


def _event_task(index: int, minute: int, status: str, start: dt.datetime) -> dict:
    timestamp = start + dt.timedelta(minutes=minute)
    return {
        "id": f"TRIAL-{index:03d}",
        "status": status,
        "target_agent": "codex",
        "predicate": f"python3 scripts/check-{index}.py",
        "receipt_target": f"git:organvm/limen:docs/receipts/trial-{index}.json",
        "dispatch_log": [
            {
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "agent": "codex",
                "session_id": f"session-{index}",
                "status": status,
                "output": f"durable owner receipt {index}",
            }
        ],
    }


def _write_board(module, start: dt.datetime, *, values: bool = True, blockers: bool = False, seam: bool = True):
    tasks: list[dict] = []
    if values or blockers:
        terminal = "done" if values else "failed_blocked"
        for index, minute in enumerate((60, 150, 240, 330, 420), start=1):
            tasks.append(_event_task(index, minute, terminal, start))
    if seam:
        tasks.append(_event_task(90, 30, "in_progress", start))
    payload = {"version": 1, "tasks": tasks}
    module.TASKS_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _start(module, start: dt.datetime):
    _write_prompt_authority(module, start)
    marker, changed = module.start_trial(now=start)
    assert changed is True
    return marker


def _samples(
    module,
    start: dt.datetime,
    *,
    minutes: list[int] | None = None,
    operator_after: int | None = None,
) -> list[dict]:
    rows: list[dict] = []
    for minute in minutes if minutes is not None else list(range(0, 481, 5)):
        timestamp = start + dt.timedelta(minutes=minute)
        count = 11 if operator_after is not None and minute >= operator_after else 10
        _write_prompt_authority(module, timestamp, count)
        rows.append(
            {
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "status": "ok",
                "alerts": [],
                "handoff_relay": {"ok": True, "check_returncode": 0},
                "task_events": module.task_event_snapshot(timestamp),
                "prompt_authority": module.prompt_authority_snapshot(timestamp),
            }
        )
    _write_jsonl(module.RECEIPT_JSONL, rows)
    return rows


def _passing_trial(module, start: dt.datetime):
    _write_board(module, start)
    active = _start(module, start)
    _samples(module, start)
    result = module.maybe_finalize_trial(now=start + dt.timedelta(hours=8))
    assert result and result.get("receipt")
    return active, result


def test_trial_passes_rebuilds_and_is_byte_idempotent(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    active, result = _passing_trial(module, start)
    first_bytes = module.TRIAL_PATH.read_bytes()

    second, changed_again = module.finalize_trial(active)

    assert result["receipt"]["pass"] is True
    assert result["receipt"]["window_count"] == 6
    assert result["receipt"]["operator_interventions"] == 0
    assert result["receipt"]["seam_count"] == 1
    assert changed_again is False
    assert second == result["receipt"]
    assert module.TRIAL_PATH.read_bytes() == first_bytes
    assert module.check_trial_receipt() == (True, [])


def test_sparse_ninety_minute_samples_fail_coverage(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start)
    marker = _start(module, start)
    _samples(module, start, minutes=[0, 90, 180, 270, 360, 450, 480])

    receipt = module.build_trial_receipt(marker)

    assert receipt["pass"] is False
    assert receipt["coverage_ok"] is False
    assert receipt["max_sample_gap_seconds"] == 5400


def test_self_consistent_arbitrary_input_hash_is_rejected(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _, result = _passing_trial(module, start)
    receipt = dict(result["receipt"])
    receipt["input_hash"] = "0" * 64
    deterministic = {key: value for key, value in receipt.items() if key not in {"generated_at", "content_hash"}}
    receipt["content_hash"] = module.canonical_hash(deterministic)
    module.TRIAL_PATH.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    terminal = json.loads(module.TRIAL_WINDOW_PATH.read_text())
    terminal["receipt_input_hash"] = receipt["input_hash"]
    terminal["receipt_content_hash"] = receipt["content_hash"]
    terminal["content_hash"] = module.canonical_hash(
        {key: value for key, value in terminal.items() if key != "content_hash"}
    )
    module.TRIAL_WINDOW_PATH.write_text(json.dumps(terminal, sort_keys=True), encoding="utf-8")

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert "trial receipt does not match exact bounded source reconstruction" in errors


def test_active_trial_cannot_be_replaced_or_backfilled(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start)
    _start(module, start)

    with pytest.raises(module.TrialContractError, match="already active"):
        module.start_trial(now=start + dt.timedelta(minutes=1))
    with pytest.raises(SystemExit):
        module.main(["--start-trial", "--trial-start", "2026-06-30T00:00:00Z"])


def test_tampered_marker_evaluator_or_duration_fails_closed(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start)
    marker = _start(module, start)
    marker["evaluator_hash"] = "f" * 64
    marker["window_end"] = (start + dt.timedelta(hours=9)).isoformat(timespec="seconds")
    marker["content_hash"] = module.canonical_hash(
        {key: value for key, value in marker.items() if key != "content_hash"}
    )
    module.TRIAL_WINDOW_PATH.write_text(json.dumps(marker), encoding="utf-8")

    result = module.maybe_finalize_trial(now=start + dt.timedelta(hours=9))

    assert result and "error" in result
    assert "exactly eight hours" in result["error"]
    assert "evaluator changed" in result["error"]


@pytest.mark.parametrize("scope,stale", [("partial:all", False), ("all", True)])
def test_trial_start_requires_fresh_exact_prompt_authority(tmp_path, monkeypatch, scope, stale):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start)
    _write_prompt_authority(module, start, scope=scope, stale=stale)

    with pytest.raises(module.TrialContractError, match="fresh exact all/all"):
        module.start_trial(now=start)


def test_operator_occurrence_delta_fails_trial(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start)
    marker = _start(module, start)
    _samples(module, start, operator_after=240)

    receipt = module.build_trial_receipt(marker)

    assert receipt["operator_interventions"] == 1
    assert receipt["pass"] is False


def test_static_redirects_are_not_owner_blocked_events(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start, values=False, blockers=False, seam=True)
    marker = _start(module, start)
    rows = _samples(module, start)
    for row in rows:
        row["dispatch_control"] = {"allow_dispatch": False, "next_command": "python3 scripts/owner.py"}
        row["value_gate"] = {"gate": {"next_action": {"source": "owner_packet"}}}
    _write_jsonl(module.RECEIPT_JSONL, rows)

    receipt = module.build_trial_receipt(marker)

    assert receipt["owner_blocked_events"] == 0
    assert receipt["windows_ok"] is False
    assert receipt["pass"] is False


def test_typed_owner_blocked_dispatch_events_satisfy_windows(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start, values=False, blockers=True, seam=True)
    marker = _start(module, start)
    _samples(module, start)

    receipt = module.build_trial_receipt(marker)

    assert receipt["owner_blocked_events"] == 5
    assert receipt["windows_ok"] is True
    assert receipt["pass"] is True


@pytest.mark.parametrize("field,value", [("predicate", "TODO"), ("receipt_target", "tmp/result.json")])
def test_untyped_or_nondurable_terminal_events_do_not_count(tmp_path, monkeypatch, field, value):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start)
    board = json.loads(module.TASKS_PATH.read_text())
    for task in board["tasks"]:
        if task["status"] == "done":
            task[field] = value
    module.TASKS_PATH.write_text(json.dumps(board), encoding="utf-8")
    marker = _start(module, start)
    _samples(module, start)

    receipt = module.build_trial_receipt(marker)

    assert receipt["value_done_events"] == 0
    assert receipt["windows_ok"] is False
    assert receipt["pass"] is False


def test_lane_token_and_launch_proxies_do_not_count_as_seams(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start, seam=False)
    marker = _start(module, start)
    rows = _samples(module, start)
    for index, row in enumerate(rows):
        row["heartbeat"] = {
            "latest_async": {"raw": "launched 1", "launched": 1},
            "latest_dispatch_lanes": "vendor-a" if index < 2 else "vendor-b",
        }
        row["token_report"] = {"session_count": index + 1}
    _write_jsonl(module.RECEIPT_JSONL, rows)

    receipt = module.build_trial_receipt(marker)

    assert receipt["seam_count"] == 0
    assert receipt["pass"] is False


@pytest.mark.parametrize("mutation", ["missing-alerts", "alert-status", "malformed-json"])
def test_incomplete_or_alert_samples_fail_closed(tmp_path, monkeypatch, mutation):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start)
    marker = _start(module, start)
    rows = _samples(module, start)
    if mutation == "missing-alerts":
        rows[10].pop("alerts")
        _write_jsonl(module.RECEIPT_JSONL, rows)
    elif mutation == "alert-status":
        rows[10]["status"] = "alert"
        _write_jsonl(module.RECEIPT_JSONL, rows)
    else:
        with module.RECEIPT_JSONL.open("a", encoding="utf-8") as handle:
            handle.write("{malformed\n")

    receipt = module.build_trial_receipt(marker)

    assert receipt["pass"] is False


def test_source_mutation_after_finalization_breaks_omega_check(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _passing_trial(module, start)
    board = json.loads(module.TASKS_PATH.read_text())
    board["tasks"].append(_event_task(999, 120, "done", start))
    module.TASKS_PATH.write_text(json.dumps(board), encoding="utf-8")

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert "trial receipt does not match exact bounded source reconstruction" in errors


def test_default_one_shot_auto_finalizes_due_marker(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    _write_board(module, start)
    _start(module, start)
    _samples(module, start)
    monkeypatch.setattr(
        module,
        "build_snapshot",
        lambda **_kwargs: {"status": "ok", "alerts": [], "dispatch_control": {"allow_dispatch": True}},
    )
    monkeypatch.setattr(module, "heal", lambda _snapshot: [])
    monkeypatch.setattr(module, "write_receipts", lambda _snapshot: None)
    monkeypatch.setattr(module, "utc_now", lambda: start + dt.timedelta(hours=8))

    rc = module.run_once(dry_run=False, json_output=False)

    assert rc == 0
    assert json.loads(module.TRIAL_WINDOW_PATH.read_text())["active"] is False
    assert module.check_trial_receipt() == (True, [])
