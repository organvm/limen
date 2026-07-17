from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from limen import fable_contract as contract


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _acceptance(now: datetime | None = None, *, category: str = "governance") -> dict:
    now = now or _now()
    return {
        "schema": contract.ACCEPTANCE_SCHEMA,
        "created_at": now.isoformat(),
        "week": contract.current_week(now),
        "category": category,
        "percent": 5,
        "sources": ["docs/fable-allotment.md"],
        "redacted_packets": [],
        "verification": ["scripts/verify-fable-gate.sh"],
        "reserve_unlocked": category == "reserve",
        "mode": "plan-only",
        "deliverable": "continuation-capsule",
        "builder_handoff": contract.builder_handoff(),
        "motion_receipt_deadline_seconds": contract.MOTION_RECEIPT_DEADLINE_SECONDS,
    }


def _balance(now: datetime | None = None, *, spent_pct: float = 5) -> dict:
    now = now or _now()
    return {
        "schema": contract.BALANCE_SCHEMA,
        "observed_at": now.isoformat(),
        "week": contract.current_week(now),
        "spent_tokens": 50,
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


def test_provider_neutral_acceptance_and_packet_have_no_model_or_tier() -> None:
    receipt = contract.validate_acceptance_receipt(_acceptance())
    encoded = json.dumps(receipt, sort_keys=True)
    assert "model" not in encoded
    assert "tier" not in encoded

    packet = {
        "schema": contract.PACKET_SCHEMA,
        "mode": "plan-only",
        "implementation_by_fable": "prohibited",
        "builder_handoff": contract.builder_handoff(),
        "path": "docs/continuations/fable/recovery.md",
    }
    assert contract.validate_packet_metadata(packet) == packet


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("mode", "build", "acceptance-mode-not-plan-only"),
        ("deliverable", "implementation", "acceptance-deliverable-invalid"),
        ("motion_receipt_deadline_seconds", 0, "acceptance-motion-deadline-invalid"),
        ("builder_handoff", {"provider_selection": "named-model"}, "builder-handoff-invalid"),
    ],
)
def test_acceptance_rejects_unbounded_or_static_builder_contract(field, value, reason) -> None:
    receipt = _acceptance()
    receipt[field] = value
    with pytest.raises(contract.ContractError, match=reason):
        contract.validate_acceptance_receipt(receipt)


def test_acceptance_rejects_future_or_week_mismatched_creation() -> None:
    now = _now()
    future = _acceptance(now)
    future["created_at"] = (now + timedelta(minutes=6)).isoformat()
    with pytest.raises(contract.ContractError, match="acceptance-created-at-future"):
        contract.validate_acceptance_receipt(future, moment=now)

    mismatched = _acceptance(now)
    mismatched["created_at"] = (now - timedelta(days=8)).isoformat()
    with pytest.raises(contract.ContractError, match="acceptance-created-at-week-mismatch"):
        contract.validate_acceptance_receipt(mismatched, moment=now)


def test_balance_rejects_stale_dark_future_and_incoherent_receipts(monkeypatch) -> None:
    now = _now()
    monkeypatch.setenv("LIMEN_FABLE_BALANCE_MAX_AGE_SECONDS", "900")

    stale = _balance(now - timedelta(minutes=16))
    with pytest.raises(contract.ContractError, match="balance-stale-observation"):
        contract.validate_balance_receipt(stale, moment=now)

    dark = _balance(now)
    dark["meter_ready"] = False
    with pytest.raises(contract.ContractError, match="balance-meter-dark"):
        contract.validate_balance_receipt(dark, moment=now)

    future = _balance(now + timedelta(minutes=6))
    with pytest.raises(contract.ContractError, match="balance-future-observation"):
        contract.validate_balance_receipt(future, moment=now)

    incoherent = _balance(now)
    incoherent["over_cap"] = True
    with pytest.raises(contract.ContractError, match="balance-over-cap-incoherent"):
        contract.validate_balance_receipt(incoherent, moment=now)

    spend_incoherent = _balance(now)
    spend_incoherent["measurement"] = {
        "method": "token-ratio",
        "numerator_tokens": 50,
        "denominator_tokens": 50,
    }
    with pytest.raises(contract.ContractError, match="balance-measurement-incoherent"):
        contract.validate_balance_receipt(spend_incoherent, moment=now)


def test_authorization_fails_closed_and_reserve_band_is_exact(tmp_path, monkeypatch) -> None:
    now = _now()
    acceptance_path = tmp_path / "acceptance.json"
    balance_path = tmp_path / "balance.json"
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(acceptance_path))
    monkeypatch.setenv("LIMEN_FABLE_BALANCE_PATH", str(balance_path))

    acceptance_path.write_text(json.dumps(_acceptance(now)))
    balance_path.write_text(json.dumps(_balance(now, spent_pct=45)))
    authority, reason = contract.authorization_status(moment=now)
    assert authority is None
    assert reason == "reserve-required"

    acceptance_path.write_text(json.dumps(_acceptance(now, category="reserve")))
    authority, reason = contract.authorization_status(moment=now)
    assert authority is not None
    assert reason == "ok"

    balance_path.write_text(json.dumps(_balance(now, spent_pct=50)))
    authority, reason = contract.authorization_status(moment=now)
    assert authority is None
    assert reason == "hard-cap"


def test_execution_profile_is_exactly_plan_only() -> None:
    contract.validate_execution_profile(
        {
            "execution_role": "fable-planner",
            "planning_only": True,
            "build_allowed": False,
            "fanout_allowed": False,
        }
    )
    with pytest.raises(contract.ContractError, match="fable-execution-profile-invalid"):
        contract.validate_execution_profile(
            {
                "execution_role": "fable-planner",
                "planning_only": True,
                "build_allowed": True,
                "fanout_allowed": False,
            }
        )
