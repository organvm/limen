from pathlib import Path

from limen.substrate_paths import find_legacy_references


def test_canonical_and_indirected_paths_pass(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "ok.sh").write_text(
        'root="${LIMEN_ROOT:-${WORKSPACE_ROOT:-$HOME/Workspace}/library/engine/organvm/limen}"\n',
        encoding="utf-8",
    )
    assert find_legacy_references(tmp_path) == []


def test_old_executable_paths_fail(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "bad.py").write_text(
        'root = Path.home() / "Workspace" / "limen"\nother = "/Users/example/Workspace/4444J99/portvs"\n',
        encoding="utf-8",
    )
    findings = find_legacy_references(tmp_path)
    assert [(item["path"], item["line"]) for item in findings] == [
        ("scripts/bad.py", 1),
        ("scripts/bad.py", 2),
    ]


def test_historical_docs_and_tests_are_not_executable_consumers(tmp_path: Path) -> None:
    for directory in ("docs", "scripts/tests"):
        path = tmp_path / directory
        path.mkdir(parents=True)
        (path / "history.md").write_text("~/Workspace/limen\n", encoding="utf-8")
    assert find_legacy_references(tmp_path) == []
