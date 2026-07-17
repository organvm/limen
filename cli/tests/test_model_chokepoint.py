"""End-to-end tests for the fail-closed Claude override shim."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import limen.model_selection as MS

REPO = Path(__file__).resolve().parents[2]
SHIM = REPO / "scripts" / "shims" / "claude"
_SELECTION_ENV = (
    "LIMEN_CLAUDE_MODEL",
    "ANTHROPIC_MODEL",
    "CLAUDE_MODEL",
    "LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT",
    "LIMEN_CLAUDE_MODEL_SELECTION_MAX_AGE_SECONDS",
    "LIMEN_FABLE_ACCEPTANCE",
    "LIMEN_FABLE_BALANCE_PATH",
)


def _profile(*, fable: bool = False) -> dict:
    return {
        "execution_role": "fable-planner" if fable else None,
        "planning_only": fable,
        "build_allowed": not fable,
        "fanout_allowed": False,
    }


def _selection(
    root: Path,
    model: str,
    *,
    fable: bool = False,
    rows: list[dict] | None = None,
) -> Path:
    models = rows or [
        {
            "id": model,
            "active": True,
            "execution_roles": ["fable-planner"] if fable else [],
        }
    ]
    value = {
        "schema": MS.CLAUDE_MODEL_SELECTION_SCHEMA,
        "authority_status": "owner-signed",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": "test-live-owner-adapter",
        "attempt_id": "attempt-shim-adversarial",
        "task_id": "task-shim-adversarial",
        "selection_source": "provider_live_catalog",
        "selected_model": model,
        "execution_profile": _profile(fable=fable),
        "models": models,
        "catalog_hash": MS._catalog_hash(MS._normalized_models(models)),
    }
    if fable:
        value["launch_contract"] = {
            "schema": "limen.fable_preservation_launch.v1",
            "orchestrator": "limen.preservation-orchestrator",
            "attempt_id": value["attempt_id"],
            "mode": "noninteractive-print",
            "resume_allowed": False,
            "direct_launch_allowed": False,
        }
        value["fable_authority"] = {"fixture": True}
    path = root / "selection.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _fable_authority(root: Path) -> tuple[Path, Path]:
    now = datetime.now(timezone.utc)
    week = (now - timedelta(days=now.weekday())).date().isoformat()
    acceptance = root / "acceptance.json"
    acceptance.write_text(
        json.dumps(
            {
                "schema": "limen.fable_acceptance.v1",
                "created_at": now.isoformat(),
                "week": week,
                "category": "adversarial-review",
                "percent": 5,
                "sources": ["docs/fable-allotment.md"],
                "redacted_packets": [],
                "verification": ["scripts/verify-fable-gate.sh"],
                "mode": "plan-only",
                "deliverable": "continuation-capsule",
                "builder_handoff": {
                    "provider_selection": "auto",
                    "requirements": {
                        "planning_only": False,
                        "build_allowed": True,
                        "fable_allowed": False,
                    },
                },
                "motion_receipt_deadline_seconds": 5400,
            }
        ),
        encoding="utf-8",
    )
    balance = root / "balance.json"
    balance.write_text(
        json.dumps(
            {
                "schema": "limen.fable_balance.v1",
                "observed_at": now.isoformat(),
                "week": week,
                "spent_tokens": 5,
                "spent_pct": 5,
                "deliberate_cap": 40,
                "hard_cap": 50,
                "over_cap": False,
                "source": "test-live-owner-adapter",
                "meter_ready": True,
                "measurement": {
                    "method": "owner-used-percent",
                    "owner_observed_pct": 5,
                },
            }
        ),
        encoding="utf-8",
    )
    return acceptance, balance


def _fable_args(model: str) -> list[str]:
    denied = "Agent,AskUserQuestion,Bash,Edit,NotebookEdit,Workflow,Write,mcp__*"
    return [
        "-p",
        "bounded plan",
        "--model",
        model,
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Glob,Grep,Read",
        "--allowedTools",
        "Glob,Grep,Read",
        "--disallowedTools",
        denied,
        "--no-chrome",
    ]


@pytest.fixture(autouse=True)
def _clear(monkeypatch) -> None:
    for name in _SELECTION_ENV:
        monkeypatch.delenv(name, raising=False)


def test_bare_spawn_stays_on_provider_auto() -> None:
    assert MS.model_for_argv(["-p", "hello"]) is None
    assert MS.model_for_argv(["--version"]) is None


def test_direct_explicit_override_requires_exact_live_receipt(tmp_path, monkeypatch) -> None:
    model = "arbitrarily-renamed-ordinary-model"
    with pytest.raises(MS.ModelSelectionBlocked, match="unavailable|unprovisioned"):
        MS.model_for_argv(["-p", "--model", model, "hello"])

    receipt = _selection(tmp_path, model)
    monkeypatch.setattr(MS, "_selection_path", lambda raw=None: receipt)
    monkeypatch.setattr(MS, "_verify_owner_selection", lambda _value: None)
    assert MS.model_for_argv(["-p", "--model", model, "hello"]) is None
    with pytest.raises(MS.ModelSelectionBlocked, match="differs from the owner selection"):
        MS.model_for_argv(["-p", "--model", "renamed-but-not-selected", "hello"])

    payload = json.loads(receipt.read_text())
    payload["selection_source"] = "manual_assertion"
    receipt.write_text(json.dumps(payload))
    with pytest.raises(MS.ModelSelectionBlocked, match="not live-catalog evidence"):
        MS.model_for_argv(["-p", "--model", model, "hello"])


def test_fable_metadata_blocks_ordinary_mutation_path(tmp_path, monkeypatch) -> None:
    model = "opaque-plan-identity"
    receipt = _selection(tmp_path, model, fable=True)
    monkeypatch.setattr(MS, "_selection_path", lambda raw=None: receipt)
    monkeypatch.setattr(MS, "_verify_owner_selection", lambda _value: None)

    class FakeContract:
        FABLE_READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch"})

        @staticmethod
        def validate_authority_bundle(value, **_kwargs):
            assert value == {"fixture": True}
            return value

    monkeypatch.setattr(MS, "_fable_contract", lambda: FakeContract)
    monkeypatch.setattr(MS, "_require_fable_orchestrator", lambda: None)

    with pytest.raises(MS.ModelSelectionBlocked, match="plan-only read-only"):
        MS.model_for_argv(["-p", "--model", model, "--allowedTools", "Edit,Write", "build"])
    assert MS.model_for_argv(_fable_args(model)) is None
    for resume_args in (
        [*_fable_args(model), "--resume", "session-id"],
        [*_fable_args(model), "--continue"],
        [*_fable_args(model), "-c"],
    ):
        with pytest.raises(MS.ModelSelectionBlocked, match="plan-only read-only"):
            MS.model_for_argv(resume_args)


def test_fable_direct_route_is_rejected_even_with_valid_receipt(tmp_path, monkeypatch) -> None:
    model = "opaque-direct-plan"
    receipt = _selection(tmp_path, model, fable=True)
    monkeypatch.setattr(MS, "_selection_path", lambda raw=None: receipt)
    monkeypatch.setattr(MS, "_verify_owner_selection", lambda _value: None)

    class FakeContract:
        FABLE_READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch"})

        @staticmethod
        def validate_authority_bundle(value, **_kwargs):
            return value

    monkeypatch.setattr(MS, "_fable_contract", lambda: FakeContract)
    with pytest.raises(MS.ModelSelectionBlocked, match="direct launch is prohibited"):
        MS.model_for_argv(_fable_args(model))


def test_fable_name_text_without_role_metadata_is_ordinary(tmp_path, monkeypatch) -> None:
    model = "vendor/fable-looking-arbitrary-rename"
    receipt = _selection(tmp_path, model, fable=False)
    monkeypatch.setattr(MS, "_selection_path", lambda raw=None: receipt)
    monkeypatch.setattr(MS, "_verify_owner_selection", lambda _value: None)
    assert MS.model_for_argv(["-p", "--model", model, "ordinary"]) is None


@pytest.fixture()
def stub_claude(tmp_path):
    stub = tmp_path / "real-claude"
    stub.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n')
    stub.chmod(0o755)
    return stub


def _run_shim(stub: Path, args: list[str], **env_overrides: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key not in _SELECTION_ENV}
    env.update({"LIMEN_REAL_CLAUDE": str(stub), "LIMEN_ROOT": str(REPO)})
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(SHIM), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_shim_passes_provider_auto_without_injection(stub_claude) -> None:
    proc = _run_shim(stub_claude, ["-p", "hello"])
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["-p", "hello"]


def test_shim_blocks_unvalidated_direct_override(stub_claude) -> None:
    proc = _run_shim(stub_claude, ["-p", "--model", "opaque-unvalidated", "build"])
    assert proc.returncode == 78
    assert proc.stdout == ""
    assert "BLOCKED:" in proc.stderr


@pytest.mark.parametrize("name", ["LIMEN_CLAUDE_MODEL", "ANTHROPIC_MODEL", "CLAUDE_MODEL"])
def test_shim_blocks_every_unvalidated_environment_override(stub_claude, name) -> None:
    proc = _run_shim(stub_claude, ["-p", "build"], **{name: "opaque-unvalidated"})
    assert proc.returncode == 78
    assert "BLOCKED:" in proc.stderr


def test_shim_rejects_caller_path_even_for_exact_ordinary_override(stub_claude, tmp_path) -> None:
    model = "opaque-live-builder"
    receipt = _selection(tmp_path, model)
    args = ["-p", "--model", model, "build"]
    proc = _run_shim(
        stub_claude,
        args,
        LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT=str(receipt),
    )
    assert proc.returncode == 78
    assert "owner validator is unprovisioned" in proc.stderr


def test_shim_blocks_fable_identity_with_build_tools(stub_claude, tmp_path) -> None:
    model = "opaque-live-planner"
    receipt = _selection(tmp_path, model, fable=True)
    acceptance, balance = _fable_authority(tmp_path)
    proc = _run_shim(
        stub_claude,
        ["-p", "--model", model, "--allowedTools", "Edit,Write", "build"],
        LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT=str(receipt),
        LIMEN_FABLE_ACCEPTANCE=str(acceptance),
        LIMEN_FABLE_BALANCE_PATH=str(balance),
    )
    assert proc.returncode == 78
    assert "owner validator is unprovisioned" in proc.stderr


def test_shim_rejects_caller_authority_even_for_exact_fable_surface(stub_claude, tmp_path) -> None:
    model = "opaque-live-planner-renamed"
    receipt = _selection(tmp_path, model, fable=True)
    acceptance, balance = _fable_authority(tmp_path)
    args = _fable_args(model)
    proc = _run_shim(
        stub_claude,
        args,
        LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT=str(receipt),
        LIMEN_FABLE_ACCEPTANCE=str(acceptance),
        LIMEN_FABLE_BALANCE_PATH=str(balance),
    )
    assert proc.returncode == 78
    assert "owner validator is unprovisioned" in proc.stderr


def test_shim_blocks_override_when_validator_is_unavailable(stub_claude, tmp_path) -> None:
    proc = _run_shim(
        stub_claude,
        ["-p", "--model", "opaque", "build"],
        LIMEN_ROOT=str(tmp_path / "missing"),
    )
    assert proc.returncode == 78
    assert "owner validator is unprovisioned" in proc.stderr


def test_malicious_worktree_cannot_inject_validator(stub_claude, tmp_path) -> None:
    marker = tmp_path / "injected"
    injected = tmp_path / "cli" / "src" / "limen"
    injected.mkdir(parents=True)
    (injected / "model_selection.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
        "def model_for_argv(args): return 'attacker-model'\n"
    )
    proc = _run_shim(
        stub_claude,
        ["-p", "--model", "attacker-model", "build"],
        LIMEN_ROOT=str(tmp_path),
        LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT=str(tmp_path / "forged.json"),
    )
    assert proc.returncode == 78
    assert "owner validator is unprovisioned" in proc.stderr
    assert not marker.exists()


def test_shim_keeps_provider_auto_available_when_validator_is_unavailable(stub_claude, tmp_path) -> None:
    proc = _run_shim(
        stub_claude,
        ["-p", "build"],
        LIMEN_ROOT=str(tmp_path / "missing"),
    )
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["-p", "build"]
