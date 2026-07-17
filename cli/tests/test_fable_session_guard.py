"""Tests for the report-only interactive Fable SessionStart observer.

Fleet launchers enforce policy. The interactive hook always returns success and
never directs, retunes, terminates, or enumerates a live peer session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "fable-session-guard.py"


def _this_monday() -> str:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).date().isoformat()


def _run(payload: dict, env_extra: dict | None = None):
    env = {"PATH": os.environ.get("PATH", "")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def _balance(spent_pct: float) -> dict:
    return {
        "schema": "limen.fable_balance.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "week": _this_monday(),
        "spent_tokens": 0,
        "spent_pct": spent_pct,
        "deliberate_cap": 40,
        "hard_cap": 50,
        "over_cap": spent_pct >= 50,
        "source": "test-owner-adapter",
        "meter_ready": True,
        "measurement": {
            "method": "owner-used-percent",
            "owner_observed_pct": spent_pct,
        },
    }


def _acceptance() -> dict:
    return {
        "schema": "limen.fable_acceptance.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "week": _this_monday(),
        "category": "governance",
        "percent": 5,
        "sources": ["docs/fable-allotment.md"],
        "redacted_packets": [],
        "verification": ["pytest"],
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


def test_non_fable_model_is_noop(tmp_path):
    proc = _run({"model": "arbitrarily-renamed-provider-id"})
    assert proc.returncode == 0
    assert proc.stderr.strip() == ""


def test_explicit_fable_role_does_not_depend_on_a_model_id(tmp_path):
    proc = _run({"model": "arbitrarily-renamed-provider-id", "execution_role": "fable-planner"})
    assert proc.returncode == 0
    assert "CONTRACT RED" in proc.stderr


def test_fable_over_cap_reports_without_controlling_the_session(tmp_path):
    balance = tmp_path / "fable-allotment.json"
    balance.write_text(json.dumps(_balance(100.0)))
    proc = _run(
        {"model": "arbitrarily-renamed-provider-id", "execution_role": "fable-planner"},
        {"LIMEN_FABLE_BALANCE_PATH": str(balance)},
    )
    assert proc.returncode == 0
    assert "CONTRACT RED" in proc.stderr
    assert "/model" not in proc.stderr
    assert "report-only" in proc.stderr
    assert "end this invocation" not in proc.stderr


def test_fable_no_receipt_reports_even_under_cap(tmp_path):
    balance = tmp_path / "fable-allotment.json"
    balance.write_text(json.dumps(_balance(5.0)))
    proc = _run(
        {"model": "arbitrarily-renamed-provider-id", "execution_role": "fable-planner"},
        {"LIMEN_FABLE_BALANCE_PATH": str(balance)},
    )
    assert proc.returncode == 0
    assert "CONTRACT RED" in proc.stderr
    assert "acceptance" in proc.stderr


def test_fable_under_cap_with_receipt_is_clean(tmp_path):
    balance = tmp_path / "fable-allotment.json"
    balance.write_text(json.dumps(_balance(5.0)))
    receipt = tmp_path / "accept.json"
    receipt.write_text(json.dumps(_acceptance()))
    proc = _run(
        {"model": "arbitrarily-renamed-provider-id", "execution_role": "fable-planner"},
        {"LIMEN_FABLE_BALANCE_PATH": str(balance), "LIMEN_FABLE_ACCEPTANCE": str(receipt)},
    )
    assert proc.returncode == 0, proc.stderr
    assert "CONTRACT RED" not in proc.stderr


def test_fable_stale_balance_fails_closed_without_session_control(tmp_path):
    balance = tmp_path / "fable-allotment.json"
    data = _balance(5.0)
    data["observed_at"] = "2020-01-01T00:00:00+00:00"
    balance.write_text(json.dumps(data))
    receipt = tmp_path / "accept.json"
    receipt.write_text(json.dumps(_acceptance()))
    proc = _run(
        {"model": "arbitrarily-renamed-provider-id", "execution_role": "fable-planner"},
        {"LIMEN_FABLE_BALANCE_PATH": str(balance), "LIMEN_FABLE_ACCEPTANCE": str(receipt)},
    )
    assert proc.returncode == 0
    assert "balance-stale-observation" in proc.stderr
    assert "/model" not in proc.stderr
