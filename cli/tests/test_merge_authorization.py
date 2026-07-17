from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "_merge_authorization.py"


def _load():
    spec = importlib.util.spec_from_file_location("merge_authorization_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _payload(now: dt.datetime, **updates) -> dict:
    value = {
        "schema": "limen.merge_authorization.v1",
        "authorization_id": "merge-fixture-001",
        "action": "merge",
        "repository": "organvm/limen",
        "pull_request": 1152,
        "head_sha": "a" * 40,
        "issued_at": (now - dt.timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + dt.timedelta(minutes=9)).isoformat().replace("+00:00", "Z"),
        "review_gate_context": "limen.pr_review_gate.v1",
        "signer_principal": "keeper-citrine",
    }
    value.update(updates)
    return value


def _unsigned_receipt(path: Path, now: dt.datetime, **updates) -> Path:
    value = _payload(now, **updates)
    value["signature"] = "not-an-ssh-signature"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


def _signed_receipt(
    tmp_path: Path,
    now: dt.datetime,
    *,
    namespace: str = "limen.merge_authorization.v1",
    allowed_principal: str | None = None,
    **updates,
) -> tuple[Path, Path]:
    ssh_keygen = shutil.which("ssh-keygen")
    if ssh_keygen is None:
        pytest.skip("ssh-keygen is required for merge-authorization signature fixtures")
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = _payload(now, **updates)
    signer = str(payload["signer_principal"])
    key = tmp_path / "signer-key"
    subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload_path = tmp_path / "authorization-payload.json"
    payload_path.write_text(canonical, encoding="utf-8")
    subprocess.run(
        [ssh_keygen, "-Y", "sign", "-f", str(key), "-n", namespace, str(payload_path)],
        check=True,
        capture_output=True,
    )
    payload["signature"] = payload_path.with_suffix(".json.sig").read_text(encoding="ascii")
    receipt = tmp_path / "authorization.json"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    receipt.chmod(0o600)
    public_key = key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed_signers = tmp_path / "allowed-signers"
    allowed_signers.write_text(
        f"{allowed_principal or signer} {public_key[0]} {public_key[1]}\n",
        encoding="utf-8",
    )
    allowed_signers.chmod(0o600)
    return receipt, allowed_signers


def _unused_signers(tmp_path: Path) -> Path:
    path = tmp_path / "unused-allowed-signers"
    path.write_text("keeper-fixture ssh-ed25519 AAAAinvalidfixture\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def test_valid_signed_receipt_permits_only_its_exact_target(tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    receipt, allowed_signers = _signed_receipt(tmp_path, now)

    authorization = mod.load_authorization(
        receipt,
        allowed_signers=allowed_signers,
        now=now,
    )

    assert authorization.signer_principal == "keeper-citrine"
    assert authorization.allowed_signers_bytes == allowed_signers.read_bytes()
    assert authorization.allowed_signers_sha256 == hashlib.sha256(allowed_signers.read_bytes()).hexdigest()
    assert authorization.permits("organvm/limen", 1152, "a" * 40)
    assert not authorization.permits("organvm/limen", 1152, "b" * 40)
    assert not authorization.permits("organvm/other", 1152, "a" * 40)
    assert not authorization.permits("organvm/limen", 1153, "a" * 40)


def test_live_trust_mode_rejects_executor_owned_signer_registry(tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    receipt, allowed_signers = _signed_receipt(tmp_path, now)

    with pytest.raises(mod.AuthorizationError, match="owned by root"):
        mod.load_authorization(
            receipt,
            allowed_signers=allowed_signers,
            required_signer_uid=0,
            now=now,
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"schema": "wrong"}, "schema"),
        ({"action": "comment"}, "action"),
        ({"review_gate_context": "pr-gate"}, "review_gate_context"),
        ({"head_sha": "short"}, "head_sha"),
        ({"repository": "not-a-repository"}, "repository"),
        ({"pull_request": 0}, "pull_request"),
        ({"signer_principal": "bad principal"}, "signer_principal"),
    ],
)
def test_malformed_receipts_fail_closed(tmp_path: Path, updates, message: str):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    path = _unsigned_receipt(tmp_path / "receipt.json", now, **updates)

    with pytest.raises(mod.AuthorizationError, match=message):
        mod.load_authorization(path, allowed_signers=_unused_signers(tmp_path), now=now)


