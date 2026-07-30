"""Encrypted content-addressed custody and dynamic source registration.

The store writes ciphertext first and never stages plaintext on disk.  Object
identities are keyed HMACs rather than public plaintext hashes.  Deterministic
per-object keys and nonces make repeated storage idempotent without reusing an
AES-GCM key/nonce pair across different plaintext objects.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.util
import fcntl
import hashlib
import hmac
import io
import json
import math
import os
import platform
import plistlib
import secrets
import shutil
import stat
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import rfc8785

from limen.prima_materia import (
    CustodyReceiptV1,
    EncryptedPayloadRefV1,
    ResourceClaimV1,
    RestorationProofV1,
    SourceAdapterV1,
    SourceCoverageV1,
)

STORE_SCHEMA = "limen.encrypted_object_manifest.v1"
RESUME_SCHEMA = "limen.encrypted_object_resume.v1"
REGISTRY_SCHEMA = "limen.source_registry.v1"
DEFAULT_CHUNK_BYTES = 4 * 1024 * 1024
MIN_CHUNK_BYTES = 64 * 1024
MAX_CHUNK_BYTES = 64 * 1024 * 1024
AES_GCM_TAG_BYTES = 16
EVP_CTRL_AEAD_SET_IVLEN = 0x9
EVP_CTRL_AEAD_GET_TAG = 0x10
EVP_CTRL_AEAD_SET_TAG = 0x11


class PrimaMateriaStoreError(RuntimeError):
    """Encrypted custody or registry validation failed closed."""


class _AuthenticationError(RuntimeError):
    """Authenticated decryption rejected the ciphertext."""


class _ChunkSink(Protocol):
    def write(self, payload: bytes) -> int: ...


@dataclass(frozen=True)
class PathPutResult:
    payload_ref: EncryptedPayloadRefV1
    source_identity_sha256: str
    source_mode: int
    source_mtime_ns: int
    plaintext_sha256: str
    plaintext_bytes: int
    chunk_count: int
    resumed_chunk_count: int
    resource_claim: ResourceClaimV1

    @property
    def canonical_digest(self) -> str:
        return _canonical_digest(
            {
                "schema": "limen.path_put_result.v1",
                "payload_ref": self.payload_ref.model_dump(mode="json"),
                "source_identity_sha256": self.source_identity_sha256,
                "source_mode": self.source_mode,
                "source_mtime_ns": str(self.source_mtime_ns),
                "plaintext_sha256": self.plaintext_sha256,
                "plaintext_bytes": self.plaintext_bytes,
                "chunk_count": self.chunk_count,
                "resumed_chunk_count": self.resumed_chunk_count,
                "resource_claim": self.resource_claim.model_dump(mode="json"),
            }
        )


@dataclass(frozen=True)
class PathRestoreResult:
    payload_ref: EncryptedPayloadRefV1
    custody_target_ref: str
    device_id: str
    destination_identity_sha256: str
    restored_output_sha256: str
    plaintext_bytes: int
    resource_claim: ResourceClaimV1

    @property
    def canonical_digest(self) -> str:
        return _canonical_digest(
            {
                "schema": "limen.path_restore_result.v1",
                "payload_ref": self.payload_ref.model_dump(mode="json"),
                "custody_target_ref": self.custody_target_ref,
                "device_id": self.device_id,
                "destination_identity_sha256": self.destination_identity_sha256,
                "restored_output_sha256": self.restored_output_sha256,
                "plaintext_bytes": self.plaintext_bytes,
                "resource_claim": self.resource_claim.model_dump(mode="json"),
            }
        )


@dataclass(frozen=True)
class DualStoreCustodyResult:
    custody_receipt: CustodyReceiptV1
    copies: tuple[PathPutResult, PathPutResult]
    restores: tuple[PathRestoreResult, PathRestoreResult]


@lru_cache(maxsize=1)
def _libcrypto() -> ctypes.CDLL:
    """Load a system OpenSSL/LibreSSL EVP implementation without Python wheels."""

    candidates: list[str] = []
    if platform.system() == "Darwin":
        candidates.extend(
            [
                "/opt/homebrew/opt/openssl@3/lib/libcrypto.dylib",
                "/usr/local/opt/openssl@3/lib/libcrypto.dylib",
            ]
        )
    discovered = ctypes.util.find_library("crypto")
    if discovered and not (platform.system() == "Darwin" and discovered.startswith("/usr/lib/")):
        candidates.append(discovered)
    for candidate in candidates:
        try:
            library = ctypes.CDLL(candidate)
        except OSError:
            continue
        required = (
            "EVP_CIPHER_CTX_new",
            "EVP_CIPHER_CTX_free",
            "EVP_aes_256_gcm",
            "EVP_EncryptInit_ex",
            "EVP_EncryptUpdate",
            "EVP_EncryptFinal_ex",
            "EVP_DecryptInit_ex",
            "EVP_DecryptUpdate",
            "EVP_DecryptFinal_ex",
            "EVP_CIPHER_CTX_ctrl",
        )
        if not all(hasattr(library, symbol) for symbol in required):
            continue
        library.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
        library.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]
        library.EVP_aes_256_gcm.restype = ctypes.c_void_p
        for name in ("EVP_EncryptInit_ex", "EVP_DecryptInit_ex"):
            function = getattr(library, name)
            function.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            function.restype = ctypes.c_int
        for name in ("EVP_EncryptUpdate", "EVP_DecryptUpdate"):
            function = getattr(library, name)
            function.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            function.restype = ctypes.c_int
        for name in ("EVP_EncryptFinal_ex", "EVP_DecryptFinal_ex"):
            function = getattr(library, name)
            function.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int),
            ]
            function.restype = ctypes.c_int
        library.EVP_CIPHER_CTX_ctrl.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        library.EVP_CIPHER_CTX_ctrl.restype = ctypes.c_int
        return library
    raise PrimaMateriaStoreError("authenticated-encryption-unavailable")


def _buffer(value: bytes) -> ctypes.Array[ctypes.c_ubyte]:
    return (ctypes.c_ubyte * len(value)).from_buffer_copy(value)


class _AesGcm:
    """Small EVP-backed AES-256-GCM wrapper with no secret-bearing argv."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise PrimaMateriaStoreError("key-must-be-256-bit")
        self.key = key
        self.library = _libcrypto()

    def _context(self) -> ctypes.c_void_p:
        context = self.library.EVP_CIPHER_CTX_new()
        if not context:
            raise PrimaMateriaStoreError("authenticated-encryption-context-failed")
        return ctypes.c_void_p(context)

    def encrypt(self, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
        if len(nonce) != 12:
            raise PrimaMateriaStoreError("aes-gcm-nonce-must-be-96-bit")
        context = self._context()
        output = (ctypes.c_ubyte * max(1, len(plaintext) + AES_GCM_TAG_BYTES))()
        tag = (ctypes.c_ubyte * AES_GCM_TAG_BYTES)()
        written = ctypes.c_int()
        final_written = ctypes.c_int()
        key_buffer = _buffer(self.key)
        nonce_buffer = _buffer(nonce)
        aad_buffer = _buffer(aad)
        plaintext_buffer = _buffer(plaintext)
        try:
            cipher = self.library.EVP_aes_256_gcm()
            checks = (
                self.library.EVP_EncryptInit_ex(
                    context,
                    cipher,
                    None,
                    None,
                    None,
                ),
                self.library.EVP_CIPHER_CTX_ctrl(
                    context,
                    EVP_CTRL_AEAD_SET_IVLEN,
                    len(nonce),
                    None,
                ),
                self.library.EVP_EncryptInit_ex(
                    context,
                    None,
                    None,
                    key_buffer,
                    nonce_buffer,
                ),
                self.library.EVP_EncryptUpdate(
                    context,
                    None,
                    ctypes.byref(written),
                    aad_buffer,
                    len(aad),
                ),
                self.library.EVP_EncryptUpdate(
                    context,
                    output,
                    ctypes.byref(written),
                    plaintext_buffer,
                    len(plaintext),
                ),
                self.library.EVP_EncryptFinal_ex(
                    context,
                    ctypes.byref(output, written.value),
                    ctypes.byref(final_written),
                ),
                self.library.EVP_CIPHER_CTX_ctrl(
                    context,
                    EVP_CTRL_AEAD_GET_TAG,
                    AES_GCM_TAG_BYTES,
                    tag,
                ),
            )
            if any(result != 1 for result in checks):
                raise PrimaMateriaStoreError("authenticated-encryption-failed")
            length = written.value + final_written.value
            return bytes(output[:length]) + bytes(tag)
        finally:
            self.library.EVP_CIPHER_CTX_free(context)

    def decrypt(self, nonce: bytes, ciphertext_and_tag: bytes, aad: bytes) -> bytes:
        if len(nonce) != 12 or len(ciphertext_and_tag) < AES_GCM_TAG_BYTES:
            raise _AuthenticationError("ciphertext-authentication-failed")
        ciphertext = ciphertext_and_tag[:-AES_GCM_TAG_BYTES]
        tag = ciphertext_and_tag[-AES_GCM_TAG_BYTES:]
        context = self._context()
        output = (ctypes.c_ubyte * max(1, len(ciphertext)))()
        written = ctypes.c_int()
        final_written = ctypes.c_int()
        key_buffer = _buffer(self.key)
        nonce_buffer = _buffer(nonce)
        aad_buffer = _buffer(aad)
        ciphertext_buffer = _buffer(ciphertext)
        tag_buffer = _buffer(tag)
        try:
            cipher = self.library.EVP_aes_256_gcm()
            checks = (
                self.library.EVP_DecryptInit_ex(
                    context,
                    cipher,
                    None,
                    None,
                    None,
                ),
                self.library.EVP_CIPHER_CTX_ctrl(
                    context,
                    EVP_CTRL_AEAD_SET_IVLEN,
                    len(nonce),
                    None,
                ),
                self.library.EVP_DecryptInit_ex(
                    context,
                    None,
                    None,
                    key_buffer,
                    nonce_buffer,
                ),
                self.library.EVP_DecryptUpdate(
                    context,
                    None,
                    ctypes.byref(written),
                    aad_buffer,
                    len(aad),
                ),
                self.library.EVP_DecryptUpdate(
                    context,
                    output,
                    ctypes.byref(written),
                    ciphertext_buffer,
                    len(ciphertext),
                ),
                self.library.EVP_CIPHER_CTX_ctrl(
                    context,
                    EVP_CTRL_AEAD_SET_TAG,
                    AES_GCM_TAG_BYTES,
                    tag_buffer,
                ),
            )
            if any(result != 1 for result in checks):
                raise _AuthenticationError("ciphertext-authentication-failed")
            if (
                self.library.EVP_DecryptFinal_ex(
                    context,
                    ctypes.byref(output, written.value),
                    ctypes.byref(final_written),
                )
                != 1
            ):
                raise _AuthenticationError("ciphertext-authentication-failed")
            length = written.value + final_written.value
            return bytes(output[:length])
        finally:
            self.library.EVP_CIPHER_CTX_free(context)


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise PrimaMateriaStoreError("invalid-base64url") from exc


def load_key(path: Path) -> bytes:
    """Load a private 256-bit key from a mode-private raw/base64url file."""

    try:
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise PrimaMateriaStoreError("key-file-not-regular")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise PrimaMateriaStoreError("key-file-not-private")
        raw = path.read_bytes()
    except OSError as exc:
        raise PrimaMateriaStoreError("key-file-unavailable") from exc
    if len(raw) == 32:
        return raw
    try:
        decoded = _decode_b64url(raw.decode("ascii").strip())
    except UnicodeDecodeError as exc:
        raise PrimaMateriaStoreError("key-file-invalid") from exc
    if len(decoded) != 32:
        raise PrimaMateriaStoreError("key-must-be-256-bit")
    return decoded


def _atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


def _hmac(key: bytes, label: bytes, payload: bytes) -> bytes:
    return hmac.new(key, label + b"\0" + payload, hashlib.sha256).digest()


def _opaque(prefix: str, payload: Any) -> str:
    return f"{prefix}{_canonical_digest(payload)[:24]}"


def _path_identity(path: Path, info: os.stat_result) -> dict[str, Any]:
    return {
        "schema": "limen.path_source_identity.v1",
        "path_sha256": hashlib.sha256(str(path.resolve(strict=False)).encode()).hexdigest(),
        "device": str(info.st_dev),
        "inode": str(info.st_ino),
        "mode": stat.S_IMODE(info.st_mode),
        "size": int(info.st_size),
        "mtime_ns": str(info.st_mtime_ns),
        "ctime_ns": str(info.st_ctime_ns),
    }


def _resource_claim(
    *,
    operation: str,
    source_identity_sha256: str,
    hydrated_inputs_bytes: int,
    workspace_bytes: int,
    temporary_expansion_bytes: int,
    output_bytes: int,
    encryption_chunking_bytes: int,
    rollback_bytes: int,
    memory_bytes: int,
    file_count: int,
    network_bytes: int,
    elapsed_seconds: float,
) -> ResourceClaimV1:
    observed_at = datetime.now(UTC)
    wall_time_seconds = max(1, math.ceil(elapsed_seconds))
    effective_until = observed_at + timedelta(seconds=wall_time_seconds)
    rollback_until = effective_until + timedelta(days=1)
    identity = {
        "operation": operation,
        "source_identity_sha256": source_identity_sha256,
        "observed_at": observed_at.isoformat(),
    }
    return ResourceClaimV1(
        claim_id=_opaque("resourceClaim", identity),
        source_instance_id=f"sourceInstance{source_identity_sha256[:24]}",
        operation_id=_opaque("operationIdentifier", identity),
        hydrated_inputs_bytes=hydrated_inputs_bytes,
        workspace_bytes=workspace_bytes,
        temporary_expansion_bytes=temporary_expansion_bytes,
        output_bytes=output_bytes,
        encryption_chunking_bytes=encryption_chunking_bytes,
        rollback_bytes=rollback_bytes,
        memory_bytes=memory_bytes,
        file_count=file_count,
        network_bytes=network_bytes,
        wall_time_seconds=wall_time_seconds,
        effective_from=observed_at,
        effective_until=effective_until,
        rollback_until=rollback_until,
    )


class EncryptedObjectStore:
    def __init__(
        self,
        root: Path,
        key: bytes,
        *,
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    ) -> None:
        if len(key) != 32:
            raise PrimaMateriaStoreError("key-must-be-256-bit")
        if not MIN_CHUNK_BYTES <= chunk_bytes <= MAX_CHUNK_BYTES:
            raise PrimaMateriaStoreError("chunk-size-out-of-range")
        candidate = root.expanduser().absolute()
        try:
            candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
            info = candidate.lstat()
        except OSError as exc:
            raise PrimaMateriaStoreError("store-root-unavailable") from exc
        if candidate.is_symlink() or not stat.S_ISDIR(info.st_mode):
            raise PrimaMateriaStoreError("store-root-not-directory")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise PrimaMateriaStoreError("store-root-not-private")
        self.root = candidate.resolve(strict=True)
        self.key = key
        self.chunk_bytes = chunk_bytes
        self.profile = {
            "schema": "limen.encryption_profile.v1",
            "algorithm": "AES-256-GCM",
            "implementation_contract": "system-libcrypto-EVP",
            "object_key_derivation": "HMAC-SHA256-object-v1",
            "nonce_derivation": "HMAC-SHA256-index-v1",
            "object_identity": "keyed-plaintext-digest-v1",
            "chunk_bytes": chunk_bytes,
        }
        self.profile_digest = _canonical_digest(self.profile)

    def _identities_from_digest(self, digest: bytes) -> tuple[str, bytes, bytes]:
        if len(digest) != hashlib.sha256().digest_size:
            raise PrimaMateriaStoreError("plaintext-digest-invalid")
        object_id = _b64url(_hmac(self.key, b"object-id", digest))
        object_key = _hmac(self.key, b"object-key", digest)
        content_auth = _b64url(_hmac(self.key, b"content-auth", digest))
        return object_id, object_key, content_auth.encode("ascii")

    def _identities(self, plaintext: bytes) -> tuple[str, bytes, bytes]:
        return self._identities_from_digest(hashlib.sha256(plaintext).digest())

    def _object_dir(self, object_id: str) -> Path:
        if not object_id or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
            for character in object_id
        ):
            raise PrimaMateriaStoreError("object-id-invalid")
        return self.root / "objects" / object_id

    def _open_regular_source(self, source: Path) -> tuple[io.BufferedIOBase, dict[str, Any]]:
        candidate = source.expanduser().absolute()
        try:
            initial = candidate.lstat()
        except OSError as exc:
            raise PrimaMateriaStoreError("source-unavailable") from exc
        if stat.S_ISLNK(initial.st_mode):
            raise PrimaMateriaStoreError("source-symlink-rejected")
        if not stat.S_ISREG(initial.st_mode):
            raise PrimaMateriaStoreError("source-not-regular-file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(candidate, flags)
            current = os.fstat(descriptor)
        except OSError as exc:
            raise PrimaMateriaStoreError("source-unavailable") from exc
        if not stat.S_ISREG(current.st_mode) or current.st_dev != initial.st_dev or current.st_ino != initial.st_ino:
            os.close(descriptor)
            raise PrimaMateriaStoreError("source-identity-drift")
        return os.fdopen(descriptor, "rb", buffering=0), _path_identity(candidate, current)

    def _source_digest(self, source: Path) -> tuple[bytes, dict[str, Any]]:
        handle, identity = self._open_regular_source(source)
        digest = hashlib.sha256()
        try:
            while True:
                chunk = handle.read(self.chunk_bytes)
                if not chunk:
                    break
                digest.update(chunk)
            final_identity = _path_identity(source.expanduser().absolute(), os.fstat(handle.fileno()))
        except OSError as exc:
            raise PrimaMateriaStoreError("source-read-failed") from exc
        finally:
            handle.close()
        if final_identity != identity:
            raise PrimaMateriaStoreError("source-identity-drift")
        return digest.digest(), identity

    def _resume_auth(self, payload: dict[str, Any]) -> str:
        return _b64url(_hmac(self.key, b"resume-state", rfc8785.dumps(payload)))

    def _write_resume(self, staging: Path, payload: dict[str, Any]) -> None:
        authenticated = {**payload, "resume_auth": self._resume_auth(payload)}
        _atomic_bytes(
            staging / "resume.json",
            json.dumps(authenticated, indent=2, sort_keys=True).encode() + b"\n",
        )

    def _load_resume(
        self,
        staging: Path,
        *,
        object_id: str,
        source_identity_sha256: str,
        plaintext_bytes: int,
        total_chunks: int,
    ) -> dict[str, Any]:
        try:
            resume_path = staging / "resume.json"
            if resume_path.is_symlink() or not resume_path.is_file():
                raise PrimaMateriaStoreError("resume-state-unavailable")
            authenticated = json.loads(resume_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PrimaMateriaStoreError("resume-state-unavailable") from exc
        if not isinstance(authenticated, dict) or set(authenticated) != {
            "schema",
            "object_id",
            "source_identity_sha256",
            "plaintext_bytes",
            "total_chunks",
            "profile",
            "chunks",
            "resume_auth",
        }:
            raise PrimaMateriaStoreError("resume-state-fields-invalid")
        resume_auth = authenticated.pop("resume_auth")
        if not isinstance(resume_auth, str) or not hmac.compare_digest(
            resume_auth,
            self._resume_auth(authenticated),
        ):
            raise PrimaMateriaStoreError("resume-state-authentication-failed")
        if (
            authenticated["schema"] != RESUME_SCHEMA
            or authenticated["object_id"] != object_id
            or authenticated["source_identity_sha256"] != source_identity_sha256
            or authenticated["plaintext_bytes"] != plaintext_bytes
            or authenticated["total_chunks"] != total_chunks
            or authenticated["profile"] != self.profile_digest
        ):
            raise PrimaMateriaStoreError("resume-state-identity-mismatch")
        chunks = authenticated["chunks"]
        if not isinstance(chunks, list) or len(chunks) > total_chunks:
            raise PrimaMateriaStoreError("resume-state-chunks-invalid")
        for index, metadata in enumerate(chunks):
            if not isinstance(metadata, dict) or metadata.get("index") != index:
                raise PrimaMateriaStoreError("resume-state-chunks-invalid")
            ciphertext_sha256 = metadata.get("ciphertext_sha256")
            ciphertext_bytes = metadata.get("ciphertext_bytes")
            plaintext_chunk_bytes = metadata.get("plaintext_bytes")
            if (
                not isinstance(ciphertext_sha256, str)
                or len(ciphertext_sha256) != 64
                or not isinstance(ciphertext_bytes, int)
                or not isinstance(plaintext_chunk_bytes, int)
            ):
                raise PrimaMateriaStoreError("resume-state-chunks-invalid")
            chunk_path = staging / f"{index:08d}-{ciphertext_sha256}.bin"
            try:
                if chunk_path.is_symlink() or not chunk_path.is_file():
                    raise PrimaMateriaStoreError("resume-chunk-unavailable")
                with chunk_path.open("rb") as handle:
                    observed = hashlib.file_digest(handle, "sha256").hexdigest()
                if observed != ciphertext_sha256 or chunk_path.stat().st_size != ciphertext_bytes:
                    raise PrimaMateriaStoreError("resume-chunk-drift")
            except OSError as exc:
                raise PrimaMateriaStoreError("resume-chunk-unavailable") from exc
        return authenticated

    def _manifest_for_path(
        self,
        *,
        object_id: str,
        object_key: bytes,
        content_auth: bytes,
        identity: dict[str, Any],
        source_identity_sha256: str,
        chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        key_nonce = _hmac(
            self.key,
            b"key-capsule-nonce",
            object_id.encode(),
        )[:12]
        object_key_capsule = _AesGcm(self.key).encrypt(
            key_nonce,
            object_key,
            object_id.encode(),
        )
        return {
            "schema": STORE_SCHEMA,
            "object_id": object_id,
            "encryption_profile": self.profile,
            "encryption_profile_digest": self.profile_digest,
            "content_auth": content_auth.decode("ascii"),
            "object_key_capsule": _b64url(object_key_capsule),
            "plaintext_bytes": identity["size"],
            "path_metadata": {
                "source_identity_sha256": source_identity_sha256,
                "mode": identity["mode"],
                "mtime_ns": identity["mtime_ns"],
                "file_count": 1,
            },
            "chunks": chunks,
        }

    def _ref_from_manifest(self, manifest: dict[str, Any], object_root: Path) -> EncryptedPayloadRefV1:
        try:
            root_info = object_root.lstat()
        except OSError as exc:
            raise PrimaMateriaStoreError("object-root-unavailable") from exc
        if object_root.is_symlink() or not stat.S_ISDIR(root_info.st_mode):
            raise PrimaMateriaStoreError("object-root-invalid")
        chunks = manifest.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise PrimaMateriaStoreError("manifest-chunks-invalid")
        ciphertext_digest = hashlib.sha256()
        ciphertext_bytes = 0
        for expected_index, metadata in enumerate(chunks):
            if not isinstance(metadata, dict) or metadata.get("index") != expected_index:
                raise PrimaMateriaStoreError("manifest-chunk-order-invalid")
            ciphertext_sha256 = metadata.get("ciphertext_sha256")
            if not isinstance(ciphertext_sha256, str):
                raise PrimaMateriaStoreError("manifest-chunk-digest-invalid")
            chunk_path = object_root / f"{expected_index:08d}-{ciphertext_sha256}.bin"
            try:
                if chunk_path.is_symlink() or not chunk_path.is_file():
                    raise PrimaMateriaStoreError("ciphertext-chunk-unavailable")
                with chunk_path.open("rb") as handle:
                    while True:
                        payload = handle.read(self.chunk_bytes)
                        if not payload:
                            break
                        ciphertext_digest.update(payload)
                        ciphertext_bytes += len(payload)
            except OSError as exc:
                raise PrimaMateriaStoreError("ciphertext-chunk-unavailable") from exc
        return EncryptedPayloadRefV1(
            object_id=str(manifest.get("object_id", "")),
            ciphertext_sha256=ciphertext_digest.hexdigest(),
            encryption_profile_digest=self.profile_digest,
            chunk_manifest_digest=_canonical_digest(manifest),
            ciphertext_bytes=ciphertext_bytes,
        )

    def _validated_manifest(self, ref: EncryptedPayloadRefV1) -> tuple[Path, dict[str, Any]]:
        object_root = self._object_dir(ref.object_id)
        try:
            root_info = object_root.lstat()
            if object_root.is_symlink() or not stat.S_ISDIR(root_info.st_mode):
                raise PrimaMateriaStoreError("object-root-invalid")
            manifest_path = object_root / "manifest.json"
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise PrimaMateriaStoreError("manifest-unavailable")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PrimaMateriaStoreError("manifest-unavailable") from exc
        if not isinstance(manifest, dict) or _canonical_digest(manifest) != ref.chunk_manifest_digest:
            raise PrimaMateriaStoreError("manifest-digest-mismatch")
        if (
            manifest.get("schema") != STORE_SCHEMA
            or manifest.get("object_id") != ref.object_id
            or manifest.get("encryption_profile") != self.profile
            or manifest.get("encryption_profile_digest") != ref.encryption_profile_digest
        ):
            raise PrimaMateriaStoreError("manifest-identity-mismatch")
        return object_root, manifest

    def _stream_restore(
        self,
        ref: EncryptedPayloadRefV1,
        sink: _ChunkSink | None,
    ) -> tuple[str, int, dict[str, Any]]:
        object_root, manifest = self._validated_manifest(ref)
        chunks = manifest.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise PrimaMateriaStoreError("manifest-chunks-invalid")
        content_auth = manifest.get("content_auth")
        if not isinstance(content_auth, str):
            raise PrimaMateriaStoreError("manifest-content-auth-invalid")
        key_nonce = _hmac(self.key, b"key-capsule-nonce", ref.object_id.encode())[:12]
        capsule = manifest.get("object_key_capsule")
        if not isinstance(capsule, str):
            raise PrimaMateriaStoreError("manifest-key-capsule-missing")
        try:
            object_key = _AesGcm(self.key).decrypt(
                key_nonce,
                _decode_b64url(capsule),
                ref.object_id.encode(),
            )
        except (_AuthenticationError, ValueError) as exc:
            raise PrimaMateriaStoreError("manifest-key-capsule-invalid") from exc
        aes = _AesGcm(object_key)
        ciphertext_digest = hashlib.sha256()
        plaintext_digest = hashlib.sha256()
        plaintext_bytes = 0
        ciphertext_bytes = 0
        total = len(chunks)
        for expected_index, metadata in enumerate(chunks):
            if not isinstance(metadata, dict) or metadata.get("index") != expected_index:
                raise PrimaMateriaStoreError("manifest-chunk-order-invalid")
            ciphertext_sha256 = metadata.get("ciphertext_sha256")
            if not isinstance(ciphertext_sha256, str):
                raise PrimaMateriaStoreError("manifest-chunk-digest-invalid")
            chunk_path = object_root / f"{expected_index:08d}-{ciphertext_sha256}.bin"
            try:
                if chunk_path.is_symlink() or not chunk_path.is_file():
                    raise PrimaMateriaStoreError("ciphertext-chunk-unavailable")
                ciphertext = chunk_path.read_bytes()
            except OSError as exc:
                raise PrimaMateriaStoreError("ciphertext-chunk-unavailable") from exc
            if hashlib.sha256(ciphertext).hexdigest() != ciphertext_sha256 or len(ciphertext) != metadata.get(
                "ciphertext_bytes"
            ):
                raise PrimaMateriaStoreError("ciphertext-chunk-drift")
            ciphertext_digest.update(ciphertext)
            ciphertext_bytes += len(ciphertext)
            nonce = _decode_b64url(str(metadata.get("nonce", "")))
            aad = rfc8785.dumps(
                {
                    "schema": STORE_SCHEMA,
                    "object_id": ref.object_id,
                    "index": expected_index,
                    "total": total,
                    "profile": self.profile_digest,
                }
            )
            try:
                plaintext = aes.decrypt(nonce, ciphertext, aad)
            except _AuthenticationError as exc:
                raise PrimaMateriaStoreError("ciphertext-authentication-failed") from exc
            if len(plaintext) != metadata.get("plaintext_bytes"):
                raise PrimaMateriaStoreError("plaintext-chunk-size-mismatch")
            if sink is not None and sink.write(plaintext) != len(plaintext):
                raise PrimaMateriaStoreError("restore-write-short")
            plaintext_digest.update(plaintext)
            plaintext_bytes += len(plaintext)
        object_id, _derived_key, observed_auth = self._identities_from_digest(plaintext_digest.digest())
        if (
            object_id != ref.object_id
            or not hmac.compare_digest(observed_auth, content_auth.encode())
            or plaintext_bytes != manifest.get("plaintext_bytes")
            or ciphertext_digest.hexdigest() != ref.ciphertext_sha256
            or ciphertext_bytes != ref.ciphertext_bytes
        ):
            raise PrimaMateriaStoreError("restored-object-mismatch")
        return plaintext_digest.hexdigest(), plaintext_bytes, manifest

    def _existing_path_result(
        self,
        *,
        final: Path,
        identity: dict[str, Any],
        source_identity_sha256: str,
        plaintext_digest: bytes,
        total_chunks: int,
        started: float,
    ) -> PathPutResult:
        try:
            manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PrimaMateriaStoreError("manifest-unavailable") from exc
        ref = self._ref_from_manifest(manifest, final)
        restored_sha256, restored_bytes, _manifest = self._stream_restore(ref, None)
        if restored_sha256 != plaintext_digest.hex() or restored_bytes != identity["size"]:
            raise PrimaMateriaStoreError("existing-object-mismatch")
        output_bytes = ref.ciphertext_bytes + (final / "manifest.json").stat().st_size
        return PathPutResult(
            payload_ref=ref,
            source_identity_sha256=source_identity_sha256,
            source_mode=identity["mode"],
            source_mtime_ns=int(identity["mtime_ns"]),
            plaintext_sha256=plaintext_digest.hex(),
            plaintext_bytes=identity["size"],
            chunk_count=total_chunks,
            resumed_chunk_count=0,
            resource_claim=_resource_claim(
                operation="put-path-existing",
                source_identity_sha256=source_identity_sha256,
                hydrated_inputs_bytes=identity["size"],
                workspace_bytes=0,
                temporary_expansion_bytes=0,
                output_bytes=output_bytes,
                encryption_chunking_bytes=self.chunk_bytes,
                rollback_bytes=0,
                memory_bytes=(2 * self.chunk_bytes) + AES_GCM_TAG_BYTES,
                file_count=total_chunks + 1,
                network_bytes=0,
                elapsed_seconds=time.monotonic() - started,
            ),
        )

    def put_path(
        self,
        source: Path,
        *,
        expected_source_identity_sha256: str | None = None,
        interrupt_after_chunks: int | None = None,
    ) -> PathPutResult:
        """Encrypt one regular file without plaintext staging or whole-file buffering."""

        started = time.monotonic()
        if interrupt_after_chunks is not None and interrupt_after_chunks < 1:
            raise PrimaMateriaStoreError("interrupt-chunk-count-invalid")
        plaintext_digest, identity = self._source_digest(source)
        source_identity_sha256 = _canonical_digest(identity)
        if expected_source_identity_sha256 is not None and source_identity_sha256 != expected_source_identity_sha256:
            raise PrimaMateriaStoreError("source-identity-drift")
        object_id, object_key, content_auth = self._identities_from_digest(plaintext_digest)
        total = max(1, (identity["size"] + self.chunk_bytes - 1) // self.chunk_bytes)
        final = self._object_dir(object_id)
        resumed_chunk_count = 0
        if final.exists():
            return self._existing_path_result(
                final=final,
                identity=identity,
                source_identity_sha256=source_identity_sha256,
                plaintext_digest=plaintext_digest,
                total_chunks=total,
                started=started,
            )

        staging_root = self.root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if staging_root.is_symlink() or not staging_root.is_dir():
            raise PrimaMateriaStoreError("staging-root-invalid")
        staging = staging_root / object_id
        lock_path = staging_root / f"{object_id}.lock"
        lock_descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            if final.exists():
                return self._existing_path_result(
                    final=final,
                    identity=identity,
                    source_identity_sha256=source_identity_sha256,
                    plaintext_digest=plaintext_digest,
                    total_chunks=total,
                    started=started,
                )
            if staging.exists():
                if staging.is_symlink() or not staging.is_dir():
                    raise PrimaMateriaStoreError("staging-object-invalid")
                state = self._load_resume(
                    staging,
                    object_id=object_id,
                    source_identity_sha256=source_identity_sha256,
                    plaintext_bytes=identity["size"],
                    total_chunks=total,
                )
                resumed_chunk_count = len(state["chunks"])
            else:
                staging.mkdir(mode=0o700)
                state = {
                    "schema": RESUME_SCHEMA,
                    "object_id": object_id,
                    "source_identity_sha256": source_identity_sha256,
                    "plaintext_bytes": identity["size"],
                    "total_chunks": total,
                    "profile": self.profile_digest,
                    "chunks": [],
                }
                self._write_resume(staging, state)

            second_digest = hashlib.sha256()
            handle, second_identity = self._open_regular_source(source)
            if second_identity != identity:
                handle.close()
                shutil.rmtree(staging)
                raise PrimaMateriaStoreError("source-identity-drift")
            chunks: list[dict[str, Any]] = list(state["chunks"])
            aes = _AesGcm(object_key)
            try:
                for index in range(total):
                    chunk = handle.read(self.chunk_bytes)
                    if index < total - 1 and len(chunk) != self.chunk_bytes:
                        raise PrimaMateriaStoreError("source-read-short")
                    if index == total - 1 and len(chunk) != identity["size"] - (index * self.chunk_bytes):
                        raise PrimaMateriaStoreError("source-read-size-drift")
                    second_digest.update(chunk)
                    if index < resumed_chunk_count:
                        continue
                    nonce = _hmac(
                        object_key,
                        b"nonce",
                        index.to_bytes(8, "big"),
                    )[:12]
                    aad = rfc8785.dumps(
                        {
                            "schema": STORE_SCHEMA,
                            "object_id": object_id,
                            "index": index,
                            "total": total,
                            "profile": self.profile_digest,
                        }
                    )
                    ciphertext = aes.encrypt(nonce, chunk, aad)
                    ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
                    metadata = {
                        "index": index,
                        "ciphertext_sha256": ciphertext_sha256,
                        "ciphertext_bytes": len(ciphertext),
                        "plaintext_bytes": len(chunk),
                        "nonce": _b64url(nonce),
                    }
                    _atomic_bytes(
                        staging / f"{index:08d}-{ciphertext_sha256}.bin",
                        ciphertext,
                    )
                    chunks.append(metadata)
                    state = {**state, "chunks": chunks}
                    self._write_resume(staging, state)
                    if interrupt_after_chunks is not None and len(chunks) >= interrupt_after_chunks:
                        raise PrimaMateriaStoreError("simulated-interruption")
                if handle.read(1):
                    raise PrimaMateriaStoreError("source-read-size-drift")
                final_identity = _path_identity(
                    source.expanduser().absolute(),
                    os.fstat(handle.fileno()),
                )
            finally:
                handle.close()
            if final_identity != identity or second_digest.digest() != plaintext_digest:
                shutil.rmtree(staging)
                raise PrimaMateriaStoreError("source-content-drift")

            manifest = self._manifest_for_path(
                object_id=object_id,
                object_key=object_key,
                content_auth=content_auth,
                identity=identity,
                source_identity_sha256=source_identity_sha256,
                chunks=chunks,
            )
            _atomic_bytes(
                staging / "manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n",
            )
            (staging / "resume.json").unlink()
            final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.rename(staging, final)
            except OSError:
                if not final.exists():
                    raise
                if staging.exists():
                    shutil.rmtree(staging)
            parent_descriptor = os.open(final.parent, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
            ref = self._ref_from_manifest(manifest, final)
            restored_sha256, restored_bytes, _validated = self._stream_restore(ref, None)
            if restored_sha256 != plaintext_digest.hex() or restored_bytes != identity["size"]:
                raise PrimaMateriaStoreError("post-write-restore-failed")
            output_bytes = ref.ciphertext_bytes + (final / "manifest.json").stat().st_size
            return PathPutResult(
                payload_ref=ref,
                source_identity_sha256=source_identity_sha256,
                source_mode=identity["mode"],
                source_mtime_ns=int(identity["mtime_ns"]),
                plaintext_sha256=plaintext_digest.hex(),
                plaintext_bytes=identity["size"],
                chunk_count=total,
                resumed_chunk_count=resumed_chunk_count,
                resource_claim=_resource_claim(
                    operation="put-path",
                    source_identity_sha256=source_identity_sha256,
                    hydrated_inputs_bytes=identity["size"],
                    workspace_bytes=0,
                    temporary_expansion_bytes=output_bytes,
                    output_bytes=output_bytes,
                    encryption_chunking_bytes=self.chunk_bytes,
                    rollback_bytes=output_bytes,
                    memory_bytes=(2 * self.chunk_bytes) + AES_GCM_TAG_BYTES,
                    file_count=total + 2,
                    network_bytes=0,
                    elapsed_seconds=time.monotonic() - started,
                ),
            )
        finally:
            os.close(lock_descriptor)

    def restore_to_path(
        self,
        ref: EncryptedPayloadRefV1,
        destination: Path,
        *,
        custody_target_ref: str,
        device_id: str,
    ) -> PathRestoreResult:
        """Authenticate and atomically restore one path without whole-file buffering."""

        started = time.monotonic()
        destination = destination.expanduser().absolute()
        parent = destination.parent
        try:
            parent_info = parent.lstat()
        except OSError as exc:
            raise PrimaMateriaStoreError("restore-parent-unavailable") from exc
        if parent.is_symlink() or not stat.S_ISDIR(parent_info.st_mode):
            raise PrimaMateriaStoreError("restore-parent-invalid")
        if os.path.lexists(destination):
            raise PrimaMateriaStoreError("restore-destination-exists")
        _object_root, manifest = self._validated_manifest(ref)
        metadata = manifest.get("path_metadata")
        if not isinstance(metadata, dict) or set(metadata) != {
            "source_identity_sha256",
            "mode",
            "mtime_ns",
            "file_count",
        }:
            raise PrimaMateriaStoreError("path-metadata-unavailable")
        source_identity_sha256 = metadata["source_identity_sha256"]
        if (
            not isinstance(source_identity_sha256, str)
            or len(source_identity_sha256) != 64
            or not isinstance(metadata["mode"], int)
            or not 0 <= metadata["mode"] <= 0o7777
            or not isinstance(metadata["mtime_ns"], str)
            or not metadata["mtime_ns"].isdigit()
            or metadata["file_count"] != 1
        ):
            raise PrimaMateriaStoreError("path-metadata-invalid")
        mtime_ns = int(metadata["mtime_ns"])
        temporary = parent / f".{destination.name}.{ref.object_id}.{secrets.token_hex(8)}.restore"
        descriptor = -1
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb", buffering=0) as handle:
                descriptor = -1
                restored_sha256, restored_bytes, _manifest = self._stream_restore(ref, handle)
                os.fchmod(handle.fileno(), metadata["mode"])
                handle.flush()
                os.fsync(handle.fileno())
            os.utime(
                temporary,
                ns=(mtime_ns, mtime_ns),
                follow_symlinks=False,
            )
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError as exc:
                raise PrimaMateriaStoreError("restore-destination-exists") from exc
            temporary.unlink()
            parent_descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
        except OSError as exc:
            raise PrimaMateriaStoreError("restore-write-failed") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
        restored_info = destination.lstat()
        destination_identity_sha256 = _canonical_digest(_path_identity(destination, restored_info))
        claim = _resource_claim(
            operation="restore-to-path",
            source_identity_sha256=source_identity_sha256,
            hydrated_inputs_bytes=ref.ciphertext_bytes,
            workspace_bytes=restored_bytes,
            temporary_expansion_bytes=restored_bytes,
            output_bytes=restored_bytes,
            encryption_chunking_bytes=self.chunk_bytes,
            rollback_bytes=restored_bytes,
            memory_bytes=(2 * self.chunk_bytes) + AES_GCM_TAG_BYTES,
            file_count=1,
            network_bytes=0,
            elapsed_seconds=time.monotonic() - started,
        )
        return PathRestoreResult(
            payload_ref=ref,
            custody_target_ref=custody_target_ref,
            device_id=device_id,
            destination_identity_sha256=destination_identity_sha256,
            restored_output_sha256=restored_sha256,
            plaintext_bytes=restored_bytes,
            resource_claim=claim,
        )

    def put(self, plaintext: bytes) -> EncryptedPayloadRefV1:
        if not isinstance(plaintext, bytes):
            raise PrimaMateriaStoreError("plaintext-must-be-bytes")
        object_id, object_key, content_auth = self._identities(plaintext)
        chunks: list[tuple[dict[str, Any], bytes]] = []
        ciphertext_digest = hashlib.sha256()
        aes = _AesGcm(object_key)
        total = max(1, (len(plaintext) + self.chunk_bytes - 1) // self.chunk_bytes)
        for index in range(total):
            chunk = plaintext[index * self.chunk_bytes : (index + 1) * self.chunk_bytes]
            nonce = _hmac(
                object_key,
                b"nonce",
                index.to_bytes(8, "big"),
            )[:12]
            aad = rfc8785.dumps(
                {
                    "schema": STORE_SCHEMA,
                    "object_id": object_id,
                    "index": index,
                    "total": total,
                    "profile": self.profile_digest,
                }
            )
            ciphertext = aes.encrypt(nonce, chunk, aad)
            ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
            ciphertext_digest.update(ciphertext)
            chunks.append(
                (
                    {
                        "index": index,
                        "ciphertext_sha256": ciphertext_sha256,
                        "ciphertext_bytes": len(ciphertext),
                        "plaintext_bytes": len(chunk),
                        "nonce": _b64url(nonce),
                    },
                    ciphertext,
                )
            )
        key_nonce = _hmac(
            self.key,
            b"key-capsule-nonce",
            object_id.encode(),
        )[:12]
        object_key_capsule = _AesGcm(self.key).encrypt(
            key_nonce,
            object_key,
            object_id.encode(),
        )
        manifest_payload = {
            "schema": STORE_SCHEMA,
            "object_id": object_id,
            "encryption_profile": self.profile,
            "encryption_profile_digest": self.profile_digest,
            "content_auth": content_auth.decode("ascii"),
            "object_key_capsule": _b64url(object_key_capsule),
            "plaintext_bytes": len(plaintext),
            "chunks": [metadata for metadata, _ciphertext in chunks],
        }
        manifest_digest = _canonical_digest(manifest_payload)
        ref = EncryptedPayloadRefV1(
            object_id=object_id,
            ciphertext_sha256=ciphertext_digest.hexdigest(),
            encryption_profile_digest=self.profile_digest,
            chunk_manifest_digest=manifest_digest,
            ciphertext_bytes=sum(len(ciphertext) for _metadata, ciphertext in chunks),
        )
        final = self._object_dir(object_id)
        if final.exists():
            if self.restore(ref) != plaintext:
                raise PrimaMateriaStoreError("existing-object-mismatch")
            return ref

        staging_root = self.root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = staging_root / f"{object_id}.{os.getpid()}.{secrets.token_hex(8)}"
        staging.mkdir(mode=0o700)
        try:
            for metadata, ciphertext in chunks:
                name = f"{metadata['index']:08d}-{metadata['ciphertext_sha256']}.bin"
                _atomic_bytes(staging / name, ciphertext)
            _atomic_bytes(
                staging / "manifest.json",
                json.dumps(
                    manifest_payload,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8")
                + b"\n",
            )
            final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.rename(staging, final)
            except OSError:
                if not final.exists():
                    raise
                if self.restore(ref) != plaintext:
                    raise PrimaMateriaStoreError("concurrent-object-mismatch") from None
            parent_descriptor = os.open(final.parent, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        if self.restore(ref) != plaintext:
            raise PrimaMateriaStoreError("post-write-restore-failed")
        return ref

    def restore(self, ref: EncryptedPayloadRefV1) -> bytes:
        object_root = self._object_dir(ref.object_id)
        try:
            manifest_path = object_root / "manifest.json"
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise PrimaMateriaStoreError("manifest-unavailable")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PrimaMateriaStoreError("manifest-unavailable") from exc
        if not isinstance(manifest, dict) or _canonical_digest(manifest) != ref.chunk_manifest_digest:
            raise PrimaMateriaStoreError("manifest-digest-mismatch")
        if (
            manifest.get("schema") != STORE_SCHEMA
            or manifest.get("object_id") != ref.object_id
            or manifest.get("encryption_profile") != self.profile
            or manifest.get("encryption_profile_digest") != ref.encryption_profile_digest
        ):
            raise PrimaMateriaStoreError("manifest-identity-mismatch")
        chunks = manifest.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise PrimaMateriaStoreError("manifest-chunks-invalid")
        content_auth = manifest.get("content_auth")
        if not isinstance(content_auth, str):
            raise PrimaMateriaStoreError("manifest-content-auth-invalid")
        expected_object_id = ref.object_id
        plaintext_parts: list[bytes] = []
        ciphertext_digest = hashlib.sha256()
        # The private manifest carries an authenticated AES-GCM key capsule;
        # no plaintext digest or unwrapped object key is persisted.
        key_nonce = _hmac(self.key, b"key-capsule-nonce", ref.object_id.encode())[:12]
        capsule = manifest.get("object_key_capsule")
        if not isinstance(capsule, str):
            raise PrimaMateriaStoreError("manifest-key-capsule-missing")
        try:
            object_key = _AesGcm(self.key).decrypt(
                key_nonce,
                _decode_b64url(capsule),
                ref.object_id.encode(),
            )
        except (_AuthenticationError, ValueError) as exc:
            raise PrimaMateriaStoreError("manifest-key-capsule-invalid") from exc
        aes = _AesGcm(object_key)
        total = len(chunks)
        for expected_index, metadata in enumerate(chunks):
            if not isinstance(metadata, dict) or metadata.get("index") != expected_index:
                raise PrimaMateriaStoreError("manifest-chunk-order-invalid")
            ciphertext_sha256 = metadata.get("ciphertext_sha256")
            if not isinstance(ciphertext_sha256, str):
                raise PrimaMateriaStoreError("manifest-chunk-digest-invalid")
            path = object_root / f"{expected_index:08d}-{ciphertext_sha256}.bin"
            try:
                if path.is_symlink() or not path.is_file():
                    raise PrimaMateriaStoreError("ciphertext-chunk-unavailable")
                ciphertext = path.read_bytes()
            except OSError as exc:
                raise PrimaMateriaStoreError("ciphertext-chunk-unavailable") from exc
            if hashlib.sha256(ciphertext).hexdigest() != ciphertext_sha256 or len(ciphertext) != metadata.get(
                "ciphertext_bytes"
            ):
                raise PrimaMateriaStoreError("ciphertext-chunk-drift")
            nonce = _decode_b64url(str(metadata.get("nonce", "")))
            aad = rfc8785.dumps(
                {
                    "schema": STORE_SCHEMA,
                    "object_id": ref.object_id,
                    "index": expected_index,
                    "total": total,
                    "profile": self.profile_digest,
                }
            )
            try:
                plaintext = aes.decrypt(nonce, ciphertext, aad)
            except _AuthenticationError as exc:
                raise PrimaMateriaStoreError("ciphertext-authentication-failed") from exc
            if len(plaintext) != metadata.get("plaintext_bytes"):
                raise PrimaMateriaStoreError("plaintext-chunk-size-mismatch")
            plaintext_parts.append(plaintext)
            ciphertext_digest.update(ciphertext)
        plaintext = b"".join(plaintext_parts)
        object_id, _derived_key, observed_auth = self._identities(plaintext)
        if (
            object_id != expected_object_id
            or not hmac.compare_digest(observed_auth, content_auth.encode())
            or len(plaintext) != manifest.get("plaintext_bytes")
            or ciphertext_digest.hexdigest() != ref.ciphertext_sha256
            or sum(int(item["ciphertext_bytes"]) for item in chunks) != ref.ciphertext_bytes
        ):
            raise PrimaMateriaStoreError("restored-object-mismatch")
        return plaintext


def _plist_command(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=15,
        )
        payload = plistlib.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException) as exc:
        raise PrimaMateriaStoreError("physical-parent-resolution-failed") from exc
    if not isinstance(payload, dict) or payload.get("Error"):
        raise PrimaMateriaStoreError("physical-parent-resolution-failed")
    return payload


def _darwin_physical_parent_identity(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["/bin/df", "-P", str(root)],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrimaMateriaStoreError("physical-parent-resolution-failed") from exc
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise PrimaMateriaStoreError("physical-parent-resolution-failed")
    fields = lines[-1].split()
    if not fields or not fields[0].startswith("/dev/"):
        raise PrimaMateriaStoreError("physical-parent-resolution-failed")
    volume = _plist_command(["/usr/sbin/diskutil", "info", "-plist", fields[0]])
    stores = volume.get("APFSPhysicalStores")
    physical_identifiers: list[str] = []
    if isinstance(stores, list):
        for item in stores:
            if isinstance(item, dict):
                value = item.get("APFSPhysicalStore")
                if isinstance(value, str) and value:
                    physical_identifiers.append(value)
    if not physical_identifiers:
        parent = volume.get("ParentWholeDisk")
        device = volume.get("DeviceIdentifier")
        candidate = parent if isinstance(parent, str) and parent else device
        if isinstance(candidate, str) and candidate:
            physical_identifiers.append(candidate)
    if not physical_identifiers:
        raise PrimaMateriaStoreError("physical-parent-resolution-failed")
    stable_identities: list[str] = []
    for identifier in sorted(set(physical_identifiers)):
        physical = _plist_command(["/usr/sbin/diskutil", "info", "-plist", identifier])
        stable = next(
            (
                physical.get(field)
                for field in ("DiskUUID", "MediaUUID", "VolumeUUID")
                if isinstance(physical.get(field), str) and physical.get(field)
            ),
            identifier,
        )
        stable_identities.append(str(stable))
    return _opaque(
        "physicalDevice",
        {
            "schema": "limen.physical_parent_identity.v1",
            "physical_identities": sorted(stable_identities),
        },
    )


def physical_parent_identity(root: Path) -> str:
    """Return an opaque physical-parent identity or fail closed."""

    if platform.system() != "Darwin":
        raise PrimaMateriaStoreError("physical-parent-resolution-unsupported")
    return _darwin_physical_parent_identity(root.expanduser().resolve(strict=True))


class DualStoreCustodyExecutor:
    """Write and independently restore one source from two physical stores."""

    def __init__(
        self,
        first: EncryptedObjectStore,
        second: EncryptedObjectStore,
        *,
        physical_parent_resolver: Callable[[Path], str] = physical_parent_identity,
    ) -> None:
        if first.profile_digest != second.profile_digest:
            raise PrimaMateriaStoreError("custody-encryption-profile-mismatch")
        self.stores = (first, second)
        self.physical_parent_resolver = physical_parent_resolver

    def _physical_parents(self) -> tuple[str, str]:
        parents = tuple(self.physical_parent_resolver(store.root) for store in self.stores)
        if any(
            not isinstance(value, str)
            or not 16 <= len(value) <= 128
            or any(
                character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
                for character in value
            )
            for value in parents
        ):
            raise PrimaMateriaStoreError("physical-parent-identity-invalid")
        if parents[0] == parents[1]:
            raise PrimaMateriaStoreError("custody-same-physical-parent")
        return parents

    def custody_path(
        self,
        source: Path,
        *,
        first_restore_destination: Path,
        second_restore_destination: Path,
    ) -> DualStoreCustodyResult:
        first_destination = first_restore_destination.expanduser().absolute()
        second_destination = second_restore_destination.expanduser().absolute()
        if first_destination == second_destination:
            raise PrimaMateriaStoreError("restore-destinations-must-differ")
        if os.path.lexists(first_destination) or os.path.lexists(second_destination):
            raise PrimaMateriaStoreError("restore-destination-exists")
        physical_parents = self._physical_parents()
        first_copy = self.stores[0].put_path(source)
        second_copy = self.stores[1].put_path(
            source,
            expected_source_identity_sha256=first_copy.source_identity_sha256,
        )
        if (
            first_copy.source_identity_sha256 != second_copy.source_identity_sha256
            or first_copy.plaintext_sha256 != second_copy.plaintext_sha256
            or first_copy.plaintext_bytes != second_copy.plaintext_bytes
        ):
            raise PrimaMateriaStoreError("custody-copy-source-mismatch")
        if self._physical_parents() != physical_parents:
            raise PrimaMateriaStoreError("custody-physical-parent-drift")
        target_refs = tuple(
            _opaque(
                "custodyTarget",
                {
                    "schema": "limen.custody_target_identity.v1",
                    "store_root_sha256": hashlib.sha256(str(store.root).encode()).hexdigest(),
                    "physical_parent": parent,
                },
            )
            for store, parent in zip(self.stores, physical_parents, strict=True)
        )
        try:
            first_restore = self.stores[0].restore_to_path(
                first_copy.payload_ref,
                first_destination,
                custody_target_ref=target_refs[0],
                device_id=physical_parents[0],
            )
            second_restore = self.stores[1].restore_to_path(
                second_copy.payload_ref,
                second_destination,
                custody_target_ref=target_refs[1],
                device_id=physical_parents[1],
            )
            if self._physical_parents() != physical_parents:
                raise PrimaMateriaStoreError("custody-physical-parent-drift")
            final_digest, final_identity = self.stores[0]._source_digest(source)
            if (
                final_digest.hex() != first_copy.plaintext_sha256
                or _canonical_digest(final_identity) != first_copy.source_identity_sha256
            ):
                raise PrimaMateriaStoreError("custody-source-drift")
        except Exception:
            first_destination.unlink(missing_ok=True)
            second_destination.unlink(missing_ok=True)
            raise
        restores = (first_restore, second_restore)
        for restore in restores:
            if (
                restore.restored_output_sha256 != first_copy.plaintext_sha256
                or restore.plaintext_bytes != first_copy.plaintext_bytes
            ):
                raise PrimaMateriaStoreError("custody-restore-mismatch")
        source_info = source.expanduser().absolute().lstat()
        for destination in (first_destination, second_destination):
            restored_info = destination.lstat()
            if (
                not stat.S_ISREG(restored_info.st_mode)
                or stat.S_IMODE(restored_info.st_mode) != stat.S_IMODE(source_info.st_mode)
                or restored_info.st_size != source_info.st_size
                or restored_info.st_mtime_ns != source_info.st_mtime_ns
            ):
                raise PrimaMateriaStoreError("custody-restore-metadata-mismatch")
        restored_at = datetime.now(UTC)
        proofs = tuple(
            RestorationProofV1(
                custody_target_ref=restore.custody_target_ref,
                device_id=restore.device_id,
                restored_at=restored_at,
                restored_output_digest=restore.restored_output_sha256,
                predicate_digest=_canonical_digest(
                    {
                        "schema": "limen.restoration_predicate_receipt.v1",
                        "custody_target_ref": restore.custody_target_ref,
                        "device_id": restore.device_id,
                        "destination_identity_sha256": (restore.destination_identity_sha256),
                        "restored_output_sha256": (restore.restored_output_sha256),
                        "source_mode": first_copy.source_mode,
                        "source_mtime_ns": str(first_copy.source_mtime_ns),
                        "plaintext_bytes": first_copy.plaintext_bytes,
                        "passed": True,
                    }
                ),
            )
            for restore in restores
        )
        custody_identity = {
            "schema": "limen.dual_store_custody_identity.v1",
            "source_identity_sha256": first_copy.source_identity_sha256,
            "plaintext_sha256": first_copy.plaintext_sha256,
            "payload_refs": [copy.payload_ref.model_dump(mode="json") for copy in (first_copy, second_copy)],
            "physical_parents": physical_parents,
            "restoration_predicates": [proof.predicate_digest for proof in proofs],
        }
        receipt = CustodyReceiptV1(
            custody_id=_opaque("custodyReceipt", custody_identity),
            encryption_profile_digest=first_copy.payload_ref.encryption_profile_digest,
            chunk_manifest_digests=(
                first_copy.payload_ref.chunk_manifest_digest,
                second_copy.payload_ref.chunk_manifest_digest,
            ),
            independent_device_ids=physical_parents,
            restoration_proofs=proofs,
        )
        return DualStoreCustodyResult(
            custody_receipt=receipt,
            copies=(first_copy, second_copy),
            restores=restores,
        )


@dataclass(frozen=True)
class SourceRegistry:
    adapters: tuple[SourceAdapterV1, ...]
    registry_digest: str

    @classmethod
    def load(cls, path: Path) -> SourceRegistry:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PrimaMateriaStoreError("source-registry-unavailable") from exc
        if not isinstance(payload, dict) or set(payload) != {"schema", "adapters"}:
            raise PrimaMateriaStoreError("source-registry-fields-mismatch")
        if payload["schema"] != REGISTRY_SCHEMA or not isinstance(payload["adapters"], list):
            raise PrimaMateriaStoreError("source-registry-schema-mismatch")
        try:
            adapters = tuple(SourceAdapterV1.model_validate(item) for item in payload["adapters"])
        except ValueError as exc:
            raise PrimaMateriaStoreError("source-adapter-invalid") from exc
        return cls.from_adapters(adapters)

    @classmethod
    def from_adapters(cls, adapters: Iterable[SourceAdapterV1]) -> SourceRegistry:
        ordered = tuple(sorted(adapters, key=lambda item: item.adapter_id))
        adapter_ids = [item.adapter_id for item in ordered]
        source_ids = [item.source_id for item in ordered]
        if len(adapter_ids) != len(set(adapter_ids)):
            raise PrimaMateriaStoreError("duplicate-adapter-id")
        if len(source_ids) != len(set(source_ids)):
            raise PrimaMateriaStoreError("duplicate-source-id")
        normalized = {
            "schema": REGISTRY_SCHEMA,
            "adapters": [item.model_dump(mode="json") for item in ordered],
        }
        return cls(ordered, _canonical_digest(normalized))

    def coverage(self, observed_source_ids: Iterable[str]) -> SourceCoverageV1:
        return SourceCoverageV1.reconcile(
            registry_digest=self.registry_digest,
            observed_source_ids=tuple(observed_source_ids),
            adapters=self.adapters,
        )

    def public_projection(self, observed_source_ids: Iterable[str]) -> dict[str, Any]:
        coverage = self.coverage(observed_source_ids)
        payload: dict[str, Any] = {
            "schema": "limen.source_registry_projection.v1",
            "registry_digest": self.registry_digest,
            "adapter_count": len(self.adapters),
            "observed_source_count": len(coverage.observed_source_ids),
            "missing_adapter_count": len(coverage.missing_adapter_source_ids),
            "registered_source_digests": [
                hashlib.sha256(value.encode()).hexdigest() for value in coverage.registered_source_ids
            ],
            "missing_adapter_source_digests": [
                hashlib.sha256(value.encode()).hexdigest() for value in coverage.missing_adapter_source_ids
            ],
        }
        return {**payload, "projection_sha256": _canonical_digest(payload)}
