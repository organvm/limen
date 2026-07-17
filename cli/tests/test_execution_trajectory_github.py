"""GitHub owner adapter tests; no network or repository mutation."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from limen.execution_trajectory import OwnerReceiptClaim, OwnerReceiptSnapshot
from limen.execution_trajectory_github import (
    CommandResult,
    GitHubTrajectoryAdapter,
    load_configured_receipt_authority,
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
EVIDENCE_DIGEST = "sha256:" + "c" * 64
VERIFIED_AT = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)


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
        ]
    )
    payloads = {"attempt-a": b'{"a":1}', "attempt-b": b'{"b":2}'}
    owner = adapter(runner)

    snapshot = owner.read_many([])
    assert dict(snapshot.records) == {}
    receipts = owner.publish_atomic(payloads, snapshot_token=snapshot.token)

    assert set(receipts) == {"attempt-a", "attempt-b"}
    assert all(f"/blob/{COMMIT}/receipts/execution-trajectories/" in receipt.reference for receipt in receipts.values())
    assert len(runner.calls) == 8
    commit_payload = json.loads(runner.calls[-2][1] or "{}")
    assert commit_payload["parents"] == [BASE]
    assert commit_payload["tree"] == TREE
    patch_payload = json.loads(runner.calls[-1][1] or "{}")
    assert patch_payload == {"force": False, "sha": COMMIT}
    assert runner.calls[-1][0][-2:] == ["--input", "-"]


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
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema": "limen.receipt_authorities.v1",
                "authorities": authorities,
            }
        )
    )


def _authority_evidence(reference: str) -> tuple[OwnerReceiptClaim, bytes]:
    claim = OwnerReceiptClaim(
        owner="github",
        reference=reference,
        digest=EVIDENCE_DIGEST,
        head_sha=EXECUTION_HEAD,
        attempt_id=ATTEMPT,
        task_id="TASK-17",
        repository="signal-garden/target",
        predicate_digest=PREDICATE,
        reconciliation_digest=RECONCILIATION,
    )
    snapshot = OwnerReceiptSnapshot(
        owner=claim.owner,
        reference=claim.reference,
        digest=claim.digest,
        head_sha=EXECUTION_HEAD,
        attempt_id=claim.attempt_id,
        task_id=claim.task_id,
        repository=claim.repository,
        predicate_digest=claim.predicate_digest,
        reconciliation_digest=RECONCILIATION,
        terminal=True,
        predicate_passed=True,
        verified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return claim, snapshot.model_dump_json().encode()


def test_configured_receipt_authority_authenticates_current_exact_owner_head(tmp_path: Path) -> None:
    config = tmp_path / "authorities.json"
    _authority_config(config)
    owner_path = f"receipts/value-authority/{hashlib.sha256(ATTEMPT.encode()).hexdigest()}.json"
    reference = f"https://github.com/signal-garden/orbit-index/blob/{BASE}/{owner_path}"
    claim, payload = _authority_evidence(reference)
    runner = ScriptedRunner(
        [
            result({"object": {"sha": BASE}}),
            result({"content": base64.b64encode(payload).decode(), "encoding": "base64"}),
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
    assert runner.calls[0][0][2].endswith("/git/ref/heads/trajectory-owner")
    assert f"?ref={BASE}" in runner.calls[1][0][2]


def test_configured_receipt_authority_rejects_stale_reference_before_content_read(
    tmp_path: Path,
) -> None:
    config = tmp_path / "authorities.json"
    _authority_config(config)
    owner_path = f"receipts/value-authority/{hashlib.sha256(ATTEMPT.encode()).hexdigest()}.json"
    reference = f"https://github.com/signal-garden/orbit-index/blob/{BASE}/{owner_path}"
    claim, _payload = _authority_evidence(reference)
    runner = ScriptedRunner([result({"object": {"sha": OTHER_HEAD}})])
    authority = load_configured_receipt_authority(config, runner=runner)
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
    assert len(runner.calls) == 1


def test_shipped_unprovisioned_registry_has_no_value_authority(tmp_path: Path) -> None:
    config = tmp_path / "authorities.json"
    _authority_config(config, empty=True)
    assert load_configured_receipt_authority(config, runner=ScriptedRunner([])) is None
