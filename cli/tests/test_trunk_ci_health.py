"""Tests for the trunk-CI-health sensor (scripts/trunk-ci-health.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "trunk-ci-health.py"


def _load():
    spec = importlib.util.spec_from_file_location("trunk_ci_health", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pr(number: int, checks: list[tuple[str, str]], draft: bool = False, updated: str = "2026-07-10T00:00:00Z") -> dict:
    return {
        "number": number,
        "isDraft": draft,
        "updatedAt": updated,
        "statusCheckRollup": [{"name": n, "conclusion": c} for n, c in checks],
    }


def test_failing_required_checks_only_required_and_bad():
    t = _load()
    pr = _pr(1, [("pr-gate", "FAILURE"), ("python", "FAILURE"), ("web", "SUCCESS")])
    # only pr-gate is required; python failing is ignored (informational)
    assert t.failing_required_checks(pr, {"pr-gate"}) == {"pr-gate"}


def test_classify_wedged_when_k_prs_share_failing_required_check():
    t = _load()
    prs = [_pr(n, [("pr-gate", "FAILURE")]) for n in range(5)]
    v = t.classify(prs, {"pr-gate"}, k=5)
    assert v["healthy"] is False
    assert v["wedged_checks"] == {"pr-gate": 5}


def test_classify_healthy_below_threshold():
    t = _load()
    prs = [_pr(n, [("pr-gate", "FAILURE")]) for n in range(3)]
    v = t.classify(prs, {"pr-gate"}, k=5)
    assert v["healthy"] is True
    assert v["wedged_checks"] == {}


def test_classify_ignores_draft_prs():
    t = _load()
    prs = [_pr(n, [("pr-gate", "FAILURE")], draft=True) for n in range(10)]
    v = t.classify(prs, {"pr-gate"}, k=5)
    assert v["healthy"] is True
    assert v["considered_prs"] == 0


def test_classify_ignores_non_required_failures():
    t = _load()
    # 10 PRs failing an informational check that is NOT required → not a wedge
    prs = [_pr(n, [("python", "FAILURE"), ("pr-gate", "SUCCESS")]) for n in range(10)]
    v = t.classify(prs, {"pr-gate"}, k=5)
    assert v["healthy"] is True


def test_classify_healthy_when_all_pass():
    t = _load()
    prs = [_pr(n, [("pr-gate", "SUCCESS")]) for n in range(10)]
    v = t.classify(prs, {"pr-gate"}, k=5)
    assert v["healthy"] is True
    assert v["failing_by_check"] == {}


def test_classify_excludes_stale_prs_from_wedge():
    # The chronic-backlog guard: many STALE PRs failing pr-gate is not an acute trunk break.
    t = _load()
    stale = [_pr(n, [("pr-gate", "FAILURE")], updated="2026-01-01T00:00:00Z") for n in range(50)]
    v = t.classify(stale, {"pr-gate"}, k=5, fresh_since="2026-07-09T00:00:00Z")
    assert v["healthy"] is True
    assert v["considered_prs"] == 0


def test_classify_wedge_fires_on_fresh_prs_only():
    t = _load()
    stale = [_pr(n, [("pr-gate", "FAILURE")], updated="2026-01-01T00:00:00Z") for n in range(50)]
    fresh = [_pr(100 + n, [("pr-gate", "FAILURE")], updated="2026-07-10T00:00:00Z") for n in range(6)]
    v = t.classify(stale + fresh, {"pr-gate"}, k=5, fresh_since="2026-07-09T00:00:00Z")
    assert v["healthy"] is False
    assert v["wedged_checks"] == {"pr-gate": 6}
    assert v["considered_prs"] == 6
