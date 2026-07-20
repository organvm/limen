#!/usr/bin/env python3
"""Preserve dirty worktree debt as owner-blocker receipts.

This is a custody helper, not a cleanup helper. It captures a private patch and
bounded public metadata for dirty worktrees, then records an owner-blocker receipt
in docs/worktree-preservation-receipts.json. Physical removal still belongs to the
reclaim acceptance surface after a human/owner decision.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.worktree_debt import worktree_debt_report  # noqa: E402

PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"
PRIVATE_SESSION_CORPUS = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
).expanduser()
PRIVATE_ROOT = PRIVATE_SESSION_CORPUS / "lifecycle" / "worktree-preserve"
ARCHIVE_ROOT = Path(
    os.environ.get(
        "LIMEN_WORKTREE_PRESERVE_ARCHIVE",
        "/Volumes/Archive4T/limen-private/worktree-preserve",
    )
).expanduser()
REMOTE_RE = re.compile(r"(?:github\.com[:/])([^/\s]+)/([^/\s]+?)(?:\.git)?$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(value: str) -> str:
    cleaned = SAFE_NAME_RE.sub("-", value.strip()).strip("-._")
    return cleaned[:80] or "worktree"


def run_git(path: Path, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_slug(remote: str) -> str | None:
    match = REMOTE_RE.search(remote.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def git_lines(path: Path, args: list[str], timeout: int = 60) -> list[str]:
    proc = run_git(path, args, timeout=timeout)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def load_receipts() -> dict[str, Any]:
    try:
        data = json.loads(PRESERVATION_RECEIPTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"generated_utc": utc_now(), "receipts": []}
    if not isinstance(data, dict):
        return {"generated_utc": utc_now(), "receipts": []}
    data.setdefault("receipts", [])
    return data


def recorded_private_path(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(PRIVATE_SESSION_CORPUS.resolve())
    except (OSError, ValueError):
        return str(path)
    return str(Path(".limen-private") / "session-corpus" / relative)


def tree_payload_digest(path: Path, *, exclude: set[str] | None = None) -> str:
    excluded = exclude or set()
    digest = hashlib.sha256()
    for child in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = child.relative_to(path).as_posix()
        if relative in excluded:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_sha256(child)))
    return digest.hexdigest()


def trees_match(source: Path, destination: Path) -> bool:
    source_files = {
        child.relative_to(source).as_posix(): file_sha256(child) for child in source.rglob("*") if child.is_file()
    }
    destination_files = {
        child.relative_to(destination).as_posix(): file_sha256(child)
        for child in destination.rglob("*")
        if child.is_file()
    }
    return bool(source_files) and source_files == destination_files


def archive_private_dir(private_dir: Path, archive_root: Path) -> tuple[Path, bool]:
    archive_dir = archive_root / private_dir.name
    archive_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(private_dir, archive_dir, dirs_exist_ok=True, copy_function=shutil.copy2)
    return archive_dir, trees_match(private_dir, archive_dir)


def public_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt_id = Path(str(receipt["private_receipt"])).parent.name
    return {
        "archive_readback_verified": receipt.get("archive_readback_verified") is True,
        "archive_receipt": f"archive://worktree-preserve/{receipt_id}",
        "archive_status": receipt.get("archive_status"),
        "branch": receipt.get("branch"),
        "classification": receipt.get("classification"),
        "dirty_patch_bytes": receipt.get("dirty_patch_bytes"),
        "dirty_paths_count": receipt.get("dirty_paths_count"),
        "evidence_updated_utc": receipt.get("evidence_updated_utc"),
        "head_prefix": str(receipt.get("head") or "")[:12],
        "lane": receipt.get("lane"),
        "next_action": receipt.get("next_action"),
        "private_receipt": f"private://worktree-preserve/{receipt_id}",
        "repo": receipt.get("repo"),
        "root": receipt.get("root"),
        "status": receipt.get("status"),
        "untracked_paths_count": receipt.get("untracked_paths_count"),
    }


def preserve_item(
    item: dict[str, Any],
    stamp: str,
    apply: bool,
    *,
    archive_root: Path = ARCHIVE_ROOT,
    require_archive: bool = False,
) -> dict[str, Any]:
    path = Path(str(item["path"]))
    root = str(item.get("name") or path.name)
    branch = run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    head = run_git(path, ["rev-parse", "HEAD"]).stdout.strip()
    remote = run_git(path, ["remote", "get-url", "origin"]).stdout.strip()
    status_branch = run_git(path, ["status", "--short", "--branch"]).stdout
    status_porcelain = run_git(path, ["status", "--porcelain=v1"]).stdout
    dirty_paths = git_lines(path, ["diff", "--name-only", "HEAD"], timeout=120)
    untracked_paths = git_lines(path, ["ls-files", "--others", "--exclude-standard"], timeout=120)
    patch = run_git(path, ["diff", "--binary", "HEAD"], timeout=180).stdout
    private_dir = PRIVATE_ROOT / f"{stamp}-{safe_name(root)}"
    private_patch = private_dir / "dirty.patch"
    private_receipt = private_dir / "receipt.json"
    if apply:
        private_dir.mkdir(parents=True, exist_ok=True)
        (private_dir / "status-branch.txt").write_text(status_branch, encoding="utf-8", errors="replace")
        (private_dir / "status-porcelain.txt").write_text(status_porcelain, encoding="utf-8", errors="replace")
        (private_dir / "dirty-paths.txt").write_text("\n".join(dirty_paths) + "\n", encoding="utf-8")
        (private_dir / "untracked-paths.txt").write_text("\n".join(untracked_paths) + "\n", encoding="utf-8")
        private_patch.write_text(patch, encoding="utf-8", errors="replace")
    patch_sha = file_sha256(private_patch) if apply else sha256_text(patch)
    receipt = {
        "branch": branch,
        "classification": "dirty worktree privately preserved; owner decision required",
        "dirty_patch_bytes": len(patch.encode("utf-8", errors="replace")),
        "dirty_patch_command": "git diff --binary HEAD",
        "dirty_patch_sha256": patch_sha,
        "dirty_paths_count": len(dirty_paths),
        "dirty_paths_sha256": sha256_text("\n".join(sorted(dirty_paths))),
        "dirty_paths_sample": dirty_paths[:25],
        "evidence_updated_utc": utc_now(),
        "head": head,
        "lane": "owner-blocker",
        "next_action": (
            "Do not delete, reclaim, force-push, or auto-port this worktree from lifecycle cleanup. "
            "A private patch/status receipt exists; create a narrow owner packet to review, push, "
            "supersede, or retire this preserved dirty state."
        ),
        "private_patch": recorded_private_path(private_patch),
        "private_patch_sha256": patch_sha,
        "private_receipt": recorded_private_path(private_receipt),
        "repo": repo_slug(remote) or remote,
        "root": root,
        "status": "private_patch_preserved",
        "untracked_paths_count": len(untracked_paths),
        "untracked_paths_sha256": sha256_text("\n".join(sorted(untracked_paths))),
        "untracked_paths_sample": untracked_paths[:25],
        "worktree": str(path),
        "worktree_status": status_branch.splitlines(),
    }
    if apply:
        archive_dir = archive_root / private_dir.name
        receipt.update(
            {
                "archive_path": str(archive_dir),
                "archive_payload_sha256": tree_payload_digest(private_dir),
                "archive_readback_verified": False,
                "archive_status": "pending",
            }
        )
        private_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            archive_dir, first_readback_ok = archive_private_dir(private_dir, archive_root)
            receipt["archive_readback_verified"] = first_readback_ok
            receipt["archive_status"] = "verified" if first_readback_ok else "readback_mismatch"
        except OSError as exc:
            receipt["archive_status"] = f"error:{exc.__class__.__name__}"
            first_readback_ok = False
        private_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        final_readback_ok = False
        if first_readback_ok:
            try:
                _, final_readback_ok = archive_private_dir(private_dir, archive_root)
            except OSError:
                final_readback_ok = False
        if not final_readback_ok:
            receipt["archive_readback_verified"] = False
            receipt["archive_status"] = "readback_mismatch"
            private_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            try:
                archive_private_dir(private_dir, archive_root)
            except OSError:
                pass
        if require_archive and not final_readback_ok:
            raise RuntimeError(f"Archive4T readback failed for {root}")
    return receipt


def select_dirty_items(
    report: dict[str, Any],
    requested_roots: list[str],
    *,
    limit: int,
    dirty_checker: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    def live_dirty(item: dict[str, Any]) -> bool:
        path = Path(str(item.get("path") or ""))
        status = run_git(path, ["status", "--porcelain=v1"])
        return status.returncode == 0 and bool(status.stdout.strip())

    check_dirty = dirty_checker or live_dirty
    items = [item for item in report.get("items", []) if isinstance(item, dict)]
    if requested_roots:
        requested = set(requested_roots)
        selected = [item for item in items if str(item.get("name")) in requested and check_dirty(item)]
        found = {str(item.get("name")) for item in selected}
        missing = sorted(requested - found)
    else:
        selected = [item for item in items if item.get("reason") == "dirty" and item.get("debt")]
        missing = []
    if limit > 0:
        selected = selected[:limit]
    return selected, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write private receipts and update preservation ledger")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--limit", type=int, default=0, help="maximum dirty roots to preserve; 0 means all")
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="preserve one exact dirty worktree root name; repeat for multiple roots",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=ARCHIVE_ROOT,
        help="external additive archive for private patch receipts",
    )
    parser.add_argument(
        "--require-archive",
        action="store_true",
        help="fail unless the private receipt is copied to and read back from the external archive",
    )
    args = parser.parse_args()
    if args.require_archive and not args.apply:
        parser.error("--require-archive requires --apply")

    report = worktree_debt_report(ROOT)
    dirty, missing = select_dirty_items(report, args.root, limit=args.limit)
    if missing:
        parser.error(f"requested root is not currently dirty: {', '.join(missing)}")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    receipts = [
        preserve_item(
            item,
            stamp,
            args.apply,
            archive_root=args.archive_root.expanduser(),
            require_archive=args.require_archive,
        )
        for item in dirty
    ]
    updated = 0
    if args.apply and receipts:
        data = load_receipts()
        receipt_rows = data.setdefault("receipts", [])
        by_root = {str(row.get("root")): row for row in receipt_rows if isinstance(row, dict)}
        for receipt in receipts:
            tracked_receipt = public_receipt(receipt)
            existing = by_root.get(str(tracked_receipt.get("root")))
            if existing is None:
                receipt_rows.append(tracked_receipt)
                updated += 1
            elif existing != tracked_receipt:
                existing.clear()
                existing.update(tracked_receipt)
                updated += 1
        data["generated_utc"] = utc_now()
        PRESERVATION_RECEIPTS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {
        "apply": bool(args.apply),
        "requested": len(dirty),
        "updated": updated,
        "roots": [receipt.get("root") for receipt in receipts],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "APPLY" if args.apply else "dry-run"
        print(f"worktree dirty preserve [{mode}]: {len(dirty)} root(s), updated {updated}")
        for root in payload["roots"][:40]:
            print(f"  {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
