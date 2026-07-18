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

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = fake_bin / "opencode"
    fake_opencode.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_opencode.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "opencode")
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
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
    intent = wt / ".limen-workstream" / "intent.md"
    kickstart = wt / ".limen-workstream" / "kickstart.sh"
    assert readme.exists()
    assert intent.exists()
    assert kickstart.exists()
    assert "Ship a bounded packet." in intent.read_text(encoding="utf-8")
    assert "Ship a bounded packet." not in readme.read_text(encoding="utf-8")
    assert "bash " in result.output and "kickstart.sh" in result.output
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout


def test_autonomous_workstream_requires_prompt_and_launches_with_dynamic_readme(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        '#!/usr/bin/env bash\nprintf "%s" "$1" > "$SESSION_PROMPT_CAPTURE"\n',
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    missing = CliRunner().invoke(main, ["workstream", "--autonomous", str(repo), "No Prompt"])
    assert missing.exit_code == 2
    assert "requires --prompt or --prompt-file" in missing.output
    assert not (repo / ".worktrees" / "no-prompt").exists()

    no_readme = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--no-readme",
            "--prompt",
            "This cannot be durable.",
            str(repo),
            "No Readme",
        ],
    )
    assert no_readme.exit_code == 2
    assert "cannot be combined with --no-readme" in no_readme.output
    assert not (repo / ".worktrees" / "no-readme").exists()

    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )

    assert result.exit_code == 0, result.output
    wt = repo / ".worktrees" / "next-epoch"
    capsule = wt / ".limen-workstream"
    readme = capsule / "README.md"
    manifest = capsule / "manifest.md"
    intent = capsule / "intent.md"
    runtime = capsule / "runtime.md"
    closeout = capsule / "closeout.md"
    kickstart = capsule / "kickstart.sh"
    readme_text = readme.read_text(encoding="utf-8")
    manifest_text = manifest.read_text(encoding="utf-8")
    intent_text = intent.read_text(encoding="utf-8")
    runtime_text = runtime.read_text(encoding="utf-8")
    kickstart_text = kickstart.read_text(encoding="utf-8")
    assert "Derive the next safe leaf from live receipts." in intent_text
    assert "Derive the next safe leaf from live receipts." not in readme_text
    assert "Autonomous: `yes`" in manifest_text
    assert "Agent: `codex`" in manifest_text
    assert "Conduct: `no`" in manifest_text
    assert "Runtime decision contract" in runtime_text
    assert "Reality determines the state" in runtime_text
    assert "Workstream: `substrate`" in manifest_text
    for module in (manifest, intent, runtime, closeout):
        assert module.exists()
        assert module.name in readme_text
    assert "workstream_export_context" in kickstart_text
    assert "workstream_launch_native_agent" in kickstart_text
    assert 'exec "$binary" "$capsule_prompt"' in kickstart_text
    assert str(readme) in kickstart_text
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout

    capsule_files = (readme, manifest, intent, runtime, closeout, kickstart)
    bytes_before = {path: path.read_bytes() for path in capsule_files}
    mtimes_before = {path: path.stat().st_mtime_ns for path in capsule_files}
    repeated = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )
    assert repeated.exit_code == 0, repeated.output
    assert "capsule index:" in repeated.output and "(unchanged)" in repeated.output
    assert {path: path.read_bytes() for path in capsule_files} == bytes_before
    assert {path: path.stat().st_mtime_ns for path in capsule_files} == mtimes_before

    prompt_capture = tmp_path / "prompt.txt"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SESSION_PROMPT_CAPTURE": str(prompt_capture),
    }
    launched = subprocess.run(["bash", str(kickstart)], cwd=wt, env=env, text=True, capture_output=True)
    assert launched.returncode == 0, launched.stderr
    launched_prompt = prompt_capture.read_text(encoding="utf-8")
    assert launched_prompt == readme_text
    assert "intent.md" in launched_prompt

    runtime.unlink()
    invalid = subprocess.run(["bash", str(kickstart)], cwd=wt, env=env, text=True, capture_output=True)
    assert invalid.returncode == 2
    assert "invalid capsule: missing or empty module" in invalid.stderr


