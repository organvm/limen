"""GitHub-owned atomic publication for execution trajectories."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import quote

from limen.execution_trajectory import (
    OwnerPublication,
    OwnerReceiptClaim,
    OwnerReceiptSnapshot,
    OwnerTrajectorySnapshot,
    ReceiptAuthority,
    TrajectoryPublicationError,
)


_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_AUTHORITY_OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_AUTHORITY_SCHEMA = "limen.receipt_authorities.v1"


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
        gh: str = "gh",
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
        self.repository = repository
        self.ref = ref
        self.root = normalized_root
        self.runner = runner or GitHubCommandRunner()
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

    def read_many(self, attempt_ids: Sequence[str]) -> OwnerTrajectorySnapshot:
        snapshot_head = self._ref_head()
        rows: dict[str, bytes] = {}
        for attempt_id in attempt_ids:
            path = quote(self._path(attempt_id), safe="/")
            endpoint = f"repos/{self.repository}/contents/{path}?ref={snapshot_head}"
            response = self._api(endpoint, allow_absent=True)
            if response is None:
                continue
            encoded = response.get("content")
            encoding = response.get("encoding")
            if not isinstance(encoded, str) or encoding != "base64":
                raise TrajectoryPublicationError(f"GitHub owner content is malformed for {attempt_id}")
            try:
                rows[attempt_id] = base64.b64decode("".join(encoded.split()), validate=True)
            except (ValueError, binascii.Error) as exc:
                raise TrajectoryPublicationError(f"GitHub owner content is invalid base64 for {attempt_id}") from exc
        return OwnerTrajectorySnapshot(token=snapshot_head, records=rows)

    def _ref_head(self) -> str:
        response = self._api(f"repos/{self.repository}/git/ref/heads/{quote(self.ref, safe='')}")
        obj = response.get("object") if response else None
        sha = str(obj.get("sha") or "") if isinstance(obj, dict) else ""
        if not _SHA.fullmatch(sha):
            raise TrajectoryPublicationError("GitHub owner ref did not resolve to an exact commit")
        return sha

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
        self._api(
            f"repos/{self.repository}/git/refs/heads/{quote(self.ref, safe='')}",
            method="PATCH",
            payload={"sha": commit_sha, "force": False},
        )

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
    configured root, and that reference must name the ref's live exact head.
    """

    def __init__(
        self,
        *,
        owner: str,
        repository: str,
        ref: str,
        root: str,
        runner: GitHubCommandRunner | None = None,
        gh: str = "gh",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not _AUTHORITY_OWNER.fullmatch(owner):
            raise ValueError("receipt authority owner is invalid")
        # Reuse the publication adapter's strict repository/ref/root validation
        # and read primitives without granting publication capability here.
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
        head, separator, path = reference_tail.partition("/")
        if not separator or not _SHA.fullmatch(head) or path != self._path(attempt_id):
            return None
        live_head = self._ref_head()
        if head != live_head:
            return None
        response = self._api(f"repos/{self.repository}/contents/{quote(path, safe='/')}?ref={live_head}")
        encoded = response.get("content")
        if not isinstance(encoded, str) or response.get("encoding") != "base64":
            return None
        try:
            payload = base64.b64decode("".join(encoded.split()), validate=True)
            snapshot = OwnerReceiptSnapshot.model_validate_json(payload)
        except (ValueError, binascii.Error):
            return None
        if (
            snapshot.owner != claim.owner
            or snapshot.reference != claim.reference
            or snapshot.digest != claim.digest
            or snapshot.head_sha != claim.head_sha
            or snapshot.attempt_id != attempt_id
            or snapshot.task_id != task_id
            or snapshot.repository != repository
            or snapshot.predicate_digest != predicate_digest
            or snapshot.reconciliation_digest != claim.reconciliation_digest
        ):
            return None
        verified_at = self._clock()
        if verified_at.tzinfo is None:
            return None
        return snapshot.model_copy(update={"verified_at": verified_at})


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
    runner: GitHubCommandRunner | None = None,
    gh: str = "gh",
    clock: Callable[[], datetime] | None = None,
) -> ReceiptAuthority | None:
    """Load a strict tracked registry. An empty shipped registry is unprovisioned."""

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
                runner=runner,
                gh=gh,
                clock=clock,
            )
        )
    return ConfiguredReceiptAuthority(authorities)
