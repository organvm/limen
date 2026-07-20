#!/usr/bin/env python3
"""Record a Claude SessionEnd worktree breadcrumb without running closeout work."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


_WORKTREE_MARKERS = ("/.claude/worktrees/", "/.worktrees/", "/.limen-worktrees/")


def _payload() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, UnicodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _worktree_root(cwd: str) -> Path | None:
    for marker in _WORKTREE_MARKERS:
        root, found, _suffix = cwd.partition(marker)
        if found and root:
            return Path(root)
    return None


def _branch(cwd: str) -> str:
    if not (Path(cwd) / ".git").exists():
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=0.25,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"


def record() -> None:
    payload = _payload()
    session_id = str(payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID") or "unknown")
    cwd = str(payload.get("cwd") or os.getcwd())
    root = _worktree_root(cwd)
    if root is None:
        return

    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    breadcrumb = {
        "ts": int(time.time()),
        "sid": session_id,
        "cwd": cwd,
        "branch": _branch(cwd),
    }
    line = (json.dumps(breadcrumb, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(
        log_dir / "session-closeout.jsonl",
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o600,
    )
    try:
        os.write(descriptor, line)
    finally:
        os.close(descriptor)


def main() -> int:
    try:
        record()
    except (OSError, UnicodeError, ValueError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
