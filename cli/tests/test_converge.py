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

import argparse

import pytest

from limen.converge import (
    AnthropicSynthesizer,
    ClaudeCliSynthesizer,
    ConcatSynthesizer,
    ConvergeResult,
    DeterministicScorer,
    LexicalGapFinder,
    LexicalRanker,
    NoopPromoter,
    Shot,
    Synthesis,
    _build_live_kit,
    converge,
    main,
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


# ─── --live CLI wiring (hermetic: fake Anthropic client, no network) ──────


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [type("Block", (), {"type": "text", "text": text})()]


class FakeAnthropicClient:
    """Mimics the non-executing model catalog and messages API."""

    def __init__(self, reply: str, catalog: tuple[str, ...] = ()) -> None:
        self._reply = reply
        self._catalog = catalog
        self.calls: list[dict] = []
        self.catalog_calls = 0
        self.messages = self
        owner = self

        class Models:
            def list(self, **_kwargs):
                return owner._list_models()

        self.models = Models()

    def _list_models(self, **_kwargs):
        self.catalog_calls += 1
        rows = [type("Model", (), {"id": identifier})() for identifier in self._catalog]
        return type("Page", (), {"data": rows, "has_next_page": lambda _self: False})()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeMessage(self._reply)


def _live_args(**overrides):
    """An argparse.Namespace shaped like main()'s --live args, with safe defaults."""
    base = dict(
        live=True,
        model=None,
        mesh=False,
        mesh_registry=None,
        promote=False,
        promote_project_root=None,
        promote_candidate_root=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_live_kit_defaults_to_cli_provider_auto_without_catalog_probe(monkeypatch):
    """Blank selection delegates to provider Auto even when an API client is present."""

    monkeypatch.setattr("shutil.which", lambda _binary: "/usr/bin/claude")
    client = FakeAnthropicClient("unused", catalog=("shape-a", "shape-z"))
    kit = _build_live_kit(_live_args(), anthropic_client=client)

    assert isinstance(kit["synthesizer"], ClaudeCliSynthesizer)
    assert isinstance(kit["promoter"], NoopPromoter)
    assert isinstance(kit["ranker"], LexicalRanker)
    assert client.catalog_calls == 0
    assert client.calls == []


@pytest.mark.parametrize(
    "catalog",
    [
        ("shape-live", "shape-old"),
        ("shape-old", "shape-live"),
        ("shape-new", "shape-live", "shape-old"),
    ],
)
def test_live_kit_accepts_exact_arbitrarily_renamed_api_override(catalog):
    """Catalog add/reorder does not change exact-ID validation or require code edits."""

    client = FakeAnthropicClient(
        '{"better_version": "the distilled one", "kept_ids": ["a"], "dropped_ids": ["b"]}',
        catalog=catalog,
    )
    kit = _build_live_kit(_live_args(model="shape-live"), anthropic_client=client)
    assert isinstance(kit["synthesizer"], AnthropicSynthesizer)
    assert kit["synthesizer"].model == "shape-live"
    result = converge("the goal", _shots(), threshold=0.0, **kit)
    assert result.better_version == "the distilled one"
    assert client.calls[0]["model"] == "shape-live"


def test_live_kit_rejects_removed_or_unverifiable_override_before_execution():
    for catalog in (("shape-other",), ()):
        client = FakeAnthropicClient("must not execute", catalog=catalog)
        with pytest.raises(RuntimeError, match="failed_blocked"):
            _build_live_kit(_live_args(model="shape-removed"), anthropic_client=client)
        assert client.calls == []


def test_anthropic_synthesizer_has_no_default_model():
    client = FakeAnthropicClient("unused", catalog=("shape-live",))
    with pytest.raises((TypeError, ValueError)):
        AnthropicSynthesizer(client=client)  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        AnthropicSynthesizer(model=" ", client=client)


# ─── Keyless claude-CLI synthesizer (the live-daemon path; no ANTHROPIC_API_KEY) ──


class _FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _shots():
    return [Shot(id="a", text="first draft", source="laneA"), Shot(id="b", text="weaker second", source="laneB")]


def test_claude_cli_synthesizer_parses_json(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    observed: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        observed.append(argv)
        return _FakeProc('{"better_version": "the one", "kept_ids": ["a"], "dropped_ids": ["b"]}')

    monkeypatch.setattr("subprocess.run", fake_run)
    syn = ClaudeCliSynthesizer()
    out = syn.synthesize("idea", _shots())
    assert out.better_version == "the one"
    assert out.kept_ids == ["a"] and out.dropped_ids == ["b"]
    assert observed and observed[0][:2] == ["/usr/bin/claude", "-p"]
    assert "--model" not in observed[0]
    assert "models" not in observed[0]
    assert "." not in observed[0]


def test_claude_cli_synthesizer_strips_code_fence(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    fenced = '```json\n{"better_version": "fenced", "kept_ids": [], "dropped_ids": []}\n```'
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _FakeProc(fenced))
    out = ClaudeCliSynthesizer().synthesize("idea", _shots())
    assert out.better_version == "fenced"


def test_claude_cli_synthesizer_non_json_keeps_top_shot(monkeypatch):
    """Non-JSON reply: the whole text is the distillate, top shot kept — never lose alchemy."""
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _FakeProc("a plain prose distillate"))
    out = ClaudeCliSynthesizer().synthesize("idea", _shots())
    assert out.better_version == "a plain prose distillate"
    assert out.kept_ids == ["a"] and out.dropped_ids == ["b"]


def test_claude_cli_synthesizer_raises_loud_on_failure(monkeypatch):
    """A CLI failure must raise (so the kit cascade / per-face guard falls through) —
    never a silent empty write masquerading as convergence."""
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _FakeProc("", returncode=1, stderr="boom"))
    with pytest.raises(RuntimeError):
        ClaudeCliSynthesizer().synthesize("idea", _shots())


def test_claude_cli_synthesizer_missing_binary_raises(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: None)
    with pytest.raises(FileNotFoundError):
        ClaudeCliSynthesizer()


def test_live_kit_uses_cli_auto_without_api_key(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    kit = _build_live_kit(_live_args())
    assert isinstance(kit["synthesizer"], ClaudeCliSynthesizer)


def test_live_kit_still_uses_provider_auto_when_api_key_is_present(monkeypatch):
    """Credential presence cannot silently change provider mechanism or spend."""

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    kit = _build_live_kit(_live_args())
    assert isinstance(kit["synthesizer"], ClaudeCliSynthesizer)


def test_cli_requires_a_mode():
    """Neither --dry-run nor --live is an error (no silent default)."""
    with pytest.raises(SystemExit):
        main(["--idea", "x", "--shot", "y"])


def test_cli_promote_requires_live():
    """--promote without --live is rejected (irreversible gate guarded)."""
    with pytest.raises(SystemExit):
        main(["--idea", "x", "--shot", "y", "--dry-run", "--promote"])


def test_cli_promote_requires_candidate_paths():
    """--promote without the CCE paths is rejected before any side effect."""
    with pytest.raises(SystemExit):
        main(["--idea", "x", "--shot", "y", "--live", "--promote"])


def test_cli_dry_run_still_works():
    """The pre-existing offline path is unchanged."""
    assert main(["--idea", "cats", "--shot", "cats are great", "--dry-run"]) == 0


def test_live_kit_without_cli_raises_so_preview_callers_can_fall_back(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: None)
    with pytest.raises(FileNotFoundError):
        _build_live_kit(_live_args())
