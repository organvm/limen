"""Canonical placement for disposable Git worktrees.

The literal Workspace tree owns worktrees as ephemeral lifecycle units.  A
repository's remote identity (or, for a repository without a remote, its root
commit identity) supplies a collision-resistant namespace so repositories with
the same basename never share a slug directory.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit


_SAFE_KEY_RE = re.compile(r"[^a-z0-9._-]+")
_SCP_REMOTE_RE = re.compile(r"^(?P<user>[^@/:]+@)?(?P<host>[^/:]+):(?P<path>.+)$")
_SLUG_RE = re.compile(r"^[a-z0-9_][a-z0-9._-]*$")


def canonical_workspace_root(configured: str | None = None) -> Path:
    """Expand variables and ``~`` before binding a lexical absolute root."""

    value = configured if configured is not None else os.environ.get("WORKSPACE_ROOT", "~/Workspace")
    expanded = os.path.expanduser(os.path.expandvars(value))
    return Path(os.path.abspath(expanded))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _canonical_remote(remote: str) -> tuple[str, str]:
    """Return a credential-free identity and a human-readable repository label."""

    text = remote.strip().rstrip("/")
    scp_match = _SCP_REMOTE_RE.fullmatch(text)
    if scp_match and "://" not in text:
        text = f"ssh://{scp_match.group('host')}/{scp_match.group('path')}"

    parsed = urlsplit(text)
    if parsed.scheme:
        if parsed.scheme == "file":
            path = Path(parsed.path).expanduser().resolve(strict=False)
            identity = f"file://{path}"
            parts = path.parts
        else:
            hostname = (parsed.hostname or "").lower()
            port = f":{parsed.port}" if parsed.port else ""
            path_text = parsed.path.rstrip("/")
            if path_text.endswith(".git"):
                path_text = path_text[:-4]
            identity = urlunsplit((parsed.scheme.lower(), f"{hostname}{port}", path_text, "", ""))
            parts = tuple(part for part in path_text.split("/") if part)
    else:
        path = Path(text).expanduser().resolve(strict=False)
        identity = f"file://{path}"
        parts = path.parts

    label_parts = [part.removesuffix(".git") for part in parts[-2:]]
    label = "--".join(label_parts) or "repository"
    return identity, label


def repository_storage_key(repo: Path) -> str:
    """Derive a stable, collision-resistant directory key for one repository."""

    repository = repo.resolve(strict=True)
    remote = _git(repository, "remote", "get-url", "origin")
    if remote:
        identity, label = _canonical_remote(remote)
        identity = f"origin:{identity}"
    else:
        roots = sorted(line for line in _git(repository, "rev-list", "--max-parents=0", "--all").splitlines() if line)
        if roots:
            identity = "roots:" + ",".join(roots)
        else:
            common = _git(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
            identity = f"common:{Path(common).resolve(strict=False)}"
        label = repository.name

    safe_label = _SAFE_KEY_RE.sub("-", label.lower()).strip("-._") or "repository"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"{safe_label}--{digest}"


def _validate_slug(slug: str) -> None:
    if slug in {".", ".."} or _SLUG_RE.fullmatch(slug) is None:
        raise ValueError("worktree slug must be one safe lowercase path component")


def _validate_runtime_container(root: Path, namespace: Path) -> None:
    """Reject an existing symlink or non-directory in the canonical container chain."""

    runtime_root = root / "runtime" / "worktrees"
    for candidate in (root, root / "runtime", runtime_root, namespace):
        if candidate.is_symlink():
            raise ValueError(f"canonical worktree container must be physical: {candidate}")
        if candidate.exists() and not candidate.is_dir():
            raise ValueError(f"canonical worktree container must be a directory: {candidate}")
    physical_root = root.resolve(strict=False)
    if not runtime_root.resolve(strict=False).is_relative_to(physical_root):
        raise ValueError("canonical runtime worktree root escapes WORKSPACE_ROOT")
    if not namespace.resolve(strict=False).is_relative_to(physical_root):
        raise ValueError("canonical repository namespace escapes WORKSPACE_ROOT")


def runtime_worktree_path(
    repo: Path,
    slug: str,
    *,
    workspace_root: Path | None = None,
) -> Path:
    """Return the canonical physical home for ``repo``'s worktree ``slug``."""

    _validate_slug(slug)
    root = workspace_root if workspace_root is not None else canonical_workspace_root()
    namespace = root / "runtime" / "worktrees" / repository_storage_key(repo)
    _validate_runtime_container(root, namespace)
    return namespace / slug
