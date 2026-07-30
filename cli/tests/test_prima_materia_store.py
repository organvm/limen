from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import rfc8785
from limen.prima_materia import SourceAdapterV1
from limen.prima_materia_store import (
    DualStoreCustodyExecutor,
    EncryptedObjectStore,
    PrimaMateriaStoreError,
    SourceRegistry,
    load_key,
)

DIGEST = "a" * 64


def _adapter(adapter_id: str, source_id: str) -> SourceAdapterV1:
    return SourceAdapterV1(
        adapter_id=adapter_id,
        source_id=source_id,
        owner_ref=f"owner:{adapter_id}",
        source_native_acquisition="source-owned cursor stream",
        cursor_schema_digest=DIGEST,
        completeness_predicate="cursor exhausted",
        privacy_transform_digest=DIGEST,
        claim_recipe=f"claim-recipe-{source_id}",
        recipe_version="recipe-v1",
        custody_target_refs=("archive", "recovery"),
        restoration_predicate="both copies restore",
    )


def test_store_encrypts_before_disk_and_restores_idempotently(tmp_path: Path) -> None:
    plaintext = b"private prima materia payload that must never be staged"
    store = EncryptedObjectStore(tmp_path / "store", b"k" * 32, chunk_bytes=64 * 1024)

    first = store.put(plaintext)
    second = store.put(plaintext)

    assert second == first
    assert store.restore(first) == plaintext
    stored = [path.read_bytes() for path in (tmp_path / "store").rglob("*") if path.is_file()]
    assert stored
    assert all(plaintext not in payload for payload in stored)
    assert first.object_id not in plaintext.decode()


def test_store_tamper_and_interrupted_staging_fail_safe(tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    interrupted = store_root / ".staging" / "interrupted"
    interrupted.mkdir(parents=True)
    store_root.chmod(0o700)
    store = EncryptedObjectStore(store_root, b"z" * 32, chunk_bytes=64 * 1024)
    ref = store.put(b"payload")

    assert interrupted.exists()
    chunk = next((store_root / "objects" / ref.object_id).glob("*.bin"))
    payload = bytearray(chunk.read_bytes())
    payload[-1] ^= 1
    chunk.write_bytes(bytes(payload))

    with pytest.raises(PrimaMateriaStoreError, match="ciphertext-chunk-drift"):
        store.restore(ref)


def test_store_rejects_rehashed_but_unauthenticated_ciphertext(
    tmp_path: Path,
) -> None:
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"a" * 32,
        chunk_bytes=64 * 1024,
    )
    ref = store.put(b"authenticated payload")
    object_root = store.root / "objects" / ref.object_id
    manifest_path = object_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_chunk = next(object_root.glob("*.bin"))
    ciphertext = bytearray(old_chunk.read_bytes())
    ciphertext[0] ^= 1
    ciphertext_bytes = bytes(ciphertext)
    new_digest = hashlib.sha256(ciphertext_bytes).hexdigest()
    new_chunk = object_root / f"00000000-{new_digest}.bin"
    new_chunk.write_bytes(ciphertext_bytes)
    old_chunk.unlink()
    manifest["chunks"][0]["ciphertext_sha256"] = new_digest
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    forged_ref = ref.model_copy(
        update={
            "ciphertext_sha256": new_digest,
            "chunk_manifest_digest": hashlib.sha256(rfc8785.dumps(manifest)).hexdigest(),
        }
    )

    with pytest.raises(
        PrimaMateriaStoreError,
        match="ciphertext-authentication-failed",
    ):
        store.restore(forged_ref)


def test_put_path_streams_large_file_and_restores_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    plaintext = (b"streaming-prima-materia-" * 70_000) + b"tail"
    source.write_bytes(plaintext)
    source.chmod(0o640)
    source_mtime_ns = 1_700_000_000_123_456_789
    os.utime(source, ns=(source_mtime_ns, source_mtime_ns))
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"p" * 32,
        chunk_bytes=64 * 1024,
    )

    result = store.put_path(source)
    destination = tmp_path / "restored.bin"
    restored = store.restore_to_path(
        result.payload_ref,
        destination,
        custody_target_ref="custodyTargetStreaming1",
        device_id="physicalDeviceStreaming1",
    )

    assert result.chunk_count > 10
    assert result.resource_claim.memory_bytes < len(plaintext)
    assert restored.restored_output_sha256 == hashlib.sha256(plaintext).hexdigest()
    assert destination.read_bytes() == plaintext
    assert destination.stat().st_mtime_ns == source_mtime_ns
    assert destination.stat().st_mode & 0o777 == 0o640
    stored_payloads = [path.read_bytes() for path in store.root.rglob("*") if path.is_file()]
    assert stored_payloads
    assert all(plaintext not in payload for payload in stored_payloads)


