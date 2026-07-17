from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from limen.dispatch import _attempt_launch_entry
from limen.execution_trajectory import (
    OwnerPublication,
    OwnerTrajectorySnapshot,
    TrajectoryPublicationError,
)
from limen.models import Task
from limen.trajectory_publication import publish_task_trajectories


class Owner:
    repository = "organvm/limen"
    root = "receipts/execution-trajectories"

    def __init__(self) -> None:
        self.records: dict[str, bytes] = {}
        self.token = "a" * 40
        self.publish_calls = 0
        self.blocked = False

    def read_many(self, attempt_ids):
        return OwnerTrajectorySnapshot(
            token=self.token,
            records={attempt_id: self.records[attempt_id] for attempt_id in attempt_ids if attempt_id in self.records},
        )

    def publish_atomic(self, payloads, *, snapshot_token):
        if self.blocked:
            raise TrajectoryPublicationError("fixture compare-and-set lost")
        assert snapshot_token == self.token
        self.publish_calls += 1
        self.records.update(payloads)
        self.token = "b" * 40
        now = datetime.now(timezone.utc)
        return {
            attempt_id: OwnerPublication(
                attempt_id=attempt_id,
                reference=(
                    f"https://github.com/{self.repository}/blob/{self.token}/"
                    f"{self.root}/{hashlib.sha256(attempt_id.encode()).hexdigest()}.json"
                ),
                digest="sha256:" + hashlib.sha256(payload).hexdigest(),
                published_at=now,
            )
            for attempt_id, payload in payloads.items()
        }


def task_with_terminal_attempt() -> Task:
    task = Task(
        id="PUBLISH-ATTEMPT",
        title="publish terminal attempt",
        repo="organvm/limen",
        target_agent="codex",
        status="failed",
        created=date(2026, 7, 17),
    )
    started = datetime.now(timezone.utc) - timedelta(seconds=5)
    launch = _attempt_launch_entry(
        task,
        "codex",
        reservation_session="fixture-session",
        started_at=started,
        output="registered before provider",
    )
    terminal = launch.model_copy(
        update={
            "timestamp": datetime.now(timezone.utc),
            "status": "failed",
            "trajectory_outcome": "failed",
            "output": "provider failed",
        }
    )
    task.dispatch_log = [launch, launch.model_copy(update={"status": "in_progress"}), terminal]
    return task


def test_terminal_attempt_publishes_once_and_records_exact_owner_receipt() -> None:
    task = task_with_terminal_attempt()
    owner = Owner()

    assert publish_task_trajectories(task, adapter=owner)
    terminal = task.dispatch_log[-1]
    assert terminal.trajectory_publication_reference.startswith("https://github.com/organvm/limen/blob/" + "b" * 40)
    assert terminal.trajectory_publication_digest.startswith("sha256:")
    assert terminal.trajectory_publication_error is None
    assert owner.publish_calls == 1

    assert not publish_task_trajectories(task, adapter=owner)
    assert owner.publish_calls == 1


def test_publication_failure_is_retry_visible_and_later_recovers() -> None:
    task = task_with_terminal_attempt()
    owner = Owner()
    owner.blocked = True

    assert publish_task_trajectories(task, adapter=owner)
    terminal = task.dispatch_log[-1]
    assert "compare-and-set lost" in str(terminal.trajectory_publication_error)
    assert terminal.trajectory_publication_reference is None

    owner.blocked = False
    assert publish_task_trajectories(task, adapter=owner)
    assert terminal.trajectory_publication_error is None
    assert terminal.trajectory_publication_reference


def test_publication_enforces_upstream_byte_bound_before_owner_mutation() -> None:
    task = task_with_terminal_attempt()
    owner = Owner()

    assert publish_task_trajectories(
        task,
        adapter=owner,
        env={"LIMEN_TRAJECTORY_MAX_BYTES": "1", "LIMEN_TRAJECTORY_MAX_RECORDS": "1"},
    )
    assert "byte bound" in str(task.dispatch_log[-1].trajectory_publication_error)
    assert owner.publish_calls == 0
