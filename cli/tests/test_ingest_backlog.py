"""Regression tests for scripts/ingest-backlog.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile
from limen.tabularius import pending_count

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ingest-backlog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ingest_backlog_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_source(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "deepening": {
                    "tasks": [
                        {
                            "id": "studium-deepen-test-work",
                            "title": "Deepen Test Work",
                            "checklist": "studium/music/test-work/CHECKLIST.md",
                        },
                        {
                            "id": "studium-deepen-odyssey",
                            "title": "Excluded in-flight work",
                        },
                        {
                            "id": "studium-deepen-gated",
                            "title": "His-gated row",
                            "gate": "human",
                        },
                    ]
                },
                "corpus_gaps": {
                    "tasks": [
                        {
                            "id": "studium-corpus-gap-test",
                            "title": "Fill Corpus Gap",
                        }
                    ]
                },
                "film": {
                    "first_pass": {
                        "tasks": [
                            {
                                "id": "studium-film-test",
                                "title": "First Film Pass",
                            },
                            {
                                "id": "studium-corpus-gap-test",
                                "title": "Duplicate ignored by id",
                            },
                        ]
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_apply_ingests_studium_content_through_tabularius(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LIMEN_STUDIUM_REPO", "organvm/studium-test")
    monkeypatch.setenv("LIMEN_SESSION_ID", "test-ingest-backlog")
    monkeypatch.delenv("LIMEN_TICKETS_PRODUCE", raising=False)
    mod = _load_module()

    board = tmp_path / "tasks.yaml"
    source = tmp_path / "expansion-backlog.yaml"
    save_limen_file(board, LimenFile(tasks=[]))
    _write_source(source)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--source", str(source), "--tasks", str(board), "--apply"])

    assert mod.main() == 0

    out = capsys.readouterr().out
    assert "through TABVLARIVS" in out
    assert pending_count(board) == 0
    tasks = load_limen_file(board).tasks
    assert [task.id for task in tasks] == [
        "studium-deepen-test-work",
        "studium-corpus-gap-test",
        "studium-film-test",
    ]
    assert {task.repo for task in tasks} == {"organvm/studium-test"}
    assert {task.type for task in tasks} == {"content"}
    assert all(task.status == "open" for task in tasks)
    assert all(task.target_agent == "any" for task in tasks)

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "nothing new" in out
    assert len(load_limen_file(board).tasks) == 3
    assert pending_count(board) == 0
