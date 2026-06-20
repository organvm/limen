"""Tests for the converge() organ.

These use FAKE in-memory adapters only — no network, no mesh, no CCE, no anthropic.
They assert the five contracted behaviours of converge():

  (a) the synthesizer's better_version is returned,
  (b) shots the synthesizer dropped appear in cited_losers,
  (c) next_shots come from the gap_finder,
  (d) promoter.promote is called when score >= threshold,
  (e) promoter.rollback is called when score < threshold.
"""

from __future__ import annotations

import pytest

from limen.converge import (
    ConcatSynthesizer,
    ConvergeResult,
    DeterministicScorer,
    LexicalGapFinder,
    LexicalRanker,
    NoopPromoter,
    Shot,
    Synthesis,
    converge,
)


# ─── Fake adapters ───────────────────────────────────────────────────


class FakeRanker:
    """Ranks by reversing the input order so we can prove rank order is honoured."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Shot]]] = []

    def rank(self, idea: str, shots: list[Shot]) -> list[Shot]:
        self.calls.append((idea, shots))
        return list(reversed(shots))


class FakeSynthesizer:
    """Returns a fixed distillate, keeping only the ids in ``keep``."""

    def __init__(self, better: str, keep: list[str]) -> None:
        self.better = better
        self.keep = keep
        self.seen_ranked: list[Shot] | None = None

    def synthesize(self, idea: str, ranked: list[Shot]) -> Synthesis:
        self.seen_ranked = ranked
        kept = [s.id for s in ranked if s.id in self.keep]
        dropped = [s.id for s in ranked if s.id not in self.keep]
        return Synthesis(better_version=self.better, kept_ids=kept, dropped_ids=dropped)


class FakeScorer:
    """Returns a fixed score so we can drive the threshold branch deterministically."""

    def __init__(self, value: float) -> None:
        self.value = value
        self.args: tuple | None = None

    def score(self, idea: str, better_version: str, shots: list[Shot]) -> float:
        self.args = (idea, better_version, shots)
        return self.value


class RecordingPromoter:
    def __init__(self) -> None:
        self.promote_args: tuple[str, str] | None = None
        self.rollback_called = False

    def promote(self, idea: str, better_version: str) -> None:
        self.promote_args = (idea, better_version)

    def rollback(self) -> None:
        self.rollback_called = True


class FakeGapFinder:
    def __init__(self, gaps: list[str]) -> None:
        self._gaps = gaps
        self.called_with: tuple | None = None

    def gaps(self, idea: str, shots: list[Shot]) -> list[str]:
        self.called_with = (idea, shots)
        return list(self._gaps)


@pytest.fixture
def shots() -> list[Shot]:
    return [
        Shot(id="a", text="first draft", source="laneA"),
        Shot(id="b", text="second draft", source="laneB"),
        Shot(id="c", text="third draft", source="laneC"),
    ]


# ─── The five contracted behaviours ──────────────────────────────────


def test_better_version_chosen_and_returned(shots):
    synth = FakeSynthesizer(better="THE DISTILLATE", keep=["a"])
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=synth,
        scorer=FakeScorer(0.9),
        promoter=RecordingPromoter(),
        gap_finder=FakeGapFinder([]),
    )
    assert isinstance(result, ConvergeResult)
    assert result.better_version == "THE DISTILLATE"


def test_dropped_shots_appear_in_cited_losers(shots):
    # keep only "a"; "b" and "c" must show up as cited losers.
    synth = FakeSynthesizer(better="x", keep=["a"])
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=synth,
        scorer=FakeScorer(0.9),
        promoter=RecordingPromoter(),
        gap_finder=FakeGapFinder([]),
    )
    loser_ids = {s.id for s in result.cited_losers}
    assert loser_ids == {"b", "c"}
    assert "a" not in loser_ids
    # cited_losers carries full Shot provenance, not just ids.
    assert all(isinstance(s, Shot) for s in result.cited_losers)


def test_cited_losers_follow_rank_order(shots):
    # FakeRanker reverses -> [c, b, a]; keep "a" -> losers in rank order are [c, b].
    synth = FakeSynthesizer(better="x", keep=["a"])
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=synth,
        scorer=FakeScorer(0.9),
        promoter=RecordingPromoter(),
        gap_finder=FakeGapFinder([]),
    )
    assert [s.id for s in result.cited_losers] == ["c", "b"]


def test_next_shots_surface_from_gap_finder(shots):
    gaps = ["explore: edge-case", "explore: failure-mode"]
    gf = FakeGapFinder(gaps)
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=FakeSynthesizer(better="x", keep=["a"]),
        scorer=FakeScorer(0.9),
        promoter=RecordingPromoter(),
        gap_finder=gf,
    )
    assert result.next_shots == gaps
    assert gf.called_with is not None  # gap_finder was actually consulted


def test_promote_called_when_score_meets_threshold(shots):
    promoter = RecordingPromoter()
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=FakeSynthesizer(better="GOOD", keep=["a"]),
        scorer=FakeScorer(0.8),
        promoter=promoter,
        gap_finder=FakeGapFinder([]),
        threshold=0.7,
    )
    assert result.promoted is True
    assert result.score == 0.8
    assert promoter.promote_args == ("the idea", "GOOD")
    assert promoter.rollback_called is False


def test_promote_called_at_exact_threshold(shots):
    promoter = RecordingPromoter()
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=FakeSynthesizer(better="OK", keep=["a"]),
        scorer=FakeScorer(0.7),
        promoter=promoter,
        gap_finder=FakeGapFinder([]),
        threshold=0.7,
    )
    assert result.promoted is True
    assert promoter.promote_args == ("the idea", "OK")


def test_rollback_called_when_score_below_threshold(shots):
    promoter = RecordingPromoter()
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=FakeSynthesizer(better="WEAK", keep=["a"]),
        scorer=FakeScorer(0.4),
        promoter=promoter,
        gap_finder=FakeGapFinder([]),
        threshold=0.7,
    )
    assert result.promoted is False
    assert result.score == 0.4
    assert promoter.rollback_called is True
    assert promoter.promote_args is None  # promote NOT called


# ─── The dependency-free fallback adapters also satisfy the contract ─


def test_fallback_adapters_end_to_end():
    """The shipped fallback kit (used by --dry-run) runs converge() with no deps."""
    shots = [
        Shot(id="1", text="cats are great pets and very fluffy", source="x"),
        Shot(id="2", text="completely unrelated text about taxes", source="y"),
    ]
    promoter = NoopPromoter()
    result = converge(
        "cats are great pets",
        shots,
        ranker=LexicalRanker(),
        synthesizer=ConcatSynthesizer(),
        scorer=DeterministicScorer(),
        promoter=promoter,
        gap_finder=LexicalGapFinder(),
        threshold=0.7,
    )
    # The on-topic shot covers the whole idea -> high score -> promoted.
    assert result.promoted is True
    assert promoter.promoted is not None
    assert "cats" in result.better_version
    # The off-topic shot is a cited loser.
    assert any(s.id == "2" for s in result.cited_losers)


def test_fallback_rollback_on_empty_idea_coverage():
    """An off-topic-only shot set scores 0 -> rollback, nothing promoted."""
    shots = [Shot(id="1", text="something about quarterly tax filings", source="z")]
    promoter = NoopPromoter()
    result = converge(
        "kittens and puppies",
        shots,
        ranker=LexicalRanker(),
        synthesizer=ConcatSynthesizer(),
        scorer=DeterministicScorer(),
        promoter=promoter,
        gap_finder=LexicalGapFinder(),
        threshold=0.7,
    )
    assert result.promoted is False
    assert promoter.rolled_back is True
    # The uncovered idea tokens become next shots.
    assert any("kittens" in nxt or "puppies" in nxt for nxt in result.next_shots)
