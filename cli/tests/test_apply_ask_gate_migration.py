from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile
from limen.tabularius import drain_once, tickets_root


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply-ask-gate-migration.py"
RECEIPT = ROOT / "docs" / "ask-gate-migration-2026-07-12.json"
BOARD = ROOT / "tasks.yaml"


def _module():
    spec = importlib.util.spec_from_file_location("apply_ask_gate_migration", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_non_merged_live_prerequisite_fails_closed() -> None:
    compiler = _module()
    payload = _payload()
    seen: list[str] = []

    def runner(command: str):
        seen.append(command)
        return SimpleNamespace(
            returncode=1 if "982" in command else 0,
            stdout="",
            stderr="PR #982 is OPEN" if "982" in command else "",
        )

    with pytest.raises(compiler.MigrationError, match="terminal_discovery_dispositions.*not satisfied"):
        compiler.check_live_prerequisites(payload, runner=runner)
    assert any("978" in command for command in seen)
    assert any("982" in command for command in seen)


def test_compilers_are_deterministic_typed_and_append_only() -> None:
    compiler = _module()
    payload = _payload()
    timestamp = compiler.parse_timestamp("2026-07-12T18:00:00Z")
    kwargs = {"timestamp": timestamp, "agent": "codex", "session_id": "test-session"}

    children_a = compiler.compile_child_tickets(payload, **kwargs)
    children_b = compiler.compile_child_tickets(payload, **kwargs)
    assert [ticket.model_dump(mode="json") for ticket in children_a] == [
        ticket.model_dump(mode="json") for ticket in children_b
    ]
    assert len(children_a) == 29
    assert len({ticket.ticket_id for ticket in children_a}) == 29
    assert all(ticket.intent == "task.upsert" and ticket.log for ticket in children_a)
    assert all(
        ticket.patch and ticket.patch.get("predicate") and ticket.patch.get("receipt_target") for ticket in children_a
    )

    parents_a = compiler.compile_parent_tickets(payload, BOARD, **kwargs)
    parents_b = compiler.compile_parent_tickets(payload, BOARD, **kwargs)
    assert [ticket.model_dump(mode="json") for ticket in parents_a] == [
        ticket.model_dump(mode="json") for ticket in parents_b
    ]
    assert len(parents_a) == 52
    assert len({ticket.ticket_id for ticket in parents_a}) == 52
    assert all(ticket.intent == "task.upsert" and ticket.log for ticket in parents_a)
    assert all(
        set(ticket.patch or {}) <= {"predicate", "receipt_target", "status"}
        and {"predicate", "receipt_target"} <= set(ticket.patch or {})
        for ticket in parents_a
    )
    assert all(ticket.log["status"] for ticket in parents_a if ticket.log)
    assert all(compiler.MIGRATION_ID in ticket.log["output"] for ticket in parents_a if ticket.log)


def test_parent_phase_refuses_before_children_cross_keeper() -> None:
    compiler = _module()
    with pytest.raises(compiler.MigrationError, match="is not admitted on the board"):
        compiler.verify_children_admitted(_payload(), BOARD)


def test_child_preflight_refuses_same_id_without_migration_custody(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    board = tmp_path / "tasks.yaml"
    first_child = payload["children"][0]
    save_limen_file(board, LimenFile(tasks=[first_child]))
    tickets = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
        agent="codex",
        session_id="preflight",
    )
    with pytest.raises(compiler.MigrationError, match="already exists without.*keeper receipt"):
        compiler.preflight_child_submission(payload, board, tickets)


def test_parent_owner_state_gate_rejects_newly_terminal_open_work() -> None:
    compiler = _module()
    payload = _payload()
    by_predicate = {row["predicate"]: row["action"] for row in payload["tasks"].values()}
    stale_predicate = payload["tasks"]["GH-organvm-limen-685"]["predicate"]

    def runner(command: str):
        action = by_predicate[command]
        satisfied = action in {"done", "superseded", "split"} or command == stale_predicate
        return SimpleNamespace(returncode=0 if satisfied else 1, stdout="", stderr="")

    with pytest.raises(compiler.MigrationError, match="GH-organvm-limen-685.*expected not satisfied"):
        compiler.check_parent_dispositions(payload, runner=runner)


def test_keeper_archive_proves_children_and_rejection_fails_closed(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile())
    tickets = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
        agent="codex",
        session_id="test-session",
    )
    submission = compiler.submit_compiled_tickets(board, tickets)
    assert submission == {"submitted": 29, "pending": 0, "archived": 0}
    drained = drain_once(board)
    assert drained.applied == 29
    assert drained.rejected == 0
    assert compiler.verify_children_admitted(payload, board) == {"admitted": 29, "rejected": 0, "pending": 0}

    rejected = tickets_root(board) / "rejected" / f"{tickets[0].ticket_id}.json.reason.txt"
    rejected.parent.mkdir(parents=True, exist_ok=True)
    rejected.write_text("synthetic rejection evidence", encoding="utf-8")
    with pytest.raises(compiler.MigrationError, match="rejected keeper ticket"):
        compiler.verify_children_admitted(payload, board)


def test_phase_rejection_preflight_submits_no_prefix(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile())
    tickets = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
        agent="codex",
        session_id="reject-before-write",
    )
    rejected = tickets_root(board) / "rejected" / f"{tickets[-1].ticket_id}.json.reason.txt"
    rejected.parent.mkdir(parents=True, exist_ok=True)
    rejected.write_text("synthetic rejection evidence", encoding="utf-8")

    with pytest.raises(compiler.MigrationError, match="was rejected"):
        compiler.submit_compiled_tickets(board, tickets)
    assert not list((tickets_root(board) / "inbox").glob("*.json"))


def test_two_phase_keeper_round_trip_supports_raw_parent_tickets(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    source = load_limen_file(BOARD)
    frozen = set(payload["frozen_ids"])
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile(tasks=[task for task in source.tasks if task.id in frozen]))
    timestamp = compiler.parse_timestamp("2026-07-12T18:00:00Z")
    kwargs = {"timestamp": timestamp, "agent": "codex", "session_id": "round-trip"}

    children = compiler.compile_child_tickets(payload, **kwargs)
    compiler.submit_compiled_tickets(board, children)
    child_drain = drain_once(board)
    assert (child_drain.applied, child_drain.rejected) == (29, 0)
    compiler.verify_children_admitted(payload, board)

    parents = compiler.compile_parent_tickets(payload, board, **kwargs)
    compiler.submit_compiled_tickets(board, parents)
    parent_drain = drain_once(board)
    assert (parent_drain.applied, parent_drain.rejected) == (52, 0)
    assert compiler.verify_parents_applied(payload, board) == {"verified": 52}

    rejected = tickets_root(board) / "rejected" / f"{parents[0].ticket_id}.json.reason.txt"
    rejected.parent.mkdir(parents=True, exist_ok=True)
    rejected.write_text("synthetic parent rejection evidence", encoding="utf-8")
    with pytest.raises(compiler.MigrationError, match="rejected keeper ticket"):
        compiler.verify_parents_applied(payload, board)


def test_apply_requires_explicit_timestamp_and_session_identity() -> None:
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--phase",
            "children",
            "--apply",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "requires explicit --timestamp and --session-id" in result.stderr
