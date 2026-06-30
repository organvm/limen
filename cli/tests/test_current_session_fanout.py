from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "current_session_fanout_under_test",
        ROOT / "scripts" / "current-session-fanout.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_current_session_fanout_uses_full_session_and_keeps_local_blockers_scoped(
    tmp_path: Path,
) -> None:
    session = tmp_path / "session.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:00:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"text": "Use 10 Codex planner worktrees for the full fleet."}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:01:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "update_plan",
                            "arguments": json.dumps(
                                {"plan": [{"step": "derive owner packets from the full session", "status": "in_progress"}]}
                            ),
                            "call_id": "plan-call",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:02:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "exec_command",
                            "arguments": json.dumps({"cmd": "domus up --dry-run"}),
                            "call_id": "domus-call",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:02:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "call_id": "domus-call",
                            "output": "Process exited with code 1\nOutput:\n! Storage lifecycle preflight blocked\n  - /Volumes/4444-iivii is not mounted\n",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:03:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": "exec_command",
                            "arguments": json.dumps({"cmd": "python3 scripts/product-ledger.py --refresh"}),
                            "call_id": "product-call",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:03:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "call_id": "product-call",
                            "output": "Process exited with code 0\nOutput:\nproduct-ledger: active products=4; wrote docs/product-ledger.md\n",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:04:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"text": "latest turn only says thanks"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    mod = _load()

    snap = mod.build_snapshot(
        Namespace(
            session=str(session),
            packet_id="PLAN-11-f3f5e6a4",
            theme="codex-planner-worktrees",
            source_plan_hash=["7eb608baa99c"],
            source_prompt_hash=["4c72667b4d9a1d74b666b8e5"],
        )
    )

    assert snap["coverage"]["user_message_occurrences"] == 2
    assert snap["coverage"]["unique_plan_hashes"] == 1
    assert "codex-planner-worktrees" in snap["themes"]
    assert snap["owner_packets"][0]["id"] == "PLAN-11-f3f5e6a4"
    assert snap["global_product_selection"]["status"] == "active"
    assert snap["global_product_selection"]["blocked_local_work_stops_global_selection"] is False
    assert any(row["id"] == "domus-storage-preflight-blocked" for row in snap["blocked_local_work"])
