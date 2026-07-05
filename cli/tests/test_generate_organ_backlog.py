"""Regression tests for scripts/generate-organ-backlog.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile
from limen.tabularius import pending_count

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate-organ-backlog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_organ_backlog_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_applies_organ_backlog_through_tabularius(monkeypatch, tmp_path, capsys):
    mod = _load_module()
    board = tmp_path / "tasks.yaml"
    ladder = tmp_path / "organ-ladder.json"
    save_limen_file(board, LimenFile(tasks=[]))
    ladder.write_text(
        json.dumps(
            {
                "organs": [
                    {
                        "pillar": "legal",
                        "organ": "Legal",
                        "repo": "organvm/limen",
                        "home": "organs/legal",
                        "stage": "scaffold",
                        "rank": 1,
                        "maturity": 10,
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("LIMEN_ORGAN_LADDER", str(ladder))
    monkeypatch.setenv("LIMEN_DISPATCH_LANES", "codex")
    monkeypatch.delenv("LIMEN_TICKETS_PRODUCE", raising=False)
    monkeypatch.setenv("LIMEN_SESSION_ID", "test-generate-organ-backlog")
    monkeypatch.setattr(mod, "_avg_headroom_pct", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--tasks", str(board), "--floor", "2", "--max-new", "2", "--apply"],
    )

    assert mod.main() == 0

    out = capsys.readouterr().out
    assert "through TABVLARIVS" in out
    assert pending_count(board) == 0
    tasks = load_limen_file(board).tasks
    assert len(tasks) == 2
    assert all(task.type == "content" for task in tasks)
    assert all("organ" in task.labels for task in tasks)
    assert {task.labels[1] for task in tasks} == {"pillar:legal"}