def test_expired_or_overbroad_window_fails_closed(tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    expired = _unsigned_receipt(
        tmp_path / "expired.json",
        now,
        issued_at=(now - dt.timedelta(minutes=10)).isoformat(),
        expires_at=(now - dt.timedelta(seconds=1)).isoformat(),
    )
    overbroad = _unsigned_receipt(
        tmp_path / "overbroad.json",
        now,
        issued_at=(now - dt.timedelta(minutes=1)).isoformat(),
        expires_at=(now + dt.timedelta(minutes=15)).isoformat(),
    )
    allowed_signers = _unused_signers(tmp_path)

    with pytest.raises(mod.AuthorizationError, match="expired"):
        mod.load_authorization(expired, allowed_signers=allowed_signers, now=now)
    with pytest.raises(mod.AuthorizationError, match="must not exceed 15 minutes"):
        mod.load_authorization(overbroad, allowed_signers=allowed_signers, now=now)


def test_tampered_payload_and_wrong_namespace_fail_signature_verification(tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    tampered, allowed_signers = _signed_receipt(tmp_path / "tampered", now)
    value = json.loads(tampered.read_text(encoding="utf-8"))
    value["head_sha"] = "b" * 40
    tampered.write_text(json.dumps(value), encoding="utf-8")
    wrong_namespace, wrong_namespace_signers = _signed_receipt(
        tmp_path / "wrong-namespace",
        now,
        namespace="limen.pr_review_receipt.v1",
    )

    with pytest.raises(mod.AuthorizationError, match="signature is invalid"):
        mod.load_authorization(tampered, allowed_signers=allowed_signers, now=now)
    with pytest.raises(mod.AuthorizationError, match="signature is invalid"):
        mod.load_authorization(
            wrong_namespace,
            allowed_signers=wrong_namespace_signers,
            now=now,
        )


def test_duplicate_json_members_fail_before_signature_verification(tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    receipt, allowed_signers = _signed_receipt(tmp_path, now)
    ambiguous = receipt.read_text(encoding="utf-8").replace(
        "{",
        '{"repository":"decoy/target",',
        1,
    )
    receipt.write_text(ambiguous, encoding="utf-8")

    with pytest.raises(mod.AuthorizationError, match="duplicate JSON member: repository"):
        mod.load_authorization(receipt, allowed_signers=allowed_signers, now=now)


def test_unknown_signer_principal_fails_closed(tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    receipt, allowed_signers = _signed_receipt(
        tmp_path,
        now,
        allowed_principal="keeper-other",
    )

    with pytest.raises(mod.AuthorizationError, match="signer is not allowed"):
        mod.load_authorization(receipt, allowed_signers=allowed_signers, now=now)


def test_symlink_and_writable_receipts_fail_closed(tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    target = _unsigned_receipt(tmp_path / "target.json", now)
    alias = tmp_path / "alias.json"
    alias.symlink_to(target)
    allowed_signers = _unused_signers(tmp_path)

    with pytest.raises(mod.AuthorizationError, match="non-symlink regular file"):
        mod.load_authorization(alias, allowed_signers=allowed_signers, now=now)

    target.chmod(0o620)
    assert os.stat(target).st_mode & 0o020
    with pytest.raises(mod.AuthorizationError, match="group- or world-writable"):
        mod.load_authorization(target, allowed_signers=allowed_signers, now=now)


def test_symlink_and_writable_allowed_signers_fail_closed(tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    receipt, allowed_signers = _signed_receipt(tmp_path, now)
    linked = tmp_path / "linked-allowed-signers"
    linked.symlink_to(allowed_signers)

    with pytest.raises(mod.AuthorizationError, match="non-symlink regular file"):
        mod.load_authorization(receipt, allowed_signers=linked, now=now)

    allowed_signers.chmod(0o620)
    assert allowed_signers.stat().st_mode & 0o020
    with pytest.raises(mod.AuthorizationError, match="group- or world-writable"):
        mod.load_authorization(receipt, allowed_signers=allowed_signers, now=now)


def test_allowed_signers_replacement_between_inspection_and_open_fails_closed(
    monkeypatch,
    tmp_path: Path,
):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    receipt, allowed_signers = _signed_receipt(tmp_path, now)
    replacement = tmp_path / "replacement-allowed-signers"
    replacement.write_text("keeper-other ssh-ed25519 AAAAreplacement\n", encoding="utf-8")
    replacement.chmod(0o600)
    real_open = mod.os.open
    swapped = False

    def swapping_open(path, flags, *args):
        nonlocal swapped
        if Path(path) == allowed_signers and not swapped:
            replacement.replace(allowed_signers)
            swapped = True
        return real_open(path, flags, *args)

    monkeypatch.setattr(mod.os, "open", swapping_open)

    with pytest.raises(mod.AuthorizationError, match="changed while it was opened"):
        mod.load_authorization(receipt, allowed_signers=allowed_signers, now=now)
    assert swapped is True


def test_signature_verifier_uses_immutable_allowed_signers_snapshot(monkeypatch, tmp_path: Path):
    mod = _load()
    now = dt.datetime(2026, 7, 16, 18, 0, tzinfo=dt.timezone.utc)
    receipt, allowed_signers = _signed_receipt(tmp_path, now)
    original = allowed_signers.read_bytes()
    replacement = tmp_path / "replacement-allowed-signers"
    replacement.write_text("keeper-other ssh-ed25519 AAAAreplacement\n", encoding="utf-8")
    replacement.chmod(0o600)
    verifier_snapshots: list[Path] = []

    def fake_run(args, **_kwargs):
        snapshot = Path(args[args.index("-f") + 1])
        verifier_snapshots.append(snapshot)
        assert snapshot != allowed_signers
        assert snapshot.read_bytes() == original
        replacement.replace(allowed_signers)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    authorization = mod.load_authorization(receipt, allowed_signers=allowed_signers, now=now)

    assert verifier_snapshots
    assert not verifier_snapshots[0].exists()
    assert authorization.allowed_signers_bytes == original
    assert authorization.allowed_signers_sha256 == hashlib.sha256(original).hexdigest()
    assert allowed_signers.read_bytes() != original
