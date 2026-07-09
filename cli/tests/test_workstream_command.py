from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.cli import main  # noqa: E402


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stdout}\n{result.stderr}")
    return result


def test_workstream_command_writes_private_kickstart_packet(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--prompt",
            "Ship a bounded packet.",
            str(repo),
            "Demo Packet",
        ],
    )

    assert result.exit_code == 0, result.output
    wt = repo / ".worktrees" / "demo-packet"
    readme = wt / ".limen-workstream" / "README.md"
    kickstart = wt / ".limen-workstream" / "kickstart.sh"
    assert readme.exists()
    assert kickstart.exists()
    assert "Ship a bounded packet." in readme.read_text(encoding="utf-8")
    kickstart_text = kickstart.read_text(encoding="utf-8")
    assert "export LIMEN_SESSION_MODE=task" in kickstart_text
    assert f'export LIMEN_SESSION_ROOT="{wt}"' in kickstart_text
    assert f'export LIMEN_ROOT="{wt}"' in kickstart_text
    assert f'export CODEX_PROJECT_DIR="{wt}"' in kickstart_text
    assert "bash " in result.output and "kickstart.sh" in result.output
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "codex-env.txt"
    codex = fake_bin / "codex"
    codex.write_text(
        "#!/usr/bin/env bash\n"
        "{\n"
        "  pwd\n"
        "  printf 'LIMEN_SESSION_MODE=%s\\n' \"$LIMEN_SESSION_MODE\"\n"
        "  printf 'LIMEN_SESSION_ROOT=%s\\n' \"$LIMEN_SESSION_ROOT\"\n"
        "  printf 'LIMEN_LIVE_ROOT=%s\\n' \"$LIMEN_LIVE_ROOT\"\n"
        "  printf 'LIMEN_ROOT=%s\\n' \"$LIMEN_ROOT\"\n"
        "  printf 'CODEX_PROJECT_DIR=%s\\n' \"$CODEX_PROJECT_DIR\"\n"
        '} > "$WORKSTREAM_ENV_CAPTURE"\n',
        encoding="utf-8",
    )
    codex.chmod(0o755)

    subprocess.run(
        ["bash", str(kickstart)],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}", "WORKSTREAM_ENV_CAPTURE": str(capture)},
        check=True,
        capture_output=True,
        text=True,
    )

    launched = capture.read_text(encoding="utf-8")
    assert launched.splitlines()[0] == str(wt)
    assert "LIMEN_SESSION_MODE=task" in launched
    assert f"LIMEN_SESSION_ROOT={wt}" in launched
    assert f"LIMEN_ROOT={wt}" in launched
    assert f"CODEX_PROJECT_DIR={wt}" in launched


def test_workstream_command_creates_distinct_worktree_roots(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    runner = CliRunner()
    first = runner.invoke(main, ["workstream", "--no-readme", str(repo), "First Pane"])
    second = runner.invoke(main, ["workstream", "--no-readme", str(repo), "Second Pane"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    wt_one = repo / ".worktrees" / "first-pane"
    wt_two = repo / ".worktrees" / "second-pane"

    top_one = _git("rev-parse", "--show-toplevel", cwd=wt_one).stdout.strip()
    top_two = _git("rev-parse", "--show-toplevel", cwd=wt_two).stdout.strip()

    assert top_one == str(wt_one)
    assert top_two == str(wt_two)
    assert top_one != top_two