def test_agent_neutral_conduct_launch_registers_protected_session_and_injects_context(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    order_capture = tmp_path / "order.txt"
    register_capture = tmp_path / "register.txt"
    context_capture = tmp_path / "context.txt"
    prompt_capture = tmp_path / "prompt.txt"

    fake_limen = fake_bin / "limen"
    fake_limen.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'register\n' >> "$ORDER_CAPTURE"
printf '%s\n' "$*" > "$REGISTER_CAPTURE"
for arg in "$@"; do
  if [[ "$arg" == "$LIMEN_CONDUCT_TOKEN" ]]; then
    printf 'token leaked through argv\n' >&2
    exit 90
  fi
done
if [[ "${REGISTER_FAIL:-0}" == "1" ]]; then
  exit 42
fi
""",
        encoding="utf-8",
    )
    fake_limen.chmod(0o755)
    fake_claude = fake_bin / "claude"
    fake_claude.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'launch\n' >> "$ORDER_CAPTURE"
printf '%s\n' \
  "$LIMEN_AGENT" \
  "$LIMEN_AGENT_CAPABILITIES" \
  "$LIMEN_SESSION_ID" \
  "$LIMEN_RUN_ID" \
  "$LIMEN_ROOT_RUN_ID" \
  "$LIMEN_PARENT_RUN_ID" \
  "$LIMEN_CONDUCTOR_AGENT" \
  "$LIMEN_CONDUCTOR_SESSION_ID" \
  "$LIMEN_TASK_ID" \
  "$LIMEN_LEASE_GENERATION" \
  "$LIMEN_EXECUTION_HASH" \
  "$LIMEN_HUMAN_PROTECTED" \
  "${LIMEN_CONDUCT_TOKEN-unset}" \
  "$LIMEN_CAPSULE_README" > "$CONTEXT_CAPTURE"
printf '%s' "$1" > "$SESSION_PROMPT_CAPTURE"
""",
        encoding="utf-8",
    )
    fake_claude.chmod(0o755)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("ORDER_CAPTURE", str(order_capture))
    monkeypatch.setenv("REGISTER_CAPTURE", str(register_capture))
    monkeypatch.setenv("CONTEXT_CAPTURE", str(context_capture))
    monkeypatch.setenv("SESSION_PROMPT_CAPTURE", str(prompt_capture))
    monkeypatch.setenv("LIMEN_CONDUCT_TOKEN", "broker-secret-must-not-leak")
    monkeypatch.setenv("LIMEN_RUN_ID", "run-child-7")
    monkeypatch.setenv("LIMEN_ROOT_RUN_ID", "run-root-1")
    monkeypatch.setenv("LIMEN_PARENT_RUN_ID", "run-parent-3")
    monkeypatch.setenv("LIMEN_CONDUCTOR_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CONDUCTOR_SESSION_ID", "codex-parent-session")
    monkeypatch.setenv("LIMEN_TASK_ID", "LIMEN-PEER-MESH")
    monkeypatch.setenv("LIMEN_LEASE_GENERATION", "17")
    monkeypatch.setenv("LIMEN_EXECUTION_HASH", "abc123")

    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--agent",
            "claude",
            "--conduct",
            "--prompt",
            "Continue through the protected peer mesh.",
            str(repo),
            "Peer Mesh",
        ],
    )

    assert result.exit_code == 0, result.output
    assert order_capture.read_text(encoding="utf-8").splitlines() == ["register", "launch"]
    register_args = register_capture.read_text(encoding="utf-8")
    assert "conduct register" in register_args
    assert "--agent claude" in register_args
    assert "--surface workstream" in register_args
    assert "--origin direct" in register_args
    assert "--human-protected" in register_args
    assert "--capability local-worktree" in register_args
    assert "broker-secret-must-not-leak" not in register_args

    wt = repo / ".worktrees" / "peer-mesh"
    capsule = wt / ".limen-workstream"
    readme = capsule / "README.md"
    manifest_text = (capsule / "manifest.md").read_text(encoding="utf-8")
    assert "Agent: `claude`" in manifest_text
    assert "Agent capabilities: `code conduct execute inspect local-worktree review`" in manifest_text
    assert "Conduct: `yes`" in manifest_text
    assert prompt_capture.read_text(encoding="utf-8") == readme.read_text(encoding="utf-8")
    assert "broker-secret-must-not-leak" not in "".join(
        path.read_text(encoding="utf-8") for path in capsule.iterdir() if path.is_file()
    )

    context = context_capture.read_text(encoding="utf-8").splitlines()
    assert context[0] == "claude"
    assert context[1] == "code conduct execute inspect local-worktree review"
    assert context[2].startswith("workstream-peer-mesh-")
    assert context[3:12] == [
        "run-child-7",
        "run-root-1",
        "run-parent-3",
        "codex",
        "codex-parent-session",
        "LIMEN-PEER-MESH",
        "17",
        "abc123",
        "1",
    ]
    assert context[12] == "unset"
    assert context[13] == str(readme)

    order_capture.write_text("", encoding="utf-8")
    monkeypatch.setenv("REGISTER_FAIL", "1")
    blocked = CliRunner().invoke(
        main,
        [
            "workstream",
            "--agent",
            "claude",
            "--conduct",
            str(repo),
            "Broker Blocked",
        ],
    )
    assert blocked.exit_code == 42
    assert order_capture.read_text(encoding="utf-8").splitlines() == ["register"]


