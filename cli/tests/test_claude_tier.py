"""Tests for the Claude-lane earned-tier ladder (dispatch._claude_model & helpers).

Mirrors the _codex_model suite in test_accelerator.py: env override wins, derive at call
-time from task class, fail-open. Haiku-first for verifiable classes; a higher tier is
pre-assigned only by explicit configuration or the reserved principled set. Historical
board-event win/waste classes are not tier authority. Escalate-on-failure reuses the existing machinery —
a 'tried:claude' retry bumps the tier one rung, and a failed lane cascades onward.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import limen.dispatch as D
from limen.model_selection import _CLAUDE_TIER_ORDER
from limen.models import Task


def _task(type_="code", labels=None, claude_tier=None):
    return Task(
        id="T1",
        title="t",
        target_agent="claude",
        type=type_,
        labels=labels or [],
        claude_tier=claude_tier,
        created=date(2026, 6, 22),
    )


def _write_ledger(root: Path, claude_classes: dict):
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "ledger.json").write_text(json.dumps({"lanes": {"claude": claude_classes}}))


def _write_tiers(root: Path, mapping: dict):
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "model-tiers.json").write_text(json.dumps({"claude": mapping}))


def _write_fable_acceptance(root: Path) -> Path:
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).date().isoformat()
    path = root / "fable-acceptance.json"
    path.write_text(
        json.dumps(
            {
                "schema": "limen.fable_acceptance.v1",
                "week": monday,
                "category": "adversarial-review",
                "percent": 5,
                "sources": ["docs/fable-allotment.md"],
                "verification": ["python3 scripts/fable-allotment.py audit"],
                "mode": "plan-only",
                "deliverable": "continuation-capsule",
                "builder_tier_max": "opus",
                "motion_receipt_deadline_seconds": 5400,
            }
        )
    )
    return path


def _clear(monkeypatch):
    for k in (
        "LIMEN_CLAUDE_MODEL",
        "LIMEN_CLAUDE_TIER_SELECT",
        "LIMEN_CLAUDE_RETRY_BUMP",
        "LIMEN_CLAUDE_OPUS_CLASSES",
        "LIMEN_CLAUDE_FABLE_CLASSES",
        "LIMEN_CLAUDE_MAX_INHERITED_TIER",
        "LIMEN_CLAUDE_FABLE_FALLBACK_TIER",
        "LIMEN_CLAUDE_HAIKU_MODEL",
        "LIMEN_CLAUDE_SONNET_MODEL",
        "LIMEN_CLAUDE_OPUS_MODEL",
        "LIMEN_CLAUDE_FABLE_MODEL",
        "LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE",
        "LIMEN_FABLE_ACCEPTANCE",
        "LIMEN_FABLE_BALANCE_PATH",
        "LIMEN_ALLOW_EXPENSIVE_CLAUDE_MODEL_PIN",
        "LIMEN_ALLOW_CLAUDE_1M_CONTEXT",
    ):
        monkeypatch.delenv(k, raising=False)


def _this_monday() -> str:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).date().isoformat()


def _write_balance(root: Path, spent_pct: float, week: str | None = None) -> Path:
    (root / "logs").mkdir(parents=True, exist_ok=True)
    path = root / "logs" / "fable-allotment.json"
    path.write_text(
        json.dumps(
            {
                "week": week if week is not None else _this_monday(),
                "schema": "limen.fable_balance.v1",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "spent_tokens": 0,
                "spent_pct": spent_pct,
                "deliberate_cap": 40,
                "hard_cap": 50,
                "over_cap": spent_pct >= 50,
                "source": "transcript-token-sum",
                "meter_ready": True,
            }
        )
    )
    return path


def _write_reserve_acceptance(root: Path) -> Path:
    path = root / "fable-reserve.json"
    path.write_text(
        json.dumps(
            {
                "schema": "limen.fable_acceptance.v1",
                "week": _this_monday(),
                "category": "reserve",
                "percent": 5,
                "reserve_unlocked": True,
                "sources": ["docs/fable-allotment.md"],
                "verification": ["python3 scripts/fable-allotment.py audit"],
                "mode": "plan-only",
                "deliverable": "continuation-capsule",
                "builder_tier_max": "opus",
                "motion_receipt_deadline_seconds": 5400,
            }
        )
    )
    return path


def test_haiku_default_for_verifiable_class(tmp_path, monkeypatch):
    """A coding task (failure cheaply detectable via CI/PR) starts at haiku."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="code")) == "haiku"


