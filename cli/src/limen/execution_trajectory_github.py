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
from typing import Mapping, Sequence
from urllib.parse import quote

from limen.execution_trajectory import (
    OwnerPublication,
    OwnerTrajectorySnapshot,
    TrajectoryPublicationError,
)


_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


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
