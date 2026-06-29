from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "aug1-view.py"


def _load():
    spec = importlib.util.spec_from_file_location("aug1_view", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pipeline_scoreboard_counts_events_without_inflating_cash(tmp_path: Path):
    aug1 = _load()
    state = tmp_path / "state" / "aug1"
    state.mkdir(parents=True)
    (state / "revenue-received.json").write_text(
        json.dumps({"received": [{"at": aug1.date.today().isoformat(), "cents": 12300}]}),
        encoding="utf-8",
    )
    (state / "engagements.json").write_text(json.dumps({"engagements": []}), encoding="utf-8")
    (state / "pipeline-scoreboard.json").write_text(
        json.dumps(
            {
                "events": [
                    {"type": "visit"},
                    {"type": "qualified_inbound"},
                    {"type": "reply"},
                    {"type": "call"},
                    {"type": "paid_trial", "forecast_cents": 900000},
                    {"type": "paid_trial"},
                    {"type": "noise"},
                    "not an event",
                ]
            }
        ),
        encoding="utf-8",
    )
    levers = tmp_path / "his-hand-levers.json"
    levers.write_text(json.dumps({"levers": []}), encoding="utf-8")
    life = tmp_path / "aug1-life.json"
    life.write_text(
        json.dumps({"ev_in_progress": True, "on_track": True, "updated": aug1.date.today().isoformat()}),
        encoding="utf-8",
    )

    aug1.STATE = state
    aug1.LEVERS_FILE = levers
    aug1.LIFE_FILE = life

    view = aug1.build_view()
    pipeline = view["ledger"]["pipeline"]

    assert pipeline == {
        "visits": 1,
        "qualified_inbound": 1,
        "replies": 1,
        "calls": 1,
        "paid_trials": 2,
        "cash_cents": 12300,
        "event_count": 6,
    }
    assert view["ledger"]["received_total_cents"] == 12300
    assert "August pipeline scoreboard" in aug1.render_html(view)
