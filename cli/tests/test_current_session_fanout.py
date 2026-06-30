from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module():
    script = ROOT / "scripts" / "current-session-fanout.py"
    spec = importlib.util.spec_from_file_location("current_session_fanout_under_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_session(path: Path, prompts: list[str]) -> None:
    rows = []
    for index, prompt in enumerate(prompts, start=1):
        turn_id = f"turn-{index}"
        rows.append(
            {
                "timestamp": f"2026-06-30T00:0{index}:00Z",
                "type": "turn_context",
                "payload": {
                    "turn_id": turn_id,
                    "cwd": "/tmp/work",
                    "model": "gpt-5-codex",
                },
            }
        )
        rows.append(
            {
                "timestamp": f"2026-06-30T00:0{index}:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                    "internal_chat_message_metadata_passthrough": {"turn_id": turn_id},
                },
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_current_session_fanout_uses_full_session_not_latest_turn(tmp_path: Path) -> None:
    mod = load_module()
    session = tmp_path / "session.jsonl"
    write_session(
        session,
        [
            "Select the global product and revenue path from every prompt.",
            "Domus preflight is locally blocked by Homebrew noise.",
            "Now do the current-session intake from the beginning of this session.",
        ],
    )

    snap = mod.build_snapshot(Namespace(session=str(session), theme="current-session-intake"))

    themes = set(snap["coverage"]["themes"])
    assert "current-session-intake" in themes
    assert "money-inbound-seo" in themes
    assert "domus-preflight-noise" in themes
    assert snap["coverage"]["unique_user_prompt_hashes"] == 3
    current = next(packet for packet in snap["owner_packets"] if packet["theme"] == "current-session-intake")
    assert current["source"]["turns"] == [1, 2, 3]


def test_blocked_local_work_does_not_stop_product_selection(tmp_path: Path) -> None:
    mod = load_module()
    session = tmp_path / "session.jsonl"
    write_session(
        session,
        [
            "Money, SEO, and first-dollar product selection should keep moving.",
            "A local reset credit quota problem is blocked and should be recorded.",
        ],
    )

    snap = mod.build_snapshot(Namespace(session=str(session), theme="current-session-intake"))

    assert snap["blocked_local_work"]
    assert snap["global_product_selection"]["status"] == "active"
    assert "blocked local work is recorded separately" in snap["global_product_selection"]["reason"]
    assert all("global-product-selection" in packet["does_not_block"] for packet in snap["blocked_local_work"])


def test_owner_packets_emit_executor_criteria_and_predicates(tmp_path: Path) -> None:
    mod = load_module()
    session = tmp_path / "session.jsonl"
    write_session(session, ["Use this session to plan worktree fanout for current-session intake."])

    snap = mod.build_snapshot(Namespace(session=str(session), theme="current-session-intake"))

    assert snap["owner_packets"]
    for packet in snap["owner_packets"]:
        assert packet["executor_criteria"]
        assert packet["verification_predicates"]
    rendered = mod.render_markdown(snap)
    assert "Use this session to plan" not in rendered
    assert "Prompt hashes" in rendered
