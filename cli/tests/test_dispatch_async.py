"""Regression tests for scripts/dispatch-async.py's reap_stale marker/lock ordering.

The lock-honoring fix deferred the `.running` marker unlink until AFTER the reopen is committed
under the queue lock — so a lock timeout can no longer leave a leaked slot (marker gone, task still
'dispatched'). These tests pin the normal (lock-acquired) behavior the restructure must preserve:
a stale marker reopens its task AND removes the marker; a marker with a result file present is left
for harvest.
"""

import importlib.util
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.execution_contract import execution_contract_hash  # noqa: E402
from limen.models import DispatchLogEntry, LimenFile, Task  # noqa: E402

_spec = importlib.util.spec_from_file_location("dispatch_async", str(ROOT / "scripts" / "dispatch-async.py"))
dispatch_async = importlib.util.module_from_spec(_spec)
sys.modules["dispatch_async"] = dispatch_async
_spec.loader.exec_module(dispatch_async)


@pytest.fixture
def board(tmp_path, monkeypatch):
    """A tmp tasks.yaml + async-runs dir wired into the module's module-level path constants."""
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "0")
    tasks_path = tmp_path / "tasks.yaml"
    runs = tmp_path / "logs" / "async-runs"
    runs.mkdir(parents=True)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T1",
                    title="t",
                    target_agent="jules",
                    status="dispatched",
                    created=date(2026, 7, 1),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=datetime.now(timezone.utc),
                            agent="jules",
                            session_id="async-reserve",
                            status="dispatched",
                        )
                    ],
                )
            ]
        ),
    )
    monkeypatch.setattr(dispatch_async, "TASKS", tasks_path)
    monkeypatch.setattr(dispatch_async, "RUNS", runs)
    monkeypatch.setattr(dispatch_async, "RECEIPT_ARCHIVE", tmp_path / ".limen-private" / "async-runs" / "archive")
    return tasks_path, runs


def _old_marker(runs: Path, tid: str, agent: str) -> Path:
    marker = runs / f"{tid}__{agent}.running"
    marker.write_text((dispatch_async._now().replace(year=2020)).isoformat())  # ancient → always stale
    return marker


def _write_valid_attempt_result(tasks_path: Path, runs: Path) -> tuple[Path, str]:
    board_state = load_limen_file(tasks_path)
    task = board_state.tasks[0]
    launch = dispatch_async._attempt_launch_entry(
        task,
        "jules",
        reservation_session="async-reserve",
        started_at=datetime.now(timezone.utc),
        output="fixture registered before detached worker execution",
    )
    task.status = "in_progress"
    task.dispatch_log = [launch, launch.model_copy(update={"status": "in_progress"})]
    save_limen_file(tasks_path, board_state)
    result = {
        "task_id": task.id,
        "agent": "jules",
        "result": False,
        "ts": datetime.now(timezone.utc).isoformat(),
        "err": None,
        "execution_contract_hash": execution_contract_hash(task),
        "execution_started": True,
        "attempt_id": launch.attempt_id,
        "model_selection": {},
    }
    raw = json.dumps(result).encode()
    receipt = runs / "T1.result.json"
    receipt.write_bytes(raw)
    return receipt, f"sha256:{hashlib.sha256(raw).hexdigest()}"


def test_reap_stale_reopens_and_removes_marker(board):
    tasks_path, runs = board
    marker = _old_marker(runs, "T1", "jules")

    reaped = dispatch_async.reap_stale(max_age_s=1)

    assert reaped == ["T1"]
    assert not marker.exists()  # marker removed — but only AFTER the reopen committed
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].status == "open"  # dead worker's task reopened for retry
    assert got["T1"].dispatch_log[-1].status == got["T1"].status
    assert got["T1"].dispatch_log[-1].attempt_id is None
    assert got["T1"].dispatch_log[-2].status == "failed"


def test_reap_stale_leaves_marker_when_result_present(board):
    tasks_path, runs = board
    marker = _old_marker(runs, "T1", "jules")
    (runs / "T1.result.json").write_text("{}")  # worker actually finished → harvest's job, not reap's

    reaped = dispatch_async.reap_stale(max_age_s=1)

    assert reaped == []
    assert marker.exists()  # left in place for harvest
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].status == "dispatched"  # untouched


def test_reap_dead_pid_marker_without_waiting_for_age(board, monkeypatch):
    tasks_path, runs = board
    marker = runs / "T1__jules.running"
    marker.write_text(
        json.dumps(
            {
                "started_at": dispatch_async._now().isoformat(),
                "agent": "jules",
                "task_id": "T1",
                "pid": 424242,
            }
        )
    )
    monkeypatch.setattr(dispatch_async, "_pid_alive", lambda pid: False)
    killed: list[int] = []
    monkeypatch.setattr(dispatch_async, "_kill_worker_group", lambda pid: killed.append(pid))

    reaped = dispatch_async.reap_stale(max_age_s=999999)

    assert reaped == ["T1"]
    assert killed == [424242]
    assert not marker.exists()
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].status == "open"
    assert got["T1"].dispatch_log[-1].status == got["T1"].status
    assert got["T1"].dispatch_log[-2].status == "failed"


