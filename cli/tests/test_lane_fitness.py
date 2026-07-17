"""Trajectory-backed lane-fitness shadow and dispatch no-steering tests."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

import limen.dispatch as D  # noqa: E402
from limen.models import LimenFile, Task  # noqa: E402


NOW = datetime(2026, 7, 16, 20, 0, tzinfo=timezone.utc)
HEAD = "f69c" * 10


def _reload_fitness_module(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    script = ROOT / "scripts" / "lane-fitness.py"
    spec = importlib.util.spec_from_file_location("lane_fitness_fresh", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trajectory(
    index: int,
    *,
    attempt_id: str | None = None,
    task_id: str | None = None,
    task_type="analysis",
    labels=("receipt-audit",),
    keeper="keeper-ivory",
    route="provider-saffron-auto",
    outcome="failed",
    verified=False,
    ended_at="2026-07-16T18:20:00Z",
):
    return {
        "schema": "limen.execution_trajectory.v1",
        "attempt_id": attempt_id or f"attempt-azimuth-{index}",
        "task_id": task_id or f"TASK-violet-{index}",
        "classification": {
            "task_type": task_type,
            "labels": list(labels),
            "workstream": "reacceptance",
        },
        "executing_keeper": keeper,
        "executing_session": f"session-indigo-{index}",
        "provider_route": route,
        "execution_profile": {"capability": "bounded-repair"},
        "spend": {"amount": 1.0, "unit": "attempt"},
        "started_at": "2026-07-16T18:00:00Z" if ended_at.startswith("2026") else "2025-01-01T00:00:00Z",
        "ended_at": ended_at,
        "outcome": outcome,
        "repository": "signal-garden/orbit-index",
        "exact_commit": HEAD,
        "pull_request": f"https://github.com/signal-garden/orbit-index/pull/{index + 1}",
        "terminal_predicate": {
            "command": "verify-azimuth --exact-head",
            "passed": verified,
            "checked_at": ended_at,
            "head_sha": HEAD,
        },
        "receipt": {
            "reference": f"receipt://azimuth/{index}",
            "digest": f"sha256:azimuth-{index}",
            "verified": verified,
            "head_sha": HEAD,
        },
    }


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _fixture_receipt_authority(_trajectory):
    return True


def _compute(module, path, *, min_attempts=5, unfit_rate=0.25, window_days=30, authority=False):
    return module.compute(
        min_attempts=min_attempts,
        unfit_rate=unfit_rate,
        window_days=window_days,
        trajectories_path=path,
        now=NOW,
        receipt_authority=_fixture_receipt_authority if authority else None,
    )


def _dispatch_task(task_id, *, type_="analysis", labels=None):
    return Task(
        id=task_id,
        title="fixture task",
        status="open",
        target_agent="provider-saffron-auto",
        type=type_,
        labels=labels or [],
        created=NOW.date(),
    )


class TestTrajectoryBackedFitness:
    def test_report_is_explicitly_shadow_only(self, tmp_path, monkeypatch):
        module = _reload_fitness_module(monkeypatch, tmp_path)
        path = _write_jsonl(tmp_path / "logs" / "execution-trajectories.jsonl", [_trajectory(1)])
        data = _compute(module, path, min_attempts=1)
        assert data["schema"] == "limen.lane_fitness_shadow.v1"
        assert data["source_schema"] == "limen.execution_trajectory.v1"
        assert data["mode"] == "shadow"
        assert data["authoritative"] is False
        assert data["steering_enabled"] is False
        assert data["value_authority"]["ready"] is False

    def test_unique_attempt_id_counts_once(self, tmp_path, monkeypatch):
        module = _reload_fitness_module(monkeypatch, tmp_path)
        row = _trajectory(1)
        path = _write_jsonl(tmp_path / "trajectories.jsonl", [row, row])
        data = _compute(module, path, min_attempts=1)
        pair = data["pairs"]["provider-saffron-auto"]["analysis"]
        assert pair["attempted"] == 1
        assert data["corpus"]["duplicate_rows"] == 1

    def test_frozen_attempt_classification_ignores_current_board_and_done_history(self, tmp_path, monkeypatch):
        module = _reload_fitness_module(monkeypatch, tmp_path)
        path = _write_jsonl(
            tmp_path / "trajectories.jsonl",
            [_trajectory(1, task_id="TASK-recurring", task_type="research", labels=("frozen-violet",))],
        )
        # Old board-event scoring would credit this historical done event and apply the mutable
        # current type. The trajectory scorer never opens tasks.yaml.
        (tmp_path / "tasks.yaml").write_text(
            "tasks:\n"
            "  - id: TASK-recurring\n"
            "    type: code\n"
            "    labels: [current-amber]\n"
            "    dispatch_log:\n"
            "      - {agent: provider-saffron-auto, status: done, timestamp: 2026-07-16T19:00:00Z}\n",
            encoding="utf-8",
        )
        data = _compute(module, path, min_attempts=1)
        classes = data["pairs"]["provider-saffron-auto"]
        assert set(classes) == {"research", "frozen-violet"}
        assert "code" not in classes and "current-amber" not in classes
        assert classes["research"]["verified_value"] == 0

    def test_value_is_credited_to_executing_keeper_not_provider_route(self, tmp_path, monkeypatch):
        module = _reload_fitness_module(monkeypatch, tmp_path)
        path = _write_jsonl(
            tmp_path / "trajectories.jsonl",
            [
                _trajectory(
                    1,
                    keeper="keeper-celadon",
                    route="provider-heliotrope-auto",
                    outcome="succeeded",
                    verified=True,
                )
            ],
        )
        data = _compute(module, path, min_attempts=1, authority=True)
        assert data["keeper_credit"] == {"keeper-celadon": {"verified_value": 1, "attempted": 1, "rate": 1.0}}
        assert "provider-heliotrope-auto" in data["pairs"]
        assert "keeper-celadon" not in data["pairs"]

    def test_unverified_success_earns_zero_value(self, tmp_path, monkeypatch):
        module = _reload_fitness_module(monkeypatch, tmp_path)
        path = _write_jsonl(
            tmp_path / "trajectories.jsonl",
            [_trajectory(1, outcome="succeeded", verified=False)],
        )
        data = _compute(module, path, min_attempts=1, authority=True)
        pair = data["pairs"]["provider-saffron-auto"]["analysis"]
        assert pair["attempted"] == 1
        assert pair["verified_value"] == 0
        assert "done" not in pair
        assert pair["fit"] is False

    def test_verified_rate_drives_shadow_fit_classification(self, tmp_path, monkeypatch):
        module = _reload_fitness_module(monkeypatch, tmp_path)
        rows = [_trajectory(i, outcome="succeeded" if i == 0 else "failed", verified=i == 0) for i in range(10)]
        path = _write_jsonl(tmp_path / "trajectories.jsonl", rows)
        data = _compute(module, path, authority=True)
        pair = data["pairs"]["provider-saffron-auto"]["analysis"]
        assert pair == {
            "verified_value": 1,
            "attempted": 10,
            "rate": 0.1,
            "fit": False,
        }
        assert data["unfit_pairs"][0]["provider_route"] == "provider-saffron-auto"

    def test_window_excludes_old_terminal_attempt(self, tmp_path, monkeypatch):
        module = _reload_fitness_module(monkeypatch, tmp_path)
        path = _write_jsonl(
            tmp_path / "trajectories.jsonl",
            [_trajectory(1, ended_at="2025-01-01T01:00:00Z")],
        )
        data = _compute(module, path)
        assert data["considered_attempts"] == 0
        assert data["pairs"] == {}

    def test_missing_trajectory_source_is_coverage_debt_not_zero_work(self, tmp_path, monkeypatch):
        module = _reload_fitness_module(monkeypatch, tmp_path)
        data = _compute(module, tmp_path / "missing.jsonl")
        assert data["pairs"] == {}
        assert data["corpus"]["source_missing"] is True

    def test_cli_write_keeps_shadow_output_observable(self, tmp_path):
        path = _write_jsonl(
            tmp_path / "execution-trajectories.jsonl",
            [_trajectory(1, outcome="succeeded", verified=True)],
        )
        env = os.environ.copy()
        env["LIMEN_ROOT"] = str(tmp_path)
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "lane-fitness.py"),
                "--write",
                "--trajectories",
                str(path),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert proc.returncode == 0, proc.stderr
        report = json.loads((tmp_path / "logs" / "lane-fitness.json").read_text(encoding="utf-8"))
        assert report["mode"] == "shadow"
        assert report["steering_enabled"] is False
        assert "LANE FITNESS SHADOW" in proc.stdout

    def test_cli_default_check_is_zero_write(self, tmp_path):
        path = _write_jsonl(
            tmp_path / "execution-trajectories.jsonl",
            [_trajectory(1, outcome="succeeded", verified=True)],
        )
        output_root = tmp_path / "output-root"
        output_root.mkdir()
        env = os.environ.copy()
        env["LIMEN_ROOT"] = str(output_root)
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "lane-fitness.py"),
                "--trajectories",
                str(path),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert list(output_root.iterdir()) == []


class TestDispatchShadowIntegration:
    def test_lane_fitness_fail_open_missing_or_corrupt(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
        assert D._lane_fitness() == {}
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "lane-fitness.json").write_text("NOT JSON", encoding="utf-8")
        assert D._lane_fitness() == {}

    def test_lane_fitness_reads_observable_shadow_pairs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
        (tmp_path / "logs").mkdir()
        payload = {
            "schema": "limen.lane_fitness_shadow.v1",
            "mode": "shadow",
            "steering_enabled": False,
            "pairs": {
                "provider-saffron-auto": {"analysis": {"verified_value": 0, "attempted": 8, "rate": 0.0, "fit": False}}
            },
        }
        (tmp_path / "logs" / "lane-fitness.json").write_text(json.dumps(payload), encoding="utf-8")
        assert D._lane_fitness()["provider-saffron-auto"]["analysis"]["fit"] is False

    def test_shadow_observation_preserves_candidate_order_exactly(self):
        fitness = {
            "provider-saffron-auto": {"analysis": {"fit": False, "verified_value": 0, "attempted": 9, "rate": 0.0}}
        }
        unfit = _dispatch_task("TASK-first")
        fit_unknown = _dispatch_task("TASK-second", type_="code")
        original = [unfit, fit_unknown]
        D._LANE_ROUTING_RECEIPTS.clear()

        observed = D._observe_lane_fitness_shadow("provider-saffron-auto", original, fitness)

        assert [task.id for task in observed] == ["TASK-first", "TASK-second"]
        assert observed is not original
        receipt = D._LANE_ROUTING_RECEIPTS["TASK-first"]
        assert receipt["source"] == "lane_fitness_shadow"
        assert receipt["mode"] == "shadow"
        assert receipt["steering_enabled"] is False
        assert receipt["would_deprioritize"] is True
        assert "TASK-second" not in D._LANE_ROUTING_RECEIPTS

    def test_shadow_recommendation_cannot_steer_real_reservation(self, monkeypatch):
        """A critical shadow-unfit task still beats a low-priority shadow-fit task."""

        monkeypatch.setenv("LIMEN_VALUE_GATE", "0")
        monkeypatch.setattr(
            D,
            "_lane_fitness",
            lambda: {
                "codex": {
                    "analysis": {"fit": False, "verified_value": 0, "attempted": 12, "rate": 0.0},
                    "code": {"fit": True, "verified_value": 12, "attempted": 12, "rate": 1.0},
                }
            },
        )
        board = LimenFile.model_validate(
            {
                "portal": {"budget": {"daily": 10, "per_agent": {"codex": 10}, "track": {"date": ""}}},
                "tasks": [
                    {
                        "id": "UNFIT-CRITICAL",
                        "title": "critical frozen-class attempt",
                        "repo": "signal-garden/orbit-index",
                        "type": "analysis",
                        "target_agent": "codex",
                        "priority": "critical",
                        "status": "open",
                        "created": "2026-07-16",
                    },
                    {
                        "id": "FIT-LOW",
                        "title": "low-priority fit route",
                        "repo": "signal-garden/orbit-index",
                        "type": "code",
                        "target_agent": "codex",
                        "priority": "low",
                        "status": "open",
                        "created": "2026-07-16",
                    },
                ],
            }
        )
        D._LANE_ROUTING_RECEIPTS.clear()

        picked = D._select_parallel_reservations(
            board,
            ["codex"],
            1,
            NOW,
            dry_run=False,
            admission_snapshot=None,
        )

        assert picked == [("codex", "UNFIT-CRITICAL")]
        assert D._LANE_ROUTING_RECEIPTS["UNFIT-CRITICAL"]["source"] == "lane_fitness_shadow"

    def test_shadow_unfit_is_observation_not_authority(self):
        fitness = {
            "provider-saffron-auto": {"analysis": {"fit": False, "verified_value": 0, "attempted": 9, "rate": 0.0}}
        }
        task = _dispatch_task("TASK-observed")
        assert D._fitness_unfit("provider-saffron-auto", task, fitness) is True
        assert D._observe_lane_fitness_shadow("provider-saffron-auto", [task], fitness) == [task]

    def test_missing_shadow_signal_preserves_order_and_records_absence(self):
        tasks = [_dispatch_task("TASK-a"), _dispatch_task("TASK-b")]
        D._LANE_ROUTING_RECEIPTS.clear()
        assert D._observe_lane_fitness_shadow("provider-umber-auto", tasks, {}) == tasks
        receipt = D._LANE_ROUTING_RECEIPTS["__absent_provider-umber-auto"]
        assert receipt["source"] == "lane_fitness_shadow_absent"
        assert receipt["steering_enabled"] is False
