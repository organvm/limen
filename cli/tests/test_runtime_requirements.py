from __future__ import annotations

from datetime import date

import pytest

from limen.dispatch import _dispatchable
from limen.models import Task
from limen.runtime_requirements import evaluate_execution_requirements


def _task(**over: object) -> Task:
    values: dict[str, object] = {
        "id": "RUNTIME-ONE",
        "title": "Runtime-gated task",
        "repo": "organvm/limen",
        "target_agent": "codex",
        "created": date(2026, 7, 13),
    }
    values.update(over)
    return Task.model_validate(values)


def test_legacy_task_without_requirements_remains_ready() -> None:
    task = _task()

    assert task.execution_requirements is None
    assert "execution_requirements" not in task.model_dump(mode="json", exclude_none=True)
    assert evaluate_execution_requirements(task).ready is True
    assert _dispatchable(task) is True


def test_mount_requirement_uses_live_probe_for_present_and_absent_mounts() -> None:
    task = _task(execution_requirements=[{"kind": "mount", "path": "/runtime/arbitrary-volume"}])

    present = evaluate_execution_requirements(task, mount_probe=lambda path: path == "/runtime/arbitrary-volume")
    absent = evaluate_execution_requirements(task, mount_probe=lambda _path: False)

    assert present.ready is True
    assert present.blockers == ()
    assert absent.ready is False
    assert absent.blockers == ("required mount unavailable: /runtime/arbitrary-volume",)


def test_dispatchable_uses_the_same_live_mount_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task(execution_requirements=[{"kind": "mount", "path": "/runtime/volume-a"}])
    monkeypatch.setattr("limen.runtime_requirements.os.path.ismount", lambda path: path == "/runtime/volume-a")
    assert _dispatchable(task) is True

    monkeypatch.setattr("limen.runtime_requirements.os.path.ismount", lambda _path: False)
    assert _dispatchable(task) is False


@pytest.mark.parametrize(
    "requirements",
    [
        [{"kind": "mount", "path": "relative/path"}],
        [{"kind": "future-kind", "path": "/runtime/volume"}],
        [{"kind": "mount", "path": "/runtime/volume", "typo": True}],
    ],
)
def test_task_model_rejects_malformed_explicit_requirements(requirements: object) -> None:
    with pytest.raises(ValueError):
        _task(execution_requirements=requirements)


def test_raw_malformed_requirement_fails_closed() -> None:
    result = evaluate_execution_requirements({"execution_requirements": "mount:/runtime/volume"})

    assert result.ready is False
    assert result.blockers == ("execution_requirements must be a list",)