def test_reap_zombie_child_marker_after_grace(board, monkeypatch):
    tasks_path, runs = board
    marker = runs / "T1__jules.running"
    started = dispatch_async._now() - dispatch_async.datetime.timedelta(seconds=300)
    marker.write_text(
        json.dumps(
            {
                "started_at": started.isoformat(),
                "agent": "jules",
                "task_id": "T1",
                "pid": 12345,
            }
        )
    )
    monkeypatch.setattr(dispatch_async, "_env_int", lambda name, default: 120)
    monkeypatch.setattr(dispatch_async, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(dispatch_async, "_worker_has_defunct_child", lambda pid: True)
    killed: list[int] = []
    monkeypatch.setattr(dispatch_async, "_kill_worker_group", lambda pid: killed.append(pid))

    reaped = dispatch_async.reap_stale(max_age_s=999999)

    assert reaped == ["T1"]
    assert killed == [12345]
    assert not marker.exists()
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].status == "open"


def test_reap_leaves_live_pid_marker_before_grace(board, monkeypatch):
    tasks_path, runs = board
    marker = runs / "T1__jules.running"
    marker.write_text(
        json.dumps(
            {
                "started_at": dispatch_async._now().isoformat(),
                "agent": "jules",
                "task_id": "T1",
                "pid": 12345,
            }
        )
    )
    monkeypatch.setattr(dispatch_async, "_env_int", lambda name, default: 120)
    monkeypatch.setattr(dispatch_async, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(dispatch_async, "_worker_has_defunct_child", lambda pid: True)

    reaped = dispatch_async.reap_stale(max_age_s=999999)

    assert reaped == []
    assert marker.exists()
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].status == "dispatched"


def test_harvest_archives_result_receipt_before_unlink(board):
    tasks_path, runs = board
    board_state = load_limen_file(tasks_path)
    task = board_state.tasks[0]
    started_at = datetime.now(timezone.utc)
    launch = dispatch_async._attempt_launch_entry(
        task,
        "jules",
        reservation_session="async-reserve",
        started_at=started_at,
        output="fixture registered before detached worker execution",
    )
    task.status = "in_progress"
    task.dispatch_log = [launch, launch.model_copy(update={"status": "in_progress"})]
    save_limen_file(tasks_path, board_state)
    result = {
        "task_id": "T1",
        "agent": "jules",
        "result": False,
        "ts": "2026-07-06T00:00:00+00:00",
        "err": "token sk-secretsecretsecret and contact test@example.com",
        "execution_contract_hash": execution_contract_hash(task),
        "execution_started": True,
        "attempt_id": launch.attempt_id,
        "model_selection": {},
    }
    receipt = runs / "T1.result.json"
    receipt.write_text(json.dumps(result))

    applied = dispatch_async.harvest()

    assert applied == 1
    assert not receipt.exists()
    archives = list(dispatch_async.RECEIPT_ARCHIVE.glob("*/*.result.json"))
    assert len(archives) == 1
    archived = json.loads(archives[0].read_text())
    assert archived["reason"] == "harvested"
    assert archived["raw_sha256"]
    assert archived["receipt"]["err"] == "token [REDACTED_TOKEN] and contact [REDACTED_EMAIL]"
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].dispatch_log[-1].agent == "jules"
    digest = "sha256:" + hashlib.sha256(json.dumps(result).encode()).hexdigest()
    assert [entry.result_receipt_digest for entry in got["T1"].dispatch_log if entry.result_receipt_digest] == [digest]


def test_harvest_board_save_failure_leaves_result_and_archive_untouched(board, monkeypatch):
    tasks_path, runs = board
    receipt, _digest = _write_valid_attempt_result(tasks_path, runs)
    before = tasks_path.read_bytes()

    def fail_save(_path, _board):
        raise OSError("adversarial board save failure")

    monkeypatch.setattr(dispatch_async, "save_limen_file", fail_save)
    with pytest.raises(OSError, match="board save failure"):
        dispatch_async.harvest()

    assert tasks_path.read_bytes() == before
    assert receipt.exists()
    assert not list(dispatch_async.RECEIPT_ARCHIVE.rglob("*.result.json"))


def test_harvest_crash_after_board_save_retries_without_double_credit(board, monkeypatch):
    tasks_path, runs = board
    receipt, digest = _write_valid_attempt_result(tasks_path, runs)
    real_finalize = dispatch_async._finalize_result_receipt

    def crash_before_archive(*_args, **_kwargs):
        raise OSError("adversarial crash after board save")

    monkeypatch.setattr(dispatch_async, "_finalize_result_receipt", crash_before_archive)
    assert dispatch_async.harvest() == 1
    assert receipt.exists()
    first = load_limen_file(tasks_path)
    first_rows = [entry for entry in first.tasks[0].dispatch_log if entry.result_receipt_digest == digest]
    assert len(first_rows) == 1

    monkeypatch.setattr(dispatch_async, "_finalize_result_receipt", real_finalize)
    assert dispatch_async.harvest() == 0
    assert not receipt.exists()
    second = load_limen_file(tasks_path)
    second_rows = [entry for entry in second.tasks[0].dispatch_log if entry.result_receipt_digest == digest]
    assert len(second_rows) == 1
    assert second.portal.budget.track.spent == first.portal.budget.track.spent
    archives = list(dispatch_async.RECEIPT_ARCHIVE.rglob("*.result.json"))
    assert len(archives) == 1
    assert json.loads(archives[0].read_text())["reason"] == "duplicate-consumed"


