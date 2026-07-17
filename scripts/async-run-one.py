#!/usr/bin/env python3
"""async-run-one.py — detached worker for the ASYNC dispatch engine.

Claims ONE already-registered attempt in tasks.yaml, runs its full isolated dispatch
(worktree → agent → commit → push → PR) via the SAME call_agent_dispatch the sync path uses, then writes the raw result to
logs/async-runs/<task-id>.result.json (atomically) and clears its running-marker. It deliberately
does not apply the result to tasks.yaml — the orchestrator (dispatch-async.py) harvests result files
under the queue-lock. This is what decouples agent runtime from the beat: the orchestrator spawns these
detached and returns immediately; a slow/stuck agent can no longer gate the whole beat.

Usage (spawned detached by dispatch-async.py; rarely run by hand):
    async-run-one.py --agent codex --task-id CIFIX-foo --reservation-id NONCE --execution-contract-hash SHA256
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
from limen.execution_contract import execution_contract_hash  # noqa: E402
from limen.attempt_custody import (  # noqa: E402
    attempt_launch_for,
    close_changed_contract_attempt,
    current_attempt_id,
)
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.dispatch import (  # noqa: E402
    _MODEL_SELECTION_RECEIPTS,
    _REMOTE_SUBMISSION_RECEIPTS,
    _validated_model_selection_receipt,
    _queue_lock,
    call_agent_dispatch,
)

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


def _result_path(task_id: str, reservation_id: str = "async-reserve") -> Path:
    suffix = "" if reservation_id == "async-reserve" else f"--{_reservation_suffix(reservation_id)}"
    return RUNS / f"{_run_stem(task_id)}{suffix}.result.json"


def _running_marker_path(task_id: str, agent: str, reservation_id: str = "async-reserve") -> Path:
    suffix = "" if reservation_id == "async-reserve" else f"--{_reservation_suffix(reservation_id)}"
    return RUNS / f"{_run_stem(task_id)}__{agent}{suffix}.running"


def _contract_hash(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("execution contract hash must be 64 lowercase hexadecimal characters")
    return value


def _reservation_id(value: str) -> str:
    if value != "async-reserve" and not _ASYNC_RESERVATION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("reservation ID must be async-reserve plus 32 lowercase hex characters")
    return value


def _failure(blocker_id: str, reason: str, **evidence: object) -> dict[str, object]:
    return {"id": blocker_id, "reason": reason[:500], **evidence}


def _load_verified_task(
    task_id: str,
    agent: str,
    reservation_id: str,
    expected_hash: str,
) -> tuple[object | None, str | bool, dict[str, object] | None, str]:
    """Load one immutable execution snapshot under the queue lock.

    The returned task object is the exact snapshot passed to dispatch. Later
    board rewrites therefore cannot change the prompt after this verification.
    """

    with _queue_lock(TASKS) as got:
        if not got:
            return (
                None,
                "__notask__",
                _failure("async-execution-queue-lock-busy", "task queue lock was unavailable before execution"),
                "",
            )
        board = load_limen_file(TASKS)
        task = next((candidate for candidate in board.tasks if candidate.id == task_id), None)
        if task is None:
            return (
                None,
                "__notask__",
                _failure("async-execution-task-missing", "reserved task disappeared before execution"),
                "",
            )
        contract_error = None
        try:
            actual_hash = execution_contract_hash(task)
        except Exception as exc:
            actual_hash = ""
            contract_error = exc
        if task.status != "dispatched":
            return (
                task,
                "__notask__",
                _failure(
                    "async-execution-status-unsafe",
                    f"fresh task status is {task.status}; expected dispatched",
                    actual_status=task.status,
                ),
                actual_hash,
            )
        last = task.dispatch_log[-1] if task.dispatch_log else None
        if (
            last is None
            or last.session_id != reservation_id
            or last.status != "dispatched"
            or last.agent != agent
            or not last.attempt_id
            or last.attempt_classification is None
            or last.execution_profile is None
        ):
            return (
                task,
                False,
                _failure(
                    "async-execution-claim-owner-mismatch",
                    "fresh task is not owned by this async reservation",
                ),
                actual_hash,
            )
        if contract_error is not None or actual_hash != expected_hash:
            closed_now = close_changed_contract_attempt(
                task,
                last,
                now=datetime.datetime.now(datetime.timezone.utc),
                agent=agent,
                phase="async-preflight",
                execution_started=False,
            )
            if closed_now:
                cost = max(0, int(task.budget_cost or 0))
                track = board.portal.budget.track
                track.spent = max(0, track.spent - cost)
                track.per_agent[agent] = max(0, track.per_agent.get(agent, 0) - cost)
                save_limen_file(TASKS, board)
            return (
                task,
                False,
                _failure(
                    (
                        "async-execution-contract-invalid"
                        if contract_error is not None
                        else "async-execution-contract-mismatch"
                    ),
                    (
                        f"fresh task cannot be canonically fingerprinted: {contract_error}"
                        if contract_error is not None
                        else "task execution contract changed after reservation"
                    ),
                    expected_hash=expected_hash,
                    actual_hash=actual_hash,
                    contract_drift_closed=closed_now,
                ),
                actual_hash,
            )
        claimed_at = datetime.datetime.now(datetime.timezone.utc)
        task.status = "in_progress"
        task.updated = claimed_at
        task.dispatch_log.append(
            last.model_copy(
                update={
                    "timestamp": claimed_at,
                    "status": "in_progress",
                    "output": "async worker claimed exact registered attempt before provider execution",
                }
            )
        )
        save_limen_file(TASKS, board)
        return task, False, None, actual_hash


def _publish_result(
    out: dict[str, object],
    *,
    task_id: str,
    agent: str,
    reservation_id: str,
    expected_hash: str,
    execution_started: bool,
) -> bool:
    """Publish under the same queue lock used by recovery.

    If exact recovery won the lock and reopened the task, fence the late result
    instead of applying it to a new claim. The counts-only receipt remains
    durable for diagnosis, but harvest will not mutate the reopened row.
    """

    with _queue_lock(TASKS) as got:
        if not got:
            return False
        board_error = None
        try:
            board = load_limen_file(TASKS)
            current = next((candidate for candidate in board.tasks if candidate.id == task_id), None)
        except Exception as exc:
            current = None
            current_hash = ""
            board_error = _failure(
                "async-result-board-unreadable",
                f"fresh board could not be verified before result publication: {exc}",
            )
        else:
            try:
                current_hash = execution_contract_hash(current) if current is not None else ""
            except Exception:
                current_hash = ""

        last = current.dispatch_log[-1] if current is not None and current.dispatch_log else None
        attempt_id = out.get("attempt_id")
        publication_safe = bool(
            board_error is None
            and current is not None
            and current.status == "in_progress"
            and current_hash == expected_hash
            and last is not None
            and last.session_id == reservation_id
            and last.status == "in_progress"
            and last.agent == agent
            and last.attempt_id == attempt_id
        )
        if publication_safe and not execution_started:
            # Another detached process already claimed this exact attempt. It owns
            # the canonical marker/result paths. The duplicate exits without
            # erasing or overwriting either artifact and without provider motion.
            return True
        closed_drift = False
        already_closed_drift = False
        launch = (
            attempt_launch_for(current, attempt_id)
            if current is not None and isinstance(attempt_id, str) and attempt_id
            else None
        )
        latest_attempt = (
            next(
                (entry for entry in reversed(current.dispatch_log) if entry.attempt_id == attempt_id),
                None,
            )
            if current is not None and isinstance(attempt_id, str)
            else None
        )
        already_closed_drift = bool(
            current is not None
            and launch is not None
            and current.status == "open"
            and last is not None
            and last.status == "open"
            and last.attempt_id is None
            and latest_attempt is not None
            and latest_attempt.status == "failed"
            and latest_attempt.session_id.startswith("contract-mismatch-")
            and (not current_hash or last.current_contract_hash == current_hash)
        )
        active_attempt_owner = bool(
            current is not None
            and launch is not None
            and current_attempt_id(current) == attempt_id
            and current.status in {"dispatched", "in_progress"}
            and latest_attempt is not None
            and latest_attempt.status == current.status
            and latest_attempt.session_id == reservation_id
            and latest_attempt.agent == agent
        )
        if (
            not publication_safe
            and active_attempt_owner
            and current_hash != expected_hash
        ):
            raw_selection = out.get("model_selection")
            validated_selection = None
            if isinstance(raw_selection, dict) and raw_selection:
                try:
                    validated_selection = _validated_model_selection_receipt(
                        current,
                        expected_attempt_id=str(attempt_id),
                        value=raw_selection,
                    )
                except ValueError as exc:
                    out["model_selection_failure"] = _failure(
                        "async-result-model-selection-fenced",
                        str(exc),
                    )
            reconciliation = {
                key: out[key]
                for key in (
                    "actual_spend",
                    "trajectory_outputs",
                    "trajectory_outputs_reconciled",
                    "trajectory_side_effects",
                    "trajectory_side_effects_reconciled",
                )
                if out.get(key) is not None
            }
            closed_drift = close_changed_contract_attempt(
                current,
                launch,
                now=datetime.datetime.now(datetime.timezone.utc),
                agent=agent,
                phase="async-result",
                stale_result=out.get("result") if isinstance(out.get("result"), (bool, str)) else None,
                model_selection=validated_selection,
                remote_submission=(
                    out.get("remote_submission") if isinstance(out.get("remote_submission"), dict) else None
                ),
                reconciliation=reconciliation,
            )
            if closed_drift:
                save_limen_file(TASKS, board)
        if closed_drift or already_closed_drift:
            out["result"] = "__contract_drift_closed__"
            out["contract_drift_closed"] = True
            out["publication_failure"] = _failure(
                "async-result-contract-drift-closed",
                "old attempt closed terminal and changed contract reopened without applying stale output",
                expected_hash=expected_hash,
                actual_hash=current_hash,
            )
        elif not publication_safe:
            out["result"] = "__notask__"
            out["publication_failure"] = board_error or _failure(
                "async-result-publication-fenced",
                "task changed or was recovered before the worker could publish its result",
                expected_hash=expected_hash,
                actual_hash=current_hash,
                actual_status=getattr(current, "status", None),
            )
        RUNS.mkdir(parents=True, exist_ok=True)
        tmp = _result_path(task_id, reservation_id).with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(out))
        tmp.replace(_result_path(task_id, reservation_id))  # atomic publish while recovery is excluded
        try:
            _running_marker_path(task_id, agent, reservation_id).unlink()
        except OSError:
            pass
        return True


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
            capture_output=True,
            text=True,
            timeout=60,
        )
        if v.returncode != 0:
            return None
        data = json.loads(v.stdout or "{}") or {}
        rollup = data.get("statusCheckRollup") or []
        failing = sorted(
            {
                c.get("name", "?")
                for c in rollup
                if (c.get("conclusion") or "").upper() in ("FAILURE", "TIMED_OUT", "CANCELLED")
            }
        )
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
    ap.add_argument("--reservation-id", default="async-reserve", type=_reservation_id)
    ap.add_argument("--execution-contract-hash", required=True, type=_contract_hash)
    a = ap.parse_args()
    err = None
    task = None
    execution_started = False
    actual_hash = ""
    validation_failure = None
    attempt_id = None
    try:
        task, result, validation_failure, actual_hash = _load_verified_task(
            a.task_id,
            a.agent,
            a.reservation_id,
            a.execution_contract_hash,
        )
        if task is not None and task.dispatch_log:
            attempt_id = current_attempt_id(task)
        if validation_failure is None and task is not None:
            execution_started = True
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
        "execution_contract_hash": a.execution_contract_hash,
        "actual_execution_contract_hash": actual_hash,
        "execution_started": execution_started,
        "attempt_id": attempt_id,
        "model_selection": dict(_MODEL_SELECTION_RECEIPTS.get(a.task_id, {})),
        "remote_submission": dict(_REMOTE_SUBMISSION_RECEIPTS.get(a.task_id, {})),
    }
    if task is not None and attempt_id:
        latest_attempt = next(
            (entry for entry in reversed(task.dispatch_log) if entry.attempt_id == attempt_id),
            None,
        )
        if latest_attempt is not None:
            for field in (
                "actual_spend",
                "trajectory_outputs",
                "trajectory_outputs_reconciled",
                "trajectory_side_effects",
                "trajectory_side_effects_reconciled",
            ):
                value = getattr(latest_attempt, field, None)
                if value is not None:
                    out[field] = value
    if validation_failure is not None:
        out["validation_failure"] = validation_failure
    if execution_started and task is not None and a.task_id.startswith("HEAL-"):
        derived = heal_outcome(task, result)
        if derived:
            out.update(derived)
    published = _publish_result(
        out,
        task_id=a.task_id,
        agent=a.agent,
        reservation_id=a.reservation_id,
        expected_hash=a.execution_contract_hash,
        execution_started=execution_started,
    )
    if not published:
        print("async worker could not acquire the queue lock for result publication", file=sys.stderr)
        return 2
    return 0 if validation_failure is None else 10


if __name__ == "__main__":
    raise SystemExit(main())
