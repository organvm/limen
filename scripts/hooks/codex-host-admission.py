#!/usr/bin/env python3
"""Codex lifecycle adapter for Limen host admission.

UserPromptSubmit can stop a second non-plan Codex root. PreToolUse is only an
early warning because Codex does not currently support a hard tool denial in
that event; guarded entrypoints acquire the authoritative heavy lease again.
SubagentStart is advisory because Codex cannot block it. Stop does no broad
scan: it releases the turn lease, with at most one lightweight closeout
continuation when the runtime marks a first Stop pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.host_admission import AdmissionController, AdmissionStateError, is_descendant  # noqa: E402

_HEAVY_COMMAND = re.compile(
    r"""(?ix)
    \b(
      verify-whole(?:\.sh)? |
      verify-scoped(?:\.sh)? |
      governance-memory-cadence(?:\.py)? |
      estate-closeout-audit(?:\.py)? |
      npm\s+(?:ci|test|run\s+build) |
      (?:python(?:3(?:\.\d+)?)?\s+-m\s+)?pytest(?:\s+-q)?\s*(?:$|(?:cli/)?tests/?(?:\s|$))
    )
    """
)


def _hash_label(prefix: str, raw: str) -> str:
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _ps_row(pid: int) -> tuple[int | None, str]:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "ppid=,comm="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, ""
    parts = result.stdout.strip().split(maxsplit=1)
    if result.returncode != 0 or not parts or not parts[0].isdigit():
        return None, ""
    return int(parts[0]), parts[1] if len(parts) > 1 else ""


def codex_owner_pid() -> int:
    """Resolve the durable Codex ancestor instead of leasing to this short hook."""

    current = os.getppid()
    fallback = current
    seen: set[int] = set()
    for _ in range(32):
        if current <= 1 or current in seen:
            break
        seen.add(current)
        parent, command = _ps_row(current)
        if "codex" in command.lower():
            return current
        if parent is None:
            break
        current = parent
    return fallback


def _turn_owner(payload: dict[str, Any]) -> str | None:
    session_id = str(payload.get("session_id") or "").strip()
    return _hash_label("codex-session", session_id) if session_id else None


def _message(text: str, *, stop: bool = False) -> dict[str, Any]:
    output: dict[str, Any] = {"systemMessage": text}
    if stop:
        output.update({"continue": False, "stopReason": text})
    return output


def _tool_command(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("command") or tool_input.get("cmd") or "")


def _needs_bounded_closeout(cwd: str) -> bool:
    """Cheap evidence only; never scan worktrees, transcripts, or remote state."""

    if not cwd:
        return False
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        ).stdout.strip()
        if not branch or branch in {"main", "master"}:
            return False
        dirty = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain=v1", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        ahead = subprocess.run(
            ["git", "-C", cwd, "rev-list", "--count", "@{upstream}..HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(dirty.returncode == 0 and dirty.stdout.strip()) or bool(
        ahead.returncode == 0 and ahead.stdout.strip().isdigit() and int(ahead.stdout) > 0
    )


def _release_execution(
    controller: AdmissionController,
    *,
    owner: str,
    pid: int,
) -> None:
    status = controller.status(probe=False)
    lease = next(
        (
            item
            for item in status.get("leases") or []
            if item.get("kind") == "execution" and item.get("owner") == owner and int(item.get("pid") or 0) == pid
        ),
        None,
    )
    if lease:
        controller.release(lease_id=str(lease["lease_id"]), owner=owner, pid=pid)


def handle(
    payload: dict[str, Any],
    *,
    controller: AdmissionController | None = None,
    owner_pid: int | None = None,
    closeout_probe: Callable[[str], bool] = _needs_bounded_closeout,
) -> dict[str, Any] | None:
    controller = controller or AdmissionController()
    event = str(payload.get("hook_event_name") or "")
    permission_mode = str(payload.get("permission_mode") or "default")
    owner = _turn_owner(payload)
    pid = owner_pid or codex_owner_pid()

    if event == "UserPromptSubmit":
        if permission_mode == "plan":
            return None
        if owner is None:
            return _message("Limen denied a non-plan Codex turn without a stable session identity.", stop=True)
        decision = controller.acquire(
            "execution",
            owner=owner,
            surface="codex-user-prompt",
            pid=pid,
        )
        if not decision["allowed"]:
            reasons = ",".join(decision.get("reasons") or ["execution-lease-held"])
            return _message(
                f"Limen denied this Codex turn: {reasons}. Finish or stop the current root first.",
                stop=True,
            )
        return None

    if event == "PreToolUse":
        command = _tool_command(payload)
        if not _HEAVY_COMMAND.search(command):
            return None
        status = controller.status(probe=True)
        heavy = next((item for item in status.get("leases") or [] if item.get("kind") == "heavy"), None)
        inherited = bool(heavy and is_descendant(pid, int(heavy["pid"])))
        reasons = list(status.get("reasons") or [])
        if heavy and not inherited:
            reasons.insert(0, "heavy-lease-held")
        if reasons:
            return _message(
                "Limen host admission denied this heavy call: "
                + ",".join(dict.fromkeys(reasons))
                + ". The guarded entrypoint will fail closed; defer or use a narrow non-heavy predicate."
            )
        return None

    if event == "SubagentStart":
        return {
            "systemMessage": (
                "Limen subagent bounds: the parent execution family owns this turn; "
                "max_threads=3, max_depth=1, and heavy entrypoints require the shared host lease."
            ),
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": (
                    "Do not start a nested subagent. Keep this child bounded and use guarded "
                    "entrypoints for heavy verification."
                ),
            },
        }

    if event == "Stop" and owner is not None:
        # Codex may expose the compatibility flag used by Stop hooks. Only that
        # explicit first-pass signal may request one continuation; otherwise Stop
        # releases immediately and can never become an unbounded loop.
        first_stop = payload.get("stop_hook_active") is False
        if first_stop and closeout_probe(str(payload.get("cwd") or "")):
            try:
                status = controller.status(probe=False)
                lease = next(
                    (
                        item
                        for item in status.get("leases") or []
                        if item.get("kind") == "execution"
                        and item.get("owner") == owner
                        and int(item.get("pid") or 0) == pid
                    ),
                    None,
                )
                if lease:
                    controller.refresh(lease_id=str(lease["lease_id"]), owner=owner, pid=pid)
            except AdmissionStateError:
                pass
            return _message(
                "One bounded closeout pass remains: preserve named changes and leave a durable "
                "owner receipt. Do not launch broad scans or full verification.",
                stop=True,
            )
        _release_execution(controller, owner=owner, pid=pid)
        return None

    return None


def main() -> int:
    event = ""
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        event = str(payload.get("hook_event_name") or "")
        output = handle(payload)
    except (AdmissionStateError, ValueError) as exc:
        output = _message(
            f"Limen host admission hook failed closed: {exc}",
            stop=event in {"UserPromptSubmit", "Stop"},
        )
    if output is not None:
        print(json.dumps(output, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
