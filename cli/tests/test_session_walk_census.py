from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "session-walk-census.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_walk_census", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_no_artifact_fails_closed_without_session_estate_scan(monkeypatch, capsys):
    census = _load()
    monkeypatch.delenv("LIMEN_CURRENT_SESSION_ARTIFACT", raising=False)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--vendor", "codex"])

    assert census.main() == 64
    assert "broad vendor-session census is unsupported" in capsys.readouterr().err


def test_raw_vendor_runtime_artifact_is_rejected(tmp_path, monkeypatch):
    census = _load()
    monkeypatch.setattr(census, "HOME", tmp_path)
    raw = tmp_path / ".claude" / "projects" / "workspace" / "peer.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_ARTIFACT", str(raw))

    with pytest.raises(census.SessionAccessError, match="private peer state"):
        census.authorized_artifact(str(raw))


def test_explicit_capability_bound_export_is_classified(tmp_path, monkeypatch):
    census = _load()
    monkeypatch.setattr(census, "HOME", tmp_path / "home")
    artifact = tmp_path / "exports" / "current-codex.jsonl"
    artifact.parent.mkdir()
    rows = [
        {"type": "session_meta", "payload": {"id": "current-codex", "cwd": "/tmp/work"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "Do the work"}},
        {
            "type": "event_msg",
            "payload": {"type": "task_complete", "last_agent_message": "Result: complete"},
        },
    ]
    artifact.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_ARTIFACT", str(artifact))

    assert census.authorized_artifact(str(artifact)) == artifact.resolve()
    assert census.classify_codex(artifact)["verdict"] == "walked"


def test_written_receipt_hashes_session_reference_and_omits_private_fields(tmp_path, monkeypatch, capsys):
    census = _load()
    sid = "private-current-codex"
    artifact = tmp_path / f"{sid}.jsonl"
    private_cwd = "/private/current/codex-worktree"
    private_prompt = "PRIVATE CURRENT CODEX PROMPT"
    rows = [
        {"type": "session_meta", "payload": {"id": sid, "cwd": private_cwd}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": private_prompt}},
        {
            "type": "event_msg",
            "payload": {"type": "task_complete", "last_agent_message": "Result: complete"},
        },
    ]
    artifact.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(census, "HOME", tmp_path / "home")
    monkeypatch.setattr(census, "LOGS", tmp_path / "receipts")
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_ARTIFACT", str(artifact))
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--vendor", "codex", "--session-artifact", str(artifact), "--write"],
    )

    assert census.main() == 0
    receipt_path = census.LOGS / "current-session-artifact-check.json"
    receipt_text = receipt_path.read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["session_ref_sha256"] == hashlib.sha256(sid.encode()).hexdigest()
    assert "session_ref" not in receipt
    combined = capsys.readouterr().out + receipt_text
    for private_value in (sid, str(artifact), private_cwd, private_prompt):
        assert private_value not in combined


def test_legacy_census_and_resume_interfaces_are_unsupported():
    census = _load()
    with pytest.raises(census.SessionControlUnsupported, match="broad cross-session census"):
        census.sweep()
    with pytest.raises(census.SessionControlUnsupported, match="cross-session resumption"):
        census.walk([], cap=1, dry=True)


def test_heartbeat_and_sensor_registry_have_no_peer_session_runner():
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    sensors = (ROOT / "institutio" / "governance" / "sensors.yaml").read_text(encoding="utf-8")
    source = SCRIPT.read_text(encoding="utf-8")

    assert "C_QUICKEN" not in heartbeat
    assert 'quicken.py" --apply' not in heartbeat
    assert "--breathe all" not in heartbeat
    assert "session-walk:" not in sensors
    assert ".rglob(" not in source
    assert '.glob("*/*.jsonl")' not in source
    assert "subprocess" not in source
    assert "--resume" not in source
    assert '["codex", "exec", "resume"' not in source
