from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from limen.cli import main
from limen.models import LimenFile
from limen.progress import build_progress_snapshot, progress_bar, render_progress


def _board() -> LimenFile:
    return LimenFile.model_validate(
        {
            "portal": {"budget": {"track": {"date": "2026-07-13"}}},
            "tasks": [
                {
                    "id": "DUE-1",
                    "title": "Pay a real obligation",
                    "repo": "organvm/finance",
                    "target_agent": "claude",
                    "priority": "critical",
                    "status": "open",
                    "labels": [
                        "origin:obligation",
                        "horizon:present",
                        "due:2026-07-14",
                        "money",
                    ],
                    "predicate": "test -f receipt.json",
                    "receipt_target": "receipt.json",
                    "value_case": "Clears a time-bound financial liability",
                    "created": "2026-07-13",
                },
                {
                    "id": "ASK-1",
                    "title": "Finish the explicit ask",
                    "repo": "organvm/limen",
                    "target_agent": "codex",
                    "priority": "high",
                    "status": "in_progress",
                    "labels": [
                        "origin:human-prompt",
                        "horizon:present",
                        "contributions",
                    ],
                    "created": "2026-07-13",
                },
                {
                    "id": "PAST-1",
                    "title": "Preserve old work",
                    "repo": "organvm/limen",
                    "target_agent": "jules",
                    "priority": "medium",
                    "status": "needs_human",
                    "labels": ["origin:system-debt", "horizon:past"],
                    "created": "2026-07-12",
                },
                {
                    "id": "DONE-1",
                    "title": "Already shipped",
                    "repo": "organvm/limen",
                    "target_agent": "codex",
                    "priority": "low",
                    "status": "done",
                    "labels": ["origin:agent-recommendation", "horizon:future"],
                    "predicate": "true",
                    "receipt_target": "https://example.invalid/pr/1",
                    "created": "2026-07-11",
                },
            ],
        }
    )


def test_snapshot_keeps_origins_horizons_and_unknown_coverage_distinct(
    tmp_path: Path,
) -> None:
    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )

    assert snapshot["summary"]["total"] == 4
    assert snapshot["summary"]["complete"] == 1
    assert snapshot["summary"]["active_debt"] == 3
    assert snapshot["summary"]["closure_pct"] == 25.0
    assert snapshot["summary"]["contract_ready_active"] == 1
    assert snapshot["summary"]["underwritten_active"] == 1
    assert snapshot["summary"]["underwriting_coverage_pct"] == 33.3
    assert snapshot["summary"]["origin_coverage_pct"] == 100.0
    assert snapshot["summary"]["horizon_coverage_pct"] == 100.0
    assert snapshot["summary"]["due_metadata_coverage_pct"] == 33.3
    by_origin = {row["origin"]: row for row in snapshot["dimensions"]["origin"]}
    assert set(by_origin) == {
        "obligation",
        "human_prompt",
        "system_debt",
        "agent_recommendation",
    }


def test_snapshot_marks_missing_sensors_dark_and_does_not_invent_zero(
    tmp_path: Path,
) -> None:
    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    assert snapshot["summary"]["source_freshness_pct"] == 0.0
    assert {row["status"] for row in snapshot["source_coverage"]} == {"dark"}


def test_render_supports_macro_and_micro_zoom() -> None:
    snapshot = build_progress_snapshot(
        _board(),
        Path("."),
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    rendered = render_progress(
        snapshot, view="origin", scope="human_prompt", ascii_only=True, limit=None
    )
    assert "BOARD CLOSURE" in rendered
    assert "WORK LOANS" in rendered
    assert "ORIGIN ZOOM" in rendered
    assert "human_prompt" in rendered
    assert "ASK-1" in rendered
    assert "DUE-1" not in rendered
    assert "never estimated effort" in rendered
    assert progress_bar(50, width=10, ascii_only=True) == "[#####.....]"


def test_progress_cli_prints_complete_json_universe(
    tmp_path: Path, monkeypatch
) -> None:
    board = _board().model_dump(mode="json")
    (tmp_path / "tasks.yaml").write_text(json.dumps(board), encoding="utf-8")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))

    result = CliRunner().invoke(main, ["progress", "--json-output"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "limen.progress-universe.v1"
    assert len(payload["tasks"]) == 4
