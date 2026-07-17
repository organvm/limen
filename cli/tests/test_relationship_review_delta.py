from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "relationship-review-delta.py"


def _load():
    spec = importlib.util.spec_from_file_location("relationship_review_delta_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _private_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o600)


def _wal_database(tmp_path: Path) -> tuple[Path, sqlite3.Connection]:
    db = tmp_path / "messages source" / "chat.db"
    db.parent.mkdir(parents=True)
    writer = sqlite3.connect(db)
    assert writer.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
    writer.execute("PRAGMA wal_autocheckpoint = 0")
    writer.execute("CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT NOT NULL)")
    writer.execute(
        "CREATE TABLE message (ROWID INTEGER PRIMARY KEY, handle_id INTEGER, is_from_me INTEGER, date INTEGER)"
    )
    writer.commit()
    assert writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)
    writer.execute("INSERT INTO handle(ROWID, id) VALUES (1, 'private-handle-17')")
    writer.execute("INSERT INTO message(handle_id, is_from_me, date) VALUES (1, 0, 1)")
    writer.commit()
    assert db.with_name("chat.db-wal").stat().st_size > 0
    return db, writer


def _immutable_database(tmp_path: Path) -> Path:
    db = tmp_path / "messages.snapshot.sqlite"
    with sqlite3.connect(db) as writer:
        writer.execute("CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT NOT NULL)")
        writer.execute(
            "CREATE TABLE message (ROWID INTEGER PRIMARY KEY, handle_id INTEGER, is_from_me INTEGER, date INTEGER)"
        )
        writer.execute("INSERT INTO handle(ROWID, id) VALUES (1, 'private-handle-17')")
        writer.execute("INSERT INTO message(handle_id, is_from_me, date) VALUES (1, 0, 1)")
        writer.commit()
    db.chmod(0o600)
    return db


def _snapshot(paths: list[Path]) -> dict[str, tuple[bytes, int, int, int]]:
    return {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_size, path.stat().st_mode)
        for path in paths
        if path.exists()
    }


def _database_files(db: Path) -> list[Path]:
    return sorted(db.parent.glob(f"{db.name}*"))


def _bundle_snapshot(root: Path) -> tuple[tuple[str, ...], dict[str, tuple[bytes, int, int, int]]]:
    paths = tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))
    files = {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            path.stat().st_size,
            path.stat().st_mode,
        )
        for path in root.rglob("*")
        if path.is_file()
    }
    return paths, files


def _owner_handoff(
    mod,
    root: Path,
    *,
    now: datetime | None = None,
    snapshot_uri_scheme: str = "https",
    snapshot_host: str = "private-owner.invalid",
) -> tuple[Path, Path, Path, Path]:
    now = now or datetime.now(timezone.utc)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    messages = _immutable_database(root)
    adapter = root / "review-adapter.json"
    _private_write(
        adapter,
        json.dumps(
            {
                "schema": mod.ADAPTER_SCHEMA,
                "people": [
                    {
                        "slug": "private-slug-17",
                        "handles": ["private-handle-17"],
                        "last_review": "2001-01-01T00:00:00+00:00",
                    }
                ],
            }
        ).encode(),
    )
    artifacts = {
        "adapter": {
            "path": adapter.name,
            "bytes": adapter.stat().st_size,
            "sha256": mod._sha256_file(adapter),
        },
        "messages": {
            "path": messages.name,
            "bytes": messages.stat().st_size,
            "sha256": mod._sha256_file(messages),
        },
    }
    snapshot_id = mod._snapshot_id(artifacts)
    snapshot_uri = f"{snapshot_uri_scheme}://{snapshot_host}/snapshots/{snapshot_id}"
    receipt_uri = f"https://{snapshot_host}/receipts/{snapshot_id}.json"
    receipt = {
        "schema": mod.SNAPSHOT_SCHEMA,
        "snapshot_id": snapshot_id,
        "produced_at": (now - timedelta(minutes=10)).isoformat(),
        "expires_at": (now + timedelta(days=1)).isoformat(),
        "custody": {
            "immutable_ref": snapshot_id,
            "snapshot_uri": snapshot_uri,
            "receipt_uri": receipt_uri,
        },
        "artifacts": artifacts,
    }
    receipt_path = root / "snapshot-receipt.json"
    receipt_payload = json.dumps(receipt, sort_keys=True).encode()
    _private_write(receipt_path, receipt_payload)
    handoff = {
        "schema": mod.HANDOFF_SCHEMA,
        "snapshot_id": snapshot_id,
        "custody_verification": "verified",
        "custody_verified_at": (now - timedelta(minutes=7)).isoformat(),
        "hydrated_at": (now - timedelta(minutes=5)).isoformat(),
        "source_snapshot_uri": snapshot_uri,
        "source_receipt_uri": receipt_uri,
        "snapshot_receipt": {
            "path": receipt_path.name,
            "sha256": mod._sha256_bytes(receipt_payload),
        },
    }
    handoff_path = root / "handoff.json"
    _private_write(handoff_path, json.dumps(handoff, sort_keys=True).encode())
    return handoff_path, receipt_path, adapter, messages


def test_live_wal_database_is_refused_without_touching_sqlite_files(tmp_path: Path) -> None:
    mod = _load()
    db, writer = _wal_database(tmp_path)
    try:
        before_names = tuple(path.name for path in _database_files(db))
        before = _snapshot(_database_files(db))

        with pytest.raises(sqlite3.OperationalError, match="mutable SQLite companions"):
            mod._count_new_inbound(db, ["private-handle-17"], 0)

        assert tuple(path.name for path in _database_files(db)) == before_names
        assert _snapshot(_database_files(db)) == before
    finally:
        writer.close()


