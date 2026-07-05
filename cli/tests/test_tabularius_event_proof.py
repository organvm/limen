from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-tabularius-event-proof.py"


def run_checker(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        text=True,
        capture_output=True,
        check=False,
    )


def write_state(path: Path, **overrides: object) -> None:
    payload: dict[str, object] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "event_log_verified": True,
        "event_log_cache_verified": True,
        "event_log_streak": 3,
        "event_log_events": 12,
        "event_log_archive_tickets": 2,
        "event_log_archive_replay_tickets": 0,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2))


def test_tabularius_event_proof_passes_with_fresh_required_streak(tmp_path: Path) -> None:
    state = tmp_path / "tabularius-organ-state.json"
    write_state(state, event_log_streak=4)

    result = run_checker("--state", state, "--min-streak", "3")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "tabularius-event-proof: pass streak=4/3" in result.stdout


def test_tabularius_event_proof_blocks_missing_state(tmp_path: Path) -> None:
    state = tmp_path / "missing.json"

    result = run_checker("--state", state)

    assert result.returncode == 1
    assert "event proof state missing" in result.stderr


def test_tabularius_event_proof_blocks_low_streak_and_false_cache(tmp_path: Path) -> None:
    state = tmp_path / "tabularius-organ-state.json"
    write_state(state, event_log_cache_verified=False, event_log_streak=1)

    result = run_checker("--state", state, "--min-streak", "3")

    assert result.returncode == 1
    assert "event_log_cache_verified is not true" in result.stderr
    assert "event_log_streak 1 is below required 3" in result.stderr


def test_tabularius_event_proof_blocks_stale_state(tmp_path: Path) -> None:
    state = tmp_path / "tabularius-organ-state.json"
    stale = datetime.now(timezone.utc) - timedelta(minutes=90)
    write_state(state, updated=stale.isoformat())

    result = run_checker("--state", state, "--max-age-minutes", "30")

    assert result.returncode == 1
    assert "event proof state is stale" in result.stderr


def test_tabularius_event_proof_json_output(tmp_path: Path) -> None:
    state = tmp_path / "tabularius-organ-state.json"
    write_state(state, event_log_streak=5)

    result = run_checker("--state", state, "--json-output")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["streak"] == 5
