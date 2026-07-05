from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-tabularius-writers.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("tabularius_writer_audit_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _scan_only_scripts(monkeypatch, module):
    monkeypatch.setattr(module, "SCAN_DIRS", ("scripts",))
    monkeypatch.setattr(module, "STRUCTURAL_ALLOWLIST", {})


def test_tabularius_writer_audit_passes_current_repo() -> None:
    module = _load_module()

    assert module.audit(ROOT) == []


def test_tabularius_writer_audit_current_repo_respects_legacy_ceiling() -> None:
    module = _load_module()

    assert module.audit(ROOT, max_legacy_writers=len(module.LEGACY_GATED_ALLOWLIST)) == []


def test_unapproved_direct_board_writer_is_blocked(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    _scan_only_scripts(monkeypatch, module)
    monkeypatch.setattr(module, "LEGACY_GATED_ALLOWLIST", set())

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "bad.py").write_text(
        "from limen.io import save_limen_file\n"
        "save_limen_file(tasks_path, limen_file)\n",
        encoding="utf-8",
    )

    errors = module.audit(tmp_path)

    assert any("scripts/bad.py: unapproved direct board writer" in error for error in errors)


def test_comment_mentions_do_not_count_as_writers(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    _scan_only_scripts(monkeypatch, module)
    monkeypatch.setattr(module, "LEGACY_GATED_ALLOWLIST", set())

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "comment.py").write_text("# save_limen_file(tasks_path, limen_file)\n", encoding="utf-8")

    assert module.audit(tmp_path) == []


def test_allowlisted_legacy_writer_requires_ticket_gate_and_producer(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    _scan_only_scripts(monkeypatch, module)
    monkeypatch.setattr(module, "LEGACY_GATED_ALLOWLIST", {"scripts/gated.py"})

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    gated = scripts / "gated.py"
    gated.write_text(
        "import os\n"
        "from limen.io import save_limen_file\n"
        "from limen.tabularius import submit_task_status\n"
        "if os.environ.get('LIMEN_TICKETS_PRODUCE') == '1':\n"
        "    submit_task_status(tasks_path, 'T-1', 'open', agent='limen')\n"
        "else:\n"
        "    save_limen_file(tasks_path, limen_file)\n",
        encoding="utf-8",
    )

    assert module.audit(tmp_path) == []

    gated.write_text(
        "import os\n"
        "from limen.io import save_limen_file\n"
        "if os.environ.get('LIMEN_TICKETS_PRODUCE') == '1':\n"
        "    pass\n"
        "else:\n"
        "    save_limen_file(tasks_path, limen_file)\n",
        encoding="utf-8",
    )

    errors = module.audit(tmp_path)
    assert errors == ["scripts/gated.py: allowlisted legacy writer is missing ticket-mode gate/producer proof"]


def test_legacy_writer_ceiling_blocks_new_fallbacks(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    _scan_only_scripts(monkeypatch, module)
    monkeypatch.setattr(module, "LEGACY_GATED_ALLOWLIST", {"scripts/gated.py"})

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "gated.py").write_text(
        "import os\n"
        "from limen.io import save_limen_file\n"
        "from limen.tabularius import submit_task_status\n"
        "if os.environ.get('LIMEN_TICKETS_PRODUCE') == '1':\n"
        "    submit_task_status(tasks_path, 'T-1', 'open', agent='limen')\n"
        "else:\n"
        "    save_limen_file(tasks_path, limen_file)\n",
        encoding="utf-8",
    )

    errors = module.audit(tmp_path, max_legacy_writers=0)
    assert errors == ["legacy gated fallback writer ceiling exceeded: 1 observed > 0 allowed"]
