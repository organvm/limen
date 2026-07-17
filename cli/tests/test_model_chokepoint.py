"""Executable proof that the Claude shim preserves provider Auto."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from limen.model_selection import model_for_argv


REPO = Path(__file__).resolve().parents[2]
SHIM = REPO / "scripts" / "shims" / "claude"


@pytest.mark.parametrize(
    "args",
    [
        ["-p", "hello"],
        ["--print", "hello"],
        ["--resume", "session-fixture", "-p", "continue"],
        ["mcp", "add", "--scope", "user", "fixture", "https://example.invalid"],
        ["--version"],
        [],
    ],
)
def test_shim_sorter_never_invents_a_model(args: list[str], monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "unvalidated-fixture")

    assert model_for_argv(args) is None


def test_declared_model_is_left_for_dispatch_boundary_to_validate() -> None:
    assert model_for_argv(["-p", "--model", "provider-reported-fixture", "x"]) is None
    assert model_for_argv(["-p", "--model=provider-reported-fixture", "x"]) is None


@pytest.fixture()
def stub_claude(tmp_path: Path) -> Path:
    stub = tmp_path / "real-claude"
    stub.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n')
    stub.chmod(0o755)
    return stub


def _run_shim(stub: Path, args: list[str], **env_overrides: str) -> list[str]:
    env = dict(os.environ)
    env.update({"LIMEN_REAL_CLAUDE": str(stub), "LIMEN_ROOT": str(REPO)})
    env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, str(SHIM), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.splitlines()


def test_shim_is_executable() -> None:
    assert SHIM.exists()
    assert os.access(SHIM, os.X_OK)


def test_shim_preserves_provider_auto_even_with_unvalidated_env_pin(stub_claude: Path) -> None:
    args = ["-p", "hello"]
    out = _run_shim(
        stub_claude,
        args,
        LIMEN_CLAUDE_MODEL="unvalidated-fixture",
    )
    assert out == args


def test_shim_passes_dispatch_validated_model_through_unchanged(stub_claude: Path) -> None:
    args = ["-p", "--model", "provider-reported-fixture", "do work"]
    assert _run_shim(stub_claude, args) == args


def test_shim_fails_open_when_sorter_unavailable(stub_claude: Path, tmp_path: Path) -> None:
    args = ["-p", "hello"]
    assert _run_shim(stub_claude, args, LIMEN_ROOT=str(tmp_path / "nonexistent")) == args
