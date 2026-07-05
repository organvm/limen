"""Tests for TABVLARIVS — the single-writer record-keeper (limen.tabularius).

What is under test: workers hand the keeper immutable tickets in a lock-free inbox, and the keeper
is the ONLY writer of tasks.yaml — it drains, folds each ticket onto the board in order, validates,
and seals through the collapse-guard. The invariants that make it safe to run every beat:
  * an empty inbox is a no-op that never touches the board;
  * a submitted ticket folds onto the board and is archived (the event log);
  * one bad ticket is quarantined and never takes the good ones (or the board) down;
  * a held queue lock defers the drain, never blocks;
  * a batch that would collapse the board is rejected whole, board intact.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from click.testing import CliRunner

from limen.cli import main
from limen.io import load_limen_file, queue_lock, save_limen_file
from limen.models import LimenFile, Task
from limen.tabularius import (
    INTENT_META,
    INTENT_ORDER,
    INTENT_REMOVE,
    INTENT_STATUS,
    INTENT_UPSERT,
    Ticket,
    _archive,
    _inbox,
    _rejected,
    compact_event_log,
    drain_once,
    event_log_path,
    event_log_manifest_path,
    new_ticket_id,
    pending_count,
    submit_board_meta,
    submit_ticket,
    submit_task_status,
    submit_task_upsert,
    sync_event_log_from_archive,
    verify_event_log,
)

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def _task(tid: str, **over) -> dict:
    base = {"id": tid, "title": f"task {tid}", "target_agent": "jules", "created": "2026-07-01"}
    base.update(over)
    return base


def _board(tasks: list[dict]) -> LimenFile:
    return LimenFile.model_validate({"version": "1.0", "tasks": tasks})


def _seed_board(tmp_path: Path, n: int = 6) -> Path:
    """A board with n tasks (above the collapse-guard floor of 5) at tmp_path/tasks.yaml."""
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, _board([_task(f"T-{i}", status="open") for i in range(n)]))
    return board


def _seed_budget_board(tmp_path: Path) -> Path:
    board = tmp_path / "tasks.yaml"
    save_limen_file(
        board,
        LimenFile.model_validate(
            {
                "version": "1.0",
                "portal": {
                    "budget": {
                        "daily": 10,
                        "per_agent": {"codex": 10},
                        "track": {"date": "2026-07-02", "spent": 0, "per_agent": {}},
                    }
                },
                "tasks": [_task(f"T-{i}", status="open") for i in range(6)],
            }
        ),
    )
    return board


def _ticket(intent: str, task_id: str | None = None, ts: datetime = _NOW, **over) -> Ticket:
    return Ticket(
        ticket_id=over.pop("ticket_id", new_ticket_id("test", ts)),
        timestamp=ts,
        agent=over.pop("agent", "claude"),
        session_id=over.pop("session_id", "sess-1"),
        intent=intent,
        task_id=task_id,
        patch=over.pop("patch", None),
        log=over.pop("log", None),
        precondition=over.pop("precondition", None),
    )


# --- the no-op contract (why it is safe every beat) ----------------------------------------------
def test_empty_inbox_is_noop(tmp_path):
    board = _seed_board(tmp_path)
    before = board.read_text()
    result = drain_once(board)
    assert result.applied == 0 and result.wrote is False and result.pending == 0
    assert board.read_text() == before  # board byte-untouched


def test_missing_inbox_is_noop(tmp_path):
    board = _seed_board(tmp_path)
    # no logs/tickets/inbox dir exists at all
    assert not _inbox(board).exists()
    result = drain_once(board)
    assert result.wrote is False and "empty" in result.note


# --- the core lifecycle: submit → drain → board updated → archived -------------------------------
def test_upsert_creates_new_task_and_archives_ticket(tmp_path):
    board = _seed_board(tmp_path)
    tk = _ticket(INTENT_UPSERT, task_id="T-new", patch=_task("T-new", status="open", priority="high"))
    submit_ticket(board, tk)
    assert pending_count(board) == 1

    result = drain_once(board)
    assert result.applied == 1 and result.wrote is True

    lf = load_limen_file(board)
    new = {t.id: t for t in lf.tasks}["T-new"]
    assert new.priority == "high" and len(lf.tasks) == 7
    # the ticket moved out of the inbox and into the archive (the event log)
    assert pending_count(board) == 0
    assert (_archive(board) / f"{tk.ticket_id}.json").exists()


def test_status_ticket_sets_status_and_appends_dispatch_log(tmp_path):
    board = _seed_board(tmp_path)
    tk = _ticket(INTENT_STATUS, task_id="T-1", log={"status": "done", "output": "shipped PR #999"})
    submit_ticket(board, tk)
    drain_once(board)

    t1 = {t.id: t for t in load_limen_file(board).tasks}["T-1"]
    assert t1.status == "done"
    assert len(t1.dispatch_log) == 1
    entry = t1.dispatch_log[0]
    assert entry.agent == "claude" and entry.status == "done" and entry.output == "shipped PR #999"


def test_compacted_event_log_folds_to_current_board(tmp_path):
    board = _seed_board(tmp_path)
    submit_ticket(board, _ticket(INTENT_STATUS, task_id="T-1", log={"status": "done"}))
    submit_ticket(board, _ticket(INTENT_UPSERT, task_id="T-new", patch=_task("T-new", status="open")))
    drain_once(board)

    result = compact_event_log(board)

    assert result.verified is True
    assert result.events == len(load_limen_file(board).tasks) + 1
    assert result.archive_tickets == 2
    assert result.event_log == event_log_path(board)
    assert result.event_log.exists()
    verify = verify_event_log(board)
    assert verify.verified is True
    assert verify.events == result.events


def test_compacted_event_log_manifest_records_archive_watermark(tmp_path):
    board = _seed_board(tmp_path)
    ticket_path = submit_task_status(board, "T-1", "done", agent="limen", session_id="test", now=_NOW)
    drain_once(board)

    result = compact_event_log(board)

    manifest = json.loads(event_log_manifest_path(result.event_log).read_text())
    assert manifest["kind"] == "tabularius.compacted-seed"
    assert manifest["archive_count"] == 1
    assert manifest["last_ticket_id"] == ticket_path.stem
    assert result.archive_replay_tickets == 0
    assert result.verified is True


def test_event_log_verification_replays_archive_after_seed_watermark(tmp_path):
    board = _seed_board(tmp_path)
    result = compact_event_log(board)
    seed_event_count = result.events

    submit_task_status(board, "T-1", "done", agent="limen", session_id="after-seed", now=_NOW)
    drain_once(board)

    verify = verify_event_log(board)

    assert verify.verified is True
    assert verify.archive_tickets == 1
    assert verify.archive_replay_tickets == 1
    assert verify.events == seed_event_count + 1
    assert verify.note == "fold(events + archive tickets after watermark) == tasks.yaml bytes"


def test_event_log_archive_replay_preserves_budget_delta_metadata(tmp_path):
    board = _seed_budget_board(tmp_path)
    result = compact_event_log(board)

    submit_task_status(
        board,
        "T-1",
        "dispatched",
        agent="codex",
        session_id="after-seed",
        budget_cost=1,
        now=_NOW,
    )
    drain_once(board)

    verify = verify_event_log(board)

    assert verify.verified is True
    assert verify.archive_replay_tickets == 1
    assert verify.events == result.events + 2  # board.meta budget delta + task status upsert


def test_sync_event_log_from_archive_appends_post_watermark_events(tmp_path):
    board = _seed_board(tmp_path)
    result = compact_event_log(board)
    ticket_path = submit_task_status(board, "T-1", "done", agent="limen", session_id="after-seed", now=_NOW)
    drain_once(board)

    sync = sync_event_log_from_archive(board)

    manifest = json.loads(event_log_manifest_path(sync.event_log).read_text())
    assert sync.verified is True
    assert sync.archive_replay_tickets == 0
    assert sync.events == result.events + 1
    assert sync.note == "synced 1 archived ticket(s); fold(events) == tasks.yaml bytes"
    assert manifest["archive_count"] == 1
    assert manifest["last_ticket_id"] == ticket_path.stem

    verify = verify_event_log(board)
    assert verify.verified is True
    assert verify.archive_replay_tickets == 0
    assert verify.events == sync.events


def test_tabularius_events_command_writes_and_verifies(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(board))

    result = CliRunner().invoke(main, ["tabularius-events", "--write", "--verify"])

    assert result.exit_code == 0, result.output
    assert event_log_path(board).exists()
    assert "fold(events) == tasks.yaml bytes: True" in result.output


def test_tabularius_events_command_syncs_archive(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    compact_event_log(board)
    submit_task_status(board, "T-1", "done", agent="limen", session_id="after-seed", now=_NOW)
    drain_once(board)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(board))

    result = CliRunner().invoke(main, ["tabularius-events", "--sync-archive", "--verify"])

    assert result.exit_code == 0, result.output
    assert "synced 1 archived ticket(s); fold(events) == tasks.yaml bytes: True" in result.output


def test_submit_task_status_emits_status_ticket(tmp_path):
    board = _seed_board(tmp_path)

    submit_task_status(
        board,
        "T-1",
        "open",
        agent="limen",
        session_id="heal",
        output="recover: reopened failed -> fresh cascade",
        patch={"target_agent": "codex", "labels": ["retry"]},
        now=_NOW,
    )
    result = drain_once(board)

    assert result.applied == 1 and result.wrote is True
    t1 = {t.id: t for t in load_limen_file(board).tasks}["T-1"]
    assert t1.status == "open"
    assert t1.target_agent == "codex"
    assert t1.labels == ["retry"]
    assert t1.dispatch_log[-1].agent == "limen"
    assert t1.dispatch_log[-1].session_id == "heal"
    assert t1.dispatch_log[-1].status == "open"
    assert t1.dispatch_log[-1].output == "recover: reopened failed -> fresh cascade"


def test_submit_task_status_rejects_invalid_or_keeper_owned_fields(tmp_path):
    import pytest

    board = _seed_board(tmp_path)

    with pytest.raises(ValueError, match="status must be one of"):
        submit_task_status(board, "T-1", "completed", agent="limen")
    with pytest.raises(ValueError, match="keeper-owned"):
        submit_task_status(board, "T-1", "open", agent="limen", patch={"dispatch_log": []})


def test_status_ticket_precondition_rejects_stale_state(tmp_path):
    board = _seed_board(tmp_path)
    submit_task_status(
        board,
        "T-1",
        "open",
        agent="limen",
        session_id="route",
        output="route: target_agent -> codex",
        patch={"target_agent": "codex"},
        precondition={"status": "dispatched"},
        now=_NOW,
    )

    result = drain_once(board)

    assert result.applied == 0
    assert result.rejected == 1
    t1 = {t.id: t for t in load_limen_file(board).tasks}["T-1"]
    assert t1.status == "open"
    assert t1.target_agent == "jules"
    assert t1.dispatch_log == []


def test_status_ticket_can_separate_task_status_from_log_status(tmp_path):
    board = _seed_board(tmp_path)
    submit_task_status(
        board,
        "T-1",
        "open",
        agent="codex",
        session_id="dispatch",
        log_status="failed->agy",
        patch={"target_agent": "agy"},
        now=_NOW,
    )

    result = drain_once(board)

    assert result.applied == 1
    t1 = {t.id: t for t in load_limen_file(board).tasks}["T-1"]
    assert t1.status == "open"
    assert t1.target_agent == "agy"
    assert t1.dispatch_log[-1].status == "failed->agy"


def test_status_ticket_applies_budget_delta(tmp_path):
    board = _seed_budget_board(tmp_path)
    submit_task_status(
        board,
        "T-1",
        "dispatched",
        agent="codex",
        session_id="https://github.com/x/y/pull/9",
        budget_cost=1,
        now=_NOW,
    )

    result = drain_once(board)

    assert result.applied == 1
    lf = load_limen_file(board)
    assert lf.portal.budget.track.spent == 1
    assert lf.portal.budget.track.per_agent["codex"] == 1


def test_submit_board_meta_updates_portal(tmp_path):
    board = _seed_budget_board(tmp_path)
    lf = load_limen_file(board)
    lf.portal.budget.daily = 42
    lf.portal.budget.track.spent = 0

    submit_board_meta(board, agent="limen", session_id="budget-reset", version=lf.version, portal=lf.portal, now=_NOW)
    result = drain_once(board)

    assert result.applied == 1
    out = load_limen_file(board)
    assert out.portal.budget.daily == 42
    assert out.portal.budget.track.spent == 0


def test_partial_patch_preserves_other_fields(tmp_path):
    board = _seed_board(tmp_path)
    # seed T-2 with a description, then patch only its priority — description must survive
    save_limen_file(
        board,
        _board(
            [_task("T-2", status="open", description="keep me", priority="low")]
            + [_task(f"P-{i}", status="open") for i in range(5)]  # distinct filler ids (no T-2 collision)
        ),
    )
    submit_ticket(board, _ticket(INTENT_UPSERT, task_id="T-2", patch={"priority": "high"}))
    drain_once(board)

    t2 = {t.id: t for t in load_limen_file(board).tasks}["T-2"]
    assert t2.priority == "high" and t2.description == "keep me"


def test_remove_ticket_drops_task(tmp_path):
    board = _seed_board(tmp_path, n=6)  # 6 → 5 does not trip the guard (floor 5)
    submit_ticket(board, _ticket(INTENT_REMOVE, task_id="T-0"))
    drain_once(board)
    ids = {t.id for t in load_limen_file(board).tasks}
    assert "T-0" not in ids and len(ids) == 5


# --- ordering: concurrent tickets replay in one deterministic total order ------------------------
def test_tickets_apply_in_timestamp_order(tmp_path):
    board = _seed_board(tmp_path)
    early = datetime(2026, 7, 2, 10, 0, 0, tzinfo=timezone.utc)
    late = datetime(2026, 7, 2, 11, 0, 0, tzinfo=timezone.utc)
    # submit the LATER one first on disk; the keeper must still apply early→late
    submit_ticket(board, _ticket(INTENT_STATUS, task_id="T-1", ts=late, log={"status": "done"}))
    submit_ticket(board, _ticket(INTENT_STATUS, task_id="T-1", ts=early, log={"status": "in_progress"}))
    drain_once(board)

    t1 = {t.id: t for t in load_limen_file(board).tasks}["T-1"]
    assert [e.status for e in t1.dispatch_log] == ["in_progress", "done"]
    assert t1.status == "done"  # latest ticket wins the final status


# --- one bad ticket never breaks the batch or the board -----------------------------------------
def test_bad_ticket_quarantined_good_ticket_survives(tmp_path):
    board = _seed_board(tmp_path)
    good = _ticket(INTENT_UPSERT, task_id="T-ok", patch=_task("T-ok", status="open"))
    # a status ticket for a task that does not exist AND lacks the required created field → invalid
    bad = _ticket(INTENT_STATUS, task_id="T-ghost", log={"status": "done"})
    submit_ticket(board, good)
    submit_ticket(board, bad)

    result = drain_once(board)
    assert result.applied == 1 and result.rejected == 1

    ids = {t.id for t in load_limen_file(board).tasks}
    assert "T-ok" in ids and "T-ghost" not in ids
    # the bad ticket landed in rejected/ with a reason sidecar, board still valid
    assert (_rejected(board) / f"{bad.ticket_id}.json").exists()
    assert (_rejected(board) / f"{bad.ticket_id}.json.reason.txt").exists()


def test_bad_meta_ticket_quarantined_good_ticket_survives(tmp_path):
    board = _seed_board(tmp_path)
    good = _ticket(INTENT_UPSERT, task_id="T-ok", patch=_task("T-ok", status="open"))
    bad = _ticket(INTENT_META, patch={"portal": {"budget": "not-a-mapping"}})
    submit_ticket(board, good)
    submit_ticket(board, bad)

    result = drain_once(board)

    assert result.applied == 1 and result.rejected == 1
    ids = {t.id for t in load_limen_file(board).tasks}
    assert "T-ok" in ids
    assert (_rejected(board) / f"{bad.ticket_id}.json").exists()


def test_bad_order_ticket_quarantined_good_ticket_survives(tmp_path):
    board = _seed_board(tmp_path)
    good = _ticket(INTENT_UPSERT, task_id="T-ok", patch=_task("T-ok", status="open"))
    bad = _ticket(INTENT_ORDER, patch={"ids": "T-2"})
    submit_ticket(board, good)
    submit_ticket(board, bad)

    result = drain_once(board)

    assert result.applied == 1 and result.rejected == 1
    ids = {t.id for t in load_limen_file(board).tasks}
    assert "T-ok" in ids
    assert (_rejected(board) / f"{bad.ticket_id}.json").exists()


def test_unparseable_ticket_is_quarantined(tmp_path):
    board = _seed_board(tmp_path)
    inbox = _inbox(board)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "garbage.json").write_text("{ this is not valid json ")
    result = drain_once(board)
    assert result.rejected == 1 and result.applied == 0
    assert (_rejected(board) / "garbage.json").exists()


# --- never dead-stop: a held lock defers, and the collapse-guard fences a bad batch --------------
def test_held_lock_defers_without_touching_board(tmp_path):
    board = _seed_board(tmp_path)
    submit_ticket(board, _ticket(INTENT_UPSERT, task_id="T-x", patch=_task("T-x", status="open")))
    before = board.read_text()
    # simulate a legacy writer holding the queue lock
    with queue_lock(board) as locked:
        assert locked
        result = drain_once(board, lock_timeout=1)
    assert result.deferred is True and result.wrote is False
    assert board.read_text() == before  # board untouched
    assert pending_count(board) == 1  # ticket still waiting

    # once the lock is free, the same ticket lands
    assert drain_once(board).applied == 1
    assert "T-x" in {t.id for t in load_limen_file(board).tasks}


def test_collapse_guard_rejects_a_shrinking_batch(tmp_path):
    board = _seed_board(tmp_path, n=6)
    # remove 5 of 6 tasks in one batch: 6 → 1 trips the collapse-guard (< floor 5)
    for i in range(5):
        submit_ticket(
            board, _ticket(INTENT_REMOVE, task_id=f"T-{i}", ts=datetime(2026, 7, 2, 12, i, tzinfo=timezone.utc))
        )
    result = drain_once(board)

    assert result.wrote is False  # board never shrunk
    assert len(load_limen_file(board).tasks) == 6  # good board intact
    assert result.rejected == 5  # the whole batch quarantined


# --- the Step-2 migration safety invariant: producer path ≡ legacy direct write -----------------
def test_producer_path_matches_legacy_direct_write(tmp_path):
    """The conversion contract for every writer: swapping `load → extend → save_limen_file` for
    `submit_task_upsert(...) + drain` yields the SAME board — identical existing tasks, identical
    new-task fields, identical order — save only for the keeper's added `updated` provenance stamp.
    This is what turns each generator conversion into a mechanical, provable change, not surgery."""
    from limen.tabularius import submit_task_upsert

    existing = [_task(f"T-{i}", status="open") for i in range(6)]
    new_tasks = [
        Task.model_validate(_task("N-1", status="open", priority="high", repo="organvm/limen")),
        Task.model_validate(_task("N-2", status="open", priority="medium", labels=["mined"])),
        Task.model_validate(_task("N-3", status="open", type="content")),
    ]

    # Path A — legacy direct write: load → extend → save
    board_a = tmp_path / "a" / "tasks.yaml"
    board_a.parent.mkdir(parents=True)
    lf = _board(existing)
    lf.tasks.extend(new_tasks)
    save_limen_file(board_a, lf)

    # Path B — producer tickets drained by the keeper (monotonic ts pins the append order)
    board_b = tmp_path / "b" / "tasks.yaml"
    board_b.parent.mkdir(parents=True)
    save_limen_file(board_b, _board(existing))
    for i, t in enumerate(new_tasks):
        submit_task_upsert(
            board_b, t, agent="gen", session_id="s", now=datetime(2026, 7, 2, 12, i, tzinfo=timezone.utc)
        )
    result = drain_once(board_b)
    assert result.applied == 3 and result.wrote is True

    a_tasks = load_limen_file(board_a).tasks
    b_tasks = load_limen_file(board_b).tasks
    assert [t.id for t in a_tasks] == [t.id for t in b_tasks]  # same set AND order
    da = {t.id: t.model_dump(mode="json", exclude_none=True) for t in a_tasks}
    db = {t.id: t.model_dump(mode="json", exclude_none=True) for t in b_tasks}
    for tid in da:
        a, b = dict(da[tid]), dict(db[tid])
        # the keeper additionally stamps `updated` provenance on each folded task — a strict add,
        # not a divergence; every other field must match the legacy write byte-for-byte.
        a.pop("updated", None)
        b.pop("updated", None)
        assert a == b, f"field divergence on {tid}: {a} vs {b}"


def test_status_producer_path_matches_legacy_direct_write(tmp_path):
    """Status-mutator conversion contract: a direct status/log edit and a status ticket fold produce
    the same task fields. This is the Step-2.2 safety rail for route/recover/dispatch harvesters."""
    from limen.models import DispatchLogEntry

    now = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
    existing = [_task("T-1", status="failed", labels=["noop", "tried:agy"])] + [
        _task(f"T-{i}", status="open") for i in range(2, 7)
    ]

    board_a = tmp_path / "a" / "tasks.yaml"
    board_a.parent.mkdir(parents=True)
    lf = _board(existing)
    task = lf.tasks[0]
    task.status = "open"
    task.target_agent = "codex"
    task.labels = ["noop"]
    task.updated = now
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=now,
            agent="limen",
            session_id="heal",
            status="open",
            output="recover: reopened failed -> fresh cascade",
        )
    )
    save_limen_file(board_a, lf)

    board_b = tmp_path / "b" / "tasks.yaml"
    board_b.parent.mkdir(parents=True)
    save_limen_file(board_b, _board(existing))
    submit_task_status(
        board_b,
        "T-1",
        "open",
        agent="limen",
        session_id="heal",
        output="recover: reopened failed -> fresh cascade",
        patch={"target_agent": "codex", "labels": ["noop"]},
        now=now,
    )
    result = drain_once(board_b)
    assert result.applied == 1 and result.wrote is True

    a_tasks = load_limen_file(board_a).tasks
    b_tasks = load_limen_file(board_b).tasks
    assert [t.id for t in a_tasks] == [t.id for t in b_tasks]
    assert {
        t.id: t.model_dump(mode="json", exclude_none=True) for t in a_tasks
    } == {t.id: t.model_dump(mode="json", exclude_none=True) for t in b_tasks}


def test_submit_task_upsert_validates_before_emitting(tmp_path):
    """The producer validates the task up front (fail-fast, like the legacy `Task(**t)`), so an
    invalid task never reaches the inbox as a silently-quarantined ticket."""
    import pytest

    board = _seed_board(tmp_path)
    # a dict missing the required `id` — must raise at submit, not land a ticket
    with pytest.raises((ValueError, Exception)):
        submit_task_upsert(board, {"title": "no id"}, agent="gen")
    assert pending_count(board) == 0  # nothing entered the inbox


def test_upsert_precondition_rejects_existing_id(tmp_path):
    board = _seed_board(tmp_path)

    submit_task_upsert(
        board,
        _task("T-1", status="open", title="must not overwrite"),
        agent="gen",
        precondition={"status": None},
        now=_NOW,
    )
    result = drain_once(board)

    assert result.applied == 0
    assert result.rejected == 1
    task = {t.id: t for t in load_limen_file(board).tasks}["T-1"]
    assert task.title == "task T-1"
