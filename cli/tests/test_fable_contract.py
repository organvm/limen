from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from limen import fable_contract as contract


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _acceptance(now: datetime | None = None, *, category: str = "governance") -> dict:
    now = now or _now()
    return {
        "schema": contract.ACCEPTANCE_SCHEMA,
        "authority_status": "owner-signed",
        "authorized": True,
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
        "authority_status": "owner-signed",
        "authorized": True,
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


def _packet(root: Path, *, name: str = "recovery.md") -> dict:
    path = root / "docs" / "continuations" / "fable" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"# Bounded plan\n"
    path.write_bytes(payload)
    return {
        "schema": contract.PACKET_SCHEMA,
        "mode": "plan-only",
        "implementation_by_fable": "prohibited",
        "builder_handoff": contract.builder_handoff(),
        "path": f"docs/continuations/fable/{name}",
        "content_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _commit_packet(root: Path, packet: dict, *, repository: str = "organvm/limen") -> str:
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Fable Test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "fable@example.invalid"], cwd=root, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"https://github.com/{repository}.git"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "add", packet["path"]], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "packet"], cwd=root, check=True, capture_output=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_provider_neutral_acceptance_and_packet_have_no_model_or_tier(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(contract, "_verify_owner_receipt", lambda receipt, _namespace: receipt)
    receipt = contract.validate_acceptance_receipt(_acceptance())
    encoded = json.dumps(receipt, sort_keys=True)
    assert "model" not in encoded
    assert "tier" not in encoded

    packet = _packet(tmp_path)
    assert contract.validate_packet_metadata(packet, root=tmp_path) == packet


def test_unsigned_proposal_fields_cannot_survive_owner_adjudication(monkeypatch) -> None:
    monkeypatch.setattr(contract, "_verify_owner_receipt", lambda receipt, _namespace: receipt)
    acceptance = _acceptance()
    acceptance["authorized"] = False
    with pytest.raises(contract.ContractError, match="acceptance-owner-authority-status-invalid"):
        contract.validate_acceptance_receipt(acceptance)

    balance = _balance()
    balance["authorized"] = False
    with pytest.raises(contract.ContractError, match="balance-owner-authority-status-invalid"):
        contract.validate_balance_receipt(balance)


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
    monkeypatch.setattr(
        contract,
        "_owner_receipt_path",
        lambda name: acceptance_path if name == "fable-acceptance.json" else balance_path,
    )
    monkeypatch.setattr(contract, "_verify_owner_receipt", lambda receipt, _namespace: receipt)

    acceptance_path.write_text(json.dumps(_acceptance(now)))
    balance_path.write_text(json.dumps(_balance(now, spent_pct=45)))
    authority, reason = contract.authorization_status(
        moment=now,
        execution_profile_value=contract.execution_profile(),
    )
    assert authority is None
    assert reason == "reserve-required"

    acceptance_path.write_text(json.dumps(_acceptance(now, category="reserve")))
    authority, reason = contract.authorization_status(
        moment=now,
        execution_profile_value=contract.execution_profile(),
    )
    assert authority is not None
    assert reason == "ok"

    balance_path.write_text(json.dumps(_balance(now, spent_pct=50)))
    authority, reason = contract.authorization_status(
        moment=now,
        execution_profile_value=contract.execution_profile(),
    )
    assert authority is None
    assert reason == "hard-cap"


def test_execution_profile_is_exactly_plan_only() -> None:
    contract.validate_execution_profile(contract.execution_profile())
    with pytest.raises(contract.ContractError, match="fable-execution-profile-invalid"):
        contract.validate_execution_profile(
            {
                "execution_role": "fable-planner",
                "planning_only": True,
                "build_allowed": True,
                "fanout_allowed": False,
            }
        )


@pytest.mark.parametrize(
    "path",
    [
        "docs/continuations/fable/../../outside.md",
        "docs/continuations/fable/../outside.md",
        "docs/continuations/fable//plan.md",
        "./docs/continuations/fable/plan.md",
        "/docs/continuations/fable/plan.md",
        r"docs\continuations\fable\plan.md",
        "docs/continuations/fable/not-markdown.txt",
    ],
)
def test_packet_path_rejects_aliases_and_traversal(path: str) -> None:
    with pytest.raises(contract.ContractError, match="fable-packet-path-invalid"):
        contract.canonical_packet_path(path)


def test_packet_must_be_regular_in_worktree_and_digest_bound(tmp_path) -> None:
    packet = _packet(tmp_path)
    contract.validate_packet_metadata(packet, root=tmp_path)

    packet["content_sha256"] = "0" * 64
    with pytest.raises(contract.ContractError, match="fable-packet-digest-mismatch"):
        contract.validate_packet_metadata(packet, root=tmp_path)

    packet["path"] = "docs/continuations/fable/missing.md"
    with pytest.raises(contract.ContractError, match="fable-packet-file-missing"):
        contract.validate_packet_metadata(packet, root=tmp_path)

    directory = tmp_path / "docs" / "continuations" / "fable" / "directory.md"
    directory.mkdir()
    packet["path"] = "docs/continuations/fable/directory.md"
    with pytest.raises(contract.ContractError, match="fable-packet-file-not-regular"):
        contract.validate_packet_metadata(packet, root=tmp_path)


def test_packet_rejects_symlink_leaf_and_symlink_parent_escape(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("outside", encoding="utf-8")
    packet_dir = tmp_path / "docs" / "continuations" / "fable"
    packet_dir.mkdir(parents=True)
    leaf = packet_dir / "leaf.md"
    leaf.symlink_to(outside)
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    packet = {
        **_packet(tmp_path, name="valid.md"),
        "path": "docs/continuations/fable/leaf.md",
        "content_sha256": digest,
    }
    with pytest.raises(contract.ContractError, match="fable-packet-file-not-regular"):
        contract.validate_packet_metadata(packet, root=tmp_path)

    escaped_root = tmp_path / "escaped"
    escaped_root.mkdir()
    (escaped_root / "parent.md").write_text("outside", encoding="utf-8")
    other_root = tmp_path / "parent-link-root"
    (other_root / "docs" / "continuations").mkdir(parents=True)
    (other_root / "docs" / "continuations" / "fable").symlink_to(escaped_root)
    escaped_packet = dict(packet)
    escaped_packet["path"] = "docs/continuations/fable/parent.md"
    escaped_packet["content_sha256"] = hashlib.sha256(b"outside").hexdigest()
    with pytest.raises(contract.ContractError, match="fable-packet-path-invalid"):
        contract.validate_packet_metadata(escaped_packet, root=other_root)


def test_packet_receipt_requires_exact_commit_and_live_pr_head(tmp_path) -> None:
    packet = _packet(tmp_path)
    commit_sha = _commit_packet(tmp_path, packet)
    receipt = {
        "schema": contract.PACKET_RECEIPT_SCHEMA,
        "path": packet["path"],
        "content_sha256": packet["content_sha256"],
        "commit_sha": commit_sha,
        "pull_request": "https://github.com/organvm/limen/pull/1169",
    }

    def exact(_url: str) -> dict[str, str]:
        return {"repository": "organvm/limen", "head_sha": commit_sha}

    assert contract.validate_packet_receipt(receipt, root=tmp_path, pr_head_resolver=exact) == receipt

    for invalid in ("", "not-exact", "A" * 40, "a" * 39, "a" * 41):
        with pytest.raises(contract.ContractError, match="fable-packet-receipt-commit-missing"):
            contract.validate_packet_receipt(
                {**receipt, "commit_sha": invalid},
                root=tmp_path,
                pr_head_resolver=exact,
            )

    with pytest.raises(contract.ContractError, match="fable-packet-receipt-pr-missing"):
        contract.validate_packet_receipt(
            {key: value for key, value in receipt.items() if key != "pull_request"},
            root=tmp_path,
            pr_head_resolver=exact,
        )
    with pytest.raises(contract.ContractError, match="fable-packet-receipt-commit-missing"):
        contract.validate_packet_receipt(
            {key: value for key, value in receipt.items() if key != "commit_sha"},
            root=tmp_path,
            pr_head_resolver=exact,
        )
    with pytest.raises(contract.ContractError, match="fable-packet-receipt-pr-head-mismatch"):
        contract.validate_packet_receipt(
            receipt,
            root=tmp_path,
            pr_head_resolver=lambda _url: {
                "repository": "organvm/limen",
                "head_sha": "b" * 40,
            },
        )
    with pytest.raises(contract.ContractError, match="fable-packet-receipt-pr-identity-mismatch"):
        contract.validate_packet_receipt(
            {**receipt, "pull_request": "https://github.com/organvm/wrong/pull/1"},
            root=tmp_path,
            pr_head_resolver=lambda _url: {
                "repository": "organvm/wrong",
                "head_sha": commit_sha,
            },
        )


def test_packet_receipt_rejects_local_drift_after_exact_commit(tmp_path) -> None:
    packet = _packet(tmp_path)
    commit_sha = _commit_packet(tmp_path, packet)
    receipt = {
        "schema": contract.PACKET_RECEIPT_SCHEMA,
        "path": packet["path"],
        "content_sha256": packet["content_sha256"],
        "commit_sha": commit_sha,
        "pull_request": "https://github.com/organvm/limen/pull/1169",
    }
    (tmp_path / packet["path"]).write_text("# drift\n", encoding="utf-8")
    with pytest.raises(contract.ContractError, match="fable-packet-digest-mismatch"):
        contract.validate_packet_receipt(
            receipt,
            root=tmp_path,
            pr_head_resolver=lambda _url: {
                "repository": "organvm/limen",
                "head_sha": commit_sha,
            },
        )


def test_authorization_rejects_missing_or_non_plan_execution_profile(
    tmp_path,
    monkeypatch,
) -> None:
    now = _now()
    acceptance = tmp_path / "acceptance.json"
    balance = tmp_path / "balance.json"
    acceptance.write_text(json.dumps(_acceptance(now)), encoding="utf-8")
    balance.write_text(json.dumps(_balance(now)), encoding="utf-8")
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(acceptance))
    monkeypatch.setenv("LIMEN_FABLE_BALANCE_PATH", str(balance))

    for profile in (
        None,
        {**contract.execution_profile(), "execution_role": "builder"},
        {**contract.execution_profile(), "planning_only": False},
        {**contract.execution_profile(), "build_allowed": True},
        {**contract.execution_profile(), "fanout_allowed": True},
    ):
        authority, reason = contract.authorization_status(
            moment=now,
            execution_profile_value=profile,
        )
        assert authority is None
        assert reason == "fable-execution-profile-invalid"
