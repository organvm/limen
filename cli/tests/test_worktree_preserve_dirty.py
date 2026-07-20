from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "worktree-preserve-dirty.py"


def load_module():
    spec = importlib.util.spec_from_file_location("worktree_preserve_dirty", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_exact_dirty_root_archive_is_checksum_verified(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "tracked.txt").write_text("before\n", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", "base")
    (repo / "tracked.txt").write_text("after\n", encoding="utf-8")

    private_corpus = tmp_path / "private" / "session-corpus"
    module.PRIVATE_SESSION_CORPUS = private_corpus
    module.PRIVATE_ROOT = private_corpus / "lifecycle" / "worktree-preserve"
    archive_root = tmp_path / "archive"
    receipt = module.preserve_item(
        {"name": "target-root", "path": str(repo)},
        "2026-07-19T000000Z",
        True,
        archive_root=archive_root,
        require_archive=True,
    )

    source = module.PRIVATE_ROOT / "2026-07-19T000000Z-target-root"
    destination = archive_root / source.name
    assert receipt["archive_readback_verified"] is True
    assert receipt["archive_status"] == "verified"
    assert receipt["private_patch"].startswith(".limen-private/session-corpus/")
    assert module.trees_match(source, destination)
    assert (destination / "dirty.patch").read_bytes() == (source / "dirty.patch").read_bytes()
    tracked = module.public_receipt(receipt)
    assert tracked["private_receipt"] == "private://worktree-preserve/2026-07-19T000000Z-target-root"
    assert tracked["archive_receipt"] == "archive://worktree-preserve/2026-07-19T000000Z-target-root"
    assert tracked["head_prefix"] == receipt["head"][:12]
    assert str(repo) not in str(tracked)
    assert receipt["private_patch_sha256"] not in str(tracked)


def test_explicit_root_selection_fails_closed_when_not_dirty() -> None:
    module = load_module()
    report = {
        "items": [
            {"name": "dirty-a", "reason": "dirty", "debt": True},
            {"name": "merged-b", "reason": "merged", "debt": False},
        ]
    }

    selected, missing = module.select_dirty_items(
        report,
        ["dirty-a", "merged-b"],
        limit=0,
        dirty_checker=lambda item: item["reason"] == "dirty",
    )

    assert [item["name"] for item in selected] == ["dirty-a"]
    assert missing == ["merged-b"]
