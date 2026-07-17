import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "fable-allotment.py"


def run_fable(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def base_accept_args(receipts_dir: Path, category: str = "governance", percent: str = "10"):
    return [
        "accept",
        "--category",
        category,
        "--percent",
        percent,
        "--slug",
        f"{category}-run",
        "--why",
        "bounded canonical synthesis",
        "--source",
        "docs/fable-allotment.md",
        "--verification",
        "python3 scripts/fable-allotment.py audit",
        "--receipts-dir",
        str(receipts_dir),
    ]


def with_slug(args: list[str], slug: str) -> list[str]:
    out = list(args)
    out[out.index("--slug") + 1] = slug
    return out


def receipt_data(category: str, percent: float) -> dict:
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).date().isoformat()
    return {
        "schema": "limen.fable_acceptance.v1",
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "week": monday,
        "category": category,
        "percent": percent,
        "slug": f"{category}-{percent}",
        "why": "test",
        "sources": ["docs/fable-allotment.md"],
        "redacted_packets": [],
        "verification": ["python3 scripts/fable-allotment.py audit"],
        "reserve_unlocked": category == "reserve",
        "mode": "plan-only",
        "deliverable": "continuation-capsule",
        "builder_handoff": {
            "provider_selection": "auto",
            "requirements": {
                "planning_only": False,
                "build_allowed": True,
                "fable_allowed": False,
            },
        },
        "motion_receipt_deadline_seconds": 5400,
    }


def test_accept_writes_unsigned_owner_proposal_not_runtime_authority(tmp_path):
    receipts_dir = tmp_path / "receipts"
    proc = run_fable(*base_accept_args(receipts_dir))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    receipt = Path(payload["receipt"])
    assert receipt.exists()
    data = json.loads(receipt.read_text())
    assert data["category"] == "governance"
    assert data["percent"] == 10
    assert data["mode"] == "plan-only"
    assert data["deliverable"] == "continuation-capsule"
    assert data["builder_handoff"]["provider_selection"] == "auto"
    assert data["builder_handoff"]["requirements"]["fable_allowed"] is False
    assert "model" not in json.dumps(data["builder_handoff"])
    assert "tier" not in json.dumps(data["builder_handoff"])
    assert receipt.stat().st_mode & 0o077 == 0
    assert payload["authorized"] is False
    assert payload["authority_status"] == "unsigned-proposal"
    assert "export LIMEN_FABLE_ACCEPTANCE=" not in proc.stdout


def test_category_cap_and_reserve_lock_are_enforced(tmp_path):
    receipts_dir = tmp_path / "receipts"
    over = run_fable(*base_accept_args(receipts_dir, category="governance", percent="11"))
    assert over.returncode == 2
    assert "above category cap" in over.stderr

    reserve = run_fable(*base_accept_args(receipts_dir, category="reserve", percent="5"))
    assert reserve.returncode == 2
    assert "reserve spend requires --reserve-unlock" in reserve.stderr


def test_weekly_category_cap_is_cumulative(tmp_path):
    receipts_dir = tmp_path / "receipts"
    first = run_fable(*with_slug(base_accept_args(receipts_dir, category="governance", percent="6"), "g1"))
    assert first.returncode == 0, first.stderr
    second = run_fable(*with_slug(base_accept_args(receipts_dir, category="governance", percent="5"), "g2"))
    assert second.returncode == 2
    assert "governance weekly spend would be 11%" in second.stderr

    # Audit also catches an already-bad receipt directory, not just future accept commands.
    bad_dir = tmp_path / "bad-receipts"
    bad_dir.mkdir()
    (bad_dir / "a.json").write_text(json.dumps(receipt_data("adversarial-review", 3)))
    (bad_dir / "b.json").write_text(json.dumps(receipt_data("adversarial-review", 3)))
    audit = run_fable("audit", "--receipts-dir", str(bad_dir))
    assert audit.returncode == 2
    assert "adversarial-review spend 6% exceeds category cap 5%" in audit.stdout


def test_audit_fails_when_deliberate_cap_is_exceeded(tmp_path):
    receipts_dir = tmp_path / "receipts"
    for category, percent in (
        ("substrate", "15"),
        ("prompt-corpus", "10"),
        ("governance", "10"),
        ("adversarial-review", "5"),
    ):
        proc = run_fable(*base_accept_args(receipts_dir, category=category, percent=percent))
        assert proc.returncode == 0, proc.stderr

    extra = run_fable(*base_accept_args(receipts_dir, category="governance", percent="1"))
    assert extra.returncode == 2
    assert "governance weekly spend would be 11%" in extra.stderr

    audit = run_fable("audit", "--receipts-dir", str(receipts_dir))
    assert audit.returncode == 0, audit.stderr
    report = json.loads(audit.stdout)
    assert report["deliberate_percent"] == 40
    assert report["total_percent"] == 40


