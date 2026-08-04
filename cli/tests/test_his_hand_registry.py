"""Durable human-gate registry corrections that must survive formatting rewrites."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_arca_key_escrow_gate_has_one_canonical_owner_receipt():
    registry = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    rows = [row for row in registry["levers"] if row.get("id") == "L-ARCA-KEY-ESCROW"]

    assert len(rows) == 1
    assert rows[0]["issue"] == 719
    assert rows[0]["owner"] == "yours"
    assert rows[0]["source_task"] == "ARCA build 2026-07-08"


def test_tcc_app_management_cutover_stays_open_for_real_vendor_update():
    registry = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    rows = [row for row in registry["levers"] if row.get("id") == "L-DOMUS-AGENT-HOST-TCC"]

    assert len(rows) == 1
    assert rows[0]["issue"] == 1703
    assert rows[0]["status"] == "open"
    assert "discharged" not in rows[0]
    assert rows[0]["owner"] == "engineering"
    assert "external host update" in rows[0]["gate"]
    assert "zero path rows" in rows[0]["label"]
    assert "non-noop" in rows[0]["steps"][-1]
    assert "strict" in rows[0]["gate"]
    assert "2.1.220" not in rows[0]["gate"]
    assert "2.1.220" not in " ".join(rows[0]["steps"])
    assert "2.1.220" not in json.dumps(rows[0])
    evidence = rows[0]["evidence"]["track_c"]
    assert evidence["baseline_strict_audit_snapshot"].endswith("2026-08-04-baseline.json")
    assert evidence["post_strict_audit_snapshot"].endswith("2026-08-04-post.json")
    assert evidence["normalized_inventory_diff"].endswith("acceptance-2026-08-04.json")
    assert "explicit" in evidence["failure_classification"]
