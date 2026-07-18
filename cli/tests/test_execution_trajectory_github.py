"""GitHub owner adapter tests; no network or repository mutation."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from limen.execution_trajectory import (
    OwnerReceiptClaim,
    OwnerReceiptEnvelope,
    OwnerReceiptPayload,
    OwnerReceiptSignature,
    canonical_owner_receipt_envelope_bytes,
    canonical_owner_receipt_payload_bytes,
)
from limen.execution_trajectory_github import (
    CommandResult,
    GitHubTrajectoryAdapter,
    load_configured_receipt_authority,
    load_system_receipt_authority,
)


BASE = "1" * 40
BASE_TREE = "2" * 40
BLOB_A = "3" * 40
BLOB_B = "4" * 40
TREE = "5" * 40
COMMIT = "6" * 40
OTHER_HEAD = "7" * 40
EXECUTION_HEAD = "8" * 40
ATTEMPT = "attempt-" + "9" * 64
PREDICATE = "sha256:" + "a" * 64
RECONCILIATION = "sha256:" + "b" * 64
VERIFIED_AT = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
SIGNATURE = "fixture-owner-signature-0001"
KEY_ID = "fixture-key-1"


class ScriptedRunner:
    def __init__(self, responses: list[CommandResult]):
        self.responses = list(responses)
        self.calls: list[tuple[list[str], str | None]] = []

    def run(self, argv, *, input_text=None, timeout=60):
        assert timeout == 60
        self.calls.append((list(argv), input_text))
        return self.responses.pop(0)


def result(payload: object, returncode: int = 0, stderr: str = "") -> CommandResult:
    return CommandResult(returncode, json.dumps(payload), stderr)


def content(payload: bytes) -> CommandResult:
    return result({"content": base64.b64encode(payload).decode(), "encoding": "base64"})


def ancestry(merge_base: str) -> CommandResult:
    return result({"merge_base_commit": {"sha": merge_base}})


def adapter(runner: ScriptedRunner) -> GitHubTrajectoryAdapter:
    return GitHubTrajectoryAdapter(
        repository="signal-garden/orbit-index",
        ref="trajectory-owner",
        root="receipts/execution-trajectories",
        runner=runner,
        gh="gh-fixture",
    )


def test_read_many_returns_exact_owner_bytes_and_treats_only_404_as_absent() -> None:
    payload = b'{"attempt":"a"}'
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            result({"content": base64.b64encode(payload).decode(), "encoding": "base64"}),
            CommandResult(1, "", "HTTP 404: Not Found"),
        ]
    )

    snapshot = adapter(runner).read_many(["attempt-a", "attempt-b"])
    assert snapshot.token == BASE
    assert dict(snapshot.records) == {"attempt-a": payload}
    with pytest.raises(TypeError):
        snapshot.records["attempt-c"] = b"mutation"
    assert len(runner.calls) == 3
    assert all(f"?ref={BASE}" in call[0][2] for call in runner.calls[1:])


def test_publish_atomic_creates_one_fast_forward_commit_for_the_batch() -> None:
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            result({"object": {"sha": BASE}}),
            result({"tree": {"sha": BASE_TREE}}),
            result({"sha": BLOB_A}),
            result({"sha": BLOB_B}),
            result({"sha": TREE}),
            result({"sha": COMMIT}),
            result({"ref": "refs/heads/trajectory-owner", "object": {"sha": COMMIT}}),
            result({"object": {"sha": COMMIT}}),
            ancestry(BASE),
            content(b'{"a":1}'),
            content(b'{"b":2}'),
        ]
    )
    payloads = {"attempt-a": b'{"a":1}', "attempt-b": b'{"b":2}'}
    owner = adapter(runner)

    snapshot = owner.read_many([])
    assert dict(snapshot.records) == {}
    receipts = owner.publish_atomic(payloads, snapshot_token=snapshot.token)

    assert set(receipts) == {"attempt-a", "attempt-b"}
    assert all(f"/blob/{COMMIT}/receipts/execution-trajectories/" in receipt.reference for receipt in receipts.values())
    assert len(runner.calls) == 12
    commit_payload = json.loads(runner.calls[6][1] or "{}")
    assert commit_payload["parents"] == [BASE]
    assert commit_payload["tree"] == TREE
    patch_payload = json.loads(runner.calls[7][1] or "{}")
    assert patch_payload == {"force": False, "sha": COMMIT}
    assert runner.calls[7][0][-2:] == ["--input", "-"]
    assert runner.calls[8][0][2].endswith("/git/ref/heads/trajectory-owner")
    assert f"/compare/{BASE}...{COMMIT}" in runner.calls[9][0][2]
    assert all(f"?ref={COMMIT}" in call[0][2] for call in runner.calls[10:])


def test_failed_compare_and_set_never_returns_publication_receipts() -> None:
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            result({"object": {"sha": BASE}}),
            result({"tree": {"sha": BASE_TREE}}),
            result({"sha": BLOB_A}),
            result({"sha": TREE}),
            result({"sha": COMMIT}),
            CommandResult(1, "", "HTTP 422: Update is not a fast forward"),
        ]
    )
    owner = adapter(runner)

    with pytest.raises(RuntimeError, match="fast forward"):
        snapshot = owner.read_many([])
        owner.publish_atomic(
            {"attempt-a": b'{"a":1}'},
            snapshot_token=snapshot.token,
        )


def test_false_success_patch_response_never_returns_publication_receipts() -> None:
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            result({"object": {"sha": BASE}}),
            result({"tree": {"sha": BASE_TREE}}),
            result({"sha": BLOB_A}),
            result({"sha": TREE}),
            result({"sha": COMMIT}),
            result({"ref": "refs/heads/trajectory-owner", "object": {"sha": OTHER_HEAD}}),
        ]
    )
    owner = adapter(runner)

    with pytest.raises(RuntimeError, match="PATCH response"):
        snapshot = owner.read_many([])
        owner.publish_atomic({"attempt-a": b'{"a":1}'}, snapshot_token=snapshot.token)


def test_exact_commit_content_mismatch_never_returns_publication_receipts() -> None:
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            result({"object": {"sha": BASE}}),
            result({"tree": {"sha": BASE_TREE}}),
            result({"sha": BLOB_A}),
            result({"sha": TREE}),
            result({"sha": COMMIT}),
            result({"ref": "refs/heads/trajectory-owner", "object": {"sha": COMMIT}}),
            result({"object": {"sha": COMMIT}}),
            ancestry(BASE),
            content(b'{"forged":true}'),
        ]
    )
    owner = adapter(runner)

    with pytest.raises(RuntimeError, match="readback mismatched"):
        snapshot = owner.read_many([])
        owner.publish_atomic({"attempt-a": b'{"a":1}'}, snapshot_token=snapshot.token)


def test_changed_owner_head_fails_before_any_blob_is_created() -> None:
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            result({"object": {"sha": OTHER_HEAD}}),
        ]
    )
    owner = adapter(runner)

    snapshot = owner.read_many([])
    assert dict(snapshot.records) == {}
    with pytest.raises(RuntimeError, match="compare-and-set lost"):
        owner.publish_atomic(
            {"attempt-a": b'{"a":1}'},
            snapshot_token=snapshot.token,
        )

    assert len(runner.calls) == 2


def test_overlapping_reads_keep_operation_local_compare_and_set_tokens() -> None:
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            result({"object": {"sha": OTHER_HEAD}}),
            result({"object": {"sha": OTHER_HEAD}}),
        ]
    )
    owner = adapter(runner)

    first = owner.read_many([])
    second = owner.read_many([])

    assert first.token == BASE
    assert second.token == OTHER_HEAD
    with pytest.raises(RuntimeError, match="compare-and-set lost"):
        owner.publish_atomic(
            {"attempt-a": b'{"a":1}'},
            snapshot_token=first.token,
        )
    assert len(runner.calls) == 3


def test_publish_requires_an_explicit_exact_head_snapshot_token() -> None:
    runner = ScriptedRunner([])
    owner = adapter(runner)

    with pytest.raises(RuntimeError, match="exact-head snapshot token"):
        owner.publish_atomic(
            {"attempt-a": b'{"a":1}'},
            snapshot_token="not-a-sha",
        )
    assert runner.calls == []


@pytest.mark.parametrize(
    ("repository", "ref", "root"),
    [
        ("not-a-repo", "main", "receipts"),
        ("signal-garden/orbit-index", "../escape", "receipts"),
        ("signal-garden/orbit-index", "main", "../receipts"),
    ],
)
def test_owner_identity_and_paths_fail_closed(repository: str, ref: str, root: str) -> None:
    with pytest.raises(ValueError):
        GitHubTrajectoryAdapter(repository=repository, ref=ref, root=root)


def test_owner_adapter_never_falls_back_to_ambient_path_or_bare_gh() -> None:
    with pytest.raises(ValueError, match="validated service runner"):
        GitHubTrajectoryAdapter(
            repository="signal-garden/orbit-index",
            ref="trajectory-owner",
            root="receipts/execution-trajectories",
        )
    with pytest.raises(ValueError, match="validated service runner"):
        GitHubTrajectoryAdapter(
            repository="signal-garden/orbit-index",
            ref="trajectory-owner",
            root="receipts/execution-trajectories",
            gh="gh",
        )


def _authority_config(path: Path, *, empty: bool = False) -> None:
    authorities = []
    if not empty:
        authorities.append(
            {
                "kind": "github",
                "owner": "github",
                "repository": "signal-garden/orbit-index",
                "ref": "trajectory-owner",
                "root": "receipts/value-authority",
                "signature_scheme": "owner-service-v1",
                "key_id": KEY_ID,
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema": "limen.receipt_authorities.v2",
                "authorities": authorities,
            }
        )
    )


def _authority_evidence(reference: str) -> tuple[OwnerReceiptClaim, bytes, bytes]:
    signed = OwnerReceiptPayload(
        owner="github",
        head_sha=EXECUTION_HEAD,
        attempt_id=ATTEMPT,
        task_id="TASK-17",
        repository="signal-garden/target",
        predicate_digest=PREDICATE,
        reconciliation_digest=RECONCILIATION,
        terminal=True,
        predicate_passed=True,
        issued_at=datetime(2026, 7, 17, 11, 59, tzinfo=timezone.utc),
    )
    envelope = OwnerReceiptEnvelope(
        payload=signed,
        signature=OwnerReceiptSignature(
            scheme="owner-service-v1",
            key_id=KEY_ID,
            value=SIGNATURE,
        ),
    )
    payload = canonical_owner_receipt_envelope_bytes(envelope)
    claim = OwnerReceiptClaim(
        owner="github",
        reference=reference,
        digest="sha256:" + hashlib.sha256(payload).hexdigest(),
        head_sha=EXECUTION_HEAD,
        attempt_id=ATTEMPT,
        task_id="TASK-17",
        repository="signal-garden/target",
        predicate_digest=PREDICATE,
        reconciliation_digest=RECONCILIATION,
    )
    return claim, payload, canonical_owner_receipt_payload_bytes(signed)


def signature_verified(unsigned: bytes) -> CommandResult:
    return result(
        {
            "valid": True,
            "owner": "github",
            "scheme": "owner-service-v1",
            "key_id": KEY_ID,
            "payload_digest": "sha256:" + hashlib.sha256(unsigned).hexdigest(),
        }
    )


def test_configured_receipt_authority_authenticates_reachable_exact_receipt_commit(tmp_path: Path) -> None:
    config = tmp_path / "authorities.json"
    _authority_config(config)
    owner_path = f"receipts/value-authority/{hashlib.sha256(ATTEMPT.encode()).hexdigest()}.json"
    reference = f"https://github.com/signal-garden/orbit-index/blob/{BASE}/{owner_path}"
    claim, payload, unsigned = _authority_evidence(reference)
    runner = ScriptedRunner(
        [
            result({"object": {"sha": OTHER_HEAD}}),
            ancestry(BASE),
            content(payload),
            signature_verified(unsigned),
        ]
    )
    authority = load_configured_receipt_authority(
        config,
        runner=runner,
        gh="gh-fixture",
        clock=lambda: VERIFIED_AT,
    )
    assert authority is not None

    snapshot = authority.verify(
        claim,
        attempt_id=ATTEMPT,
        task_id="TASK-17",
        repository="signal-garden/target",
        predicate_digest=PREDICATE,
    )

    assert snapshot is not None
    assert snapshot.verified_at == VERIFIED_AT
    assert snapshot.reference == reference
    assert snapshot.digest == claim.digest
    assert runner.calls[0][0][2].endswith("/git/ref/heads/trajectory-owner")
    assert f"/compare/{BASE}...{OTHER_HEAD}" in runner.calls[1][0][2]
    assert f"?ref={BASE}" in runner.calls[2][0][2]
    assert runner.calls[3][0][1:3] == ["verify-signature", "--owner"]


def test_configured_receipt_authority_rejects_diverged_reference_before_content_read(
    tmp_path: Path,
) -> None:
    config = tmp_path / "authorities.json"
    _authority_config(config)
    owner_path = f"receipts/value-authority/{hashlib.sha256(ATTEMPT.encode()).hexdigest()}.json"
    reference = f"https://github.com/signal-garden/orbit-index/blob/{BASE}/{owner_path}"
    claim, _payload, _unsigned = _authority_evidence(reference)
    runner = ScriptedRunner([result({"object": {"sha": OTHER_HEAD}}), ancestry(OTHER_HEAD)])
    authority = load_configured_receipt_authority(config, runner=runner, gh="gh-fixture")
    assert authority is not None

    assert (
        authority.verify(
            claim,
            attempt_id=ATTEMPT,
            task_id="TASK-17",
            repository="signal-garden/target",
            predicate_digest=PREDICATE,
        )
        is None
    )
    assert len(runner.calls) == 2


def test_owner_receipt_envelope_has_no_commit_or_digest_self_reference() -> None:
    owner_path = f"receipts/value-authority/{hashlib.sha256(ATTEMPT.encode()).hexdigest()}.json"
    reference = f"https://github.com/signal-garden/orbit-index/blob/{BASE}/{owner_path}"
    claim, payload, _unsigned = _authority_evidence(reference)
    decoded = json.loads(payload)

    assert claim.reference not in payload.decode()
    assert claim.digest not in payload.decode()
    assert "reference" not in decoded
    assert "digest" not in decoded
    assert "reference" not in decoded["payload"]
    assert "digest" not in decoded["payload"]


def test_owner_receipt_rejects_false_signature_or_content_digest(tmp_path: Path) -> None:
    config = tmp_path / "authorities.json"
    _authority_config(config)
    owner_path = f"receipts/value-authority/{hashlib.sha256(ATTEMPT.encode()).hexdigest()}.json"
    reference = f"https://github.com/signal-garden/orbit-index/blob/{BASE}/{owner_path}"
    claim, payload, _unsigned = _authority_evidence(reference)
    forged = claim.model_copy(update={"digest": "sha256:" + "0" * 64})
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            ancestry(BASE),
            content(payload),
        ]
    )
    authority = load_configured_receipt_authority(config, runner=runner, gh="gh-fixture")
    assert authority is not None

    assert (
        authority.verify(
            forged,
            attempt_id=ATTEMPT,
            task_id="TASK-17",
            repository="signal-garden/target",
            predicate_digest=PREDICATE,
        )
        is None
    )
    assert len(runner.calls) == 3


def test_owner_receipt_rejects_false_independent_signature(tmp_path: Path) -> None:
    config = tmp_path / "authorities.json"
    _authority_config(config)
    owner_path = f"receipts/value-authority/{hashlib.sha256(ATTEMPT.encode()).hexdigest()}.json"
    reference = f"https://github.com/signal-garden/orbit-index/blob/{BASE}/{owner_path}"
    claim, payload, unsigned = _authority_evidence(reference)
    rejected_signature = json.loads(signature_verified(unsigned).stdout)
    rejected_signature["valid"] = False
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            ancestry(BASE),
            content(payload),
            result(rejected_signature),
        ]
    )
    authority = load_configured_receipt_authority(config, runner=runner, gh="gh-fixture")
    assert authority is not None

    assert (
        authority.verify(
            claim,
            attempt_id=ATTEMPT,
            task_id="TASK-17",
            repository="signal-garden/target",
            predicate_digest=PREDICATE,
        )
        is None
    )
    assert len(runner.calls) == 4


def test_shipped_unprovisioned_registry_has_no_value_authority(tmp_path: Path) -> None:
    config = tmp_path / "authorities.json"
    _authority_config(config, empty=True)
    assert load_configured_receipt_authority(config, runner=ScriptedRunner([]), gh="gh-fixture") is None


def test_production_authority_ignores_forged_path_and_checkout_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "gh"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    _authority_config(tmp_path / "execution-receipt-authorities.json")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIMEN_RECEIPT_AUTHORITY_CONFIG", str(tmp_path / "execution-receipt-authorities.json"))

    with pytest.raises(ValueError, match="unprovisioned"):
        load_system_receipt_authority()
