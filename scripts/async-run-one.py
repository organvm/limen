#!/usr/bin/env python3
"""async-run-one.py — detached worker for the ASYNC dispatch engine.

Runs ONE task's full isolated dispatch (worktree → agent → commit → push → PR) via the SAME
call_agent_dispatch the sync path uses, then writes the raw result to
logs/async-runs/<task-id>.result.json (atomically) and clears its running-marker. It deliberately
does NOT touch tasks.yaml — the orchestrator (dispatch-async.py) harvests result files under the
queue-lock. This is what decouples agent runtime from the beat: the orchestrator spawns these
detached and returns immediately; a slow/stuck agent can no longer gate the whole beat.

Usage (spawned detached by dispatch-async.py; rarely run by hand):
    async-run-one.py --agent codex --task-id CIFIX-foo
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file  # noqa: E402
from limen.dispatch import _REMOTE_SUBMISSION_RECEIPTS, call_agent_dispatch  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
RUNS = ROOT / "logs" / "async-runs"
_SAFE_STEM_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ASYNC_RESERVATION_RE = re.compile(r"^async-reserve:[0-9a-f]{32}$")


def _run_stem(task_id: str) -> str:
    if _SAFE_STEM_RE.fullmatch(task_id):
        return task_id
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("._-") or "task"
    digest = hashlib.sha1(task_id.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:80]}--{digest}"


def _reservation_suffix(reservation_id: str) -> str:
    return hashlib.sha256(reservation_id.encode("utf-8")).hexdigest()[:16]


def _result_path(task_id: str, reservation_id: str) -> Path:
    return RUNS / f"{_run_stem(task_id)}--{_reservation_suffix(reservation_id)}.result.json"


def _running_marker_path(task_id: str, agent: str, reservation_id: str) -> Path:
    return RUNS / f"{_run_stem(task_id)}__{agent}--{_reservation_suffix(reservation_id)}.running"


def heal_outcome(task, result):
    """Mechanically derive a heal receipt's outcome — never trust agent prose.

    The gap (retro 06-24→07-08 finding 2): 59% of heal receipts produced no PR
    and nothing distinguished "already green" from "gave up silently", so heal
    convergence could be neither asserted nor falsified. For HEAL-* tasks this
    probes the TARGET PR's post-run state via gh and returns
    {outcome: already_green|fixed|gave_up, failing_checks: [...]}.
    Fail-open: any probe error returns None (receipt ships without the field,
    counted by heal-convergence.py as legacy/uncovered).
    """
    import re
    import subprocess

    blob = f"{task.context or ''} {' '.join(str(u) for u in (task.urls or []))}"
    m = re.search(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", blob)
    if not m:
        return None
    repo, num = m.group(1), m.group(2)
    try:
        v = subprocess.run(
            ["gh", "pr", "view", num, "-R", repo, "--json", "statusCheckRollup,mergeable"],
            capture_output=True, text=True, timeout=60,
        )
        if v.returncode != 0:
            return None
        data = json.loads(v.stdout or "{}") or {}
        rollup = data.get("statusCheckRollup") or []
        failing = sorted({c.get("name", "?") for c in rollup
                          if (c.get("conclusion") or "").upper() in ("FAILURE", "TIMED_OUT", "CANCELLED")})
        green = not failing and str(data.get("mergeable", "")).upper() != "CONFLICTING"
        if green:
            outcome = "already_green" if result in ("__noop__", False, None) else "fixed"
        else:
            outcome = "gave_up"
        return {"outcome": outcome, "failing_checks": failing}
    except Exception:  # noqa: BLE001 — outcome derivation must never sink the worker
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--reservation-id", required=True)
    a = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    err = None
    task = None
    try:
        lf = load_limen_file(TASKS)
        task = next((t for t in lf.tasks if t.id == a.task_id), None)
        reservation = task.dispatch_log[-1] if task is not None and task.dispatch_log else None
        if (
            task is None
            or task.status != "dispatched"
            or reservation is None
            or reservation.status != "dispatched"
            or reservation.agent != a.agent
            or reservation.session_id != a.reservation_id
            or not _ASYNC_RESERVATION_RE.fullmatch(a.reservation_id)
        ):
            result = "__notask__"
            err = "async reservation was superseded before worker execution"
        else:
            result = call_agent_dispatch(a.agent, task, dry_run=False)
    except Exception as e:  # never crash without leaving a result the harvester can apply
        result = False
        err = str(e)[:300]
    out = {
        "task_id": a.task_id,
        "agent": a.agent,
        "reservation_id": a.reservation_id,
        "result": result,  # bool | str (PR url / __noop__ / __ratelimit__ / __timeout__)
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "err": err,
        "remote_submission": dict(_REMOTE_SUBMISSION_RECEIPTS.get(a.task_id, {})),
    }
    if task is not None and a.task_id.startswith("HEAL-"):
        derived = heal_outcome(task, result)
        if derived:
            out.update(derived)
    result_path = _result_path(a.task_id, a.reservation_id)
    tmp = result_path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(out))
    tmp.replace(result_path)  # atomic publish
    try:
        _running_marker_path(a.task_id, a.agent, a.reservation_id).unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
