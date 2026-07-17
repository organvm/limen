"""Claude routing uses provider Auto or fresh opaque owner selections."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import limen.dispatch as D
import limen.model_selection as MS
from limen.models import Task


def _task(*, labels: list[str] | None = None, claude_tier: str | None = None) -> Task:
    return Task(
        id="CLAUDE-DYNAMIC",
        title="provider-neutral task",
        target_agent="claude",
        labels=labels or [],
        claude_tier=claude_tier,
        created=date(2026, 7, 17),
    )


def _generic_profile() -> dict[str, object]:
    return {
        "execution_role": None,
        "planning_only": False,
        "build_allowed": True,
        "fanout_allowed": False,
    }


def _fable_profile() -> dict[str, object]:
    return {
        "execution_role": "fable-planner",
        "planning_only": True,
        "build_allowed": False,
        "fanout_allowed": False,
    }


def _selection(
    root: Path,
    *,
    selected: str,
    profile: dict[str, object],
    rows: list[dict] | None = None,
    observed_at: datetime | None = None,
) -> Path:
    models = rows or [{"id": selected, "active": True, "execution_roles": []}]
    normalized = MS._normalized_models(models)
    receipt = {
        "schema": MS.CLAUDE_MODEL_SELECTION_SCHEMA,
        "observed_at": (observed_at or datetime.now(timezone.utc)).isoformat(),
        "source": "test-live-owner-adapter",
        "attempt_id": "attempt-arbitrarily-renamed",
        "selection_source": "provider_live_catalog",
        "selected_model": selected,
        "execution_profile": profile,
        "models": models,
        "catalog_hash": MS._catalog_hash(normalized),
    }
    path = root / "claude-model-selection.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def _acceptance(root: Path) -> Path:
    now = datetime.now(timezone.utc)
    path = root / "acceptance.json"
    path.write_text(
        json.dumps(
            {
                "schema": "limen.fable_acceptance.v1",
                "created_at": now.isoformat(),
                "week": (now - timedelta(days=now.weekday())).date().isoformat(),
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
    return path


def _balance(root: Path, *, spent_pct: float = 5) -> Path:
    now = datetime.now(timezone.utc)
    path = root / "balance.json"
    path.write_text(
        json.dumps(
            {
                "schema": "limen.fable_balance.v1",
                "observed_at": now.isoformat(),
                "week": (now - timedelta(days=now.weekday())).date().isoformat(),
                "spent_tokens": 5,
                "spent_pct": spent_pct,
                "deliberate_cap": 40,
                "hard_cap": 50,
                "over_cap": spent_pct >= 50,
                "source": "test-live-owner-adapter",
                "meter_ready": True,
                "measurement": {
                    "method": "owner-used-percent",
                    "owner_observed_pct": spent_pct,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture(autouse=True)
def _clear(monkeypatch) -> None:
    for name in (
        "LIMEN_CLAUDE_MODEL",
        "LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT",
        "LIMEN_CLAUDE_MODEL_SELECTION_MAX_AGE_SECONDS",
        "LIMEN_FABLE_ACCEPTANCE",
        "LIMEN_FABLE_BALANCE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_provider_auto_ignores_legacy_tiers_and_name_shapes() -> None:
    assert D._claude_model(_task()) is None
    assert D._claude_model(_task(labels=["tier:any-renamed-shape"], claude_tier="opus")) is None
    assert MS._CLAUDE_TIER_ORDER == ()
    assert MS._claude_opus_classes() == set()
    assert MS._claude_fable_classes() == set()


def test_explicit_override_requires_fresh_exact_live_selection(tmp_path, monkeypatch) -> None:
    model = "shape-z-with-no-semantic-name"
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", model)
    with pytest.raises(D.ClaudeLaunchContractError, match="no live selection receipt"):
        D._claude_launch_selection(_task())

    receipt = _selection(
        tmp_path,
        selected=model,
        profile=_generic_profile(),
        rows=[
            {"id": "shape-y", "active": True, "execution_roles": []},
            {"id": model, "active": True, "execution_roles": []},
        ],
    )
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT", str(receipt))
    assert D._claude_launch_selection(_task()) == (model, False)

    payload = json.loads(receipt.read_text())
    payload["selected_model"] = "shape-y"
    receipt.write_text(json.dumps(payload))
    with pytest.raises(D.ClaudeLaunchContractError, match="differs from the owner selection"):
        D._claude_launch_selection(_task())


def test_catalog_add_remove_reorder_uses_opaque_ids(tmp_path, monkeypatch) -> None:
    selected = "renamed-02"
    rows = [
        {"id": "renamed-03", "active": True, "execution_roles": []},
        {"id": selected, "active": True, "execution_roles": []},
        {"id": "renamed-01", "active": True, "execution_roles": []},
    ]
    receipt = _selection(tmp_path, selected=selected, profile=_generic_profile(), rows=rows)
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT", str(receipt))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", selected)
    assert D._claude_model(_task()) == selected

    reordered = list(reversed(rows))
    payload = json.loads(receipt.read_text())
    payload["models"] = reordered
    payload["catalog_hash"] = MS._catalog_hash(MS._normalized_models(reordered))
    receipt.write_text(json.dumps(payload))
    assert D._claude_model(_task()) == selected

    payload["models"] = [row for row in rows if row["id"] != selected]
    payload["catalog_hash"] = MS._catalog_hash(MS._normalized_models(payload["models"]))
    receipt.write_text(json.dumps(payload))
    assert D._claude_model(_task()) is None
    with pytest.raises(D.ClaudeLaunchContractError, match="absent from the live catalog"):
        D._claude_launch_selection(_task())


def test_stale_or_profile_mismatched_selection_fails_closed(tmp_path, monkeypatch) -> None:
    model = "shape-stale"
    receipt = _selection(
        tmp_path,
        selected=model,
        profile={"execution_role": "different-owner-profile"},
        observed_at=datetime.now(timezone.utc) - timedelta(minutes=6),
    )
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT", str(receipt))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", model)
    with pytest.raises(D.ClaudeLaunchContractError, match="stale"):
        D._claude_launch_selection(_task())

    receipt = _selection(
        tmp_path,
        selected=model,
        profile={"execution_role": "different-owner-profile"},
    )
    with pytest.raises(D.ClaudeLaunchContractError, match="profile does not match"):
        D._claude_launch_selection(_task())


def test_fable_identity_requires_role_authority_and_read_only_launch(tmp_path, monkeypatch) -> None:
    model = "opaque-planner-77"
    receipt = _selection(
        tmp_path,
        selected=model,
        profile=_fable_profile(),
        rows=[{"id": model, "active": True, "execution_roles": ["fable-planner"]}],
    )
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT", str(receipt))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", model)
    task = _task(labels=["execution-role:fable-planner", "mode:plan-only"])

    with pytest.raises(D.ClaudeLaunchContractError, match="acceptance-missing"):
        D._agent_argv("claude", task)

    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_acceptance(tmp_path)))
    monkeypatch.setenv("LIMEN_FABLE_BALANCE_PATH", str(_balance(tmp_path)))
    argv = D._agent_argv("claude", task)
    assert argv[argv.index("--model") + 1] == model
    assert set(argv[argv.index("--tools") + 1].split(",")) == {"Glob", "Grep", "Read"}
    assert set(argv[argv.index("--allowedTools") + 1].split(",")) == {"Glob", "Grep", "Read"}
    assert {
        "Agent",
        "AskUserQuestion",
        "Bash",
        "Edit",
        "NotebookEdit",
        "Workflow",
        "Write",
        "mcp__*",
    } <= set(argv[argv.index("--disallowedTools") + 1].split(","))


def test_fable_role_does_not_come_from_identifier_text(tmp_path, monkeypatch) -> None:
    model = "vendor/fable-looking-but-builder-owned"
    receipt = _selection(tmp_path, selected=model, profile=_generic_profile())
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT", str(receipt))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", model)
    assert D._claude_launch_selection(_task()) == (model, False)


def test_fable_role_metadata_and_profile_must_agree(tmp_path, monkeypatch) -> None:
    model = "opaque-role-bound"
    receipt = _selection(
        tmp_path,
        selected=model,
        profile=_generic_profile(),
        rows=[{"id": model, "active": True, "execution_roles": ["fable-planner"]}],
    )
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT", str(receipt))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", model)
    with pytest.raises(D.ClaudeLaunchContractError, match="not mutually bound"):
        D._claude_launch_selection(_task())


def test_fable_hard_cap_closes_live_selection(tmp_path, monkeypatch) -> None:
    model = "opaque-planner-capped"
    receipt = _selection(
        tmp_path,
        selected=model,
        profile=_fable_profile(),
        rows=[{"id": model, "active": True, "execution_roles": ["fable-planner"]}],
    )
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT", str(receipt))
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_acceptance(tmp_path)))
    monkeypatch.setenv("LIMEN_FABLE_BALANCE_PATH", str(_balance(tmp_path, spent_pct=50)))
    task = _task(labels=["execution-role:fable-planner", "mode:plan-only"])
    with pytest.raises(D.ClaudeLaunchContractError, match="hard-cap"):
        D._claude_launch_selection(task)


def test_plain_claude_argv_uses_provider_auto_and_build_tools() -> None:
    argv = D._agent_argv("claude", _task())
    assert "--model" not in argv
    assert {"Edit", "Write"} <= set(argv[argv.index("--allowedTools") + 1].split(","))