def test_harvest_rejects_stale_model_selection_from_identical_profile_retry(board):
    tasks_path, runs = board
    board_state = load_limen_file(tasks_path)
    task = board_state.tasks[0]
    first = dispatch_async._attempt_launch_entry(
        task,
        "jules",
        reservation_session="prior-attempt",
        started_at=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
        output="prior reservation",
    )
    task.dispatch_log = [first]
    second = dispatch_async._attempt_launch_entry(
        task,
        "jules",
        reservation_session="async-reserve",
        started_at=datetime(2026, 7, 17, 12, 1, tzinfo=timezone.utc),
        output="current retry reservation",
    )
    task.status = "in_progress"
    task.dispatch_log.extend([second, second.model_copy(update={"status": "in_progress"})])
    assert second.execution_profile == first.execution_profile
    assert second.attempt_id != first.attempt_id
    save_limen_file(tasks_path, board_state)
    result = {
        "task_id": task.id,
        "agent": "jules",
        "result": False,
        "ts": "2026-07-17T12:02:00+00:00",
        "err": None,
        "execution_contract_hash": execution_contract_hash(task),
        "execution_started": True,
        "attempt_id": second.attempt_id,
        "model_selection": {
            "attempt_id": first.attempt_id,
            "execution_profile": second.execution_profile,
            "selected_model": "fixture/runtime-output",
            "selection_source": "provider_live_catalog",
            "catalog_hash": "a" * 64,
        },
    }
    receipt = runs / "T1.result.json"
    receipt.write_text(json.dumps(result))

    assert dispatch_async.harvest() == 0
    assert not receipt.exists()
    current = load_limen_file(tasks_path).tasks[0]
    assert current.status == "in_progress"
    assert current.dispatch_log[-1].attempt_id == second.attempt_id
    assert current.dispatch_log[-1].selected_model is None
    archived = list(dispatch_async.RECEIPT_ARCHIVE.glob("*/*.result.json"))
    assert len(archived) == 1
    payload = json.loads(archived[0].read_text())
    assert payload["reason"] == "harvest-fenced"
    assert "registered attempt identity" in payload["blocker"]


def test_harvest_archives_malformed_result_receipt_before_unlink(board):
    tasks_path, runs = board
    receipt = runs / "T1.result.json"
    receipt.write_text("[1, 2, 3]")

    applied = dispatch_async.harvest()

    assert applied == 0
    assert not receipt.exists()
    archives = list(dispatch_async.RECEIPT_ARCHIVE.glob("*/*.result.json"))
    assert len(archives) == 1
    archived = json.loads(archives[0].read_text())
    assert archived["reason"] == "malformed-result"
    assert archived["parse_error"] == "result receipt JSON root is not an object"
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].status == "dispatched"


def test_async_reservation_value_gate_withholds_generic_non_value_work(tmp_path, monkeypatch):
    # Disable the independent dispatch and local-worktree admission gates so this value-routing test
    # is hermetic. Their host probes are covered by dedicated suites and would mask the behavior this
    # test actually asserts. Every other test in this file gets the overrides via the `board` fixture;
    # this one builds its board inline.
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "0")
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "0")
    tasks_path = tmp_path / "tasks.yaml"
    runs = tmp_path / "logs" / "async-runs"
    runs.mkdir(parents=True)
    lf = LimenFile(
        tasks=[
            Task(
                id="GENERIC-WORK",
                title="Generic queue churn",
                repo="organvm/generic-repo",
                target_agent="codex",
                priority="critical",
                status="open",
                created=date(2026, 7, 8),
            ),
            Task(
                id="VALUE-WORK",
                title="Value-tier owner work",
                repo="organvm/value-repo",
                target_agent="codex",
                priority="low",
                status="open",
                created=date(2026, 7, 8),
            ),
        ]
    )
    lf.portal.budget.daily = 10
    lf.portal.budget.per_agent = {"codex": 10}
    lf.portal.budget.track.spent = 0
    lf.portal.budget.track.per_agent = {}
    save_limen_file(tasks_path, lf)
    monkeypatch.setattr(dispatch_async, "TASKS", tasks_path)
    monkeypatch.setattr(dispatch_async, "RUNS", runs)
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/value-repo")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))

    picked = dispatch_async.reserve_and_launch(["codex"], per_agent=5, cap=5, dry=True)

    assert picked == [("codex", "VALUE-WORK")]