def test_board_event_waste_class_cannot_preassign_sonnet(tmp_path, monkeypatch):
    """Historical board outcomes remain telemetry and cannot choose a provider tier."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research", "value-discovery"]})
    assert D._claude_model(_task(type_="research")) == "haiku"
    assert D._claude_model(_task(type_="code", labels=["value-discovery"])) == "haiku"


def test_opus_for_reserved_class(tmp_path, monkeypatch):
    """The reserved principled set (undetectable AND high-stakes) → opus; highest tier wins."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="code", labels=["canon"])) == "opus"
    # The explicit reserved class wins regardless of irrelevant historical waste telemetry.
    assert D._claude_model(_task(type_="research", labels=["synthesis"])) == "opus"


def test_fable_is_reserved_above_opus_and_requires_acceptance(tmp_path, monkeypatch):
    """Fable is a top rung, but it is not reached unless the run carries written acceptance."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    assert _CLAUDE_TIER_ORDER[-1] == "fable"

    _write_tiers(tmp_path, {"fable": ["final-canonical-decision"]})
    task = _task(type_="final-canonical-decision", labels=["mode:plan-only"])
    assert D._claude_model(task) == "sonnet"

    acceptance = _write_fable_acceptance(tmp_path)
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(acceptance))
    _write_balance(tmp_path, 5.0)
    assert D._claude_model(task) == "fable"

    monkeypatch.setenv("LIMEN_CLAUDE_FABLE_MODEL", "claude-fable-5")
    assert D._resolve_claude_model("fable") == "claude-fable-5"


def test_env_override_wins(tmp_path, monkeypatch):
    """An explicit cheap LIMEN_CLAUDE_MODEL pin wins over class derivation."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "claude-sonnet-4-6")
    _write_ledger(tmp_path, {"waste_classes": []})
    assert D._claude_model(_task(type_="code")) == "claude-sonnet-4-6"


def test_global_opus_and_large_context_pin_is_guarded(tmp_path, monkeypatch):
    """A global Opus/1M pin would become inherited fan-out, so it needs explicit gates."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "claude-opus-4-8[1m]")
    _write_ledger(tmp_path, {"waste_classes": []})
    assert D._claude_model(_task(type_="code")) == "sonnet"

    monkeypatch.setenv("LIMEN_ALLOW_EXPENSIVE_CLAUDE_MODEL_PIN", "1")
    assert D._claude_model(_task(type_="code")) == "sonnet"

    monkeypatch.setenv("LIMEN_ALLOW_CLAUDE_1M_CONTEXT", "1")
    assert D._claude_model(_task(type_="code")) == "claude-opus-4-8[1m]"


def test_global_fable_pin_cannot_bypass_task_scoped_plan_contract(tmp_path, monkeypatch):
    """A global model pin has no task/capsule boundary and therefore never selects Fable."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "claude-fable-5")
    assert D._claude_model(_task(type_="code")) == "sonnet"
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    _write_balance(tmp_path, 5.0)
    assert D._claude_model(_task(type_="code", labels=["mode:plan-only"])) == "sonnet"


def test_lower_tier_alias_cannot_smuggle_fable_through_cap_fallback(tmp_path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    monkeypatch.setenv("LIMEN_CLAUDE_OPUS_MODEL", "renamed-fable-provider-id")
    _write_balance(tmp_path, 100.0)
    assert D._resolve_claude_model("fable") == "opus"


def test_missing_corrupt_or_hostile_board_ledger_is_ignored(tmp_path, monkeypatch):
    """Board-event ledgers cannot alter tier selection, whether absent, corrupt, or hostile."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))  # no ledger.json written
    assert D._claude_model(_task(type_="research")) == "haiku"
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "ledger.json").write_text("{ this is not json")
    assert D._claude_model(_task(type_="research")) == "haiku"
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="research")) == "haiku"


def test_feature_flag_off_is_bare_invocation(tmp_path, monkeypatch):
    """LIMEN_CLAUDE_TIER_SELECT=0 → None = today's bare `claude -p` (instant rollback)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_CLAUDE_TIER_SELECT", "0")
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="research")) is None


