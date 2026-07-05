from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

from limen.io import load_limen_file
from limen.tabularius import pending_count


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jules-land.py"


def load_jules_land():
    spec = importlib.util.spec_from_file_location("jules_land", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_jules_land_marks_done_through_tabularius(tmp_path, monkeypatch, capsys) -> None:
    module = load_jules_land()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "JULES-1",
                        "title": "Land me",
                        "repo": "organvm/limen",
                        "target_agent": "jules",
                        "status": "in_progress",
                        "created": "2026-07-05",
                        "dispatch_log": [
                            {
                                "timestamp": "2026-07-05T00:00:00+00:00",
                                "agent": "jules",
                                "session_id": "123",
                                "status": "in_progress",
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        )
    )
    monkeypatch.delenv("LIMEN_TICKETS_PRODUCE", raising=False)
    monkeypatch.setattr(module, "TASKS", tasks)
    monkeypatch.setattr(module, "completed_sessions", lambda sid_map: [("123", "JULES-1")])
    monkeypatch.setattr(
        module,
        "land_one",
        lambda task, sid, apply: f"LANDED {task.id} -> https://github.com/organvm/limen/pull/9",
    )
    monkeypatch.setattr(sys, "argv", ["jules-land.py", "--apply"])

    assert module.main() == 0

    out = capsys.readouterr().out
    assert "via TABVLARIVS" in out
    task = load_limen_file(tasks).tasks[0]
    assert task.status == "done"
    assert task.dispatch_log[-1].agent == "jules"
    assert task.dispatch_log[-1].session_id == "https://github.com/organvm/limen/pull/9"
    assert task.dispatch_log[-1].output == "jules-land: landed session 123 as PR"
    assert pending_count(tasks) == 0
