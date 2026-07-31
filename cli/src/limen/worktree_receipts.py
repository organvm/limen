"""Exact identity binding for worktree preservation receipts.

Receipt-assisted lifecycle decisions are safe only when the durable evidence
names the same physical checkout, repository, and commit that is live now.
Legacy basename-only rows remain readable history but never authorize a
classification or removal.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
import subprocess
from typing import Any

from limen.worktree_layout import repository_storage_key


def _git(path: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def live_worktree_receipt_fields(path: Path) -> dict[str, str] | None:
    """Return the exact live identity required on a preservation receipt."""

    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError:
        return None
    top = _git(resolved, "rev-parse", "--path-format=absolute", "--show-toplevel")
    head = _git(resolved, "rev-parse", "--verify", "HEAD")
    if not top or not head:
        return None
    try:
        if Path(top).resolve(strict=True) != resolved:
            return None
        repository_key = repository_storage_key(resolved)
    except (OSError, ValueError):
        return None
    return {
        "worktree": str(resolved),
        "head": head,
        "repository_key": repository_key,
    }


def receipt_worktree_key(receipt: Mapping[str, Any]) -> str | None:
    """Return one receipt's normalized absolute worktree key, if it has one."""

    raw = receipt.get("worktree")
    if not isinstance(raw, str) or not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        return None
    try:
        return str(candidate.resolve(strict=False))
    except OSError:
        return None


def _receipt_rows(receipts: object) -> Iterable[Mapping[str, Any]]:
    if isinstance(receipts, Mapping):
        if "root" in receipts:
            values: Iterable[object] = (receipts,)
        else:
            values = receipts.values()
    elif isinstance(receipts, Iterable) and not isinstance(receipts, (str, bytes)):
        values = receipts
    else:
        values = ()
    return (value for value in values if isinstance(value, Mapping))


def matching_worktree_receipt(path: Path, receipts: object) -> Mapping[str, Any] | None:
    """Select exactly one fully bound receipt; missing or ambiguous evidence fails closed."""

    identity = live_worktree_receipt_fields(path)
    if identity is None:
        return None
    matches = [
        receipt
        for receipt in _receipt_rows(receipts)
        if receipt_worktree_key(receipt) == identity["worktree"]
        and receipt.get("head") == identity["head"]
        and receipt.get("repository_key") == identity["repository_key"]
    ]
    return matches[0] if len(matches) == 1 else None


__all__ = [
    "live_worktree_receipt_fields",
    "matching_worktree_receipt",
    "receipt_worktree_key",
]