def test_agent_argv_injects_claude_model(tmp_path, monkeypatch):
    """_agent_argv threads the task through and injects -m for the claude lane; backward
    -compatible with the no-task call (codex/opencode callers stay valid)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    argv = D._agent_argv("claude", _task(type_="research"))
    # claude CLI uses --model, NOT -m (codex/opencode use -m; claude rejects it).
    assert "--model" in argv and "haiku" in argv, argv
    assert "-m" not in argv, argv  # regression guard: never emit -m for the claude lane
    assert "-p" in D._agent_argv("claude")  # no task → no crash, static flags intact


def test_retry_bump_on_tried_claude(tmp_path, monkeypatch):
    """A task that already failed on the claude lane (the cascade's 'tried:claude' breadcrumb)
    bumps one rung — the in-tier expression of escalate-on-failed-check. Capped at opus, gateable."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": ["research"]})
    assert D._claude_model(_task(type_="code", labels=["tried:claude"])) == "sonnet"  # haiku→sonnet
    assert D._claude_model(_task(type_="research", labels=["tried:claude"])) == "sonnet"  # haiku→sonnet
    assert D._claude_model(_task(type_="code", labels=["canon", "tried:claude"])) == "opus"  # caps
    acceptance = _write_fable_acceptance(tmp_path)
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(acceptance))
    assert D._claude_model(_task(type_="code", labels=["canon", "tried:claude"])) == "opus"
    monkeypatch.setenv("LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE", "1")
    _write_balance(tmp_path, 5.0)
    assert D._claude_model(_task(type_="code", labels=["canon", "tried:claude", "mode:plan-only"])) == "fable"
    monkeypatch.setenv("LIMEN_CLAUDE_RETRY_BUMP", "0")
    assert D._claude_model(_task(type_="code", labels=["tried:claude"])) == "haiku"  # gated off


def test_per_task_pin_and_tier_aliases_resolve(tmp_path, monkeypatch):
    """The optional per-task claude_tier escape hatch overrides class derivation (env still wins);
    tier→model resolution prefers the bare CLI alias, env-overridable per tier."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    assert D._claude_model(_task(type_="code", claude_tier="opus")) == "opus"
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "pinned-x")
    assert D._claude_model(_task(type_="code", claude_tier="opus")) == "pinned-x"  # env wins above pin
    monkeypatch.delenv("LIMEN_CLAUDE_MODEL")
    monkeypatch.setenv("LIMEN_CLAUDE_SONNET_MODEL", "claude-sonnet-4-6")
    assert D._resolve_claude_model("sonnet") == "claude-sonnet-4-6"
    assert D._resolve_claude_model("haiku") == "haiku"  # bare alias when unset (derive-never-pin)


def test_explicit_model_tiers_override_is_the_only_class_promotion(tmp_path, monkeypatch):
    """The optional operator map may promote classes; the board ledger may not."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})  # ledger empty → would be haiku
    _write_tiers(tmp_path, {"opus": ["migration"], "sonnet": ["docs"]})
    assert D._claude_model(_task(type_="migration")) == "opus"
    assert D._claude_model(_task(type_="docs")) == "sonnet"


def test_failed_claude_escalates_via_existing_cascade(monkeypatch):
    """Escalate-on-failure also rides the EXISTING lane cascade unchanged: a failed claude
    attempt re-routes to the next lane. Documents the cross-lane escalate rung (no new code)."""
    monkeypatch.delenv("LIMEN_DISPATCH_LANES", raising=False)
    monkeypatch.setattr(D, "_lane_cascade", lambda: ["codex", "opencode", "agy", "claude", "gemini", "jules", "ollama"])
    assert D._next_lane("claude") == "gemini"


