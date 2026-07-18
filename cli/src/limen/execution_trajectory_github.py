"""GitHub-owned atomic publication for execution trajectories."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import quote

from limen.execution_trajectory import (
    OwnerPublication,
    OwnerReceiptClaim,
    OwnerReceiptEnvelope,
    OwnerReceiptSnapshot,
    OwnerTrajectorySnapshot,
    ReceiptAuthority,
    TrajectoryPublicationError,
    canonical_owner_receipt_envelope_bytes,
    canonical_owner_receipt_payload_bytes,
)


_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_AUTHORITY_OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_AUTHORITY_SCHEMA = "limen.receipt_authorities.v2"
_SYSTEM_CONFIG_SCHEMA = "limen.execution_owner_service.v1"
_SYSTEM_OWNER_CONFIG = Path("/Library/Application Support/org.limen.execution-owner/config.json")
_SYSTEM_OWNER_EXECUTABLE = Path("/Library/PrivilegedHelperTools/org.limen.execution-owner")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class GitHubCommandRunner:
    def run(self, argv: Sequence[str], *, input_text: str | None = None, timeout: int = 60) -> CommandResult:
        try:
            result = subprocess.run(
                list(argv),
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return CommandResult(127, "", str(exc))
        return CommandResult(result.returncode, result.stdout or "", result.stderr or "")


def _assert_root_custodied(path: Path, *, executable: bool) -> None:
    """Reject symlinks or executor-writable components across the full path."""

    if not path.is_absolute():
        raise ValueError("owner service path must be absolute")
    components = [Path(path.anchor)]
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        components.append(cursor)
    for index, component in enumerate(components):
        try:
            metadata = os.lstat(component)
        except OSError as exc:
            raise ValueError(f"owner service is unprovisioned: missing {component}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"owner service custody rejects symlink {component}")
        if metadata.st_uid != 0:
            raise ValueError(f"owner service custody requires root ownership for {component}")
        if metadata.st_mode & 0o022:
            raise ValueError(f"owner service custody rejects group/world-writable {component}")
        is_leaf = index == len(components) - 1
        if not is_leaf and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"owner service ancestor is not a directory: {component}")
        if is_leaf:
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"owner service leaf is not a regular file: {component}")
            if executable and metadata.st_mode & 0o111 == 0:
                raise ValueError(f"owner service verifier is not executable: {component}")


class SystemOwnerCommandRunner(GitHubCommandRunner):
    """Invoke only the root-custodied owner client with an inert environment.

    The client talks to the owner LaunchDaemon; GitHub/App credentials remain in
    that daemon's custody and are never inherited by the executing session.
    """

    def __init__(self, *, executable: Path, expected_digest: str) -> None:
        if executable != _SYSTEM_OWNER_EXECUTABLE:
            raise ValueError("owner service executable path is not the fixed system path")
        if not _SHA256.fullmatch(expected_digest):
            raise ValueError("owner service executable digest is invalid")
        _assert_root_custodied(executable, executable=True)
        actual = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
        if actual != expected_digest:
            raise ValueError("owner service executable identity does not match root-custodied configuration")
        self.executable = executable

    def run(self, argv: Sequence[str], *, input_text: str | None = None, timeout: int = 60) -> CommandResult:
        exact = list(argv)
        if not exact or exact[0] != str(self.executable):
            return CommandResult(127, "", "owner service invocation was redirected")
        try:
            result = subprocess.run(
                exact,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env={
                    "HOME": "/var/empty",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": "/usr/bin:/bin",
                },
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return CommandResult(127, "", str(exc))
        return CommandResult(result.returncode, result.stdout or "", result.stderr or "")


@dataclass(frozen=True)
class SystemOwnerConfiguration:
    runner: SystemOwnerCommandRunner
    trajectory_owner: Mapping[str, str]
    receipt_authorities: tuple[Mapping[str, str], ...]


def load_system_owner_configuration() -> SystemOwnerConfiguration:
    """Load the one production owner surface; checkout and environment are irrelevant."""

    _assert_root_custodied(_SYSTEM_OWNER_CONFIG, executable=False)
    try:
        raw = _SYSTEM_OWNER_CONFIG.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("owner service root-custodied configuration is unreadable") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "verifier",
        "trajectory_owner",
        "receipt_authorities",
    }:
        raise ValueError("owner service configuration shape is invalid")
    verifier = payload.get("verifier")
    trajectory = payload.get("trajectory_owner")
    authorities = payload.get("receipt_authorities")
    if (
        payload.get("schema") != _SYSTEM_CONFIG_SCHEMA
        or not isinstance(verifier, dict)
        or set(verifier) != {"path", "sha256"}
        or verifier.get("path") != str(_SYSTEM_OWNER_EXECUTABLE)
        or not isinstance(trajectory, dict)
        or set(trajectory) != {"repository", "ref", "root"}
        or not isinstance(authorities, list)
        or not 1 <= len(authorities) <= 32
    ):
        raise ValueError("owner service configuration schema is invalid")
    runner = SystemOwnerCommandRunner(
        executable=_SYSTEM_OWNER_EXECUTABLE,
        expected_digest=str(verifier.get("sha256") or ""),
    )
    return SystemOwnerConfiguration(
        runner=runner,
        trajectory_owner={key: str(value) for key, value in trajectory.items()},
        receipt_authorities=tuple(
            {str(key): str(value) for key, value in row.items()} if isinstance(row, dict) else {} for row in authorities
        ),
    )


class GitHubTrajectoryAdapter:
    """Publish one bounded batch as one fast-forward commit on an owner ref.

    Blob creation may leave unreachable objects if a compare-and-set loses, but
    none of the trajectory paths become visible until the single ref update.
    """

    def __init__(
        self,
        *,
        repository: str,
        ref: str,
        root: str,
        runner: GitHubCommandRunner | None = None,
        gh: str | None = None,
    ) -> None:
        if not _REPOSITORY.fullmatch(repository):
            raise ValueError("repository must be exact OWNER/NAME")
        if not _REF.fullmatch(ref) or ".." in ref or ref.endswith("/") or "//" in ref:
            raise ValueError("ref is unsafe")
        normalized_root = root.strip("/")
        if (
            not normalized_root
            or not _PATH.fullmatch(normalized_root)
            or any(segment in {".", ".."} for segment in normalized_root.split("/"))
        ):
            raise ValueError("root is unsafe")
        if runner is None or not gh:
            raise ValueError("owner operations require an explicitly validated service runner")
        self.repository = repository
        self.ref = ref
        self.root = normalized_root
        self.runner = runner
        self.gh = gh

    @staticmethod
    def _filename(attempt_id: str) -> str:
        return hashlib.sha256(attempt_id.encode()).hexdigest() + ".json"

    def _path(self, attempt_id: str) -> str:
        return f"{self.root}/{self._filename(attempt_id)}"

    def _api(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        payload: Mapping[str, object] | None = None,
        allow_absent: bool = False,
    ) -> dict[str, object] | None:
        argv = [self.gh, "api", endpoint]
        input_text = None
        if method != "GET":
            argv.extend(["-X", method, "--input", "-"])
            input_text = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
        result = self.runner.run(argv, input_text=input_text, timeout=60)
        if allow_absent and result.returncode != 0 and "404" in result.stderr:
            return None
        if result.returncode != 0:
            raise TrajectoryPublicationError(
                f"GitHub owner operation failed for {endpoint}: {result.stderr.strip()[:240]}"
            )
        try:
            decoded = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise TrajectoryPublicationError(f"GitHub owner returned invalid JSON for {endpoint}") from exc
        if not isinstance(decoded, dict):
            raise TrajectoryPublicationError(f"GitHub owner returned non-object JSON for {endpoint}")
        return decoded

    @staticmethod
    def _content_bytes(response: Mapping[str, object], attempt_id: str) -> bytes:
        encoded = response.get("content")
        encoding = response.get("encoding")
        if not isinstance(encoded, str) or encoding != "base64":
            raise TrajectoryPublicationError(f"GitHub owner content is malformed for {attempt_id}")
        try:
            return base64.b64decode("".join(encoded.split()), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TrajectoryPublicationError(f"GitHub owner content is invalid base64 for {attempt_id}") from exc

    def read_many(self, attempt_ids: Sequence[str]) -> OwnerTrajectorySnapshot:
        snapshot_head = self._ref_head()
        rows: dict[str, bytes] = {}
        for attempt_id in attempt_ids:
            path = quote(self._path(attempt_id), safe="/")
            endpoint = f"repos/{self.repository}/contents/{path}?ref={snapshot_head}"
            response = self._api(endpoint, allow_absent=True)
            if response is None:
                continue
            rows[attempt_id] = self._content_bytes(response, attempt_id)
        return OwnerTrajectorySnapshot(token=snapshot_head, records=rows)

    def _ref_head(self) -> str:
        response = self._api(f"repos/{self.repository}/git/ref/heads/{quote(self.ref, safe='')}")
        obj = response.get("object") if response else None
        sha = str(obj.get("sha") or "") if isinstance(obj, dict) else ""
        if not _SHA.fullmatch(sha):
            raise TrajectoryPublicationError("GitHub owner ref did not resolve to an exact commit")
        return sha

    def _require_ancestor(self, ancestor: str, descendant: str) -> None:
        response = self._api(f"repos/{self.repository}/compare/{ancestor}...{descendant}")
        merge_base = response.get("merge_base_commit") if response else None
        merge_base_sha = str(merge_base.get("sha") or "") if isinstance(merge_base, dict) else ""
        if merge_base_sha != ancestor:
            raise TrajectoryPublicationError("GitHub owner publication is not reachable from its base")

    def publish_atomic(
        self,
        payloads: Mapping[str, bytes],
        *,
        snapshot_token: str,
    ) -> Mapping[str, OwnerPublication]:
        if not payloads:
            return {}
        base_sha = snapshot_token
        if not _SHA.fullmatch(base_sha):
            raise TrajectoryPublicationError("GitHub owner publication requires an exact-head snapshot token")
        if self._ref_head() != base_sha:
            raise TrajectoryPublicationError("GitHub owner compare-and-set lost before publication")
        commit = self._api(f"repos/{self.repository}/git/commits/{base_sha}")
        tree = commit.get("tree") if commit else None
        base_tree = str(tree.get("sha") or "") if isinstance(tree, dict) else ""
        if not _SHA.fullmatch(base_tree):
            raise TrajectoryPublicationError("GitHub owner commit lacks an exact tree")

        entries: list[dict[str, object]] = []
        for attempt_id in sorted(payloads):
            encoded = base64.b64encode(payloads[attempt_id]).decode()
            blob = self._api(
                f"repos/{self.repository}/git/blobs",
                method="POST",
                payload={"content": encoded, "encoding": "base64"},
            )
            blob_sha = str(blob.get("sha") or "") if blob else ""
            if not _SHA.fullmatch(blob_sha):
                raise TrajectoryPublicationError(f"GitHub owner blob lacks an exact SHA for {attempt_id}")
            entries.append(
                {
                    "path": self._path(attempt_id),
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                }
            )

        tree_response = self._api(
            f"repos/{self.repository}/git/trees",
            method="POST",
            payload={"base_tree": base_tree, "tree": entries},
        )
        tree_sha = str(tree_response.get("sha") or "") if tree_response else ""
        if not _SHA.fullmatch(tree_sha):
            raise TrajectoryPublicationError("GitHub owner created tree lacks an exact SHA")
        commit_response = self._api(
            f"repos/{self.repository}/git/commits",
            method="POST",
            payload={
                "message": f"limen: publish {len(payloads)} execution trajectories",
                "tree": tree_sha,
                "parents": [base_sha],
            },
        )
        commit_sha = str(commit_response.get("sha") or "") if commit_response else ""
        if not _SHA.fullmatch(commit_sha):
            raise TrajectoryPublicationError("GitHub owner created commit lacks an exact SHA")
        patched = self._api(
            f"repos/{self.repository}/git/refs/heads/{quote(self.ref, safe='')}",
            method="PATCH",
            payload={"sha": commit_sha, "force": False},
        )
        patched_ref = str(patched.get("ref") or "") if patched else ""
        patched_object = patched.get("object") if patched else None
        patched_sha = str(patched_object.get("sha") or "") if isinstance(patched_object, dict) else ""
        if patched_ref != f"refs/heads/{self.ref}" or patched_sha != commit_sha:
            raise TrajectoryPublicationError("GitHub owner PATCH response did not confirm the exact new head")
        if self._ref_head() != commit_sha:
            raise TrajectoryPublicationError("GitHub owner ref readback did not confirm the exact new head")
        self._require_ancestor(base_sha, commit_sha)
        for attempt_id, payload in sorted(payloads.items()):
            path = quote(self._path(attempt_id), safe="/")
            response = self._api(f"repos/{self.repository}/contents/{path}?ref={commit_sha}")
            if self._content_bytes(response or {}, attempt_id) != payload:
                raise TrajectoryPublicationError(f"GitHub owner exact-commit readback mismatched {attempt_id}")

        published_at = datetime.now(timezone.utc)
        return {
            attempt_id: OwnerPublication(
                attempt_id=attempt_id,
                reference=f"https://github.com/{self.repository}/blob/{commit_sha}/{self._path(attempt_id)}",
                digest="sha256:" + hashlib.sha256(payload).hexdigest(),
                published_at=published_at,
            )
            for attempt_id, payload in payloads.items()
        }


class GitHubReceiptAuthority:
    """Authenticate value evidence from one fixed GitHub owner ref.

    The claim may select only the exact attempt-derived path under the
    configured root. Its receipt commit may be the live ref head or any
    reachable ancestor, so a later fast-forward never invalidates an accepted
    immutable receipt.
    """

    def __init__(
        self,
        *,
        owner: str,
        repository: str,
        ref: str,
        root: str,
        signature_scheme: str,
        key_id: str,
        runner: GitHubCommandRunner,
        gh: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not _AUTHORITY_OWNER.fullmatch(owner):
            raise ValueError("receipt authority owner is invalid")
        if signature_scheme != "owner-service-v1":
            raise ValueError("receipt authority signature scheme is unsupported")
        if not re.fullmatch(r"^[A-Za-z0-9._-]{1,128}$", key_id):
            raise ValueError("receipt authority key ID is invalid")
        # Reuse strict identity/path validation without granting publication.
        adapter = GitHubTrajectoryAdapter(
            repository=repository,
            ref=ref,
            root=root,
            runner=runner,
            gh=gh,
        )
        self.owner = owner
        self.repository = adapter.repository
        self.ref = adapter.ref
        self.root = adapter.root
        self.runner = adapter.runner
        self.gh = adapter.gh
        self.signature_scheme = signature_scheme
        self.key_id = key_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _filename(attempt_id: str) -> str:
        return hashlib.sha256(attempt_id.encode()).hexdigest() + ".json"

    def _path(self, attempt_id: str) -> str:
        return f"{self.root}/{self._filename(attempt_id)}"

    def _api(self, endpoint: str) -> dict[str, object]:
        result = self.runner.run([self.gh, "api", endpoint], timeout=60)
        if result.returncode != 0:
            raise TrajectoryPublicationError(
                f"GitHub receipt authority failed for {endpoint}: {result.stderr.strip()[:240]}"
            )
        try:
            decoded = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise TrajectoryPublicationError("GitHub receipt authority returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise TrajectoryPublicationError("GitHub receipt authority returned non-object JSON")
        return decoded

    def _ref_head(self) -> str:
        response = self._api(f"repos/{self.repository}/git/ref/heads/{quote(self.ref, safe='')}")
        obj = response.get("object")
        sha = str(obj.get("sha") or "") if isinstance(obj, dict) else ""
        if not _SHA.fullmatch(sha):
            raise TrajectoryPublicationError("GitHub receipt authority ref lacks an exact head")
        return sha

    def _receipt_commit_is_reachable(self, receipt_commit: str, live_head: str) -> bool:
        response = self._api(f"repos/{self.repository}/compare/{receipt_commit}...{live_head}")
        merge_base = response.get("merge_base_commit")
        merge_base_sha = str(merge_base.get("sha") or "") if isinstance(merge_base, dict) else ""
        return merge_base_sha == receipt_commit

    def _verify_owner_signature(self, envelope: OwnerReceiptEnvelope) -> bool:
        signature = envelope.signature
        if signature.scheme != self.signature_scheme or signature.key_id != self.key_id:
            return False
        unsigned = canonical_owner_receipt_payload_bytes(envelope.payload)
        unsigned_digest = "sha256:" + hashlib.sha256(unsigned).hexdigest()
        result = self.runner.run(
            [
                self.gh,
                "verify-signature",
                "--owner",
                self.owner,
                "--scheme",
                self.signature_scheme,
                "--key-id",
                self.key_id,
                "--signature",
                signature.value,
            ],
            input_text=unsigned.decode("utf-8"),
            timeout=60,
        )
        if result.returncode != 0:
            return False
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False
        return bool(
            isinstance(response, dict)
            and response.get("valid") is True
            and response.get("owner") == self.owner
            and response.get("scheme") == self.signature_scheme
            and response.get("key_id") == self.key_id
            and response.get("payload_digest") == unsigned_digest
        )

    def matches(self, claim: OwnerReceiptClaim) -> bool:
        return claim.owner == self.owner and claim.reference.startswith(f"https://github.com/{self.repository}/blob/")

    def verify(
        self,
        claim: OwnerReceiptClaim,
        *,
        attempt_id: str,
        task_id: str,
        repository: str,
        predicate_digest: str,
    ) -> OwnerReceiptSnapshot | None:
        if not self.matches(claim) or claim.attempt_id != attempt_id:
            return None
        prefix = f"https://github.com/{self.repository}/blob/"
        reference_tail = claim.reference.removeprefix(prefix)
        receipt_commit, separator, path = reference_tail.partition("/")
        if not separator or not _SHA.fullmatch(receipt_commit) or path != self._path(attempt_id):
            return None
        live_head = self._ref_head()
        if not self._receipt_commit_is_reachable(receipt_commit, live_head):
            return None
        response = self._api(f"repos/{self.repository}/contents/{quote(path, safe='/')}?ref={receipt_commit}")
        encoded = response.get("content")
        if not isinstance(encoded, str) or response.get("encoding") != "base64":
            return None
        try:
            payload = base64.b64decode("".join(encoded.split()), validate=True)
            decoded = json.loads(payload)
            envelope = OwnerReceiptEnvelope.model_validate(decoded)
        except (ValueError, binascii.Error, json.JSONDecodeError):
            return None
        if canonical_owner_receipt_envelope_bytes(envelope) != payload:
            return None
        if "reference" in decoded or "digest" in decoded:
            return None
        if "reference" in decoded.get("payload", {}) or "digest" in decoded.get("payload", {}):
            return None
        if "reference" in decoded.get("signature", {}) or "digest" in decoded.get("signature", {}):
            return None
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if digest != claim.digest or not self._verify_owner_signature(envelope):
            return None
        signed = envelope.payload
        if (
            signed.owner != claim.owner
            or signed.head_sha != claim.head_sha
            or signed.attempt_id != attempt_id
            or signed.task_id != task_id
            or signed.repository != repository
            or signed.predicate_digest != predicate_digest
            or signed.reconciliation_digest != claim.reconciliation_digest
        ):
            return None
        verified_at = self._clock()
        if verified_at.tzinfo is None:
            return None
        return OwnerReceiptSnapshot(
            owner=signed.owner,
            reference=claim.reference,
            digest=claim.digest,
            head_sha=signed.head_sha,
            attempt_id=signed.attempt_id,
            task_id=signed.task_id,
            repository=signed.repository,
            predicate_digest=signed.predicate_digest,
            reconciliation_digest=signed.reconciliation_digest,
            terminal=signed.terminal,
            predicate_passed=signed.predicate_passed,
            verified_at=verified_at,
        )


class ConfiguredReceiptAuthority:
    """Finite fixed registry; a claim cannot provide or redirect a verifier."""

    def __init__(self, authorities: Sequence[GitHubReceiptAuthority]) -> None:
        if not authorities or len(authorities) > 32:
            raise ValueError("receipt authority registry must contain 1..32 owners")
        self.authorities = tuple(authorities)

    def verify(
        self,
        claim: OwnerReceiptClaim,
        *,
        attempt_id: str,
        task_id: str,
        repository: str,
        predicate_digest: str,
    ) -> OwnerReceiptSnapshot | None:
        candidates = [authority for authority in self.authorities if authority.matches(claim)]
        if len(candidates) != 1:
            return None
        return candidates[0].verify(
            claim,
            attempt_id=attempt_id,
            task_id=task_id,
            repository=repository,
            predicate_digest=predicate_digest,
        )


def load_configured_receipt_authority(
    path: Path,
    *,
    runner: GitHubCommandRunner,
    gh: str,
    clock: Callable[[], datetime] | None = None,
) -> ReceiptAuthority | None:
    """Parse an explicit fixture configuration.

    Production never calls this function: it has no CLI/environment route and
    always resolves :func:`load_system_receipt_authority` instead.
    """

    try:
        payload = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("receipt authority registry is unreadable") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "authorities"}:
        raise ValueError("receipt authority registry shape is invalid")
    rows = payload.get("authorities")
    if payload.get("schema") != _AUTHORITY_SCHEMA or not isinstance(rows, list) or len(rows) > 32:
        raise ValueError("receipt authority registry schema is invalid")
    if not rows:
        return None
    authorities: list[GitHubReceiptAuthority] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "kind",
            "owner",
            "repository",
            "ref",
            "root",
            "signature_scheme",
            "key_id",
        }:
            raise ValueError("receipt authority entry shape is invalid")
        if row.get("kind") != "github":
            raise ValueError("receipt authority kind is unsupported")
        authorities.append(
            GitHubReceiptAuthority(
                owner=str(row["owner"]),
                repository=str(row["repository"]),
                ref=str(row["ref"]),
                root=str(row["root"]),
                signature_scheme=str(row["signature_scheme"]),
                key_id=str(row["key_id"]),
                runner=runner,
                gh=gh,
                clock=clock,
            )
        )
    return ConfiguredReceiptAuthority(authorities)


def _authorities_from_system(
    config: SystemOwnerConfiguration,
    *,
    clock: Callable[[], datetime] | None = None,
) -> ReceiptAuthority:
    authorities: list[GitHubReceiptAuthority] = []
    for row in config.receipt_authorities:
        if (
            set(row)
            != {
                "kind",
                "owner",
                "repository",
                "ref",
                "root",
                "signature_scheme",
                "key_id",
            }
            or row.get("kind") != "github-signed"
        ):
            raise ValueError("owner service receipt authority entry is invalid")
        authorities.append(
            GitHubReceiptAuthority(
                owner=row["owner"],
                repository=row["repository"],
                ref=row["ref"],
                root=row["root"],
                signature_scheme=row["signature_scheme"],
                key_id=row["key_id"],
                runner=config.runner,
                gh=str(_SYSTEM_OWNER_EXECUTABLE),
                clock=clock,
            )
        )
    return ConfiguredReceiptAuthority(authorities)


def load_system_receipt_authority() -> ReceiptAuthority:
    """Return the fixed system authority or raise while unprovisioned."""

    return _authorities_from_system(load_system_owner_configuration())


def load_system_trajectory_adapter() -> GitHubTrajectoryAdapter:
    """Return the fixed system trajectory publisher or raise while unprovisioned."""

    config = load_system_owner_configuration()
    return GitHubTrajectoryAdapter(
        repository=config.trajectory_owner["repository"],
        ref=config.trajectory_owner["ref"],
        root=config.trajectory_owner["root"],
        runner=config.runner,
        gh=str(_SYSTEM_OWNER_EXECUTABLE),
    )
