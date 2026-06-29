from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-acceptance-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("prompt_acceptance_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wire_paths(acceptance, tmp_path: Path):
    acceptance.ROOT = tmp_path
    acceptance.HOME = tmp_path
    acceptance.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    acceptance.BATCH_REVIEW_INDEX = acceptance.PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
    acceptance.PRIORITY_INDEX = acceptance.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    acceptance.PACKET_INDEX = acceptance.PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
    acceptance.LIFECYCLE_INDEX = acceptance.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    acceptance.AUG1_VIEW_PATH = tmp_path / "logs" / "aug1-view.json"
    acceptance.OUTWARD_RECIPROCITY_PATH = tmp_path / "state" / "outward-reciprocity.json"
    acceptance.DOC_PATH = tmp_path / "docs" / "prompt-acceptance-ledger.md"
    acceptance.PRIVATE_INDEX = acceptance.PRIVATE_ROOT / "lifecycle" / "prompt-acceptance-ledger.json"


def _write_base_fixture(acceptance):
    acceptance.PRIVATE_ROOT.joinpath("lifecycle").mkdir(parents=True)
    acceptance.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "session_items": [
                    {
                        "session_key": "old-private-session-key",
                        "family": "session_lifecycle",
                        "first_event": "2026-06-01T00:00:00Z",
                        "last_event": "2026-06-01T00:10:00Z",
                        "prompt_events": 80,
                        "prompt_hashes": [f"old-hash-{idx}" for idx in range(20)],
                        "private_source_path": "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR",
                    },
                    {
                        "session_key": "new-private-session-key",
                        "family": "session_lifecycle",
                        "first_event": "2026-06-27T00:00:00Z",
                        "last_event": "2026-06-27T00:10:00Z",
                        "prompt_events": 2,
                        "prompt_hashes": ["new-hash"],
                    },
                    {
                        "session_key": "closed-private-session-key",
                        "family": "worktree_lifecycle",
                        "first_event": "2026-06-20T00:00:00Z",
                        "last_event": "2026-06-20T00:10:00Z",
                        "prompt_events": 4,
                        "prompt_hashes": ["closed-hash"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    acceptance.PACKET_INDEX.write_text(
        json.dumps(
            {
                "packets": [
                    {
                        "id": "packet-old-lineage-session_lifecycle",
                        "source_batch": "batch-old",
                        "family": "session_lifecycle",
                        "status": "packetized",
                        "owner": "session lifecycle",
                        "route": "RAW_PRIVATE_PROMPT should not leak",
                        "session_keys": ["old-private-session-key"],
                        "prompt_events": 80,
                        "prompt_hashes": ["old-full-hash"],
                    },
                    {
                        "id": "packet-new-evolved-session_lifecycle",
                        "source_batch": "batch-new",
                        "family": "session_lifecycle",
                        "status": "packetized",
                        "owner": "session lifecycle",
                        "route": "new owner route",
                        "session_keys": ["new-private-session-key"],
                        "prompt_events": 2,
                        "prompt_hashes": ["new-full-hash"],
                    },
                    {
                        "id": "packet-closed-worktree_lifecycle",
                        "source_batch": "batch-closed",
                        "family": "worktree_lifecycle",
                        "status": "owner-recorded",
                        "owner": "worktree lifecycle",
                        "resolution": {"next_action": "owner receipt recorded"},
                        "session_keys": ["closed-private-session-key"],
                        "prompt_events": 4,
                        "prompt_hashes": ["closed-full-hash"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    acceptance.BATCH_REVIEW_INDEX.write_text(
        json.dumps({"batches": [], "review_queue": [], "counts": {"statuses": {}}}),
        encoding="utf-8",
    )
    acceptance.LIFECYCLE_INDEX.write_text(json.dumps({"sessions": []}), encoding="utf-8")
    acceptance.AUG1_VIEW_PATH.parent.mkdir(parents=True)
    acceptance.AUG1_VIEW_PATH.write_text(
        json.dumps(
            {
                "deadline": "2026-08-01",
                "gate": {"pass": False, "legs": [{"ok": True}, {"ok": False}]},
                "next_act": "open a rail",
            }
        ),
        encoding="utf-8",
    )
    acceptance.OUTWARD_RECIPROCITY_PATH.parent.mkdir(parents=True)
    acceptance.OUTWARD_RECIPROCITY_PATH.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "id": "staged-session-reciprocity",
                        "status": "staged",
                        "related_packets": ["packet-new-evolved-session_lifecycle"],
                        "public_safe_summary": "Public-safe staged receipt",
                        "human_gate_required": True,
                    },
                    {
                        "id": "absorbed-worktree-reciprocity",
                        "status": "absorbed",
                        "related_families": ["worktree_lifecycle"],
                        "public_safe_summary": "Absorbed worktree lesson",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_acceptance_orders_new_evolved_prompt_before_old_lineage(tmp_path: Path):
    acceptance = _load()
    _wire_paths(acceptance, tmp_path)
    _write_base_fixture(acceptance)

    snapshot = acceptance.build_snapshot(limit=10)
    ids = [row["source_ref"] for row in snapshot["acceptance_packets"]]

    assert ids.index("packet-new-evolved-session_lifecycle") < ids.index("packet-old-lineage-session_lifecycle")
    new_row = next(row for row in snapshot["acceptance_packets"] if row["source_ref"] == "packet-new-evolved-session_lifecycle")
    old_row = next(row for row in snapshot["acceptance_packets"] if row["source_ref"] == "packet-old-lineage-session_lifecycle")
    assert new_row["prompt_receipt"]["lineage_weight"] < old_row["prompt_receipt"]["lineage_weight"]
    assert new_row["evolved_intent"]["rule"] == "newer form wins; earlier repeats count as lineage evidence"


def test_acceptance_redacts_public_output_and_counts_statuses(tmp_path: Path):
    acceptance = _load()
    _wire_paths(acceptance, tmp_path)
    _write_base_fixture(acceptance)

    snapshot = acceptance.build_snapshot(limit=10)
    markdown = acceptance.render_markdown(snapshot, limit=10)
    acceptance.write_outputs(snapshot, markdown)

    assert snapshot["coverage"]["prompt_packets_total"] == 3
    assert snapshot["coverage"]["prompt_packets_closed"] == 1
    assert snapshot["coverage"]["prompt_packets_open"] == 2
    assert snapshot["counts"]["acceptance_statuses"]["needs_reciprocity_gate"] == 1
    assert snapshot["counts"]["acceptance_statuses"]["needs_owner_outcome"] == 1
    assert snapshot["counts"]["acceptance_statuses"]["closed"] == 1
    assert snapshot["counts"]["reciprocity_statuses"] == {"staged": 1, "absorbed": 1}
    assert "late-August unemployment runway" in markdown

    public_text = json.dumps(snapshot["public_packets"]) + markdown
    for forbidden in [
        "RAW_PRIVATE_PROMPT",
        "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR",
        "old-full-hash",
        "new-full-hash",
        "old-private-session-key",
        "new-private-session-key",
        "closed-private-session-key",
        "private_source_path",
        "prompt_hashes",
        "session_keys",
    ]:
        assert forbidden not in public_text
    assert acceptance.DOC_PATH.exists()
    assert acceptance.PRIVATE_INDEX.exists()


def test_acceptance_rejects_unknown_reciprocity_status(tmp_path: Path):
    acceptance = _load()
    _wire_paths(acceptance, tmp_path)
    _write_base_fixture(acceptance)
    acceptance.OUTWARD_RECIPROCITY_PATH.write_text(
        json.dumps({"receipts": [{"id": "bad", "status": "almost_sent"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid outward reciprocity status"):
        acceptance.build_snapshot(limit=10)
