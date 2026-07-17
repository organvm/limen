from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quicken.py"


def _load():
    spec = importlib.util.spec_from_file_location("quicken", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _claude_export(path: Path, sid: str) -> None:
    rows = [
        {
            "type": "ai-title",
            "aiTitle": "PRIVATE CURRENT INVOCATION TITLE",
            "cwd": "/private/current/worktree",
        },
        {
            "type": "last-prompt",
            "lastPrompt": "PRIVATE CURRENT INVOCATION PROMPT",
            "cwd": "/private/current/worktree",
        },
        {
            "type": "assistant",
            "timestamp": "2026-07-16T20:00:00Z",
            "cwd": "/private/current/worktree",
            "message": {"content": [{"type": "text", "text": "PRIVATE RESPONSE"}]},
        },
    ]
    assert path.stem == sid
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_malformed_numeric_env_falls_back(monkeypatch):
    monkeypatch.setenv("LIMEN_QUICKEN_STALE_MIN", "not-an-int")
    monkeypatch.setenv("LIMEN_QUICKEN_HORIZON_DAYS", "0")
    monkeypatch.setenv("LIMEN_QUICKEN_CLOSED_HRS", "-1")

    quicken = _load()

    assert quicken.STALE_MIN == 20
    assert quicken.HORIZON_DAYS == 3
    assert quicken.CLOSED_HRS == 18


def test_breathe_is_unconditionally_unsupported():
    quicken = _load()

    with pytest.raises(quicken.SessionControlUnsupported, match="cross-session resumption"):
        quicken.breathe([], "all", dry=True)


def test_no_artifact_fails_closed_without_scanning(monkeypatch, capsys):
    quicken = _load()
    monkeypatch.delenv("LIMEN_CURRENT_SESSION_ARTIFACT", raising=False)
    monkeypatch.setenv("CLAUDE_SESSION_ID", "current")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    assert quicken.main() == 64
    assert "broad Claude-session census is unsupported" in capsys.readouterr().err


def test_raw_vendor_runtime_artifact_is_rejected(tmp_path, monkeypatch):
    quicken = _load()
    monkeypatch.setattr(quicken, "HOME", tmp_path)
    raw = tmp_path / ".claude" / "projects" / "workspace" / "current.jsonl"
    raw.parent.mkdir(parents=True)
    _claude_export(raw, "current")
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_ARTIFACT", str(raw))

    with pytest.raises(quicken.SessionAccessError, match="private peer state"):
        quicken.authorized_artifact(str(raw), "current")


def test_only_bound_current_invocation_export_is_classified(tmp_path, monkeypatch):
    quicken = _load()
    monkeypatch.setattr(quicken, "HOME", tmp_path / "home")
    artifact = tmp_path / "current.jsonl"
    _claude_export(artifact, "current")
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_ARTIFACT", str(artifact))

    rows = quicken.gather(time.time(), "current", str(artifact))

    assert len(rows) == 1
    assert rows[0]["session_id"] == "current"


def test_artifact_identity_must_match_current_invocation(tmp_path, monkeypatch):
    quicken = _load()
    monkeypatch.setattr(quicken, "HOME", tmp_path / "home")
    artifact = tmp_path / "other.jsonl"
    _claude_export(artifact, "other")
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_ARTIFACT", str(artifact))

    with pytest.raises(quicken.SessionAccessError, match="does not match the current invocation"):
        quicken.authorized_artifact(str(artifact), "current")


def test_default_success_is_zero_write_and_stdout_is_redacted(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "private-current-sid"
    artifact = tmp_path / f"{sid}.jsonl"
    receipt_out = tmp_path / "receipts" / "quicken.json"
    _claude_export(artifact, sid)
    monkeypatch.setattr(quicken, "HOME", tmp_path / "home")
    monkeypatch.setattr(quicken, "RECEIPT_OUT", receipt_out)
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_ARTIFACT", str(artifact))
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--session-artifact", str(artifact), "--self", sid],
    )

    assert quicken.main() == 0
    assert not receipt_out.exists()
    output = capsys.readouterr().out
    receipt = json.loads(output)
    assert receipt["session_ref_sha256"] == hashlib.sha256(sid.encode()).hexdigest()
    for private_value in (
        sid,
        str(artifact),
        "PRIVATE CURRENT INVOCATION TITLE",
        "PRIVATE CURRENT INVOCATION PROMPT",
        "/private/current/worktree",
    ):
        assert private_value not in output


def test_apply_writes_only_redacted_bound_artifact_receipt(tmp_path, monkeypatch, capsys):
    quicken = _load()
    sid = "private-current-sid"
    artifact = tmp_path / f"{sid}.jsonl"
    receipt_out = tmp_path / "receipts" / "quicken.json"
    _claude_export(artifact, sid)
    monkeypatch.setattr(quicken, "HOME", tmp_path / "home")
    monkeypatch.setattr(quicken, "RECEIPT_OUT", receipt_out)
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_ARTIFACT", str(artifact))
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--session-artifact", str(artifact), "--self", sid, "--apply"],
    )

    assert quicken.main() == 0
    receipt = json.loads(receipt_out.read_text(encoding="utf-8"))
    assert receipt == {
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "checked_at": receipt["checked_at"],
        "producer": "quicken",
        "schema": "limen.current_session_artifact_check.v1",
        "session_ref_sha256": hashlib.sha256(sid.encode()).hexdigest(),
        "state": receipt["state"],
        "vendor": "claude",
    }
    combined = capsys.readouterr().out + receipt_out.read_text(encoding="utf-8")
    for private_value in (
        sid,
        str(artifact),
        "PRIVATE CURRENT INVOCATION TITLE",
        "PRIVATE CURRENT INVOCATION PROMPT",
        "/private/current/worktree",
    ):
        assert private_value not in combined


def test_quicken_source_has_one_receipt_write_and_no_legacy_mutator():
    source = SCRIPT.read_text(encoding="utf-8")

    assert '.glob("*/*.jsonl")' not in source
    assert "PROJECTS" not in source
    assert "--resume" not in source
    assert "tasks.yaml" not in source
    assert "save_limen_file" not in source
    assert "hang_residue" not in source
    assert "write_residue" not in source
    assert "RESIDUE_OUT" not in source
    assert "subprocess" not in source
    assert source.count(".write_text(") == 1
    assert 'raise SessionControlUnsupported("cross-session resumption is unsupported")' in source
