from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import cli  # noqa: E402


def _reaper_root(tmp_path: Path) -> Path:
    root = tmp_path / "limen"
    script = root / "scripts" / "reclaim-worktrees.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return root


def test_worktree_reap_forwards_check_json_output_and_exit_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _reaper_root(tmp_path)
    observed: list[tuple[list[str], Path]] = []

    def fake_run(args, *, cwd, capture_output, text, check):
        assert capture_output is text is True
        assert check is False
        observed.append((args, cwd))
        return subprocess.CompletedProcess(args, 7, '{"mode":"CHECK"}\n', "bounded warning\n")

    monkeypatch.setattr(cli, "resolve_limen_repo_root", lambda: root)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = CliRunner().invoke(cli.main, ["worktree", "reap", "--check", "--json"])

    assert result.exit_code == 7
    assert observed == [
        (
            [
                sys.executable,
                str(root / "scripts" / "reclaim-worktrees.py"),
                "--check",
                "--json",
            ],
            root,
        )
    ]
    assert '{"mode":"CHECK"}' in result.output
    assert "bounded warning" in result.output


def test_worktree_reap_default_is_dry_run_and_help_is_forwarded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _reaper_root(tmp_path)
    observed: list[list[str]] = []

    def fake_run(args, **_kwargs):
        observed.append(args)
        return subprocess.CompletedProcess(args, 0, "usage: reclaim-worktrees.py\n", "")

    monkeypatch.setattr(cli, "resolve_limen_repo_root", lambda: root)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    default = CliRunner().invoke(cli.main, ["worktree", "reap"])
    help_result = CliRunner().invoke(cli.main, ["worktree", "reap", "--help"])

    assert default.exit_code == 0
    assert help_result.exit_code == 0
    assert observed == [
        [sys.executable, str(root / "scripts" / "reclaim-worktrees.py")],
        [sys.executable, str(root / "scripts" / "reclaim-worktrees.py"), "--help"],
    ]
    assert all("--apply" not in args for args in observed)
    assert "usage: reclaim-worktrees.py" in help_result.output