def _this_monday() -> str:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).date().isoformat()


def test_balance_writes_current_week_report(tmp_path):
    """`balance` writes logs/fable-allotment.json with the cap fields for the current ISO-week."""
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    empty_transcripts = tmp_path / "no-transcripts"
    empty_transcripts.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "balance"],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(root),
            "LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR": str(empty_transcripts),
            "LIMEN_FABLE_WEEKLY_TOKENS": "1000000",
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["week"] == _this_monday()
    assert out["schema"] == "limen.fable_balance.v1"
    assert out["meter_ready"] is True
    assert out["observed_at"]
    assert out["measurement"] == {
        "method": "token-ratio",
        "numerator_tokens": 0,
        "denominator_tokens": 1000000,
        "unbound_usage_rows": 0,
        "role_binding": "execution_role:fable-planner",
    }
    assert out["deliberate_cap"] == 40 and out["hard_cap"] == 50
    assert out["spent_tokens"] == 0 and out["spent_pct"] == 0.0
    assert out["over_cap"] is False
    written = json.loads((root / "logs" / "fable-allotment.json").read_text())
    assert written == out


def test_balance_is_idempotent(tmp_path):
    """Re-running balance on the same inputs produces an identical file (fixed point)."""
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    empty = tmp_path / "t"
    empty.mkdir()
    env = {
        "LIMEN_ROOT": str(root),
        "LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR": str(empty),
        "LIMEN_FABLE_WEEKLY_TOKENS": "1000000",
        "PATH": __import__("os").environ.get("PATH", ""),
    }
    subprocess.run([sys.executable, str(SCRIPT), "balance"], capture_output=True, text=True, env=env)
    first = (root / "logs" / "fable-allotment.json").read_text()
    subprocess.run([sys.executable, str(SCRIPT), "balance"], capture_output=True, text=True, env=env)
    assert (root / "logs" / "fable-allotment.json").read_text() == first


def test_balance_without_owner_denominator_is_explicitly_dark(tmp_path):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "balance", "--no-write"],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(root),
            "LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR": str(transcripts),
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["meter_ready"] is False
    assert out["spent_pct"] is None
    assert out["over_cap"] is None
    assert out["measurement"] == {
        "method": "token-ratio",
        "numerator_tokens": 0,
        "denominator_tokens": None,
        "unbound_usage_rows": 0,
        "role_binding": "execution_role:fable-planner",
    }


def test_transcript_balance_fails_dark_on_unbound_provider_model_rows(tmp_path):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    (transcripts / "session.jsonl").write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": {
                    "model": "arbitrarily-renamed-provider-id",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        )
        + "\n"
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "balance", "--no-write"],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(root),
            "LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR": str(transcripts),
            "LIMEN_FABLE_WEEKLY_TOKENS": "1000000",
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["meter_ready"] is False
    assert out["spent_pct"] is None
    assert out["measurement"]["unbound_usage_rows"] == 1


def test_transcript_balance_uses_explicit_role_not_provider_model_name(tmp_path):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    (transcripts / "session.jsonl").write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "execution_role": "fable-planner",
                "message": {
                    "model": "arbitrarily-renamed-provider-id",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        )
        + "\n"
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "balance", "--no-write"],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(root),
            "LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR": str(transcripts),
            "LIMEN_FABLE_WEEKLY_TOKENS": "100",
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["meter_ready"] is True
    assert out["spent_tokens"] == 15
    assert out["spent_pct"] == 15.0
    assert out["measurement"]["unbound_usage_rows"] == 0


def test_fresh_owner_used_percent_meter_needs_no_provider_model_catalog(tmp_path):
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    meter = tmp_path / "usage-meter.json"
    meter.write_text(
        json.dumps(
            {
                "schema": "limen.fable_usage_meter.v1",
                "execution_role": "fable-planner",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "week": _this_monday(),
                "meter_ready": True,
                "weekly_used_percent": 12.5,
            }
        )
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "balance", "--no-write"],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(root),
            "LIMEN_FABLE_USAGE_METER_PATH": str(meter),
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["meter_ready"] is True
    assert out["source"] == "owner-used-percent"
    assert out["spent_pct"] == 12.5
    assert out["measurement"] == {
        "method": "owner-used-percent",
        "owner_observed_pct": 12.5,
    }