# ── The .claude/agents/ tier floor is a PROJECTION of the same brain, bound by parity ──────────
# In-harness subagents (Task tool + Workflow agent()) default to inheriting the session model, so a
# fan-out of trivial workers silently rides the session's Opus. The .claude/agents/ type files carry
# a `model:` FLOOR (a per-call model still escalates). These tests bind those pins to the earned-tier
# ladder so the two projections cannot drift. ([[fleet-model-floor-bleed]] [[derive-never-pin-hardcodes]])

# Each agent TYPE → the brain job class it serves. Its pinned model MUST equal the tier the ladder
# derives for that class (verify/scan are default-cheap; synth's "synthesis" is reserved-Opus).
_AGENT_TYPE_JOB_CLASS = {"verify": "verify", "scan": "scan", "synth": "synthesis"}


def _agents_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".claude" / "agents"


def _frontmatter_model(md: Path) -> str | None:
    text = md.read_text()
    block = re.search(r"^---\s*$(.*?)^---\s*$", text, re.MULTILINE | re.DOTALL)
    scope = block.group(1) if block else text
    hit = re.search(r"^model:\s*(\S+)\s*$", scope, re.MULTILINE)
    return hit.group(1) if hit else None


def test_agent_type_pins_match_the_earned_tier_ladder(tmp_path, monkeypatch):
    """A pinned agent-type model MUST equal the tier the earned-tier ladder derives for the job
    class it serves — so dropping "synthesis" from the reserved set (or changing the default rung)
    breaks THIS test, not production. This is the anti-drift binding, mapping-aware not set-only."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})  # empty ledger → only reserved classes lift to opus
    agents = _agents_dir()
    for type_name, job_class in _AGENT_TYPE_JOB_CLASS.items():
        md = agents / f"{type_name}.md"
        assert md.exists(), f"missing agent type file: {md}"
        pinned = _frontmatter_model(md)
        expected = D._claude_model(_task(type_=job_class))
        assert pinned == expected, (
            f"{type_name}.md pins model={pinned!r} but the earned-tier ladder maps job class "
            f"{job_class!r} → {expected!r}; the agent-type floor drifted from the brain"
        )


# ── Live weekly Fable cap: the runtime backstop layered on the accept-time receipt gate ────────
# A valid acceptance receipt is necessary-not-sufficient. Once the week's Fable spend crosses the
# caps in logs/fable-allotment.json, even an accepted Fable selection downgrades to Opus.


def test_fable_over_hard_cap_downgrades_even_with_receipt(tmp_path, monkeypatch):
    """spent_pct ≥ 50 → hard downgrade to opus, no exception (even a valid receipt)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    _write_tiers(tmp_path, {"fable": ["final-canonical-decision"]})
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    task = _task(type_="final-canonical-decision", labels=["mode:plan-only"])
    # Under cap → fable.
    _write_balance(tmp_path, 10.0)
    assert D._claude_tier_for(task) == "fable"
    assert D._claude_model(task) == "fable"
    # Over the hard cap → opus, receipt notwithstanding.
    _write_balance(tmp_path, 60.0)
    assert D._claude_tier_for(task) == "opus"
    assert D._claude_model(task) == "opus"


def test_fable_reserve_band_passes_only_reserve_receipt(tmp_path, monkeypatch):
    """40 ≤ spent_pct < 50 → only a current-week reserve receipt passes; else opus."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    _write_tiers(tmp_path, {"fable": ["final-canonical-decision"]})
    task = _task(type_="final-canonical-decision", labels=["mode:plan-only"])
    _write_balance(tmp_path, 45.0)
    # A non-reserve receipt is valid for acceptance but does not pass the 40–50% band.
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    assert D._claude_tier_for(task) == "opus"
    # A reserve receipt passes the band.
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_reserve_acceptance(tmp_path)))
    assert D._claude_tier_for(task) == "fable"
    # …but not at/over the hard cap.
    _write_balance(tmp_path, 55.0)
    assert D._claude_tier_for(task) == "opus"


def test_fable_cap_fails_closed_when_no_balance_or_stale(tmp_path, monkeypatch):
    """No balance file, or a stale prior-week one, closes Fable to Opus."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    _write_tiers(tmp_path, {"fable": ["final-canonical-decision"]})
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    task = _task(type_="final-canonical-decision", labels=["mode:plan-only"])
    assert D._claude_tier_for(task) == "opus"
    _write_balance(tmp_path, 99.0, week="2020-01-06")
    assert D._claude_tier_for(task) == "opus"


