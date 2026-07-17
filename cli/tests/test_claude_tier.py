"""Claude routing follows live provider state or provider Auto."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import limen.dispatch as D
from limen.models import Task


@pytest.fixture(autouse=True)
def clear_override(monkeypatch) -> None:
    monkeypatch.delenv("LIMEN_CLAUDE_MODEL", raising=False)
    D._MODEL_SELECTION_RECEIPTS.clear()


def task(*, labels: list[str] | None = None, claude_tier: str | None = None) -> Task:
    return Task(
        id="CLAUDE-DYNAMIC",
        title="provider-neutral task",
        target_agent="claude",
        labels=labels or [],
        claude_tier=claude_tier,
        created=date(2026, 7, 17),
    )


def test_legacy_tier_words_are_opaque_and_provider_auto_wins() -> None:
    plain = task()
    hinted = task(labels=["tier:any-renamed-shape"], claude_tier="opus")
    launch = D._attempt_launch_entry(
        hinted,
        "claude",
        reservation_session="claude-tier-test",
        started_at=datetime.now(timezone.utc),
        output="fixture model-selection attempt",
    )
    hinted.status = "in_progress"
    hinted.dispatch_log.extend([launch, launch.model_copy(update={"status": "in_progress"})])

    assert D._claude_model(plain) is None
    assert D._claude_model(hinted) is None
    assert D._MODEL_SELECTION_RECEIPTS[hinted.id]["attempt_id"] == launch.attempt_id
    assert D._MODEL_SELECTION_RECEIPTS[hinted.id]["selection_source"] == "claude_auto"


def test_explicit_override_fails_closed_without_executing_claude_as_a_prompt(monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "shape-z")
    monkeypatch.setattr(D, "_resolve_agent_binary", lambda *_args: pytest.fail("must not resolve Claude metadata"))
    monkeypatch.setattr(D, "_run_capture", lambda *_args, **_kwargs: pytest.fail("must not execute Claude metadata"))

    with pytest.raises(D.ProviderModelSelectionBlocked, match="no safe metadata catalog"):
        D._claude_model(task())


def test_unreachable_or_removed_override_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_CLAUDE_MODEL", "shape-removed")

    with pytest.raises(D.ProviderModelSelectionBlocked, match="no safe metadata catalog"):
        D._claude_model(task())
