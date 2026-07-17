from __future__ import annotations

import copy
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from limen import fable_contract, model_selection, owner_authority


def _authority(tmp_path: Path):
    root = tmp_path / "authority"
    root.mkdir()
    private_key = root / "test-owner"
    subprocess.run(
        ["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
    )
    public_parts = private_key.with_suffix(".pub").read_text().split()
    (root / "allowed_signers").write_text(f"{owner_authority.OWNER_PRINCIPAL} {public_parts[0]} {public_parts[1]}\n")

    class TestAuthority:
        @staticmethod
        def receipt_path(name: str) -> Path:
            return root / "receipts" / name

        @staticmethod
        def verify_receipt(receipt, *, namespace: str):
            return owner_authority.verify_receipt(
                receipt,
                namespace=namespace,
                _trust_root=root,
                _require_sealed=False,
            )

    def sign(receipt: dict, namespace: str) -> dict:
        payload = tmp_path / f"{namespace}.json"
        payload.write_bytes(owner_authority.canonical_payload(receipt))
        subprocess.run(
            ["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", namespace, str(payload)],
            check=True,
            capture_output=True,
        )
        signed = copy.deepcopy(receipt)
        signed["owner_attestation"] = {
            "schema": owner_authority.ATTESTATION_SCHEMA,
            "principal": owner_authority.OWNER_PRINCIPAL,
            "namespace": namespace,
            "signature": payload.with_suffix(".json.sig").read_text(),
        }
        return signed

    return root, TestAuthority, sign


def _acceptance(now: datetime) -> dict:
    return {
        "schema": fable_contract.ACCEPTANCE_SCHEMA,
        "authority_status": "owner-signed",
        "authorized": True,
        "created_at": now.isoformat(),
        "week": fable_contract.current_week(now),
        "category": "adversarial-review",
        "percent": 5,
        "sources": ["owner://fable/acceptance"],
        "redacted_packets": [],
        "verification": ["scripts/verify-fable-gate.sh"],
        "reserve_unlocked": False,
        "mode": "plan-only",
        "deliverable": "continuation-capsule",
        "builder_handoff": fable_contract.builder_handoff(),
        "motion_receipt_deadline_seconds": fable_contract.MOTION_RECEIPT_DEADLINE_SECONDS,
    }


def _balance(now: datetime) -> dict:
    return {
        "schema": fable_contract.BALANCE_SCHEMA,
        "authority_status": "owner-signed",
        "authorized": True,
        "observed_at": now.isoformat(),
        "week": fable_contract.current_week(now),
        "spent_tokens": 50,
        "spent_pct": 5,
        "deliberate_cap": 40,
        "hard_cap": 50,
        "over_cap": False,
        "source": "owner://fable/usage-meter",
        "meter_ready": True,
        "measurement": {"method": "owner-used-percent", "owner_observed_pct": 5},
    }


def test_fixed_owner_root_ignores_caller_home_and_limen_root(monkeypatch) -> None:
    expected_home = Path(__import__("pwd").getpwuid(os.getuid()).pw_dir).resolve()
    monkeypatch.setenv("HOME", "/tmp/attacker-home")
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/attacker-worktree")
    assert owner_authority.authority_root() == (
        expected_home / "Library" / "Application Support" / "org.organvm.limen" / "authority"
    )


def test_same_user_immutable_file_is_not_independent_custody(tmp_path) -> None:
    path = tmp_path / "same-user-authority"
    path.write_text("fixture")
    with pytest.raises(owner_authority.OwnerAuthorityError, match="unsealed"):
        owner_authority._sealed_regular_file(path)


def test_owner_signature_rejects_tampered_source(tmp_path) -> None:
    root, _authority_module, sign = _authority(tmp_path)
    receipt = sign({"schema": "fixture.v1", "source": "owner"}, "limen-test")
    assert (
        owner_authority.verify_receipt(
            receipt,
            namespace="limen-test",
            _trust_root=root,
            _require_sealed=False,
        )
        == receipt
    )
    receipt["source"] = "executor-forgery"
    with pytest.raises(owner_authority.OwnerAuthorityError, match="signature-invalid"):
        owner_authority.verify_receipt(
            receipt,
            namespace="limen-test",
            _trust_root=root,
            _require_sealed=False,
        )


def test_forged_zero_spend_cannot_authorize_fable(tmp_path, monkeypatch) -> None:
    _root, authority_module, sign = _authority(tmp_path)
    monkeypatch.setattr(fable_contract, "_owner_authority", lambda: authority_module)
    now = datetime.now(timezone.utc)
    acceptance = sign(_acceptance(now), "limen-fable-acceptance")
    balance = sign(_balance(now), "limen-fable-balance")
    assert fable_contract.validate_acceptance_receipt(acceptance, moment=now) == acceptance
    assert fable_contract.validate_balance_receipt(balance, moment=now) == balance

    forged = copy.deepcopy(balance)
    forged["spent_tokens"] = 0
    forged["spent_pct"] = 0
    forged["measurement"]["owner_observed_pct"] = 0
    with pytest.raises(fable_contract.ContractError, match="signature-invalid"):
        fable_contract.validate_balance_receipt(forged, moment=now)


def test_signed_selection_binds_role_catalog_and_rejects_tamper(tmp_path, monkeypatch) -> None:
    root, authority_module, sign = _authority(tmp_path)
    monkeypatch.setattr(model_selection, "_owner_authority", lambda: authority_module)
    model = "provider/opaque-renamed-id"
    models = [{"id": model, "active": True, "execution_roles": ["implementation-builder"]}]
    receipt = {
        "schema": model_selection.CLAUDE_MODEL_SELECTION_SCHEMA,
        "authority_status": "owner-signed",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": "owner://claude/live-catalog",
        "attempt_id": "attempt-signed-selection",
        "task_id": "task-signed-selection",
        "selection_source": "claude_live_catalog",
        "selected_model": model,
        "execution_profile": {
            "execution_role": "implementation-builder",
            "planning_only": False,
            "build_allowed": True,
        },
        "models": models,
        "catalog_hash": model_selection._catalog_hash(model_selection._normalized_models(models)),
    }
    signed = sign(receipt, "limen-claude-model-selection")
    path = authority_module.receipt_path("claude-model-selection.json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(signed))
    assert model_selection.load_selection_receipt()["selected_model"] == model

    signed["source"] = "executor://forged-source"
    path.write_text(json.dumps(signed))
    with pytest.raises(model_selection.ModelSelectionBlocked, match="attestation is invalid"):
        model_selection.load_selection_receipt()
