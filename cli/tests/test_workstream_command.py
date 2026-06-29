from __future__ import annotations

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
    readme_text = readme.read_text(encoding="utf-8")
    assert "Ship a bounded packet." in readme_text
    kickstart_text = kickstart.read_text(encoding="utf-8")
    for agent in ("codex", "claude", "gemini", "opencode", "agy", "shell"):
        assert f'bash "{kickstart}" {agent}' in readme_text
        assert agent in kickstart_text
    assert "bash " in result.output and "kickstart.sh" in result.output
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout


def test_workstream_agent_open_wires_through_without_launching(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN202
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setattr("limen.cli.subprocess.run", fake_run)

    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--agent",
            "claude",
            "--open",
            "limen",
            "Claude Packet",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls
    assert "--agent" in calls[0]
    assert calls[0][calls[0].index("--agent") + 1] == "claude"
    assert "--open" in calls[0]


def test_workstream_legacy_launch_shortcuts_still_open_selected_agent(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN202
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setattr("limen.cli.subprocess.run", fake_run)

    for shortcut, agent in (("--codex", "codex"), ("--shell", "shell")):
        result = CliRunner().invoke(main, ["workstream", shortcut, "limen", f"{agent} packet"])
        assert result.exit_code == 0, result.output

    assert len(calls) == 2
    for call, agent in zip(calls, ("codex", "shell"), strict=True):
        assert "--agent" in call
        assert call[call.index("--agent") + 1] == agent
        assert "--open" in call
