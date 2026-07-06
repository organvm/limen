"""Regression tests for scripts/mine-backlog.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile
from limen.tabularius import pending_count

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "mine-backlog.py"


class _Result:
    returncode = 0
    stderr = ""

    def __init__(self, payload: object):
        self.stdout = json.dumps(payload)


def _load_module():
    spec = importlib.util.spec_from_file_location("mine_backlog_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_apply_mines_issue_through_tabularius(monkeypatch, tmp_path, capsys):
    mod = _load_module()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile(tasks=[]))

    def fake_run(args, *, capture_output, text, timeout):
        assert args[:3] == ["gh", "search", "issues"]
        return _Result(
            [
                {
                    "repository": {"nameWithOwner": "organvm/limen"},
                    "number": 44,
                    "title": "Build the record keeper probe",
                    "labels": [{"name": "ship-now"}],
                    "url": "https://github.com/organvm/limen/issues/44",
                    "body": "Turn the record keeper into a live probe.",
                }
            ]
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/limen")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))
    monkeypatch.delenv("LIMEN_TICKETS_PRODUCE", raising=False)
    monkeypatch.setenv("LIMEN_SESSION_ID", "test-mine-backlog")
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--tasks", str(board), "--owners", "organvm", "--limit", "1", "--apply"],
    )

    assert mod.main() == 0

    out = capsys.readouterr().out
    assert "through TABVLARIVS" in out
    assert pending_count(board) == 0
    tasks = load_limen_file(board).tasks
    assert [task.id for task in tasks] == ["GH-organvm-limen-44"]
    assert tasks[0].priority == "high"
    assert tasks[0].status == "open"
    assert tasks[0].urls == ["https://github.com/organvm/limen/issues/44"]
