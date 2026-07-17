"""Harvest must not false-done a jules task.

Regression guard for the 2026-06-25 VIGILIA dispatch, where harvest marked
tasks 'done' the instant a ``{session_id}.diff`` file existed — even when the
diff was an empty placeholder (``index 0000000..e69de29``) or off-task. 'done'
must mean a hand actually moved.
"""

from datetime import date, datetime, timezone

import pytest

from limen.dispatch import _attempt_launch_entry
from limen.harvest import _diff_is_real, check_jules_harvest
from limen.models import DispatchLogEntry, LimenFile, Task

REAL_DIFF = """diff --git a/atlas.json b/atlas.json
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/atlas.json
@@ -0,0 +1,2 @@
+{
+  "repos": []
+}
"""

# what jules actually returned for VIGILIA-CONTINUITY: an empty placeholder file.
EMPTY_PLACEHOLDER = """diff --git a/patch.diff b/patch.diff
new file mode 100644
index 0000000..e69de29
"""


def _task(tid: str, session_id: str) -> Task:
    return Task(
        id=tid,
        title=tid,
        target_agent="jules",
        status="dispatched",
        created=date(2026, 6, 25),
        dispatch_log=[
            DispatchLogEntry(
                timestamp=datetime(2026, 6, 25, tzinfo=timezone.utc),
                agent="jules",
                session_id=session_id,
                status="dispatched",
            )
        ],
    )


def _write_diff(harvest_dir, session_id: str, content: str) -> None:
    harvest_dir.mkdir(parents=True, exist_ok=True)
    (harvest_dir / f"{session_id}.diff").write_text(content)


@pytest.fixture(autouse=True)
def _no_jules_subprocess(monkeypatch):
    # keep the test hermetic: don't shell out to `jules remote list`.
    monkeypatch.setattr("limen.harvest._get_jules_sessions", lambda d: {})


def test_diff_is_real_accepts_real_unified_diff():
    assert _diff_is_real(REAL_DIFF) is True


def test_diff_is_real_rejects_empty_placeholder():
    assert _diff_is_real(EMPTY_PLACEHOLDER) is False


def test_diff_is_real_rejects_blank():
    assert _diff_is_real("") is False
    assert _diff_is_real("   \n   \n") is False


def test_diff_is_real_rejects_non_diff_text():
    assert _diff_is_real("I finished the task, looks good!") is False


def test_harvest_marks_real_diff_done(tmp_path):
    harvest_dir = tmp_path / "harvest"
    _write_diff(harvest_dir, "555", REAL_DIFF)
    task = _task("LIMEN-1", "555")
    limen = LimenFile(tasks=[task])

    updated = check_jules_harvest(limen, harvest_dir)

    assert updated == ["LIMEN-1"]
    assert task.status == "done"
    assert task.dispatch_log[-1].status == "done"


def test_harvest_rejects_empty_diff_instead_of_false_done(tmp_path):
    harvest_dir = tmp_path / "harvest"
    _write_diff(harvest_dir, "777", EMPTY_PLACEHOLDER)
    task = _task("LIMEN-2", "777")
    limen = LimenFile(tasks=[task])

    updated = check_jules_harvest(limen, harvest_dir)

    assert updated == []  # NOT counted as a completion
    assert task.status == "failed"  # preserved for recovery, not false-done or cancelled
    assert "noop" in task.labels
    assert "cancelled" not in task.labels
    assert task.dispatch_log[-1].status == "failed"


def test_harvest_carries_attempt_and_model_receipts_into_terminal_row(tmp_path):
    harvest_dir = tmp_path / "harvest"
    _write_diff(harvest_dir, "888", REAL_DIFF)
    task = Task(
        id="LIMEN-3",
        title="receipt transport",
        repo="organvm/limen",
        target_agent="jules",
        status="dispatched",
        created=date(2026, 7, 17),
    )
    launch = _attempt_launch_entry(
        task,
        "jules",
        reservation_session="888",
        started_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        output="registered before provider",
    )
    task.dispatch_log = [
        launch,
        launch.model_copy(
            update={
                "status": "dispatched",
                "selected_model": "provider/reported-fixture",
                "selection_source": "provider_live_catalog",
                "catalog_hash": "a" * 64,
            }
        ),
    ]

    assert check_jules_harvest(LimenFile(tasks=[task]), harvest_dir) == ["LIMEN-3"]
    terminal = task.dispatch_log[-1]
    assert terminal.status == "done"
    assert terminal.trajectory_outcome == "succeeded"
    assert terminal.attempt_id == launch.attempt_id
    assert terminal.selected_model == "provider/reported-fixture"
    assert terminal.selection_source == "provider_live_catalog"