def test_agent_auto_uses_canonical_current_lane_and_invalid_lane_fails_before_worktree(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    selected_capture = tmp_path / "selected.txt"
    fake_opencode = fake_bin / "opencode"
    fake_opencode.write_text(
        '#!/usr/bin/env bash\nprintf "%s" "$LIMEN_AGENT" > "$SELECTED_CAPTURE"\n',
        encoding="utf-8",
    )
    fake_opencode.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "opencode")
    monkeypatch.setenv("SELECTED_CAPTURE", str(selected_capture))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    launched = CliRunner().invoke(main, ["workstream", "--agent", "auto", str(repo), "Auto Lane"])
    assert launched.exit_code == 0, launched.output
    assert selected_capture.read_text(encoding="utf-8") == "opencode"
    manifest = repo / ".worktrees" / "auto-lane" / ".limen-workstream" / "manifest.md"
    assert "Agent: `opencode`" in manifest.read_text(encoding="utf-8")

    invalid = CliRunner().invoke(main, ["workstream", "--agent", "not-a-lane", str(repo), "Invalid Lane"])
    assert invalid.exit_code != 0
    assert not (repo / ".worktrees" / "invalid-lane").exists()


def test_primary_native_agent_launch_adapters_preserve_selected_identity(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    fake_agent = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$LIMEN_AGENT" > "$CAPTURE_DIR/$LIMEN_AGENT.identity"
printf '%s\n' "$@" > "$CAPTURE_DIR/$LIMEN_AGENT.args"
"""
    for agent in ("codex", "claude", "copilot", "agy", "opencode"):
        executable = fake_bin / agent
        executable.write_text(fake_agent, encoding="utf-8")
        executable.chmod(0o755)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("CAPTURE_DIR", str(capture_dir))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    for agent in ("codex", "claude", "copilot", "agy", "opencode"):
        result = CliRunner().invoke(
            main,
            [
                "workstream",
                "--autonomous",
                "--agent",
                agent,
                "--prompt",
                f"Exercise the native {agent} launch adapter.",
                str(repo),
                f"Native {agent}",
            ],
        )
        assert result.exit_code == 0, f"{agent}: {result.output}"
        assert (capture_dir / f"{agent}.identity").read_text(encoding="utf-8").strip() == agent
        args = (capture_dir / f"{agent}.args").read_text(encoding="utf-8").splitlines()
        if agent == "opencode":
            assert args[0] == "--prompt"
        elif agent == "agy":
            assert args[0] == "--prompt-interactive"
        else:
            assert args[0].startswith("# Continuation capsule:")
