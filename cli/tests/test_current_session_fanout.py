from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "current-session-fanout.py"


def _load():
    spec = importlib.util.spec_from_file_location("current_session_fanout", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_session(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def _args(session: Path, **kwargs):
    defaults = {
        "session": str(session),
        "packet_id": "PLAN-03-f0b8bc86",
        "theme": "dynamic-substrate",
        "executor_lanes": "codex,opencode",
        "source_plan_hash": [],
        "source_prompt_hash": [],
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def test_full_session_derivation_records_local_blocker_without_stopping_product(tmp_path: Path):
    mod = _load()
    mod.ROOT = tmp_path
    mod.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    mod.PRIVATE_INDEX = mod.PRIVATE_ROOT / "lifecycle" / "current-session-fanout.json"
    mod.DOC_PATH = tmp_path / "docs" / "current-session-fanout.md"
    session = tmp_path / "session.jsonl"
    early_prompt = "GLOBAL_PRODUCT_SECRET_TEXT product selection revenue value"
    late_prompt = "local domus substrate blocker"
    _write_session(
        session,
        [
            {"timestamp": "2026-06-30T00:00:00Z", "type": "session_meta", "payload": {"type": "session_meta"}},
            {
                "timestamp": "2026-06-30T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"text": early_prompt}]},
            },
            {
                "timestamp": "2026-06-30T00:00:02Z",
                "type": "turn_context",
                "payload": {"turn_id": "t1"},
            },
            {
                "timestamp": "2026-06-30T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": "Permission denied while running domus preflight; local blocker recorded",
                },
            },
            {
                "timestamp": "2026-06-30T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": late_prompt},
            },
        ],
    )

    snapshot = mod.build_snapshot(_args(session))
    markdown = mod.render_markdown(snapshot)

    packets = {packet["packet_key"]: packet for packet in snapshot["owner_packets"]}
    assert snapshot["coverage"]["records_read"] == 5
    assert snapshot["coverage"]["turn_count"] == 1
    assert "global-product-selection" in packets
    assert "blocked-local-work" in packets
    assert packets["blocked-local-work"]["status"] == "blocked-local-recorded"
    assert packets["global-product-selection"]["status"] == "active"
    assert packets["global-product-selection"]["continues_despite_local_blockers"] is True
    assert snapshot["continuation_policy"]["local_blockers_do_not_stop_global_selection"] is True
    assert mod.stable_hash(early_prompt) in snapshot["provenance"]["source_prompt_hashes"]
    assert early_prompt not in json.dumps(snapshot)
    assert early_prompt not in markdown


def test_owner_packets_emit_executor_criteria_and_predicates(tmp_path: Path):
    mod = _load()
    mod.ROOT = tmp_path
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [
            {
                "timestamp": "2026-06-30T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"text": "dynamic-substrate fanout owner packet verification predicate"}],
                },
            },
            {
                "timestamp": "2026-06-30T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "update_plan",
                    "arguments": json.dumps(
                        {"plan": [{"step": "plan current-session fanout stream", "status": "in_progress"}]}
                    ),
                },
            },
        ],
    )

    snapshot = mod.build_snapshot(_args(session))

    assert snapshot["owner_packets"]
    for packet in snapshot["owner_packets"]:
        assert packet["executor_criteria"]
        assert packet["verification_predicates"]
    planner = {
        packet["packet_key"]: packet for packet in snapshot["owner_packets"]
    }["current-session-fanout-planner"]
    assert any("py_compile" in predicate for predicate in planner["verification_predicates"])
    assert snapshot["provenance"]["source_plan_hashes"]


def test_provided_hashes_are_preserved_without_raw_bodies(tmp_path: Path):
    mod = _load()
    mod.ROOT = tmp_path
    session = tmp_path / "session.jsonl"
    _write_session(
        session,
        [
            {
                "timestamp": "2026-06-30T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"text": "product selection"}],
                },
            }
        ],
    )

    snapshot = mod.build_snapshot(
        _args(
            session,
            source_plan_hash=["7eb608baa99c,c93bc2c89ad8"],
            source_prompt_hash=["4c72667b4d9a1d74b666b8e5"],
        )
    )

    assert "7eb608baa99c" in snapshot["provenance"]["source_plan_hashes"]
    assert "c93bc2c89ad8" in snapshot["provenance"]["source_plan_hashes"]
    assert "4c72667b4d9a1d74b666b8e5" in snapshot["provenance"]["source_prompt_hashes"]
    assert snapshot["privacy"]["raw_prompt_bodies_stored"] is False
    assert snapshot["privacy"]["raw_plan_bodies_stored"] is False