def test_immutable_snapshot_reads_current_payload_and_creates_no_sqlite_files(tmp_path: Path) -> None:
    mod = _load()
    db = _immutable_database(tmp_path)
    before_names = tuple(path.name for path in _database_files(db))
    before = _snapshot(_database_files(db))

    assert mod._count_new_inbound(db, ["private-handle-17"], 0) == 1
    connection = mod._open_chat_db(db)
    try:
        assert connection.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE forbidden_write(value TEXT)")
    finally:
        connection.close()

    assert tuple(path.name for path in _database_files(db)) == before_names
    assert _snapshot(_database_files(db)) == before


def test_owner_handoff_works_without_any_checkout_and_observation_is_zero_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    handoff, _receipt, _adapter, _messages = _owner_handoff(mod, tmp_path / "private handoff")
    monkeypatch.setattr(mod, "THRESHOLD", 1)

    assert not (tmp_path / "Workspace" / "4444J99" / "relationship-pipeline").exists()
    assert not (tmp_path / "Workspace" / "_people-private").exists()
    before = _bundle_snapshot(handoff.parent)
    assert mod.main(["--json", "--handoff", str(handoff)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output) == {"available": True, "checked": 1, "review_due": 1, "threshold": 1}
    assert "private-slug-17" not in output
    assert "private-handle-17" not in output
    assert _bundle_snapshot(handoff.parent) == before


def test_environment_injects_the_same_owner_handoff_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    handoff, *_ = _owner_handoff(mod, tmp_path / "private handoff")
    monkeypatch.setenv("LIMEN_RELATIONSHIP_REVIEW_HANDOFF", str(handoff))

    assert mod.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is True


def test_missing_handoff_reports_unknown_coverage_not_zero_due(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    assert mod.main(["--json", "--handoff", str(tmp_path / "absent.json")]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "available": False,
        "checked": 0,
        "review_due": None,
        "threshold": mod.THRESHOLD,
        "reason": "snapshot_unavailable",
    }


def test_stale_snapshot_receipt_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    stale_now = datetime.now(timezone.utc) - timedelta(days=20)
    handoff, *_ = _owner_handoff(mod, tmp_path / "private handoff", now=stale_now)

    assert mod.main(["--json", "--handoff", str(handoff)]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is False


def test_local_only_custody_claim_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    handoff, *_ = _owner_handoff(mod, tmp_path / "private handoff", snapshot_uri_scheme="file")

    assert mod.main(["--json", "--handoff", str(handoff)]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is False

    loopback_handoff, *_ = _owner_handoff(
        mod,
        tmp_path / "loopback handoff",
        snapshot_host="localhost",
    )
    assert mod.main(["--json", "--handoff", str(loopback_handoff)]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is False


def test_tampered_artifact_is_refused_without_leaking_private_values(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    handoff, _receipt, adapter, _messages = _owner_handoff(mod, tmp_path / "private handoff")
    _private_write(
        adapter,
        json.dumps(
            {
                "schema": mod.ADAPTER_SCHEMA,
                "people": [
                    {
                        "slug": "private-tampered-slug",
                        "handles": ["private-tampered-handle"],
                        "last_review": "2001-01-01T00:00:00+00:00",
                    }
                ],
            }
        ).encode(),
    )

    assert mod.main(["--json", "--handoff", str(handoff)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["available"] is False
    assert "private-tampered-slug" not in output
    assert "private-tampered-handle" not in output


def test_sqlite_companion_appearing_during_observation_suppresses_the_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    handoff, _receipt, _adapter, messages = _owner_handoff(mod, tmp_path / "private handoff")
    real_count = mod._count_new_inbound

    def race_count(chat_db: Path, handles: list[str], since_ns: int) -> int:
        result = real_count(chat_db, handles, since_ns)
        messages.with_name(f"{messages.name}-wal").write_bytes(b"appeared after open")
        return result

    monkeypatch.setattr(mod, "_count_new_inbound", race_count)
    assert mod.main(["--json", "--handoff", str(handoff)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["available"] is False
    assert output["review_due"] is None


def test_world_readable_or_symlinked_private_handoff_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    handoff, *_ = _owner_handoff(mod, tmp_path / "private handoff")
    handoff.chmod(0o644)
    assert mod.main(["--json", "--handoff", str(handoff)]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is False

    handoff.chmod(0o600)
    alias = tmp_path / "handoff-alias.json"
    alias.symlink_to(handoff)
    assert mod.main(["--json", "--handoff", str(alias)]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is False


def test_invalid_threshold_fails_cleanly_before_private_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = _load()
    handoff, *_ = _owner_handoff(mod, tmp_path / "private handoff")
    monkeypatch.setenv("LIMEN_RELATIONSHIP_REVIEW_THRESHOLD", "not-a-number")

    assert mod.main(["--json", "--handoff", str(handoff)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "available": False,
        "checked": 0,
        "review_due": None,
        "threshold": None,
        "reason": "internal_valueerror",
    }


def test_raw_registry_adapter_and_chat_paths_are_not_a_supported_bypass() -> None:
    mod = _load()
    for flag in ("--registry", "--adapter", "--chat-db", "--notify"):
        with pytest.raises(SystemExit) as exc:
            mod.main([flag, "/tmp/forbidden"] if flag != "--notify" else [flag])
        assert exc.value.code == 2

    sensor_registry = (ROOT / "institutio/governance/sensors.yaml").read_text(encoding="utf-8")
    assert "LIMEN_RELATIONSHIP_REVIEW_NOTIFY" not in sensor_registry
    assert "relationship-review-delta.py --notify" not in sensor_registry
