"""Honest-work gate: dispatch/route must skip lanes the LIVE usage meter says are dead.

Regression guard for the 2026-06-19 bug where codex burned its 5h token budget (usage.json
health="exhausted") yet the dispatcher kept assigning to it because _down_lanes() only read a
static hand-maintained file. The fix derives the down-set from logs/usage.json (self-healing)."""

import json

import pytest


from limen.dispatch import _creds_lanes_down, _down_lanes, _usage_dead_lanes


@pytest.fixture(autouse=True)
def disable_oauth_preflight(monkeypatch):
    monkeypatch.setenv("LIMEN_OAUTH_PREFLIGHT", "0")


@pytest.fixture(autouse=True)
def set_claude_fleet_token(monkeypatch):
    """Existing tests don't care about claude creds; set a dummy token so _creds_lanes_down
    doesn't mark claude as down and break those assertions. Tests that DO test the creds gate
    override this via monkeypatch.delenv."""
    monkeypatch.setenv("LIMEN_CLAUDE_AUTH_TOKEN", "test-fleet-token")


def _write_usage(root, vendors):
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "usage.json").write_text(json.dumps({"generated": "t", "vendors": vendors}))


def test_usage_dead_lanes_flags_exhausted_ratelimited_and_reserve(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(
        tmp_path,
        {
            "codex": {"health": "exhausted"},
            "gemini": {"health": "rate-limited"},
            "jules": {"health": "low"},  # at/below reserve -> STOP before 0 (paced-out)
            "opencode": {"health": "throttle"},  # still has runway -> stays UP (steer signal only)
            "claude": {"health": "ok"},
        },
    )
    assert _usage_dead_lanes() == {"codex", "gemini", "jules"}


def test_throttle_lane_stays_up(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(tmp_path, {"codex": {"health": "throttle"}, "claude": {"health": "ok"}})
    assert _usage_dead_lanes() == set()
    assert _down_lanes() == set()


def test_down_lanes_unions_manual_file_and_live_meter(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(tmp_path, {"codex": {"health": "exhausted"}})
    (tmp_path / "logs" / "lanes-down.txt").write_text("agy  # bin missing\n# a comment line\n\n")
    assert _down_lanes() == {"codex", "agy"}


def test_reserve_low_lane_is_down_ok_stays_up(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(tmp_path, {"codex": {"health": "ok"}, "claude": {"health": "low"}})
    assert _down_lanes() == {"claude"}


def test_missing_usage_json_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    assert _usage_dead_lanes() == set()
    assert _down_lanes() == set()


def test_creds_lanes_down_gates_claude_without_auth_tokens(monkeypatch):
    """claude is in _creds_lanes_down when neither fleet token nor API key is set."""
    for key in ("LIMEN_CLAUDE_AUTH_TOKEN", "LIMEN_CLAUDE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert "claude" in _creds_lanes_down()


def test_creds_lanes_down_skips_claude_when_fleet_token_set(monkeypatch):
    monkeypatch.setenv("LIMEN_CLAUDE_AUTH_TOKEN", "sk-abc123")
    monkeypatch.delenv("LIMEN_CLAUDE_API_KEY", raising=False)
    assert "claude" not in _creds_lanes_down()


def test_creds_lanes_down_skips_claude_when_api_key_set(monkeypatch):
    monkeypatch.delenv("LIMEN_CLAUDE_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("LIMEN_CLAUDE_API_KEY", "sk-ant-xyz789")
    assert "claude" not in _creds_lanes_down()


def test_down_lanes_includes_claude_when_auth_missing(tmp_path, monkeypatch):
    """Integration: _down_lanes includes claude when credentials AND usage are quiet."""
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    for key in ("LIMEN_CLAUDE_AUTH_TOKEN", "LIMEN_CLAUDE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / "logs").mkdir(parents=True)
    (tmp_path / "usage.json").write_text('{"vendors": {}}')
    assert "claude" in _down_lanes()
