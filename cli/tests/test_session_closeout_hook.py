from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "hooks" / "session-closeout.sh"


def test_session_end_records_payload_breadcrumb_without_running_slow_owners(tmp_path: Path) -> None:
    limen_root = tmp_path / "limen"
    worktree = limen_root / ".worktrees" / "large board"
    worktree.mkdir(parents=True)
    (limen_root / "logs").mkdir()
    (limen_root / "tasks.yaml").write_text(
        "tasks:\n" + ('  - id: "fixture"\n    status: open\n' * 50_000),
        encoding="utf-8",
    )

    marker = tmp_path / "slow-owner-ran"
    scripts = limen_root / "scripts"
    scripts.mkdir()
    for name in ("handoff-relay.py", "orphan-watchers.py", "claude-workflow-guard.py"):
        (scripts / name).write_text(
            f"import pathlib, time\ntime.sleep(2)\npathlib.Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )

    supplied = {
        "hook_event_name": "SessionEnd",
        "session_id": "claude-session-from-stdin",
        "cwd": str(worktree),
    }
    env = {**os.environ, "LIMEN_ROOT": str(limen_root), "CLAUDE_SESSION_ID": "wrong-env-session"}
    started = time.monotonic()
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(supplied),
        capture_output=True,
        text=True,
        cwd=limen_root,
        env=env,
        timeout=2,
        check=False,
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 0
    assert elapsed < 1
    assert not marker.exists()
    breadcrumb = json.loads((limen_root / "logs" / "session-closeout.jsonl").read_text(encoding="utf-8"))
    assert breadcrumb["sid"] == supplied["session_id"]
    assert breadcrumb["cwd"] == supplied["cwd"]
    assert breadcrumb["branch"] == "unknown"
    assert isinstance(breadcrumb["ts"], int)


def test_claude_session_end_declares_five_second_outer_timeout() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    handlers = [
        hook
        for group in settings["hooks"]["SessionEnd"]
        for hook in group["hooks"]
        if "session-closeout.sh" in hook["command"]
    ]

    assert len(handlers) == 1
    assert handlers[0]["timeout"] == 5
