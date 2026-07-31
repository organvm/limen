"""Literal Workspace manifest validation and machine-wide convergence court.

PORTVS owns the manifest.  This module deliberately owns only the court: it
validates the contract, compares it with the physical tree, discovers repository
roots recursively, and verifies the custody assertions that make a private move
safe.  Repository and private interiors remain recursively owned by Git and the
sealed inventory named by the manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import time
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import yaml

from limen.repository_ignored import ignored_entry_is_regenerable, ignored_entries_from_porcelain


SCHEMA = "portvs.workspace_manifest.v1"
REPORT_SCHEMA = "limen.substrate_convergence_report.v1"
KINDS = frozenset({"structural", "repository", "private", "ephemeral", "index"})
RESIDENCIES = frozenset({"structural", "laptop", "private", "ephemeral", "remote-index"})
OPAQUE_KINDS = frozenset({"private", "ephemeral"})
DIRECTORY_KINDS = frozenset({"structural", "repository", "private", "ephemeral"})
LIMIT_KEYS = (
    "max_scan_entries",
    "max_violations",
    "max_unmeasured",
    "max_compatibility_links",
)
GIT_TIMEOUT_SECONDS = 60
REPOSITORY_FETCH_BUDGET_SECONDS = 120.0
LSOF_TIMEOUT_SECONDS = 15
_monotonic = time.monotonic


class ManifestError(ValueError):
    """The workspace manifest is missing, malformed, or unsafe."""


class ActiveCwdDiscoveryError(RuntimeError):
    """Live process CWDs could not be measured safely."""


@dataclass(frozen=True)
class Row:
    path: str
    kind: str
    owner_ref: str
    residency: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass
class ScanBudget:
    """One shared budget for every structural, repository, and runtime scan."""

    limit: int
    consumed: int = 0

    def consume(self, count: int = 1) -> bool:
        if count < 0:
            raise ValueError("scan budget debit cannot be negative")
        if self.consumed + count > self.limit:
            return False
        self.consumed += count
        return True

    @property
    def remaining(self) -> int:
        return self.limit - self.consumed


@dataclass
class RepositoryFetchBudget:
    """One aggregate wall-clock deadline shared by every declared origin fetch."""

    limit_seconds: float
    started_at: float = field(default_factory=lambda: _monotonic())
    exhausted: bool = False

    def timeout(self) -> float | None:
        remaining = self.limit_seconds - (_monotonic() - self.started_at)
        if remaining <= 0:
            self.exhausted = True
            return None
        return min(float(GIT_TIMEOUT_SECONDS), remaining)


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_relative_path(value: object, *, field: str = "path") -> str:
    if not _nonempty_string(value):
        raise ManifestError(f"{field} must be a non-empty relative POSIX path")
    text = str(value)
    if "\\" in text:
        raise ManifestError(f"{field} {text!r} must use POSIX separators")
    pure = PurePosixPath(text)
    if pure.is_absolute() or text in {".", ".."} or any(part in {"", ".", ".."} for part in pure.parts):
        raise ManifestError(f"{field} {text!r} is not a normalized relative path")
    normalized = pure.as_posix()
    if normalized != text.rstrip("/"):
        raise ManifestError(f"{field} {text!r} is not normalized (want {normalized!r})")
    return normalized


def _required(row: Mapping[str, Any], keys: Iterable[str], *, path: str) -> None:
    missing = [key for key in keys if not _nonempty_string(row.get(key))]
    if missing:
        raise ManifestError(f"{path}: missing required field(s): {', '.join(missing)}")


def load_manifest(path: Path) -> tuple[dict[str, Any], list[Row], bytes]:
    if not path.is_file():
        raise ManifestError(f"workspace manifest missing: {path}")
    raw_bytes = path.read_bytes()
    try:
        data = yaml.safe_load(raw_bytes) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"workspace manifest is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("workspace manifest root must be a mapping")
    if data.get("schema") != SCHEMA:
        raise ManifestError(f"workspace manifest schema must be {SCHEMA!r}")
    limits = data.get("limits")
    if not isinstance(limits, dict):
        raise ManifestError("limits must be a mapping")
    missing_limits = [key for key in LIMIT_KEYS if key not in limits]
    if missing_limits:
        raise ManifestError(f"limits missing required field(s): {', '.join(missing_limits)}")
    raw_rows = data.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ManifestError("workspace manifest rows must be a non-empty list")

    rows: list[Row] = []
    seen_paths: set[str] = set()
    repository_remotes: dict[str, str] = {}
    for index, value in enumerate(raw_rows):
        if not isinstance(value, dict):
            raise ManifestError(f"rows[{index}] must be a mapping")
        _required(value, ("path", "kind", "owner_ref", "residency"), path=f"rows[{index}]")
        row_path = _safe_relative_path(value["path"])
        kind = str(value["kind"])
        residency = str(value["residency"])
        if kind not in KINDS:
            raise ManifestError(f"{row_path}: kind {kind!r} is not one of {sorted(KINDS)}")
        if residency not in RESIDENCIES:
            raise ManifestError(f"{row_path}: residency {residency!r} is not one of {sorted(RESIDENCIES)}")
        if row_path in seen_paths:
            raise ManifestError(f"duplicate manifest path: {row_path}")
        seen_paths.add(row_path)

        if kind == "repository":
            _required(value, ("remote", "custody_ref"), path=row_path)
            remote = canonical_remote(str(value["remote"]))
            if remote in repository_remotes:
                raise ManifestError(
                    f"{row_path}: remote duplicates {repository_remotes[remote]} ({remote}); "
                    "one repository has one canonical physical home"
                )
            repository_remotes[remote] = row_path
        elif kind == "ephemeral":
            _required(value, ("reaper",), path=row_path)
            if "expires_after" not in value:
                raise ManifestError(f"{row_path}: missing required field: expires_after")
            expires_after = value["expires_after"]
            if not isinstance(expires_after, int) or isinstance(expires_after, bool) or expires_after <= 0:
                raise ManifestError(f"{row_path}: expires_after must be a positive integer number of seconds")
        elif kind == "private":
            _required(
                value,
                ("sealed_inventory_ref", "restoration_receipt_ref", "custody_label"),
                path=row_path,
            )
        elif kind == "index":
            _required(value, ("source_ref", "generator"), path=row_path)

        rows.append(
            Row(
                path=row_path,
                kind=kind,
                owner_ref=str(value["owner_ref"]),
                residency=residency,
                raw=value,
            )
        )

    _validate_parent_ownership(rows)
    _validate_compatibility_rows(data)
    return data, rows, raw_bytes


def _validate_parent_ownership(rows: Sequence[Row]) -> None:
    by_path = {row.path: row for row in rows}
    for row in rows:
        parts = PurePosixPath(row.path).parts
        for depth in range(1, len(parts)):
            parent_path = PurePosixPath(*parts[:depth]).as_posix()
            parent = by_path.get(parent_path)
            if parent is None:
                raise ManifestError(
                    f"{row.path}: parent {parent_path!r} has no manifest row; structural containment must be literal"
                )
            if parent.kind != "structural":
                raise ManifestError(
                    f"{row.path}: nested below {parent.path} ({parent.kind}); "
                    "that owner's interior is opaque to the Workspace manifest"
                )


def _validate_compatibility_rows(data: Mapping[str, Any]) -> None:
    migration = data.get("migration") or {}
    if not isinstance(migration, dict):
        raise ManifestError("migration must be a mapping")
    links = migration.get("compatibility_links") or []
    if not isinstance(links, list):
        raise ManifestError("migration.compatibility_links must be a list")
    seen: set[str] = set()
    targets: dict[str, str] = {}
    for index, row in enumerate(links):
        if not isinstance(row, dict):
            raise ManifestError(f"migration.compatibility_links[{index}] must be a mapping")
        _required(row, ("path", "target", "owner_ref", "expires_at"), path=f"compatibility_links[{index}]")
        path = _safe_relative_path(row["path"], field="compatibility link path")
        target = _safe_relative_path(row["target"], field="compatibility link target")
        if path in seen:
            raise ManifestError(f"duplicate compatibility link path: {path}")
        seen.add(path)
        targets[path] = target
        try:
            datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ManifestError(f"{path}: expires_at must be an ISO-8601 timestamp") from exc
        if path == target or target.startswith(path + "/"):
            raise ManifestError(f"{path}: compatibility link target would form a cycle")

    dependencies = {
        path: {candidate for candidate in targets if target == candidate or target.startswith(candidate + "/")}
        for path, target in targets.items()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(path: str, chain: tuple[str, ...]) -> None:
        if path in visiting:
            cycle = " -> ".join((*chain, path))
            raise ManifestError(f"compatibility link graph contains a cycle: {cycle}")
        if path in visited:
            return
        visiting.add(path)
        for dependency in sorted(dependencies[path]):
            visit(dependency, (*chain, path))
        visiting.remove(path)
        visited.add(path)

    for path in sorted(targets):
        visit(path, ())


def resolve_workspace_root(data: Mapping[str, Any], override: Path | None = None) -> Path:
    if override is not None:
        root = override.expanduser()
    else:
        configured = data.get("workspace_root")
        if not _nonempty_string(configured):
            raise ManifestError("workspace_root must be a non-empty absolute path")
        root = Path(os.path.expandvars(str(configured))).expanduser()
    if not root.is_absolute():
        raise ManifestError(f"workspace root must be absolute: {root}")
    # Preserve the lexical root until the physical-directory check has run.
    # ``resolve`` here would erase the evidence that Workspace itself is a
    # symlink and make the workspace_symlink verdict unreachable.
    return Path(os.path.abspath(root))


def canonical_remote(value: str) -> str:
    text = value.strip()
    if not text:
        raise ManifestError("repository remote cannot be empty")
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text.removeprefix("git@github.com:")
    elif text.startswith("ssh://git@github.com/"):
        text = "https://github.com/" + text.removeprefix("ssh://git@github.com/")
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower() == "github.com":
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if path.count("/") != 1:
            raise ManifestError(f"GitHub remote has unexpected shape: {value!r}")
        return f"https://github.com/{path.lower()}"
    if text.startswith("file://"):
        return str(Path(parsed.path).resolve(strict=False))
    candidate_path = Path(text).expanduser()
    if candidate_path.is_absolute():
        return str(candidate_path.resolve(strict=False))
    raise ManifestError(f"unsupported repository remote: {value!r}")


def _run_git(
    repo: Path,
    *args: str,
    timeout: float = GIT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(repo), *args]
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env={
                **os.environ,
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_bounded(path: Path, *, max_symlinks: int = 64) -> Path:
    """Resolve a path without allowing a filesystem symlink loop to hang or escape measurement."""

    current = Path(os.path.abspath(path))
    seen: set[Path] = set()
    for _ in range(max_symlinks):
        parts = current.parts
        cursor = Path(parts[0])
        for index, part in enumerate(parts[1:], start=1):
            cursor /= part
            if not cursor.is_symlink():
                continue
            lexical = Path(os.path.abspath(cursor))
            if lexical in seen:
                raise RuntimeError(f"symlink loop detected at {lexical}")
            seen.add(lexical)
            raw_target = Path(os.readlink(cursor))
            target = raw_target if raw_target.is_absolute() else cursor.parent / raw_target
            current = Path(os.path.abspath(target.joinpath(*parts[index + 1 :])))
            break
        else:
            return current
    raise RuntimeError(f"symlink resolution exceeded {max_symlinks} links")


def _check_symlink_chain(root: Path, relative: str) -> Violation | None:
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if not cursor.exists() and not cursor.is_symlink():
            return None
        if cursor.is_symlink():
            try:
                target = _resolve_bounded(cursor)
            except (OSError, RuntimeError) as exc:
                return Violation(
                    "unmeasured_state",
                    relative,
                    f"cannot resolve symlink component {cursor}: {exc}",
                )
            if not _is_within(target, root):
                return Violation(
                    "symlink_escape",
                    relative,
                    f"symlink component {cursor} resolves outside the Workspace root",
                )
            return Violation(
                "structural_symlink",
                relative,
                f"canonical Workspace entries must be physical, not symlinks ({cursor})",
            )
    return None


def _expected_direct_children(rows: Sequence[Row]) -> dict[str, set[str]]:
    expected: dict[str, set[str]] = {"": set()}
    for row in rows:
        pure = PurePosixPath(row.path)
        parent = "" if str(pure.parent) == "." else pure.parent.as_posix()
        expected.setdefault(parent, set()).add(pure.name)
    return expected


def _discover_tree(
    root: Path,
    rows: Sequence[Row],
    *,
    max_scan_entries: int,
    now: datetime,
) -> tuple[list[Violation], list[str], list[dict[str, Any]], bool]:
    violations: list[Violation] = []
    repositories: list[str] = []
    ephemeral_roots: list[dict[str, Any]] = []
    truncated = False
    budget = ScanBudget(max_scan_entries)
    fetch_budget = RepositoryFetchBudget(REPOSITORY_FETCH_BUDGET_SECONDS)
    expected_children = _expected_direct_children(rows)

    if not root.is_dir():
        return (
            [Violation("workspace_missing", ".", f"Workspace root is absent: {root}")],
            repositories,
            ephemeral_roots,
            False,
        )
    if root.is_symlink():
        violations.append(Violation("workspace_symlink", ".", "Workspace root must be a physical directory"))

    structural_paths = [""] + [row.path for row in rows if row.kind == "structural"]
    for parent_rel in structural_paths:
        parent = root if not parent_rel else root / parent_rel
        if not parent.is_dir() or parent.is_symlink():
            continue
        expected = expected_children.get(parent_rel, set())
        try:
            actual_entries = parent.iterdir()
        except OSError as exc:
            violations.append(Violation("unmeasured_state", parent_rel or ".", f"cannot list directory: {exc}"))
            continue
        try:
            for child in actual_entries:
                if not budget.consume():
                    violations.append(
                        Violation(
                            "unmeasured_state",
                            parent_rel or ".",
                            f"shared scan budget exhausted after {budget.consumed} entries",
                        )
                    )
                    truncated = True
                    break
                if child.name not in expected:
                    rel = child.relative_to(root).as_posix()
                    violations.append(
                        Violation(
                            "undeclared_entry",
                            rel,
                            "entry has no Workspace manifest row",
                        )
                    )
        except OSError as exc:
            violations.append(Violation("unmeasured_state", parent_rel or ".", f"cannot list directory: {exc}"))
        if truncated:
            break

    for row in rows:
        candidate = root / row.path
        escape = _check_symlink_chain(root, row.path)
        if escape is not None:
            violations.append(escape)
            continue
        if not candidate.exists():
            violations.append(Violation("declared_entry_missing", row.path, f"declared {row.kind} is absent"))
            continue
        if row.kind in DIRECTORY_KINDS:
            if not candidate.is_dir():
                violations.append(Violation("wrong_entry_type", row.path, f"{row.kind} must be a directory"))
                continue
        elif row.kind == "index" and not candidate.is_file():
            violations.append(Violation("wrong_entry_type", row.path, "index must be a regular file"))

        if row.kind == "repository":
            repositories.append(row.path)
            violations.extend(_audit_repository(candidate, row, fetch_budget=fetch_budget))
            nested, nested_truncated = _discover_nested_repositories(
                candidate,
                row.path,
                budget=budget,
            )
            violations.extend(nested)
            if nested_truncated:
                truncated = True
        elif row.kind == "ephemeral":
            ephemeral_violations, receipt, ephemeral_truncated = _audit_ephemeral_root(
                candidate,
                row,
                now=now,
                budget=budget,
            )
            violations.extend(ephemeral_violations)
            ephemeral_roots.append(receipt)
            if ephemeral_truncated:
                truncated = True

    return violations, sorted(repositories), ephemeral_roots, truncated


def _registered_submodules(repo: Path) -> set[Path]:
    gitmodules = repo / ".gitmodules"
    if not gitmodules.is_file():
        return set()
    proc = _run_git(repo, "config", "-f", str(gitmodules), "--get-regexp", r"^submodule\..*\.path$")
    if proc.returncode not in {0, 1}:
        return set()
    result: set[Path] = set()
    for line in proc.stdout.splitlines():
        _, _, value = line.partition(" ")
        if value.strip():
            result.add((repo / value.strip()).resolve(strict=False))
    return result


def _discover_nested_repositories(
    repo: Path,
    manifest_path: str,
    *,
    budget: ScanBudget,
) -> tuple[list[Violation], bool]:
    """Find competing checkouts inside a declared repository.

    Registered Git submodules are Git-owned interiors and therefore valid.
    Ad-hoc nested clones and in-repository worktrees are competing physical
    homes and must move to ``runtime/worktrees``.
    """

    if budget.remaining <= 0:
        return [
            Violation(
                "unmeasured_state",
                manifest_path,
                "shared scan budget left no entries for recursive repository discovery",
            )
        ], True
    registered_submodules = _registered_submodules(repo)
    violations: list[Violation] = []
    for dirpath, dirnames, filenames in os.walk(repo, followlinks=False):
        current = Path(dirpath)
        if current == repo and ".git" in dirnames:
            dirnames.remove(".git")
        debit = len(dirnames) + len(filenames)
        if not budget.consume(debit):
            return (
                violations
                + [
                    Violation(
                        "unmeasured_state",
                        manifest_path,
                        f"recursive repository scan exhausted the shared budget after {budget.consumed} entries",
                    )
                ],
                True,
            )
        if current == repo:
            continue
        has_git = ".git" in dirnames or ".git" in filenames
        if has_git:
            resolved = current.resolve(strict=False)
            if resolved not in registered_submodules:
                rel = current.relative_to(repo).as_posix()
                violations.append(
                    Violation(
                        "undeclared_nested_repository",
                        f"{manifest_path}/{rel}",
                        "nested checkout is not a registered Git submodule; use the canonical "
                        "Workspace row or runtime/worktrees",
                    )
                )
            dirnames[:] = []
            continue
        dirnames[:] = [name for name in dirnames if name not in {".git", "__pycache__", "node_modules"}]
    return violations, False


def _audit_ephemeral_root(
    root: Path,
    row: Row,
    *,
    now: datetime,
    budget: ScanBudget,
) -> tuple[list[Violation], dict[str, Any], bool]:
    """Measure top-level lifecycle units and emit a bounded reaper receipt."""

    expires_after = int(row.raw["expires_after"])
    reaper = str(row.raw["reaper"])
    entry_count = 0
    expired_names: list[str] = []
    oldest_age_seconds = 0
    violations: list[Violation] = []
    truncated = False
    try:
        entries = root.iterdir()
        for entry in entries:
            if not budget.consume():
                violations.append(
                    Violation(
                        "unmeasured_state",
                        row.path,
                        f"ephemeral scan exhausted the shared budget after {budget.consumed} entries",
                    )
                )
                truncated = True
                break
            entry_count += 1
            try:
                age_seconds = max(0, int(now.timestamp() - entry.lstat().st_mtime))
            except OSError as exc:
                violations.append(
                    Violation(
                        "unmeasured_state",
                        f"{row.path}/{entry.name}",
                        f"cannot stat ephemeral lifecycle unit: {exc}",
                    )
                )
                continue
            oldest_age_seconds = max(oldest_age_seconds, age_seconds)
            if age_seconds > expires_after:
                expired_names.append(entry.name)
    except OSError as exc:
        violations.append(Violation("unmeasured_state", row.path, f"cannot list ephemeral root: {exc}"))

    if expired_names:
        sample = ", ".join(sorted(expired_names)[:5])
        violations.append(
            Violation(
                "ephemeral_entries_expired",
                row.path,
                f"{len(expired_names)} lifecycle unit(s) exceed expires_after={expires_after}; "
                f"reaper={reaper!r}; sample={sample}",
            )
        )
    receipt = {
        "path": row.path,
        "reaper": reaper,
        "expires_after": expires_after,
        "entry_count": entry_count,
        "expired_entry_count": len(expired_names),
        "oldest_age_seconds": oldest_age_seconds,
    }
    return violations, receipt, truncated


def _audit_repository(
    repo: Path,
    row: Row,
    *,
    fetch_budget: RepositoryFetchBudget,
) -> list[Violation]:
    violations: list[Violation] = []
    if not (repo / ".git").exists():
        return [Violation("repository_missing_git", row.path, "declared repository is not a Git worktree")]
    top = _run_git(repo, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve(strict=False) != repo.resolve(strict=False):
        violations.append(Violation("repository_wrong_root", row.path, "path is not the Git worktree root"))
        return violations

    live_remote_verified = False
    origin = _run_git(repo, "remote", "get-url", "origin")
    if origin.returncode != 0:
        violations.append(Violation("repository_remote_missing", row.path, "origin remote is unavailable"))
    else:
        try:
            actual_remote = canonical_remote(origin.stdout.strip())
            expected_remote = canonical_remote(str(row.raw["remote"]))
            if actual_remote != expected_remote:
                violations.append(
                    Violation(
                        "repository_remote_mismatch",
                        row.path,
                        f"origin is {actual_remote}, manifest requires {expected_remote}",
                    )
                )
            else:
                fetch_timeout = fetch_budget.timeout()
                if fetch_timeout is None:
                    violations.append(
                        Violation(
                            "repository_unmeasured",
                            row.path,
                            "aggregate repository fetch deadline exhausted; "
                            "custody and preservation cannot be accepted",
                        )
                    )
                else:
                    fetch = _run_git(
                        repo,
                        "fetch",
                        "--prune",
                        "--no-tags",
                        "origin",
                        "+refs/heads/*:refs/remotes/origin/*",
                        timeout=fetch_timeout,
                    )
                    if fetch.returncode != 0:
                        violations.append(
                            Violation(
                                "repository_unmeasured",
                                row.path,
                                "live origin fetch failed within the aggregate deadline; "
                                "custody and preservation cannot be accepted",
                            )
                        )
                    else:
                        live_remote_verified = True
        except ManifestError as exc:
            violations.append(Violation("repository_remote_invalid", row.path, str(exc)))

    custody_ref = str(row.raw["custody_ref"])
    if not custody_ref.startswith("refs/remotes/origin/"):
        violations.append(
            Violation(
                "repository_custody_invalid",
                row.path,
                "custody_ref must name the freshly fetched refs/remotes/origin namespace",
            )
        )
    elif live_remote_verified:
        custody = _run_git(repo, "rev-parse", "--verify", "--quiet", f"{custody_ref}^{{commit}}")
        if custody.returncode != 0:
            violations.append(
                Violation("repository_custody_missing", row.path, f"live custody ref is absent: {custody_ref}")
            )

    status = _run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        violations.append(Violation("repository_unmeasured", row.path, "git status failed"))
    elif status.stdout.strip():
        violations.append(Violation("repository_dirty", row.path, "repository has tracked or untracked changes"))

    ignored_status = _run_git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--ignored=matching",
        "--untracked-files=all",
    )
    if ignored_status.returncode != 0:
        violations.append(Violation("repository_unmeasured", row.path, "cannot enumerate ignored entries"))
    else:
        ignored_entries = ignored_entries_from_porcelain(ignored_status.stdout)
        uncustodied = sorted(path for path in ignored_entries if not ignored_entry_is_regenerable(path))
        if uncustodied:
            sample = ", ".join(uncustodied[:10])
            violations.append(
                Violation(
                    "repository_uncustodied_ignored",
                    row.path,
                    f"{len(uncustodied)} ignored entry or subtree root(s) lack explicit "
                    f"regenerable evidence or custody: {sample}",
                )
            )

    if live_remote_verified:
        remote_refs_result = _run_git(
            repo,
            "for-each-ref",
            "--format=%(refname)",
            "refs/remotes/origin",
        )
        if remote_refs_result.returncode != 0:
            violations.append(
                Violation("repository_unmeasured", row.path, "cannot enumerate freshly fetched origin refs")
            )
        else:
            remote_refs = [ref for ref in remote_refs_result.stdout.splitlines() if ref and not ref.endswith("/HEAD")]
            head_contains = _run_git(
                repo,
                "for-each-ref",
                "--format=%(refname)",
                "--contains",
                "HEAD",
                "refs/remotes/origin",
            )
            if head_contains.returncode != 0 or not any(
                ref and not ref.endswith("/HEAD") for ref in head_contains.stdout.splitlines()
            ):
                violations.append(
                    Violation(
                        "repository_unpreserved",
                        row.path,
                        "exact HEAD is not reachable from any freshly fetched live origin ref",
                    )
                )
            violations.extend(_audit_local_branch_custody(repo, row.path, remote_refs))
            violations.extend(_audit_stash_custody(repo, row.path, remote_refs))
    return violations


def _unreachable_commit_count(repo: Path, commitish: str, remote_refs: Sequence[str]) -> int | None:
    args = ["rev-list", "--count", commitish]
    if remote_refs:
        args.extend(["--not", *remote_refs])
    result = _run_git(repo, *args)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _audit_local_branch_custody(
    repo: Path,
    manifest_path: str,
    remote_refs: Sequence[str],
) -> list[Violation]:
    branches = _run_git(repo, "for-each-ref", "--format=%(refname)", "refs/heads")
    if branches.returncode != 0:
        return [Violation("repository_unmeasured", manifest_path, "cannot enumerate local branches")]
    unpreserved: list[tuple[str, int]] = []
    for ref in branches.stdout.splitlines():
        if not ref:
            continue
        count = _unreachable_commit_count(repo, ref, remote_refs)
        if count is None:
            return [
                Violation(
                    "repository_unmeasured",
                    manifest_path,
                    f"cannot measure local branch custody for {ref.removeprefix('refs/heads/')}",
                )
            ]
        if count:
            unpreserved.append((ref.removeprefix("refs/heads/"), count))
    if not unpreserved:
        return []
    summary = ", ".join(f"{name}={count}" for name, count in sorted(unpreserved)[:10])
    return [
        Violation(
            "repository_unpreserved_branches",
            manifest_path,
            f"{len(unpreserved)} local branch(es) contain commits absent from live origin refs: {summary}",
        )
    ]


def _audit_stash_custody(
    repo: Path,
    manifest_path: str,
    remote_refs: Sequence[str],
) -> list[Violation]:
    stash_ref = _run_git(repo, "rev-parse", "--verify", "--quiet", "refs/stash")
    if stash_ref.returncode == 1 and not stash_ref.stderr.strip():
        return []
    if stash_ref.returncode != 0:
        return [Violation("repository_unmeasured", manifest_path, "cannot inspect refs/stash")]
    reflog = _run_git(repo, "reflog", "show", "--format=%H", "refs/stash")
    if reflog.returncode != 0:
        return [Violation("repository_unmeasured", manifest_path, "cannot enumerate stash custody")]
    stash_commits = sorted({commit for commit in reflog.stdout.splitlines() if commit})
    uncustodied = 0
    for commit in stash_commits:
        count = _unreachable_commit_count(repo, commit, remote_refs)
        if count is None:
            return [Violation("repository_unmeasured", manifest_path, "cannot measure stash custody")]
        if count:
            uncustodied += 1
    if not uncustodied:
        return []
    return [
        Violation(
            "repository_uncustodied_stashes",
            manifest_path,
            f"{uncustodied} stash snapshot(s) are not reachable from freshly fetched live origin refs",
        )
    ]


def _resolve_reference(
    ref: str,
    *,
    manifest_path: Path,
    workspace_root: Path,
    rows: Sequence[Row],
) -> tuple[Path, str | None]:
    path_text, separator, fragment = ref.partition("#")
    if path_text.startswith("workspace://"):
        relative = _safe_relative_path(path_text.removeprefix("workspace://"), field="workspace reference")
        path = workspace_root / relative
        if not path.exists():
            # During migration, references may resolve through the declared
            # repository's unique legacy home. The canonical row still remains
            # absent and therefore red until the physical move completes.
            candidates: list[Path] = []
            for owner in sorted(rows, key=lambda item: len(PurePosixPath(item.path).parts), reverse=True):
                if owner.kind != "repository":
                    continue
                prefix = owner.path + "/"
                if relative != owner.path and not relative.startswith(prefix):
                    continue
                suffix = relative.removeprefix(owner.path).lstrip("/")
                for legacy in owner.raw.get("legacy_paths") or []:
                    legacy_rel = _safe_relative_path(legacy, field=f"{owner.path} legacy path")
                    candidate = workspace_root / legacy_rel
                    if suffix:
                        candidate /= suffix
                    if candidate.exists():
                        candidates.append(candidate)
                break
            unique = {candidate.resolve(strict=False) for candidate in candidates}
            if len(unique) == 1:
                path = unique.pop()
    elif path_text.startswith("manifest://"):
        relative = _safe_relative_path(path_text.removeprefix("manifest://"), field="manifest reference")
        path = manifest_path.parent / relative
    elif path_text.startswith("file://"):
        path = Path(urlparse(path_text).path)
    else:
        path = Path(path_text)
        if not path.is_absolute():
            path = manifest_path.parent / path
    return path.resolve(strict=False), fragment if separator else None


def _read_receipt_rows(
    path: Path,
    *,
    collection_keys: Sequence[str] = ("receipts",),
) -> list[Mapping[str, Any]]:
    if not path.is_file():
        return []
    try:
        if path.suffix == ".jsonl":
            rows: list[Mapping[str, Any]] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
            return rows
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in collection_keys:
            nested = value.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
        return [value]
    return []


def _copy_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _audit_private_custody(
    manifest_path: Path,
    workspace_root: Path,
    rows: Sequence[Row],
) -> tuple[list[Violation], list[dict[str, Any]]]:
    violations: list[Violation] = []
    receipts: list[dict[str, Any]] = []
    for row in rows:
        if row.kind != "private":
            continue
        inventory, inventory_fragment = _resolve_reference(
            str(row.raw["sealed_inventory_ref"]),
            manifest_path=manifest_path,
            workspace_root=workspace_root,
            rows=rows,
        )
        receipt_path, fragment = _resolve_reference(
            str(row.raw["restoration_receipt_ref"]),
            manifest_path=manifest_path,
            workspace_root=workspace_root,
            rows=rows,
        )
        label = str(row.raw["custody_label"])
        inventory_available = inventory.is_file()
        inventory_rows = _read_receipt_rows(
            inventory,
            collection_keys=("sealed_inventories", "inventories"),
        )
        inventory_label_matches = inventory_fragment in {None, label}
        sealed_inventory = next(
            (
                candidate
                for candidate in inventory_rows
                if str(candidate.get("label", candidate.get("custody_label", ""))) == label
                and candidate.get("sealed") is True
            ),
            None,
        )
        inventory_verified = inventory_label_matches and sealed_inventory is not None
        if not inventory_available:
            violations.append(
                Violation("private_inventory_missing", row.path, "sealed inventory reference is unavailable")
            )
        elif not inventory_verified:
            violations.append(
                Violation(
                    "private_inventory_unverified",
                    row.path,
                    "sealed inventory has no matching custody_label entry with sealed=true",
                )
            )
        receipt_label_matches = fragment in {None, label}
        candidates = [
            candidate for candidate in _read_receipt_rows(receipt_path) if str(candidate.get("label", "")) == label
        ]
        valid = next(
            (
                candidate
                for candidate in candidates
                if candidate.get("restoration_passed") is True
                and _copy_count(candidate.get("copy_count", 0)) >= 2
                and candidate.get("independent_physical_devices") is True
            ),
            None,
        )
        restoration_verified = receipt_label_matches and valid is not None
        receipts.append(
            {
                "path": row.path,
                "custody_label": label,
                "inventory_available": inventory_available,
                "sealed_inventory_verified": inventory_verified,
                "restoration_receipt_available": receipt_path.is_file(),
                "restoration_verified": restoration_verified,
                "custody_verified": inventory_verified and restoration_verified,
            }
        )
        if not restoration_verified:
            violations.append(
                Violation(
                    "private_restoration_unverified",
                    row.path,
                    "no matching two-copy, independent-device, restoration-passed receipt",
                )
            )
    return violations, receipts


def _compatibility_violations(
    data: Mapping[str, Any],
    root: Path,
    *,
    now: datetime,
    active_cwds: Sequence[Path],
) -> tuple[list[Violation], list[dict[str, Any]]]:
    violations: list[Violation] = []
    report: list[dict[str, Any]] = []
    migration = data.get("migration") or {}
    for raw in migration.get("compatibility_links") or []:
        rel = str(raw["path"])
        target_rel = str(raw["target"])
        path = root / rel
        target = root / target_rel
        expires = datetime.fromisoformat(str(raw["expires_at"]).replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        # Compare lexical paths. Resolving the compatibility symlink makes its
        # prefix indistinguishable from the canonical target and falsely
        # classifies canonical consumers as legacy users.
        active = sorted(str(cwd) for cwd in active_cwds if _is_within(cwd, path))
        # Once the doorway itself is a symlink, the kernel retains only the
        # physical cwd inode. Tools such as macOS lsof therefore report the
        # canonical target for both direct consumers and processes that entered
        # through the legacy doorway. Do not call those consumers legacy, but
        # also do not silently accept removal while their lexical entry path is
        # unknowable.
        ambiguous = sorted(
            str(cwd)
            for cwd in active_cwds
            if path.is_symlink() and _is_within(cwd, target) and not _is_within(cwd, path)
        )
        present = path.exists() or path.is_symlink()
        resolution_error: str | None = None
        correct = False
        if path.is_symlink():
            try:
                correct = _resolve_bounded(path) == _resolve_bounded(target)
            except (OSError, RuntimeError) as exc:
                resolution_error = str(exc)
        report.append(
            {
                "path": rel,
                "target": target_rel,
                "present": present,
                "correct": correct,
                "expired": now.astimezone(UTC) >= expires.astimezone(UTC),
                "active_cwd_count": len(active),
                "ambiguous_cwd_count": len(ambiguous),
            }
        )
        if path.exists() or path.is_symlink():
            violations.append(
                Violation(
                    "compatibility_link_unresolved",
                    rel,
                    "temporary compatibility doorway remains; final architecture requires zero",
                )
            )
            if not correct:
                violations.append(Violation("compatibility_link_mismatch", rel, f"link must resolve to {target_rel}"))
            if resolution_error is not None:
                violations.append(
                    Violation(
                        "unmeasured_state",
                        rel,
                        f"compatibility symlink resolution failed closed: {resolution_error}",
                    )
                )
        if active:
            violations.append(
                Violation(
                    "active_legacy_path",
                    rel,
                    f"{len(active)} active process cwd(s) still depend on this compatibility path",
                )
            )
        if ambiguous:
            violations.append(
                Violation(
                    "unmeasured_state",
                    rel,
                    f"{len(ambiguous)} canonical-target cwd(s) have no observable lexical entry path; "
                    "compatibility removal must wait until they close",
                )
            )
        if present and now.astimezone(UTC) >= expires.astimezone(UTC):
            violations.append(Violation("compatibility_link_expired", rel, "compatibility link has expired"))
    return violations, report


def collect_active_cwds() -> list[Path]:
    command = ["lsof", "-a", "-d", "cwd", "-F", "n"]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=LSOF_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ActiveCwdDiscoveryError(f"lsof unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise ActiveCwdDiscoveryError(f"lsof exited {proc.returncode}")
    raw_paths = [Path(line[1:]) for line in proc.stdout.splitlines() if line.startswith("n/")]
    if not raw_paths:
        raise ActiveCwdDiscoveryError("lsof returned no absolute CWD records")
    return _normalize_active_cwds(raw_paths)


def _normalize_active_cwds(values: Sequence[Path]) -> list[Path]:
    result: set[Path] = set()
    for item in values:
        expanded = item.expanduser()
        if not expanded.is_absolute():
            raise ManifestError("active CWD entries must be absolute")
        # abspath/normpath removes lexical "." and ".." without dereferencing a
        # compatibility link. That lexical prefix is the dependency evidence.
        result.add(Path(os.path.abspath(expanded)))
    return sorted(result, key=str)


def load_active_cwds(path: Path) -> list[Path]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"active CWD fixture is invalid: {path}: {exc}") from exc
    if not isinstance(value, list) or not all(_nonempty_string(item) for item in value):
        raise ManifestError("active CWD fixture must be a JSON array of absolute paths")
    raw_paths = [Path(str(item)).expanduser() for item in value]
    if any(not item.is_absolute() for item in raw_paths):
        raise ManifestError("active CWD fixture entries must be absolute")
    return _normalize_active_cwds(raw_paths)


def audit(
    manifest_path: Path,
    *,
    workspace_root: Path | None = None,
    active_cwds: Sequence[Path] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    data, rows, manifest_bytes = load_manifest(manifest_path)
    root = resolve_workspace_root(data, workspace_root)
    limits = data["limits"]
    if not isinstance(limits, dict):
        raise ManifestError("limits must be a mapping")
    max_scan_entries = limits["max_scan_entries"]
    if not isinstance(max_scan_entries, int) or isinstance(max_scan_entries, bool) or max_scan_entries <= 0:
        raise ManifestError("limits.max_scan_entries must be a positive integer")
    max_violations = limits["max_violations"]
    max_unmeasured = limits["max_unmeasured"]
    max_compatibility_links = limits["max_compatibility_links"]
    for key, value in (
        ("max_violations", max_violations),
        ("max_unmeasured", max_unmeasured),
        ("max_compatibility_links", max_compatibility_links),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ManifestError(f"limits.{key} must be a non-negative integer")

    audit_now = now or datetime.now(UTC)
    if audit_now.tzinfo is None:
        audit_now = audit_now.replace(tzinfo=UTC)
    violations, repositories, ephemeral_roots, truncated = _discover_tree(
        root,
        rows,
        max_scan_entries=max_scan_entries,
        now=audit_now,
    )
    custody_violations, custody = _audit_private_custody(manifest_path, root, rows)
    violations.extend(custody_violations)
    if active_cwds is None:
        try:
            measured_cwds = collect_active_cwds()
        except ActiveCwdDiscoveryError as exc:
            measured_cwds = []
            violations.append(
                Violation(
                    "unmeasured_state",
                    ".",
                    f"active CWD discovery failed closed: {exc}",
                )
            )
    else:
        measured_cwds = _normalize_active_cwds(list(active_cwds))
    compat_violations, compatibility = _compatibility_violations(
        data,
        root,
        now=audit_now,
        active_cwds=measured_cwds,
    )
    violations.extend(compat_violations)

    unmeasured_count = sum(v.code in {"unmeasured_state", "repository_unmeasured"} for v in violations)
    compatibility_count = sum(1 for row in compatibility if row["present"])
    if len(violations) > max_violations:
        violations.append(
            Violation(
                "residue_cap_breached",
                ".",
                f"violations={len(violations)} exceeds max_violations={max_violations}",
            )
        )
    if unmeasured_count > max_unmeasured:
        violations.append(
            Violation(
                "unmeasured_cap_breached",
                ".",
                f"unmeasured={unmeasured_count} exceeds max_unmeasured={max_unmeasured}",
            )
        )
    if compatibility_count > max_compatibility_links:
        violations.append(
            Violation(
                "compatibility_cap_breached",
                ".",
                f"compatibility_links={compatibility_count} exceeds max_compatibility_links={max_compatibility_links}",
            )
        )

    ordered = sorted(violations, key=lambda item: (item.path, item.code, item.message))
    root_text = str(root)
    try:
        root_stat = root.stat()
        root_device: int | None = root_stat.st_dev
        root_inode: int | None = root_stat.st_ino
    except OSError:
        root_device = None
        root_inode = None
    return {
        "schema": REPORT_SCHEMA,
        "ok": not ordered,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "workspace_root": str(root),
        "workspace_root_identity": {
            "lexical_sha256": hashlib.sha256(root_text.encode("utf-8")).hexdigest(),
            "device": root_device,
            "inode": root_inode,
        },
        "counts": {
            "manifest_rows": len(rows),
            "repositories": len(repositories),
            "private_roots": sum(row.kind == "private" for row in rows),
            "compatibility_links": compatibility_count,
            "violations": len(ordered),
            "unmeasured": unmeasured_count,
        },
        "scan_truncated": truncated,
        "repositories": repositories,
        "ephemeral_roots": ephemeral_roots,
        "private_custody": custody,
        "compatibility_links": compatibility,
        "violations": [item.as_dict() for item in ordered],
    }


def render_text(report: Mapping[str, Any]) -> str:
    verdict = "OK" if report["ok"] else "FAIL"
    counts = report["counts"]
    lines = [
        f"substrate-convergence: {verdict}",
        f"  root: {report['workspace_root']}",
        f"  manifest: sha256:{report['manifest_sha256']}",
        (
            "  counts: "
            f"rows={counts['manifest_rows']} repositories={counts['repositories']} "
            f"private={counts['private_roots']} compatibility={counts['compatibility_links']} "
            f"violations={counts['violations']} unmeasured={counts['unmeasured']}"
        ),
    ]
    for violation in report["violations"]:
        lines.append(f"  [{violation['code']}] {violation['path']}: {violation['message']}")
    return "\n".join(lines)