def test_put_path_resumes_authenticated_chunks_after_interruption(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"resume-me-" * 40_000)
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"r" * 32,
        chunk_bytes=64 * 1024,
    )

    with pytest.raises(PrimaMateriaStoreError, match="simulated-interruption"):
        store.put_path(source, interrupt_after_chunks=2)

    staging = next((store.root / ".staging").iterdir())
    if staging.suffix == ".lock":
        staging = next(path for path in (store.root / ".staging").iterdir() if path.is_dir())
    assert len(list(staging.glob("*.bin"))) == 2

    result = store.put_path(source)
    destination = tmp_path / "restored.bin"
    store.restore_to_path(
        result.payload_ref,
        destination,
        custody_target_ref="custodyTargetResume1",
        device_id="physicalDeviceResume1",
    )

    assert result.resumed_chunk_count == 2
    assert destination.read_bytes() == source.read_bytes()
    assert not staging.exists()


def test_put_path_rejects_tampered_resume_state(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"tamper-resume-" * 20_000)
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"q" * 32,
        chunk_bytes=64 * 1024,
    )
    with pytest.raises(PrimaMateriaStoreError, match="simulated-interruption"):
        store.put_path(source, interrupt_after_chunks=1)
    staging = next(path for path in (store.root / ".staging").iterdir() if path.is_dir())
    resume = staging / "resume.json"
    payload = json.loads(resume.read_text(encoding="utf-8"))
    payload["plaintext_bytes"] += 1
    resume.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        PrimaMateriaStoreError,
        match="resume-state-authentication-failed",
    ):
        store.put_path(source)


def test_put_path_rejects_source_drift_between_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"a" * (128 * 1024))
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"d" * 32,
        chunk_bytes=64 * 1024,
    )
    original = store._source_digest

    def digest_then_drift(candidate: Path) -> tuple[bytes, dict[str, object]]:
        digest, identity = original(candidate)
        candidate.write_bytes(b"b" * (128 * 1024))
        return digest, identity

    monkeypatch.setattr(store, "_source_digest", digest_then_drift)

    with pytest.raises(PrimaMateriaStoreError, match="source-identity-drift"):
        store.put_path(source)
    assert not (store.root / "objects").exists()


def test_put_path_and_restore_reject_alias_and_existing_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    alias = tmp_path / "alias.bin"
    alias.symlink_to(source)
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"l" * 32,
        chunk_bytes=64 * 1024,
    )

    with pytest.raises(PrimaMateriaStoreError, match="source-symlink-rejected"):
        store.put_path(alias)

    result = store.put_path(source)
    destination = tmp_path / "destination.bin"
    destination.write_bytes(b"preserve")
    with pytest.raises(PrimaMateriaStoreError, match="restore-destination-exists"):
        store.restore_to_path(
            result.payload_ref,
            destination,
            custody_target_ref="custodyTargetExisting1",
            device_id="physicalDeviceExisting1",
        )
    assert destination.read_bytes() == b"preserve"


def test_restore_to_path_removes_partial_output_after_ciphertext_tamper(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"authenticated-stream-" * 10_000)
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"t" * 32,
        chunk_bytes=64 * 1024,
    )
    result = store.put_path(source)
    chunk = next((store.root / "objects" / result.payload_ref.object_id).glob("*.bin"))
    ciphertext = bytearray(chunk.read_bytes())
    ciphertext[-1] ^= 1
    chunk.write_bytes(ciphertext)
    destination = tmp_path / "destination.bin"

    with pytest.raises(PrimaMateriaStoreError, match="ciphertext-chunk-drift"):
        store.restore_to_path(
            result.payload_ref,
            destination,
            custody_target_ref="custodyTargetTamper1",
            device_id="physicalDeviceTamper1",
        )
    assert not destination.exists()
    assert not list(tmp_path.glob(".*.restore"))


def test_dual_store_rejects_same_physical_parent_before_writes(
    tmp_path: Path,
) -> None:
    first = EncryptedObjectStore(
        tmp_path / "first",
        b"c" * 32,
        chunk_bytes=64 * 1024,
    )
    second = EncryptedObjectStore(
        tmp_path / "second",
        b"c" * 32,
        chunk_bytes=64 * 1024,
    )
    source = tmp_path / "source.bin"
    source.write_bytes(b"must-not-write")
    executor = DualStoreCustodyExecutor(
        first,
        second,
        physical_parent_resolver=lambda _root: "physicalDeviceShared1",
    )

    with pytest.raises(
        PrimaMateriaStoreError,
        match="custody-same-physical-parent",
    ):
        executor.custody_path(
            source,
            first_restore_destination=tmp_path / "restore-first",
            second_restore_destination=tmp_path / "restore-second",
        )
    assert not (first.root / "objects").exists()
    assert not (second.root / "objects").exists()


