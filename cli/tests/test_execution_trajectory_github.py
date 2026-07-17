"""GitHub owner adapter tests; no network or repository mutation."""

from __future__ import annotations

import base64
import json

import pytest

from limen.execution_trajectory_github import CommandResult, GitHubTrajectoryAdapter


BASE = "1" * 40
BASE_TREE = "2" * 40
BLOB_A = "3" * 40
BLOB_B = "4" * 40
TREE = "5" * 40
COMMIT = "6" * 40
OTHER_HEAD = "7" * 40


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
