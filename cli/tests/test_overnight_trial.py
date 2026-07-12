"""Prospective, append-bound eight-hour unattended-trial contract tests."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "overnight-watch.py"


class Clock:
    def __init__(self, value: dt.datetime):
        self.value = value


def _fresh_module(tmp_path, monkeypatch, start: dt.datetime):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_PRIVATE_SESSION_CORPUS", str(tmp_path / "private"))
    monkeypatch.setenv("LIMEN_OVERNIGHT_WATCH_RECEIPT", str(tmp_path / "logs" / "watch.jsonl"))
    monkeypatch.setenv("LIMEN_OVERNIGHT_TRIAL_RECEIPT", str(tmp_path / "logs" / "trial.json"))
    monkeypatch.setenv("LIMEN_OVERNIGHT_TRIAL_WINDOW", str(tmp_path / "logs" / "window.json"))
    monkeypatch.setenv("LIMEN_OVERNIGHT_TRIAL_OBSERVATIONS", str(tmp_path / "logs" / "trial-observations.jsonl"))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks.yaml").write_text('{"version":1,"tasks":[]}\n', encoding="utf-8")
    (tmp_path / "logs" / "handoff.json").write_text('{"fresh":true}\n', encoding="utf-8")
    spec = importlib.util.spec_from_file_location("overnight_trial_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    clock = Clock(start)
    monkeypatch.setattr(module, "utc_now", lambda: clock.value)
    monotonic_base = 10_000_000_000_000
    monkeypatch.setattr(
        module.time,
        "monotonic_ns",
        lambda: monotonic_base + int((clock.value - start).total_seconds() * 1_000_000_000),
    )
    monkeypatch.setattr(module, "_anchor_created_ns", lambda _path: int(start.timestamp() * 1_000_000_000))
    monkeypatch.setattr(
        module,
        "handoff_relay_snapshot",
        lambda **_kwargs: {"ok": True, "check_returncode": 0},
    )
    return module, clock


def _path_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "mode": stat.st_mode & 0o777}


def _write_prompt_authority(
    module,
    at: dt.datetime,
    *,
    operator_count: int = 0,
    scope: str = "all",
    stale: bool = False,
    unsupported: int = 0,
    unresolved: int = 0,
):
    at = at.astimezone(dt.timezone.utc).replace(microsecond=0)
    source = module.PROMPT_ATOM_SNAPSHOT
    source.parent.mkdir(parents=True, exist_ok=True)
    events = source.parent / "prompt-events.jsonl"
    outcomes = source.parent / "prompt-atom-outcomes.jsonl"
    if not events.exists():
        events.write_text("", encoding="utf-8")
    if not outcomes.exists():
        outcomes.write_text("", encoding="utf-8")
    actual_count, errors = module._operator_count_from_event_bytes(events.read_bytes())
    assert errors == 0
    assert actual_count == operator_count
    cursor = {
        "version": 2,
        "scanner_version": 2,
        "scope": scope,
        "target_scope": "all",
        "all_baseline_complete": scope == "all",
        "pending_files": 0,
        "source_errors": [],
        "unsupported_source_count": unsupported,
        "unresolved_unit_count": unresolved,
        "adapter_gaps": [],
        "source_families": {"fixture": {"discovered": 1, "converged": 1, "pending": 0, "errors": 0, "unsupported": 0}},
        "files": {},
        "last_scan_at": (at - dt.timedelta(minutes=20) if stale else at).isoformat(timespec="seconds"),
    }
    cursor_path = source.parent / "source-cursor.json"
    cursor_path.write_text(json.dumps(cursor, sort_keys=True), encoding="utf-8")
    snapshot = {
        "version": 1,
        "source_cursor_digest": module._cursor_digest(cursor),
        "source_scope": module._cursor_semantic(cursor),
        "coverage": {"operator_occurrences": operator_count},
        "validation": {"ok": True, "errors": []},
        "journal_signatures": {
            "events": _path_signature(events),
            "outcomes": _path_signature(outcomes),
            "cursor": _path_signature(cursor_path),
        },
    }
    source.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")


def _append_operator_occurrence(module, index: int) -> None:
    path = module.PROMPT_ATOM_SNAPSHOT.parent / "prompt-events.jsonl"
    row = {
        "occurrence": {"occurrence_id": f"operator-{index}", "authority": "operator"},
        "atoms": [],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _load_board(module) -> dict:
    return json.loads(module.TASKS_PATH.read_text())


def _append_task_event(
    module,
    at: dt.datetime,
    index: int,
    status: str,
    *,
    agent: str = "codex",
    session_id: str | None = None,
    predicate: str | None = None,
    receipt_target: str | None = None,
) -> None:
    board = _load_board(module)
    board.setdefault("tasks", []).append(
        {
            "id": f"TRIAL-{index:03d}",
            "status": status,
            "target_agent": agent,
            "predicate": predicate or "python3 -c 'raise SystemExit(0)'",
            "receipt_target": receipt_target or f"git:organvm/limen:docs/receipts/trial-{index}.json",
            "dispatch_log": [
                {
                    "timestamp": at.isoformat(timespec="seconds"),
                    "agent": agent,
                    "session_id": session_id or f"session-{index}",
                    "status": status,
                    "output": f"durable owner receipt {index}",
                }
            ],
        }
    )
    module.TASKS_PATH.write_text(json.dumps(board, sort_keys=True), encoding="utf-8")


def _watch_snapshot(at: dt.datetime) -> dict:
    return {
        "timestamp": at.isoformat(timespec="seconds"),
        "launchd": {"ok": True, "state": "running", "env": {}},
        "log_age_sec": 0,
        "heartbeat": {"latest_tick": {"timestamp": at.isoformat(timespec="seconds")}},
        "worker_count": 0,
        "heartbeat_child_count": 0,
        "stale_tick_count": 0,
        "handoff_relay": {"ok": True, "check_returncode": 0},
        "value_gate": {"returncode": 0},
        "dispatch_control": {"allow_dispatch": True},
        "plist_drift": [],
        "throughput": {"below_floor": False},
    }


def _install_proof_stubs(module, monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "_prove_terminal_event",
        lambda entry: {"event_id": entry["event_id"], "proof_hash": module.canonical_hash(entry)},
    )
    monkeypatch.setattr(
        module,
        "_prove_session_event",
        lambda entry: (
            {
                "event_id": entry["event_id"],
                "provider": "jules",
                "proof_hash": module.canonical_hash(entry),
            }
            if entry.get("agent") == "jules" and str(entry.get("session_id") or "").isdigit()
            else None
        ),
    )


def _start(module, start: dt.datetime):
    _write_prompt_authority(module, start)
    marker, changed = module.start_trial()
    assert changed is True
    return marker


def _observe(module, clock: Clock, at: dt.datetime, *, operator_count: int = 0):
    clock.value = at
    _write_prompt_authority(module, at, operator_count=operator_count)
    snapshot = _watch_snapshot(at)
    module.write_jsonl(snapshot)
    return module.append_trial_observation(snapshot)


def _run_trial(
    module,
    clock: Clock,
    start: dt.datetime,
    *,
    value_minutes: tuple[int, ...] = (60, 150, 240, 330, 420),
    seam_agent: str = "jules",
    seam_session: str = "12345678901234567890",
    omit_samples: set[int] | None = None,
    operator_at: int | None = None,
):
    marker = _start(module, start)
    operator_count = 0
    for minute in range(5, 481, 5):
        at = start + dt.timedelta(minutes=minute)
        if minute in value_minutes:
            _append_task_event(module, at, minute, "done")
        if minute == 30:
            _append_task_event(
                module,
                at,
                900,
                "in_progress",
                agent=seam_agent,
                session_id=seam_session,
            )
        if operator_at is not None and minute == operator_at:
            _append_operator_occurrence(module, 1)
            operator_count = 1
        if minute not in (omit_samples or set()):
            _observe(module, clock, at, operator_count=operator_count)
    clock.value = start + dt.timedelta(hours=8)
    return marker, module.maybe_finalize_trial()


def test_trial_passes_rebuilds_and_is_byte_idempotent(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    active, result = _run_trial(module, clock, start)
    assert result and result.get("receipt")
    first_bytes = module.TRIAL_PATH.read_bytes()

    second, changed_again = module.finalize_trial(active)

    assert result["receipt"]["pass"] is True
    assert result["receipt"]["operator_interventions"] == 0
    assert result["receipt"]["seam_count"] == 1
    assert result["receipt"]["max_value_gap_seconds"] == 5400
    assert changed_again is False
    assert second == result["receipt"]
    assert module.TRIAL_PATH.read_bytes() == first_bytes
    assert module.check_trial_receipt() == (True, [])
    serialized = module.TRIAL_PATH.read_text()
    assert "TRIAL-" not in serialized
    assert "session-" not in serialized
    assert "predicate" not in serialized
    assert "receipt_target" not in serialized


def test_preseeded_future_events_and_samples_cannot_count(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    for index, minute in enumerate((60, 150, 240, 330, 420), start=1):
        _append_task_event(module, start + dt.timedelta(minutes=minute), index, "done")
    _append_task_event(
        module,
        start + dt.timedelta(minutes=30),
        99,
        "in_progress",
        agent="jules",
        session_id="12345678901234567890",
    )
    synthetic = [_watch_snapshot(start + dt.timedelta(minutes=minute)) for minute in range(5, 481, 5)]
    module.RECEIPT_JSONL.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in synthetic), encoding="utf-8"
    )
    marker = _start(module, start)
    for minute in range(5, 481, 5):
        _observe(module, clock, start + dt.timedelta(minutes=minute))
    clock.value = start + dt.timedelta(hours=8)
    receipt = module.build_trial_receipt(marker)

    assert receipt["value_done_events"] == 0
    assert receipt["seam_count"] == 0
    assert receipt["pass"] is False


def test_finalize_refuses_before_due_time(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    marker = _start(module, start)
    clock.value = start + dt.timedelta(hours=1)

    with pytest.raises(module.TrialContractError, match="cannot be finalized before"):
        module.finalize_trial(marker)


def test_wall_clock_jump_cannot_backfill_eight_hours(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    marker = _start(module, start)
    clock.value = start + dt.timedelta(hours=8)
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: marker["monotonic_start_ns"] + 1_000_000_000)

    with pytest.raises(module.TrialContractError, match="monotonic custody"):
        module.finalize_trial(marker)


@pytest.mark.parametrize(
    "scope,stale,unsupported,unresolved",
    [("partial:all", False, 0, 0), ("all", True, 0, 0), ("all", False, 2, 0), ("all", False, 0, 3)],
)
def test_start_fails_closed_without_fresh_exact_prompt_authority(
    tmp_path, monkeypatch, scope, stale, unsupported, unresolved
):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _write_prompt_authority(
        module,
        start,
        scope=scope,
        stale=stale,
        unsupported=unsupported,
        unresolved=unresolved,
    )

    with pytest.raises(module.TrialContractError, match="fresh exact all/all"):
        module.start_trial()


def test_stored_prompt_freshness_lie_is_rejected(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _write_prompt_authority(module, start)
    snapshot = module.prompt_authority_snapshot(start)
    snapshot.update({"last_scan_at": "2000-01-01T00:00:00+00:00", "age_sec": 0, "fresh": True})

    errors = module._prompt_snapshot_errors(snapshot, start)

    assert "prompt authority age is not derived from scan time" in errors
    assert "prompt authority freshness claim is invalid" in errors


def test_arbitrary_session_string_does_not_count_as_seam(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(
        module,
        clock,
        start,
        seam_agent="not-a-provider",
        seam_session="arbitrary-string",
    )

    assert result["receipt"]["seam_count"] == 0
    assert result["receipt"]["pass"] is False


def test_failed_predicate_or_missing_receipt_does_not_count(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    monkeypatch.setattr(module, "_receipt_target_proof", lambda _target: None)
    monkeypatch.setattr(
        module,
        "_prove_session_event",
        lambda entry: {
            "event_id": entry["event_id"],
            "provider": "jules",
            "proof_hash": module.canonical_hash(entry),
        },
    )
    _, result = _run_trial(module, clock, start)

    assert result["receipt"]["value_done_events"] == 0
    assert result["receipt"]["pass"] is False


def test_real_predicate_and_receipt_proof_are_both_required(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    entry = {
        "event_id": "a" * 64,
        "predicate": "test -f tasks.yaml",
        "receipt_target": "git:organvm/limen:docs/receipt.json",
        "output_present": True,
    }
    monkeypatch.setattr(module, "_receipt_target_proof", lambda _target: {"object_hash": "b" * 64})
    assert module._prove_terminal_event(entry) is not None
    entry["predicate"] = "test -f missing-file"
    assert module._prove_terminal_event(entry) is None


@pytest.mark.parametrize(
    "predicate",
    ["sh -c 'rm -rf /tmp/x'", "gh issue close 1 --repo organvm/limen", "test -f tasks.yaml && touch x"],
)
def test_mutating_predicates_are_never_executed(tmp_path, monkeypatch, predicate):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)

    assert module._predicate_is_observation_only(predicate) is False
    assert module._predicate_proof(predicate) is None


def test_rolling_value_gap_over_ninety_minutes_fails(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(module, clock, start, value_minutes=(5, 175, 180, 355, 360, 480))

    receipt = result["receipt"]
    assert receipt["max_value_gap_seconds"] == 10500
    assert receipt["rolling_value_ok"] is False
    assert receipt["pass"] is False


def test_sample_gap_over_ten_minutes_fails(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(module, clock, start, omit_samples={100, 105})

    assert result["receipt"]["max_sample_gap_seconds"] == 900
    assert result["receipt"]["coverage_ok"] is False
    assert result["receipt"]["pass"] is False


def test_operator_journal_delta_fails_trial(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(module, clock, start, operator_at=240)

    assert result["receipt"]["operator_interventions"] == 1
    assert result["receipt"]["pass"] is False


@pytest.mark.parametrize("source", ["watch", "observation", "tasks", "prompt"])
def test_source_rewrite_or_truncation_breaks_checker(tmp_path, monkeypatch, source):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    if source == "prompt":
        events = module.PROMPT_ATOM_SNAPSHOT.parent / "prompt-events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        events.write_text(
            json.dumps(
                {"occurrence": {"occurrence_id": "derived-1", "authority": "derived"}, "atoms": []},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    _run_trial(module, clock, start)
    if source == "watch":
        payload = bytearray(module.RECEIPT_JSONL.read_bytes())
        payload[5] = ord("X")
        module.RECEIPT_JSONL.write_bytes(bytes(payload))
    elif source == "observation":
        module.TRIAL_OBSERVATION_PATH.write_bytes(module.TRIAL_OBSERVATION_PATH.read_bytes()[:-10])
    elif source == "tasks":
        board = _load_board(module)
        board["tasks"] = board["tasks"][1:]
        module.TASKS_PATH.write_text(json.dumps(board), encoding="utf-8")
    else:
        events = module.PROMPT_ATOM_SNAPSHOT.parent / "prompt-events.jsonl"
        events.write_text("", encoding="utf-8")

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert errors


def test_active_trial_cannot_be_replaced_or_backfilled(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _start(module, start)

    with pytest.raises(module.TrialContractError, match="already active"):
        module.start_trial()
    with pytest.raises(SystemExit):
        module.main(["--start-trial", "--trial-start", "2026-06-30T00:00:00Z"])


def test_missing_or_backdated_prospective_anchor_fails_closed(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    marker = _start(module, start)
    module._trial_anchor_path(marker).unlink()

    assert "prospective trial anchor is missing or malformed" in module._active_marker_errors(marker)
