"""Eight-hour unattended-trial finalization and content-addressing tests."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "overnight-watch.py"


def _fresh_module(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("overnight_trial_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def _trial_inputs(module, *, owner_blocked: bool = False, alert: bool = False):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(hours=8)
    watch = []
    ticks = []
    for index in range(17):
        timestamp = start + dt.timedelta(minutes=30 * index)
        launched = 1 if index == 1 else 0
        route = {
            "allow_dispatch": not owner_blocked,
            "next_command": "python3 scripts/owner-packet.py --write" if owner_blocked else "",
        }
        gate = {
            "action": "owner_route" if owner_blocked else "continue_current_work",
            "evidence": {"next_product_owner": "organvm/example"} if owner_blocked else {},
            "next_action": (
                {
                    "source": "owner_packet",
                    "command": "python3 scripts/owner-packet.py --write",
                }
                if owner_blocked
                else {}
            ),
            "pressures": {"value_commits": index},
        }
        watch.append(
            {
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "status": "blocked" if owner_blocked else "ok",
                "alerts": ([{"id": "WATCH_ALERT", "evidence": "x"}] if alert and index == 8 else []),
                "handoff_relay": {"ok": True},
                "operator_prompts": {"count": 0, "source": "noninteractive-one-shot"},
                "dispatch_control": route,
                "value_gate": {"gate": gate},
                "heartbeat": {
                    "latest_async": {
                        "raw": f"async event {index}" if launched else "async idle",
                        "launched": launched,
                    },
                    "latest_dispatch_lanes": "codex,jules",
                },
                "token_report": {"session_count": 1 if index == 0 else 2},
            }
        )
        ticks.append(
            {
                "ts": timestamp.isoformat(timespec="seconds"),
                "done": 0 if owner_blocked else index,
                "archived": 0,
            }
        )
    _write_jsonl(module.RECEIPT_JSONL, watch)
    _write_jsonl(module.TICKS_PATH, ticks)
    return start, end, watch


def test_eight_hour_trial_passes_and_is_byte_idempotent(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start, end, _ = _trial_inputs(module)

    first, changed = module.finalize_trial(start, end)
    first_bytes = module.TRIAL_PATH.read_bytes()
    second, changed_again = module.finalize_trial(start, end)

    assert changed is True
    assert changed_again is False
    assert module.TRIAL_PATH.read_bytes() == first_bytes
    assert second == first
    assert first["pass"] is True
    assert first["hours"] == 8
    assert first["window_count"] == 6
    assert first["seam_count"] >= 1
    assert first["operator_prompts"] == 0
    assert first["watch_alerts"] == 0
    assert first["handoff_fresh"] is True
    assert len(first["evaluator_hash"]) == 64
    assert len(first["input_hash"]) == 64
    assert len(first["content_hash"]) == 64
    assert "organvm/example" not in first_bytes.decode()
    assert "owner-packet" not in first_bytes.decode()
    assert module.check_trial_receipt() == (True, [])


def test_every_ninety_minute_window_requires_value_or_owner_blocker(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start, end, watch = _trial_inputs(module)
    for record in watch:
        record["value_gate"]["gate"]["pressures"]["value_commits"] = 0
    ticks = [{"ts": record["timestamp"], "done": 0, "archived": 0} for record in watch]
    _write_jsonl(module.RECEIPT_JSONL, watch)
    _write_jsonl(module.TICKS_PATH, ticks)

    receipt = module.build_trial_receipt(start, end)

    assert receipt["pass"] is False
    assert receipt["windows_ok"] is False
    assert all(window["pass"] is False for window in receipt["windows"])


def test_owner_routed_blocker_satisfies_each_value_window(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start, end, _ = _trial_inputs(module, owner_blocked=True)

    receipt = module.build_trial_receipt(start, end)

    assert receipt["windows_ok"] is True
    assert receipt["owner_blockers"] >= receipt["window_count"]
    assert receipt["pass"] is True


def test_trial_fails_closed_on_alert_or_uninstrumented_prompt_sample(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start, end, watch = _trial_inputs(module, alert=True)
    watch[4].pop("operator_prompts")
    _write_jsonl(module.RECEIPT_JSONL, watch)

    receipt = module.build_trial_receipt(start, end)

    assert receipt["pass"] is False
    assert receipt["watch_alerts"] == 1
    assert receipt["operator_prompt_samples_complete"] is False


def test_due_active_marker_auto_finalizes_once(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    start, end, _ = _trial_inputs(module)
    marker, changed = module.start_trial(start)

    result = module.maybe_finalize_trial(now=end)
    second = module.maybe_finalize_trial(now=end + dt.timedelta(minutes=1))

    assert changed is True
    assert marker["active"] is True
    assert result and result["receipt"]["pass"] is True
    assert second is None
    assert json.loads(module.TRIAL_WINDOW_PATH.read_text())["active"] is False
