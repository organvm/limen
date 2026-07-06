from __future__ import annotations

import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "session-corpus-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_corpus_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_external_session_roots_are_bounded(monkeypatch, tmp_path: Path):
    ledger = _load()
    archive = tmp_path / "Archive4T"
    archive.mkdir()
    for idx in range(5):
        (archive / f"chat-{idx}.md").write_text(f"prompt {idx}\n", encoding="utf-8")

    monkeypatch.setattr(ledger, "LOCAL_SOURCES", [])
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_ROOTS", str(archive))
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_FILES_PER_ROOT", "2")

    rows, limits = ledger.scan_local_files(None)

    assert len(rows) == 2
    assert {row["source"] for row in rows} == {"external-session-root-1"}
    assert all(row["root"] == str(archive) for row in rows)
    assert limits["external-session-root-1"]["truncated"] is True
    assert limits["external-session-root-1"]["truncation_reason"] == "file-cap"
    assert limits["external-session-root-1"]["candidate_files"] == 2


def test_external_session_roots_honor_depth_limit(monkeypatch, tmp_path: Path):
    ledger = _load()
    archive = tmp_path / "Archive4T"
    shallow = archive / "shallow"
    deep = archive / "a" / "b" / "c"
    shallow.mkdir(parents=True)
    deep.mkdir(parents=True)
    (shallow / "keep.md").write_text("nearby\n", encoding="utf-8")
    (deep / "skip.md").write_text("too deep\n", encoding="utf-8")

    monkeypatch.setattr(ledger, "LOCAL_SOURCES", [])
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_ROOTS", str(archive))
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_FILES_PER_ROOT", "10")
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_DEPTH", "1")

    rows, limits = ledger.scan_local_files(None)

    assert [Path(row["path"]).name for row in rows] == ["keep.md"]
    assert limits["external-session-root-1"]["max_depth"] == 1


def test_multiple_external_roots_use_path_separator(monkeypatch, tmp_path: Path):
    ledger = _load()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "one.md").write_text("one\n", encoding="utf-8")
    (second / "two.md").write_text("two\n", encoding="utf-8")

    monkeypatch.setattr(ledger, "LOCAL_SOURCES", [])
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_ROOTS", os.pathsep.join([str(first), str(second)]))

    rows, _limits = ledger.scan_local_files(None)

    assert {row["source"] for row in rows} == {"external-session-root-1", "external-session-root-2"}


def test_limen_root_symlink_is_resolved(monkeypatch, tmp_path: Path):
    real_root = tmp_path / "Workspace" / "limen"
    real_root.mkdir(parents=True)
    link_root = tmp_path / "limen"
    link_root.symlink_to(real_root, target_is_directory=True)

    monkeypatch.setenv("LIMEN_ROOT", str(link_root))
    ledger = _load()

    assert ledger.ROOT == real_root.resolve()
    assert ledger.WORKSPACE == real_root.parent.resolve()
