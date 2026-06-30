#!/usr/bin/env python3
"""Read-only full-fleet overnight readiness doctor."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import PAID_AGENT_ORDER, capacity_fill_snapshot, classify_lanes  # noqa: E402
from limen.dispatch import _down_lanes  # noqa: E402
from limen.io import load_limen_file  # noqa: E402

HOME = Path.home()
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
LIVE_ROOT = Path(os.environ.get("LIMEN_LIVE_ROOT", ROOT))
POLICY_PATH = ROOT / "logs" / "autonomy-policy.json"
PAUSE_MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"
QUEUE_LOCK = ROOT / "logs" / ".queue.lock.d"
HEARTBEAT_PLIST = Path(
    os.environ.get("LIMEN_HEARTBEAT_PLIST", HOME / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist")
)
LAUNCHD_LABEL = os.environ.get("LIMEN_HEARTBEAT_LABEL", "com.limen.heartbeat")
LIVE_ROOT_RECEIPT = ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "live-root-gate.json"


def run_command(args: list[str], *, cwd: Path | None = None, timeout: int = 20) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {"returncode": None, "stdout": exc.stdout or "", "stderr": exc.stderr or "", "timed_out": True}
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc), "timed_out": False}


def read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text())
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def read_plist(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
    except Exception as exc:
        return {"present": False, "path": str(path), "env": {}, "error": str(exc)}
    return {
        "present": True,
        "path": str(path),
        "keep_alive": data.get("KeepAlive"),
        "run_at_load": data.get("RunAtLoad"),
        "env": data.get("EnvironmentVariables") or {},
    }


def parse_launchd(text: str) -> dict[str, Any]:
    env: dict[str, str] = {}
    in_env = False
    state = "missing"
    pid = None
    for raw in text.splitlines():
        line = raw.strip()
        if line == "environment = {":
            in_env = True
            continue
        if in_env and line == "}":
            in_env = False
            continue
        if in_env and " => " in line:
            key, value = line.split(" => ", 1)
            if key.startswith("LIMEN_"):
                env[key] = value
        elif line.startswith("state = "):
            state = line.split("=", 1)[1].strip()
        elif line.startswith("pid = "):
            pid = line.split("=", 1)[1].strip()
    return {"running": state == "running" or bool(pid), "state": state, "pid": pid, "env": env}


def launchd_snapshot() -> dict[str, Any]:
    result = run_command(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"], timeout=8)
    parsed = parse_launchd(str(result.get("stdout") or ""))
    parsed["probe"] = {"returncode": result["returncode"], "timed_out": result["timed_out"]}
    return parsed


def git_dirty_snapshot(root: Path) -> dict[str, Any]:
    result = run_command(["git", "-C", str(root), "status", "--porcelain=v1"], timeout=12)
    lines = [line for line in str(result.get("stdout") or "").splitlines() if line.strip()]
    receipt_present = LIVE_ROOT_RECEIPT.exists()
    return {
        "path": str(root),
        "present": root.exists(),
        "dirty_entries": len(lines) if result.get("returncode") == 0 else None,
        "dirty_paths": [line[3:] if len(line) > 3 else line for line in lines[:30]],
        "preservation_receipt_present": receipt_present,
        "preserved_or_clean": (result.get("returncode") == 0 and not lines) or receipt_present,
        "probe": {"returncode": result["returncode"], "timed_out": result["timed_out"]},
    }


def queue_lock_snapshot() -> dict[str, Any]:
    if not QUEUE_LOCK.exists():
        return {"path": str(QUEUE_LOCK), "present": False, "healthy": True}
    try:
        age_s = dt.datetime.now().timestamp() - QUEUE_LOCK.stat().st_mtime
    except OSError:
        age_s = None
    return {
        "path": str(QUEUE_LOCK),
        "present": True,
        "age_seconds": age_s,
        "healthy": bool(age_s is not None and age_s < 7200),
    }


def policy_snapshot() -> dict[str, Any]:
    policy = read_json(POLICY_PATH)
    mode = "paused" if PAUSE_MARKER.exists() else str(policy.get("mode") or "observe")
    return {
        "path": str(POLICY_PATH),
        "mode": mode,
        "dispatch_enabled": bool(policy.get("dispatch_enabled")),
        "pause_marker_exists": PAUSE_MARKER.exists(),
    }


def async_enabled(plist: dict[str, Any], launchd: dict[str, Any], waived: bool) -> dict[str, Any]:
    values = {
        "process_env": os.environ.get("LIMEN_DISPATCH_ASYNC"),
        "plist": (plist.get("env") or {}).get("LIMEN_DISPATCH_ASYNC"),
        "loaded": (launchd.get("env") or {}).get("LIMEN_DISPATCH_ASYNC"),
    }
    enabled = any(str(value) == "1" for value in values.values())
    return {"enabled": enabled, "waived": waived, "values": values, "ok": enabled or waived}


def derive_blockers(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    policy = snapshot["policy"]
    launchd = snapshot["launchd"]
    async_state = snapshot["async"]
    live_root = snapshot["live_root"]
    queue = snapshot["queue_lock"]
    classifications = snapshot["lane_classification"]
    capacity_fill = snapshot["capacity_fill"]

    if policy.get("mode") != "dispatch" or not policy.get("dispatch_enabled"):
        blockers.append(
            {
                "id": "autonomy-policy-not-dispatch",
                "evidence": f"mode={policy.get('mode')}, dispatch_enabled={policy.get('dispatch_enabled')}",
            }
        )
    if not launchd.get("running"):
        blockers.append({"id": "heartbeat-not-running", "evidence": f"launchd state={launchd.get('state')}"})
    if not async_state.get("ok"):
        blockers.append({"id": "async-not-enabled", "evidence": f"values={async_state.get('values')}"})
    if not live_root.get("preserved_or_clean"):
        blockers.append(
            {
                "id": "live-root-dirty-unpreserved",
                "evidence": f"dirty_entries={live_root.get('dirty_entries')}, receipt={LIVE_ROOT_RECEIPT}",
            }
        )
    if not queue.get("healthy"):
        blockers.append({"id": "queue-lock-unhealthy", "evidence": f"{QUEUE_LOCK} age={queue.get('age_seconds')}"})

    statuses = {row["agent"]: row["status"] for row in classifications}
    missing = [lane for lane in PAID_AGENT_ORDER if lane not in statuses]
    bad_status = [f"{lane}:{status}" for lane, status in statuses.items() if status not in {"active", "down", "depleted", "human-gated"}]
    if missing:
        blockers.append({"id": "lane-classification-missing", "evidence": ", ".join(missing)})
    if bad_status:
        blockers.append({"id": "lane-classification-invalid", "evidence": ", ".join(bad_status)})

    row_agents = {str(row.get("agent")) for row in capacity_fill.get("rows") or []}
    omitted = [lane for lane in PAID_AGENT_ORDER if lane not in row_agents]
    if omitted:
        blockers.append({"id": "capacity-fill-silent-lanes", "evidence": ", ".join(omitted)})
    for blocker in capacity_fill.get("blockers") or []:
        blockers.append(
            {
                "id": str(blocker.get("id") or "capacity-fill-blocker"),
                "evidence": str(blocker.get("evidence") or "capacity fill blocker"),
            }
        )
    return blockers


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    board = load_limen_file(TASKS)
    down = _down_lanes()
    plist = read_plist(HEARTBEAT_PLIST)
    launchd = launchd_snapshot()
    snapshot: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "policy": policy_snapshot(),
        "heartbeat_plist": plist,
        "launchd": launchd,
        "async": async_enabled(plist, launchd, bool(args.waive_async)),
        "live_root": git_dirty_snapshot(LIVE_ROOT),
        "queue_lock": queue_lock_snapshot(),
        "lane_classification": classify_lanes(board, down_lanes=down),
        "capacity_fill": capacity_fill_snapshot(board, down_lanes=down),
    }
    snapshot["blockers"] = derive_blockers(snapshot)
    snapshot["status"] = "ready" if not snapshot["blockers"] else "blocked"
    return snapshot


def render_text(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Overnight Doctor",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        "",
        "## Gates",
        "",
        f"- Autonomy: mode `{snapshot['policy']['mode']}`, dispatch_enabled `{snapshot['policy']['dispatch_enabled']}`",
        f"- Heartbeat: state `{snapshot['launchd']['state']}`, pid `{snapshot['launchd'].get('pid')}`",
        f"- Async: ok `{snapshot['async']['ok']}`, values `{snapshot['async']['values']}`, waived `{snapshot['async']['waived']}`",
        f"- Live root: dirty `{snapshot['live_root']['dirty_entries']}`, preserved_or_clean `{snapshot['live_root']['preserved_or_clean']}`",
        f"- Queue lock: healthy `{snapshot['queue_lock']['healthy']}`",
        "",
        "## Fleet",
        "",
        "| Lane | Kind | Status | Detail |",
        "|---|---|---|---|",
    ]
    for row in snapshot["lane_classification"]:
        detail = str(row["detail"]).replace("|", "\\|")
        lines.append(f"| `{row['agent']}` | `{row['kind']}` | `{row['status']}` | {detail} |")
    lines += ["", "## Blockers", ""]
    blockers = snapshot["blockers"]
    if blockers:
        lines.extend(f"- `{b['id']}`: {b['evidence']}" for b in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether full-fleet overnight autonomy is ready.")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown text")
    parser.add_argument("--waive-async", action="store_true", help="explicitly waive async-dispatch readiness")
    args = parser.parse_args()
    snapshot = build_snapshot(args)
    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(render_text(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
