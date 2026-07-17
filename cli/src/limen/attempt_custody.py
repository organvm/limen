"""Immutable execution-attempt custody helpers shared by dispatch and harvest."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from limen.execution_contract import execution_contract_hash
from limen.execution_trajectory import ExecutionOutput, ExecutionSideEffect, ExecutionSpend
from limen.models import DispatchLogEntry, Task


_REMOTE_FIELDS = (
    "provider_run_id",
    "provider_url",
    "base_sha",
    "control_repo",
    "control_ref",
    "control_ref_kind",
    "control_sha",
    "workflow_id",
    "workflow_path",
    "workflow_event",
    "verification_context_digest",
    "remote_state",
    "remote_request_id",
    "remote_receipt",
)

_RECONCILIATION_FIELDS = (
    "actual_spend",
    "trajectory_outputs",
    "trajectory_outputs_reconciled",
    "trajectory_side_effects",
    "trajectory_side_effects_reconciled",
    "trajectory_exact_commit",
    "trajectory_pull_request",
    "trajectory_predicate",
    "trajectory_owner_receipt",
)


def attempt_launch_for(task: Task, attempt_id: str | None = None) -> DispatchLogEntry | None:
    """Return persisted launch evidence; never synthesize it after execution."""

    for entry in task.dispatch_log:
        if (
            entry.attempt_id
            and (attempt_id is None or entry.attempt_id == attempt_id)
            and entry.attempt_classification is not None
            and entry.execution_profile is not None
        ):
            return entry
    return None


def current_attempt_id(task: Task) -> str | None:
    return next((entry.attempt_id for entry in reversed(task.dispatch_log) if entry.attempt_id), None)


def attempt_contract_is_current(task: Task, launch: DispatchLogEntry) -> bool:
    """Prove the owner row still carries the exact contract frozen at launch."""

    if not launch.attempt_contract_hash:
        return False
    try:
        return execution_contract_hash(task) == launch.attempt_contract_hash
    except (TypeError, ValueError):
        return False


def remote_custody_updates(receipt: Mapping[str, object] | None) -> dict[str, object]:
    """Select only typed remote-attempt fields from an already validated receipt."""

    if receipt is None:
        return {}
    return {field: receipt[field] for field in _REMOTE_FIELDS if receipt.get(field) is not None}


def reconciliation_custody_updates(receipt: Mapping[str, object] | None) -> dict[str, object]:
    """Select bounded reconciliation fields; model validation remains the final fence."""

    if receipt is None:
        return {}
    updates = {
        field: receipt[field]
        for field in _RECONCILIATION_FIELDS
        if receipt.get(field) is not None
        and field
        not in {
            "actual_spend",
            "trajectory_outputs",
            "trajectory_outputs_reconciled",
            "trajectory_side_effects",
            "trajectory_side_effects_reconciled",
        }
    }
    spend = receipt.get("actual_spend")
    if spend is not None:
        try:
            updates["actual_spend"] = ExecutionSpend.model_validate(spend).model_dump(
                mode="json",
                exclude_defaults=True,
            )
        except (TypeError, ValueError):
            updates["actual_spend"] = None
    raw_outputs = receipt.get("trajectory_outputs")
    if isinstance(raw_outputs, (list, tuple)):
        outputs: list[dict[str, object]] = []
        output_valid = len(raw_outputs) <= 64
        for value in raw_outputs[:64]:
            try:
                outputs.append(ExecutionOutput.model_validate(value).model_dump(mode="json"))
            except (TypeError, ValueError):
                output_valid = False
        updates["trajectory_outputs"] = outputs
        updates["trajectory_outputs_reconciled"] = bool(receipt.get("trajectory_outputs_reconciled") and output_valid)
    raw_effects = receipt.get("trajectory_side_effects")
    if isinstance(raw_effects, (list, tuple)):
        effects: list[dict[str, object]] = []
        effect_valid = len(raw_effects) <= 64
        for value in raw_effects[:64]:
            try:
                effects.append(ExecutionSideEffect.model_validate(value).model_dump(mode="json"))
            except (TypeError, ValueError):
                effect_valid = False
        updates["trajectory_side_effects"] = effects
        updates["trajectory_side_effects_reconciled"] = bool(
            receipt.get("trajectory_side_effects_reconciled") and effect_valid
        )
    return updates


def close_changed_contract_attempt(
    task: Task,
    launch: DispatchLogEntry,
    *,
    now: datetime,
    agent: str,
    phase: str,
    stale_result: bool | str | None = None,
    model_selection: Mapping[str, Any] | None = None,
    remote_submission: Mapping[str, object] | None = None,
    reconciliation: Mapping[str, object] | None = None,
    execution_started: bool = True,
) -> bool:
    """Close the authoritative stale attempt once and expose the new contract.

    Returns ``True`` only when this call appended the terminal attempt.  Callers
    use that edge to reconcile one-time actions such as refunding a reservation
    that never reached provider execution.
    """

    attempt_id = str(launch.attempt_id or "")
    if not attempt_id or current_attempt_id(task) != attempt_id:
        return False
    latest_attempt_event = next(
        (entry for entry in reversed(task.dispatch_log) if entry.attempt_id == attempt_id),
        None,
    )
    terminal_statuses = {"done", "failed", "failed_blocked", "needs_human"}
    closed_now = latest_attempt_event is None or latest_attempt_event.status not in terminal_statuses
    if closed_now:
        output = "execution contract changed after reservation; stale attempt closed without applying provider output"
        if stale_result is not None:
            output += f"; stale provider result preserved for old attempt only: {str(stale_result)[:300]}"
        update: dict[str, Any] = {
            "timestamp": now,
            "agent": agent,
            "session_id": f"contract-mismatch-{phase}",
            "status": "failed",
            "trajectory_outcome": "failed",
            "output": output,
        }
        if not execution_started:
            update.update(
                {
                    "actual_spend": None,
                    "trajectory_outputs": None,
                    "trajectory_outputs_reconciled": None,
                    "trajectory_side_effects": None,
                    "trajectory_side_effects_reconciled": None,
                    "effect_receipt": None,
                    "selected_model": None,
                    "selection_source": None,
                    "catalog_hash": None,
                }
            )
            update.update({field: None for field in _REMOTE_FIELDS})
        if execution_started:
            if model_selection is not None:
                update.update(
                    {
                        "selected_model": model_selection.get("selected_model"),
                        "selection_source": model_selection.get("selection_source"),
                        "catalog_hash": model_selection.get("catalog_hash"),
                    }
                )
            update.update(remote_custody_updates(remote_submission))
            source_reconciliation = {
                field: getattr(latest_attempt_event or launch, field, None) for field in _RECONCILIATION_FIELDS
            }
            source_reconciliation.update(dict(reconciliation or {}))
            update.update(reconciliation_custody_updates(source_reconciliation))
        task.dispatch_log.append((latest_attempt_event or launch).model_copy(update=update))
    task.status = "open"
    task.updated = now
    head = task.dispatch_log[-1] if task.dispatch_log else None
    try:
        current_contract_hash = execution_contract_hash(task)
    except (TypeError, ValueError):
        current_contract_hash = None
    if (
        head is None
        or head.status != "open"
        or head.attempt_id is not None
        or head.current_contract_hash != current_contract_hash
    ):
        task.dispatch_log.append(
            DispatchLogEntry(
                timestamp=now,
                agent=agent,
                session_id=f"contract-mismatch-{phase}-requeue",
                status="open",
                route_to=task.target_agent,
                current_contract_hash=current_contract_hash,
                output="dispatch: changed execution contract reopened for a fresh attempt",
            )
        )
    return closed_now
