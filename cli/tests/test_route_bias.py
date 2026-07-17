"""Historical board-event projections are telemetry, never provider-routing authority."""

from __future__ import annotations

import importlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
route = importlib.import_module("route")


def _ledger(tmp: Path, lanes: dict):
    (tmp / "logs").mkdir(parents=True, exist_ok=True)
    (tmp / "logs" / "ledger.json").write_text(json.dumps({"lanes": lanes}))


def _self_improve(tmp: Path, lane_adjustments: list[dict]):
    (tmp / "logs").mkdir(parents=True, exist_ok=True)
    (tmp / "logs" / "self-improve-proposal.json").write_text(json.dumps({"lane_adjustments": lane_adjustments}))


def test_board_event_ledger_cannot_create_route_bias(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(
        tmp_path,
        {
            "opencode": {"waste_classes": ["code", "build-out"], "win_classes": []},
            "jules": {"waste_classes": ["coverage", "code"], "win_classes": ["revenue", "product"]},
        },
    )
    assert route._ledger_bias({"type": "code", "labels": ["coverage"]}) == {}
    assert route._ledger_bias({"type": "code", "labels": ["revenue", "build-out"]}) == {}


def test_missing_ledger_has_the_same_non_authoritative_result(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)  # no logs/ledger.json written
    assert route._ledger_bias({"type": "code", "labels": ["build-out"]}) == {}


def test_historical_board_files_cannot_change_pick_distribution(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(
        tmp_path,
        {
            "opencode": {"waste_classes": ["code", "build-out"], "win_classes": []},
            "codex": {"waste_classes": [], "win_classes": ["code", "build-out"]},
            "claude": {"waste_classes": [], "win_classes": ["code", "build-out"]},
            "agy": {"waste_classes": [], "win_classes": ["code", "build-out"]},
        },
    )
    _self_improve(
        tmp_path,
        [
            {"lane": "codex", "target_weight": 0.1},
            {"lane": "opencode", "target_weight": 2.0},
        ],
    )
    health = {"codex": True, "claude": True, "agy": True, "opencode": True}
    budget = {"codex": 100, "claude": 100, "agy": 100, "opencode": 100}
    assigned: dict[str, int] = {}
    picks = []
    for _ in range(28):
        v = route._pick_local({"title": "build it", "type": "code", "labels": ["build-out"]}, health, assigned, budget)
        picks.append(v)
        assigned[v] = assigned.get(v, 0) + 1
    c = Counter(picks)
    assert max(c.values()) - min(c.values()) <= 1, c
    assert set(c) == set(health)


def test_self_improve_lane_weights_are_not_consumed(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    monkeypatch.setattr(route, "_vendor_cliff_urgency", lambda: {})
    _self_improve(
        tmp_path,
        [
            {"lane": "codex", "target_weight": 1.0},
            {"lane": "opencode", "target_weight": 1.25},
        ],
    )

    assert route._learned_weights() == {}

    health = {"codex": True, "opencode": True}
    budget = {"codex": 100, "opencode": 100}
    assigned = {"codex": 1, "opencode": 1}
    pick = route._pick_local({"title": "ordinary code task", "type": "code"}, health, assigned, budget)

    assert pick == "codex"


def test_retired_board_weight_knobs_cannot_restore_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _self_improve(tmp_path, [{"lane": "opencode", "target_weight": 0.1}])

    monkeypatch.setenv("LIMEN_SI_WEIGHT_FLOOR", "not-a-float")
    monkeypatch.setenv("LIMEN_SI_WEIGHT_CEILING", "also-not-a-float")
    assert route._learned_weights() == {}

    _ledger(tmp_path, {"opencode": {"waste_classes": ["code"], "win_classes": []}})
    monkeypatch.setenv("LIMEN_LEDGER_BIAS_FLOOR", "not-a-float")
    assert route._ledger_bias({"type": "code"}) == {}


def test_malformed_usage_runway_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps({"vendors": {"codex": {"runway_h": "bad-meter-value"}, "claude": {"runway_h": 3}}})
    )

    runway = route._vendor_runway()

    assert runway["codex"] == float("inf")
    assert runway["claude"] == 3.0


def test_deploy_still_opencode_despite_bias(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(tmp_path, {"opencode": {"waste_classes": ["code"], "win_classes": []}})
    health = {"codex": True, "claude": True, "agy": True, "opencode": True}
    budget = {"codex": 100, "claude": 100, "agy": 100}
    v = route._pick_local({"title": "deploy cloudflare worker", "type": "infra"}, health, {}, budget)
    assert v == "opencode", "the deploy specialty fires before weighting — bias never blocks it"


def test_slow_task_routes_to_jules_not_back_to_local(tmp_path, monkeypatch):
    """A "slow"-labelled task already timed out on a wall-clock-bound sync local lane (dispatch.py's
    timeout->jules path). The local-first router must NOT steal it back to a local lane — that re-times-
    out and retargets to jules every beat, an infinite loop where jules never actually runs. It must go
    to the async remote lane (jules) while jules is healthy."""
    monkeypatch.setattr(route, "ROOT", tmp_path)
    # every local lane is healthy, so the local-first path WOULD fire (clone-on-demand) — the slow
    # guard must intercept and route to jules before that.
    task = {"id": "S1", "repo": "o/r", "type": "content", "labels": ["slow", "generated"], "budget_cost": 2}
    health = {a: True for a in route.PAID_AGENT_ORDER}
    pick, reason = route.route_task(task, health, tmp_path, assigned={}, budget={"jules": 100}, runway={})
    assert pick == "jules", f"slow task stolen back to a local sync lane (infinite loop): {pick} ({reason})"


def test_slow_task_falls_through_to_local_when_jules_down(tmp_path, monkeypatch):
    """Never strand: if jules is DOWN, a slow task still routes to a healthy local lane rather than
    going unroutable — the async carve-out only applies while jules can actually take it."""
    monkeypatch.setattr(route, "ROOT", tmp_path)
    task = {"id": "S2", "repo": "o/r", "type": "content", "labels": ["slow"], "budget_cost": 2}
    health = {a: True for a in route.PAID_AGENT_ORDER}
    health["jules"] = False
    budget = {a: 100 for a in route.PAID_AGENT_ORDER}
    pick, _reason = route.route_task(task, health, tmp_path, assigned={}, budget=budget, runway={})
    assert pick in route.LOCAL_CHECKOUT_AGENTS, f"slow task stranded when jules down: {pick}"


def test_existing_healthy_assignment_is_sticky(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    task = {"id": "T-STICKY", "repo": "o/r", "type": "code", "target_agent": "opencode"}
    health = {"opencode": True, "codex": True, "jules": False}

    assert route._existing_assignment_usable(task, "opencode", health, tmp_path)


def test_existing_down_assignment_is_not_sticky(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    task = {"id": "T-DOWN", "repo": "o/r", "type": "code", "target_agent": "opencode"}
    health = {"opencode": False, "codex": True}

    assert not route._existing_assignment_usable(task, "opencode", health, tmp_path)


def test_slow_local_assignment_not_sticky_when_jules_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    task = {"id": "T-SLOW", "repo": "o/r", "type": "code", "labels": ["slow"], "target_agent": "opencode"}
    health = {"opencode": True, "codex": True, "jules": True}

    assert not route._existing_assignment_usable(task, "opencode", health, tmp_path)
    assert route._existing_assignment_usable(task, "jules", health, tmp_path)


def test_jules_not_stranded_when_sole_capable(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(tmp_path, {"jules": {"waste_classes": ["coverage"], "win_classes": ["revenue"]}})
    # only jules healthy; repo set but no local checkout under workdir → extended pick, jules sole option
    task = {"title": "add coverage", "type": "code", "labels": ["coverage"], "repo": "o/r"}
    health = {a: (a == "jules") for a in route.PAID_AGENT_ORDER}
    pick, _reason = route.route_task(task, health, tmp_path, assigned={}, budget={})
    assert pick == "jules", "a coverage task on a no-checkout repo still routes to jules — never stranded"