def test_dual_store_proves_independent_copies_and_restores(
    tmp_path: Path,
) -> None:
    first = EncryptedObjectStore(
        tmp_path / "first",
        b"c" * 32,
        chunk_bytes=64 * 1024,
    )
    second = EncryptedObjectStore(
        tmp_path / "second",
        b"c" * 32,
        chunk_bytes=64 * 1024,
    )
    source = tmp_path / "source.bin"
    source.write_bytes(b"dual-restore-" * 30_000)
    source.chmod(0o600)
    identities = {
        first.root: "physicalDeviceArchive4T1",
        second.root: "physicalDeviceT7Recovery1",
    }
    executor = DualStoreCustodyExecutor(
        first,
        second,
        physical_parent_resolver=identities.__getitem__,
    )
    first_restore = tmp_path / "restore-first"
    second_restore = tmp_path / "restore-second"

    result = executor.custody_path(
        source,
        first_restore_destination=first_restore,
        second_restore_destination=second_restore,
    )

    assert first_restore.read_bytes() == source.read_bytes()
    assert second_restore.read_bytes() == source.read_bytes()
    assert result.custody_receipt.independent_device_ids == tuple(identities.values())
    assert {proof.device_id for proof in result.custody_receipt.restoration_proofs} == set(identities.values())
    assert len(result.custody_receipt.restoration_proofs) == 2
    assert all(proof.passed for proof in result.custody_receipt.restoration_proofs)


def test_dual_store_rejects_physical_parent_drift_before_restore(
    tmp_path: Path,
) -> None:
    first = EncryptedObjectStore(
        tmp_path / "first",
        b"c" * 32,
        chunk_bytes=64 * 1024,
    )
    second = EncryptedObjectStore(
        tmp_path / "second",
        b"c" * 32,
        chunk_bytes=64 * 1024,
    )
    source = tmp_path / "source.bin"
    source.write_bytes(b"parent-drift")
    calls: dict[Path, int] = {}

    def resolver(root: Path) -> str:
        calls[root] = calls.get(root, 0) + 1
        if root == second.root and calls[root] > 1:
            return "physicalDeviceUnexpected1"
        if root == first.root:
            return "physicalDeviceArchive4T1"
        return "physicalDeviceT7Recovery1"

    executor = DualStoreCustodyExecutor(
        first,
        second,
        physical_parent_resolver=resolver,
    )
    first_restore = tmp_path / "restore-first"
    second_restore = tmp_path / "restore-second"

    with pytest.raises(
        PrimaMateriaStoreError,
        match="custody-physical-parent-drift",
    ):
        executor.custody_path(
            source,
            first_restore_destination=first_restore,
            second_restore_destination=second_restore,
        )
    assert not first_restore.exists()
    assert not second_restore.exists()


def test_put_path_restores_empty_file(tmp_path: Path) -> None:
    source = tmp_path / "empty.bin"
    source.touch(mode=0o600)
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"e" * 32,
        chunk_bytes=64 * 1024,
    )

    result = store.put_path(source)
    destination = tmp_path / "restored-empty.bin"
    store.restore_to_path(
        result.payload_ref,
        destination,
        custody_target_ref="custodyTargetEmpty1",
        device_id="physicalDeviceEmpty1",
    )

    assert result.chunk_count == 1
    assert result.plaintext_bytes == 0
    assert destination.read_bytes() == b""


def test_key_file_must_be_private_and_256_bit(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_bytes(b"k" * 32)
    key.chmod(0o644)

    with pytest.raises(PrimaMateriaStoreError, match="key-file-not-private"):
        load_key(key)

    key.chmod(0o600)
    assert load_key(key) == b"k" * 32


def test_dynamic_source_registry_is_order_independent_and_keeps_unknown_debt() -> None:
    first = _adapter("adapter-z", "sourceIdentifierB2")
    second = _adapter("adapter-a", "sourceIdentifierA1")
    missing = "sourceIdentifierC3"

    left = SourceRegistry.from_adapters((first, second))
    right = SourceRegistry.from_adapters((second, first))
    projection = left.public_projection((first.source_id, second.source_id, missing))

    assert left.registry_digest == right.registry_digest
    assert projection["adapter_count"] == 2
    assert projection["observed_source_count"] == 3
    assert projection["missing_adapter_count"] == 1
    encoded = json.dumps(projection, sort_keys=True)
    assert missing not in encoded
    assert first.source_id not in encoded


def test_source_registry_load_rejects_duplicate_source(tmp_path: Path) -> None:
    adapter = _adapter("adapter-a", "sourceIdentifierA1")
    duplicate = adapter.model_copy(update={"adapter_id": "adapter-b"})
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "limen.source_registry.v1",
                "adapters": [
                    adapter.model_dump(mode="json"),
                    duplicate.model_dump(mode="json"),
                ],
            }
        ),
        encoding="utf-8",
    )
    os.chmod(registry, 0o600)

    with pytest.raises(PrimaMateriaStoreError, match="duplicate-source-id"):
        SourceRegistry.load(registry)
