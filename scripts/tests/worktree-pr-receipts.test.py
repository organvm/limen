#!/usr/bin/env python3
"""Hermetic default-branch refusal for the lifecycle PR publisher."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "worktree-pr-receipts.py"
SPEC = importlib.util.spec_from_file_location("worktree_pr_receipts", SOURCE)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    def fake_git(cwd: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        del cwd, timeout
        if args == ("rev-parse", "--is-inside-work-tree"):
            return subprocess.CompletedProcess(args, 0, "true\n", "")
        if args == ("status", "--porcelain"):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ("fetch", "--prune", "origin"):
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"unexpected git call after default-branch detection: {args!r}")

    module.git = fake_git
    module.origin_repo = lambda cwd: "organvm/limen"
    module.current_branch = lambda cwd: "main"
    module.default_branch = lambda cwd, repo: "main"
    module.patch_equivalent_or_merged = lambda cwd, base: (_ for _ in ()).throw(
        AssertionError("default branch reached preservation analysis")
    )
    module.remote_head_exists = lambda cwd, branch: (_ for _ in ()).throw(
        AssertionError("default branch reached remote publication")
    )

    result = module.process_item(
        {
            "name": "default-checkout",
            "path": str(root),
            "reason": "unpushed-commits",
        },
        apply=True,
    )

assert result["action"] == "refused_default_branch", result
assert result["branch"] == result["base"] == "main", result
print("PASS: lifecycle receipt publisher refuses the repository default branch before any push")