def test_fable_per_task_pin_is_also_capped(tmp_path, monkeypatch):
    """A per-task claude_tier='fable' pin is subject to the same live cap."""
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_ledger(tmp_path, {"waste_classes": []})
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    task = _task(type_="code", labels=["mode:plan-only"], claude_tier="fable")
    _write_balance(tmp_path, 10.0)
    assert D._claude_tier_for(task) == "fable"
    _write_balance(tmp_path, 70.0)
    assert D._claude_tier_for(task) == "opus"


def test_all_agent_type_models_are_valid_tier_aliases():
    """Every .claude/agents/ pin is a bare tier alias (or `inherit`) drawn from the one vocabulary —
    never a dated model id (derive-never-pin). The membership assert on a known rung kills a vacuous
    import that silently empties the tier set."""
    valid = set(_CLAUDE_TIER_ORDER) | {"inherit"}
    assert "haiku" in valid and "opus" in valid and "fable" in valid, "tier vocabulary failed to load"
    files = sorted(_agents_dir().glob("*.md"))
    assert files, "no .claude/agents/*.md type files found"
    for md in files:
        pinned = _frontmatter_model(md)
        assert pinned in valid, (
            f"{md.name} pins model={pinned!r} ∉ {sorted(valid)} — use a bare tier alias so "
            f"_resolve_claude_model resolves it to today's model (derive-never-pin)"
        )


def test_fable_launch_uses_only_capsule_tools_and_prompt(tmp_path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    _write_balance(tmp_path, 5.0)
    task = _task(type_="final-canonical-decision", labels=["mode:plan-only"], claude_tier="fable")

    argv = D._agent_argv("claude", task)
    allowed = D._claude_tool_rules(D._option_values(argv, "--allowedTools"))
    denied = D._claude_tool_rules(D._option_values(argv, "--disallowedTools"))
    assert {"Read", "Glob", "Grep", "Write", "Edit"} <= allowed
    assert {"Bash", "NotebookEdit", "Agent", "Workflow"} <= denied
    prompt = D._build_fable_plan_prompt(task)
    assert "PLAN-ONLY" in prompt
    assert "Do not implement" in prompt
    assert D._fable_packet_relative_path(task).as_posix() in prompt


def test_fable_output_validator_rejects_any_source_change(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    task = _task(type_="final-canonical-decision", labels=["mode:plan-only"], claude_tier="fable")
    D._write_fable_packet(task, tmp_path, status="ready")
    assert D._validate_fable_plan_output(task, tmp_path) == (True, "ok")
    (tmp_path / "implementation.py").write_text("raise SystemExit('not allowed')\n")
    valid, reason = D._validate_fable_plan_output(task, tmp_path)
    assert valid is False
    assert "outside its capsule boundary" in reason


def test_fable_motion_deadline_stops_only_own_synthetic_process(tmp_path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_balance(tmp_path, 5.0)
    monkeypatch.setattr(D, "_FABLE_MOTION_DEADLINE_SECONDS", 0)
    monkeypatch.setenv("LIMEN_FABLE_AUDIT_INTERVAL_SECONDS", "1")
    run, reason = D._run_fable_capture(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path),
        timeout=10,
        env={**__import__("os").environ},
    )
    assert reason == "motion-without-durable-receipt-5400s"
    assert run.returncode is not None


def test_fable_exact_launch_rechecks_balance_before_spawning(tmp_path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_FABLE_ACCEPTANCE", str(_write_fable_acceptance(tmp_path)))
    task = _task(type_="final-canonical-decision", labels=["mode:plan-only"], claude_tier="fable")
    called = False

    def forbidden_spawn(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("Fable process must not start with absent balance state")

    monkeypatch.setattr(D, "_run_fable_capture", forbidden_spawn)
    result = D._run_isolated_agent("claude", task, tmp_path, ["claude", "--model", "fable"], 3)
    assert result is True
    assert called is False
    assert "prelaunch-balance-absent" in (tmp_path / D._fable_packet_relative_path(task)).read_text()
