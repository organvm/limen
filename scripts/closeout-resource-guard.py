#!/usr/bin/env python3
"""Resource guard for interactive closeout and local whole-repo verification.

The guard observes local process and launchd state. It does not mutate runtime
state, stop daemons, or edit receipts.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Iterable, NamedTuple

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))

NEXT_COMMANDS = (
    "bash scripts/closeout-fast.sh",
    "run the lane-specific predicate for the files touched in this change",
    "use the remote CI verify receipt as the whole-repo proof",
)

BACKLOG_GENERATORS = (
    "mine-backlog.py",
    "generate-backlog.py",
    "generate-organ-backlog.py",
    "generate-revenue-backlog.py",
    "ingest-backlog.py",
    "discover-value.py",
    "self-improve.py",
)

LAUNCHD_LABELS = {
    "com.limen.heartbeat": "limen heartbeat is active",
    "com.limen.watchdog": "limen watchdog is active",
}


class ProcessInfo(NamedTuple):
    pid: int
    command: str


class LaunchdInfo(NamedTuple):
    label: str
    pid: int | None
    active: bool


class Hazard(NamedTuple):
    id: str
    source: str
    detail: str


def _compact_command(command: str, limit: int = 220) -> str:
    command = " ".join(command.split())
    if len(command) <= limit:
        return command
    return command[: limit - 3] + "..."


def collect_processes() -> list[ProcessInfo]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []

    processes: list[ProcessInfo] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if not match:
            continue
        pid = int(match.group(1))
        command = match.group(2)
        if "closeout-resource-guard.py" in command:
            continue
        processes.append(ProcessInfo(pid=pid, command=command))
    return processes


def collect_launchd() -> list[LaunchdInfo]:
    try:
        proc = subprocess.run(
            ["launchctl", "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []

    out: list[LaunchdInfo] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        pid_raw, _status, label = parts[0], parts[1], parts[2]
        if label not in LAUNCHD_LABELS:
            continue
        pid = int(pid_raw) if pid_raw.isdigit() else None
        out.append(LaunchdInfo(label=label, pid=pid, active=pid is not None))
    return out


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _script_in_command(command: str, script_name: str) -> bool:
    return script_name in command or f"scripts/{script_name}" in command


def _is_full_pytest(command: str) -> bool:
    if "pytest" not in command:
        return False
    tokens = _tokens(command)
    pytest_index = next((i for i, token in enumerate(tokens) if token == "pytest" or token.endswith("/pytest")), None)
    if pytest_index is None:
        for i, token in enumerate(tokens):
            if token == "-m" and i + 1 < len(tokens) and tokens[i + 1] == "pytest":
                pytest_index = i + 1
                break
    if pytest_index is None:
        return False

    selectors = [token for token in tokens[pytest_index + 1 :] if not token.startswith("-")]
    if not selectors:
        return True
    if any("::" in selector or selector.endswith(".py") for selector in selectors):
        return False
    broad_dirs = {"cli/tests", "web/api/tests", "tests", "."}
    return any(selector.rstrip("/") in broad_dirs for selector in selectors)


def _is_broad_du(command: str) -> bool:
    tokens = _tokens(command)
    if not tokens:
        return False
    exe = Path(tokens[0]).name
    if exe != "du":
        return False
    if any(token.startswith("--max-depth") or token in {"-d", "--depth"} for token in tokens):
        return False
    targets = [token for token in tokens[1:] if not token.startswith("-")]
    if not targets:
        return True
    broad_targets = {"/", ".", "..", "*", "~", os.environ.get("HOME", "")}
    for target in targets:
        expanded = os.path.expanduser(target)
        if target in broad_targets or expanded in broad_targets:
            return True
        if expanded.startswith("/Users") or expanded.startswith("/Volumes"):
            return True
    return False


def classify_process(process: ProcessInfo) -> Hazard | None:
    command = process.command
    lowered = command.lower()
    detail = f"pid {process.pid}: {_compact_command(command)}"

    if _script_in_command(command, "verify-whole.sh"):
        return Hazard("verify-whole-active", "process", detail)
    if _is_full_pytest(command):
        return Hazard("full-pytest-active", "process", detail)
    if _script_in_command(command, "worktree-debt.py"):
        return Hazard("worktree-debt-active", "process", detail)
    if _script_in_command(command, "session-lifecycle-pressure.py"):
        return Hazard("session-lifecycle-pressure-active", "process", detail)
    for script_name in BACKLOG_GENERATORS:
        if _script_in_command(command, script_name):
            return Hazard("backlog-generator-active", "process", detail)
    if _is_broad_du(command):
        return Hazard("broad-du-active", "process", detail)
    if "claude" in lowered and (" agents" in lowered or ".claude/agents" in lowered or "agent(" in lowered):
        return Hazard("claude-agents-active", "process", detail)
    if "heartbeat-loop.sh" in command or "com.limen.heartbeat" in command:
        return Hazard("heartbeat-active", "process", detail)
    if "com.limen.watchdog" in command or ("limen" in lowered and "watchdog" in lowered):
        return Hazard("watchdog-active", "process", detail)
    return None


def classify_launchd(item: LaunchdInfo) -> Hazard | None:
    if not item.active or item.label not in LAUNCHD_LABELS:
        return None
    pid = f" pid {item.pid}" if item.pid is not None else ""
    return Hazard(item.label.replace("com.limen.", "") + "-active", "launchd", f"{LAUNCHD_LABELS[item.label]}{pid}")


def hazards_from_snapshots(
    processes: Iterable[ProcessInfo],
    launchd: Iterable[LaunchdInfo],
) -> list[Hazard]:
    hazards: list[Hazard] = []
    seen: set[tuple[str, str, str]] = set()
    for hazard in [classify_process(process) for process in processes]:
        if hazard and (hazard.id, hazard.source, hazard.detail) not in seen:
            hazards.append(hazard)
            seen.add((hazard.id, hazard.source, hazard.detail))
    for hazard in [classify_launchd(item) for item in launchd]:
        if hazard and (hazard.id, hazard.source, hazard.detail) not in seen:
            hazards.append(hazard)
            seen.add((hazard.id, hazard.source, hazard.detail))
    return hazards


def evaluate(
    *,
    mode: str,
    warn_only: bool,
    allow_override: bool,
    hazards: list[Hazard],
) -> dict[str, Any]:
    has_hazards = bool(hazards)
    effective_warn = warn_only or mode == "closeout-fast"
    if has_hazards and mode == "verify-whole" and allow_override:
        status = "override"
        exit_code = 0
    elif has_hazards and effective_warn:
        status = "warn"
        exit_code = 0
    elif has_hazards:
        status = "blocked"
        exit_code = 12
    else:
        status = "clear"
        exit_code = 0
    return {
        "mode": mode,
        "status": status,
        "exit_code": exit_code,
        "warn_only": effective_warn,
        "override": allow_override,
        "hazards": [hazard._asdict() for hazard in hazards],
        "next_commands": list(NEXT_COMMANDS),
        "root": str(ROOT),
    }


def render_text(result: dict[str, Any]) -> str:
    status = result["status"]
    mode = result["mode"]
    lines = [f"closeout resource guard: {status} ({mode})"]
    hazards = result.get("hazards") or []
    if hazards:
        lines.append("active resource hazards:")
        for hazard in hazards:
            lines.append(f"- {hazard['id']} [{hazard['source']}]: {hazard['detail']}")
        if status == "blocked":
            lines.append("local whole-repo verification is deferred until the active automation quiets.")
        elif status == "override":
            lines.append("explicit override accepted through LIMEN_VERIFY_ALLOW_CONCURRENT=1.")
    else:
        lines.append("no active closeout resource hazards detected.")

    lines.append("safe closeout path:")
    for command in result["next_commands"]:
        lines.append(f"- {command}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observe whether closeout can safely run broad local gates.")
    parser.add_argument("--mode", choices=("verify-whole", "closeout-fast"), default="verify-whole")
    parser.add_argument("--warn-only", action="store_true", help="report hazards but exit 0")
    parser.add_argument("--json", action="store_true", help="emit machine-readable guard output")
    args = parser.parse_args(argv)

    hazards = hazards_from_snapshots(collect_processes(), collect_launchd())
    result = evaluate(
        mode=args.mode,
        warn_only=args.warn_only,
        allow_override=os.environ.get("LIMEN_VERIFY_ALLOW_CONCURRENT") == "1",
        hazards=hazards,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text(result), end="")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
