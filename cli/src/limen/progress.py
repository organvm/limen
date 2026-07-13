"""Truthful macro/micro progress projection for the whole Limen work universe.

The board, prompt corpus, obligations, recommendations, and estate sensors are
different sources of work.  This module keeps those dimensions separate and
renders their coverage explicitly.  A missing source or missing classification
is debt; it is never interpreted as zero work.

Progress bars are intentionally conservative:

* macro bars are the share of tasks in ``done`` or ``archived``;
* micro bars show canonical lifecycle stage, not estimated effort;
* blocked and human-routed work remains debt until its task reaches a terminal
  board state with its own durable receipt.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from limen.models import LimenFile, Task
from limen.workstream import assign_channel

SCHEMA = "limen.progress-universe.v1"
COMPLETE_STATUSES = frozenset({"done", "archived"})
BLOCKED_STATUSES = frozenset({"failed", "failed_blocked", "needs_human"})
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
LIFECYCLE_STAGE = {
    "open": 0,
    "dispatched": 25,
    "in_progress": 50,
    "failed": 50,
    "failed_blocked": 50,
    "needs_human": 50,
    "done": 100,
    "archived": 100,
}

_ORIGIN_ALIASES = {
    "ask": "human_prompt",
    "human": "human_prompt",
    "human_ask": "human_prompt",
    "prompt": "human_prompt",
    "human_prompt": "human_prompt",
    "due": "obligation",
    "external": "obligation",
    "obligation": "obligation",
    "agent": "agent_recommendation",
    "agent_recommendation": "agent_recommendation",
    "recommendation": "agent_recommendation",
    "system": "system_debt",
    "debt": "system_debt",
    "system_debt": "system_debt",
}
_HORIZON_ALIASES = {
    "past": "past",
    "recovery": "past",
    "present": "present",
    "now": "present",
    "current": "present",
    "next": "future",
    "future": "future",
    "later": "future",
}


def _slug(value: Any) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return normalized or None


def _field_or_label(task: Task, fields: Iterable[str], label_prefixes: Iterable[str]) -> str | None:
    """Read explicit metadata without guessing from a title or task ID."""

    for field in fields:
        value = getattr(task, field, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    prefixes = tuple(f"{prefix}:" for prefix in label_prefixes)
    for label in task.labels:
        lowered = str(label).strip().lower()
        for prefix in prefixes:
            if lowered.startswith(prefix) and lowered[len(prefix) :].strip():
                return lowered[len(prefix) :].strip()
    return None


def task_origin(task: Task) -> str:
    raw = _field_or_label(
        task,
        ("intent_origin", "work_origin", "origin"),
        ("origin", "intent-origin", "work-origin"),
    )
    value = _slug(raw)
    return _ORIGIN_ALIASES.get(value or "", value or "unknown")


def task_horizon(task: Task) -> str:
    raw = _field_or_label(task, ("time_horizon", "horizon"), ("horizon", "time-horizon"))
    value = _slug(raw)
    return _HORIZON_ALIASES.get(value or "", value or "unknown")


def task_due(task: Task) -> str | None:
    return _field_or_label(
        task,
        ("due_at", "due_on", "due_date", "deadline"),
        ("due", "due-at", "due-on", "deadline"),
    )


def task_value_case(task: Task) -> str | None:
    """Return the explicit reason this task deserves scarce work capacity."""

    return _field_or_label(
        task,
        ("value_case", "expected_value", "work_credit"),
        ("value", "value-case", "work-credit"),
    )


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 1)


def _task_row(task: Task, root: Path) -> dict[str, Any]:
    complete = task.status in COMPLETE_STATUSES
    contract_ready = bool(task.predicate and task.receipt_target)
    origin = task_origin(task)
    horizon = task_horizon(task)
    value_case = task_value_case(task)
    underwriting_ready = bool(
        task.repo
        and origin != "unknown"
        and horizon != "unknown"
        and value_case
        and task.predicate
        and task.receipt_target
    )
    credit_booking = (
        "board_claim_with_contract"
        if complete and contract_ready
        else ("unsubstantiated_terminal_claim" if complete else "not_booked")
    )
    return {
        "id": task.id,
        "title": task.title,
        "repo": task.repo or "unknown",
        "workstream": assign_channel(task, root),
        "origin": origin,
        "horizon": horizon,
        "due": task_due(task),
        "value_case": value_case,
        "credit_forecast": value_case,
        "credit_booking": credit_booking,
        "agent": task.target_agent,
        "priority": task.priority,
        "status": task.status,
        "complete": complete,
        "blocked": task.status in BLOCKED_STATUSES,
        "lifecycle_stage_pct": LIFECYCLE_STAGE.get(task.status, 0),
        "predicate_present": bool(task.predicate),
        "receipt_target_present": bool(task.receipt_target),
        "contract_ready": contract_ready,
        "underwriting_ready": underwriting_ready,
        "work_loan_cost_runs": task.budget_cost,
        "debit_requested_runs": task.budget_cost,
        "updated": task.updated.isoformat() if task.updated else None,
        "url": task.urls[0] if task.urls else None,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    complete = sum(bool(row["complete"]) for row in rows)
    debt = total - complete
    blocked = sum(bool(row["blocked"]) for row in rows)
    contract_ready_active = sum(bool(row["contract_ready"]) and not row["complete"] for row in rows)
    underwritten_active = sum(bool(row["underwriting_ready"]) and not row["complete"] for row in rows)
    requested_active_debit_runs = sum(int(row["debit_requested_runs"]) for row in rows if not row["complete"])
    underwritten_active_debit_runs = sum(
        int(row["debit_requested_runs"]) for row in rows if row["underwriting_ready"] and not row["complete"]
    )
    forecast_credit_active = sum(bool(row["credit_forecast"]) and not row["complete"] for row in rows)
    board_credit_claims = sum(row["credit_booking"] == "board_claim_with_contract" for row in rows)
    unsubstantiated_terminal_claims = sum(row["credit_booking"] == "unsubstantiated_terminal_claim" for row in rows)
    return {
        "total": total,
        "complete": complete,
        "active_debt": debt,
        "blocked": blocked,
        "closure_pct": _percent(complete, total),
        "contract_ready_active": contract_ready_active,
        "contract_coverage_pct": _percent(contract_ready_active, debt),
        "underwritten_active": underwritten_active,
        "underwriting_coverage_pct": _percent(underwritten_active, debt),
        "requested_active_debit_runs": requested_active_debit_runs,
        "underwritten_active_debit_runs": underwritten_active_debit_runs,
        "ununderwritten_active_debit_runs": (requested_active_debit_runs - underwritten_active_debit_runs),
        "debit_underwriting_coverage_pct": _percent(underwritten_active_debit_runs, requested_active_debit_runs),
        "forecast_credit_active": forecast_credit_active,
        "forecast_credit_coverage_pct": _percent(forecast_credit_active, debt),
        "board_credit_claims": board_credit_claims,
        "unsubstantiated_terminal_claims": unsubstantiated_terminal_claims,
    }


def _groups(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = row.get(field)
        key = str(value) if value not in (None, "") else "unknown"
        buckets.setdefault(key, []).append(row)
    grouped = [{field: key, **_summarize(items)} for key, items in buckets.items()]
    return sorted(grouped, key=lambda item: (-int(item["active_debt"]), str(item[field])))


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


def _timestamp(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("generated_at", "generated", "ts", "timestamp", "checked_at"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    freshness = payload.get("freshness")
    if isinstance(freshness, dict):
        return _timestamp(freshness)
    current_ops = payload.get("current_ops")
    if isinstance(current_ops, dict):
        return _timestamp(current_ops)
    return None


def _age_hours(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return round(max(0.0, (now - parsed.astimezone(UTC)).total_seconds() / 3600), 2)


def _source_coverage(root: Path, now: datetime) -> list[dict[str, Any]]:
    definitions = (
        ("omega", "Omega acceptance rungs", root / "logs" / "omega.json", 2.0),
        (
            "handoff",
            "Warm handoff and provider headroom",
            root / "logs" / "handoff.json",
            1.5,
        ),
        (
            "prompt_authority",
            "Prompt corpus authority seal",
            root / "docs" / "prompt-authority-seal.json",
            24.0,
        ),
        (
            "lifecycle",
            "Local and remote lifecycle pressure",
            root / "logs" / "session-lifecycle-pressure.json",
            24.0,
        ),
        ("mail", "Mail obligations", root / "logs" / "uma-mail-status.json", 24.0),
        (
            "contributions",
            "Contribution estate",
            root / "logs" / "contributions.json",
            24.0,
        ),
        (
            "financial",
            "Financial organ",
            root / "logs" / "financial-organ-state.json",
            24.0,
        ),
        (
            "portfolio",
            "Portfolio repo and PR census",
            root / "logs" / "portfolio-debt.json",
            24.0,
        ),
    )
    rows: list[dict[str, Any]] = []
    for source_id, label, path, max_age in definitions:
        payload = _read_json(path)
        generated = _timestamp(payload)
        age = _age_hours(generated, now)
        status = "dark" if payload is None else ("undated" if generated is None else "ready")
        if payload is not None and age is not None and age > max_age:
            status = "stale"
        if source_id == "mail" and isinstance(payload, dict):
            freshness = (payload.get("current_ops") or {}).get("freshness") or {}
            if freshness.get("is_stale") is True:
                status = "stale"
        rows.append(
            {
                "id": source_id,
                "label": label,
                "status": status,
                "path": str(path.relative_to(root)),
                "generated_at": generated,
                "age_hours": age,
                "max_age_hours": max_age,
            }
        )
    return rows


def build_progress_snapshot(limen: LimenFile, root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Build the lossless board projection and its source-completeness manifest."""

    generated = (now or datetime.now(UTC)).astimezone(UTC)
    rows = [_task_row(task, root) for task in limen.tasks]
    active = [row for row in rows if not row["complete"]]
    summary = _summarize(rows)
    origin_known = sum(row["origin"] != "unknown" for row in active)
    horizon_known = sum(row["horizon"] != "unknown" for row in active)
    due_known = sum(row["due"] is not None for row in active)
    source_rows = _source_coverage(root, generated)
    source_ready = sum(row["status"] == "ready" for row in source_rows)

    summary.update(
        {
            "origin_coverage_pct": _percent(origin_known, len(active)),
            "horizon_coverage_pct": _percent(horizon_known, len(active)),
            "due_metadata_coverage_pct": _percent(due_known, len(active)),
            "source_freshness_pct": _percent(source_ready, len(source_rows)),
        }
    )
    return {
        "schema": SCHEMA,
        "generated_at": generated.isoformat().replace("+00:00", "Z"),
        "progress_definition": {
            "macro": "done or archived tasks divided by all tasks in the selected group",
            "micro": "canonical lifecycle stage; this is not an effort estimate",
            "debt": "every task not done or archived, plus every dark or stale required source",
            "underwriting": (
                "active task has explicit origin, horizon, value case, owner repo, predicate, receipt target, "
                "and run cost"
            ),
            "accounting": (
                "requested run cost is a debit; value case is forecast credit; terminal board state with a "
                "predicate and receipt target is only a board credit claim until the owning receipt is verified"
            ),
        },
        "summary": summary,
        "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
        "dimensions": {
            field: _groups(rows, field) for field in ("workstream", "origin", "horizon", "agent", "repo", "status")
        },
        "source_coverage": source_rows,
        "tasks": rows,
    }


def progress_bar(percent: float, *, width: int = 20, ascii_only: bool = False) -> str:
    bounded = max(0.0, min(100.0, float(percent)))
    filled = int(round(width * bounded / 100.0))
    on, off = ("#", ".") if ascii_only else ("█", "░")
    return f"[{on * filled}{off * (width - filled)}]"


def _short(value: str, width: int) -> str:
    return value if len(value) <= width else value[: max(1, width - 1)] + "…"


def render_progress(
    snapshot: dict[str, Any],
    *,
    view: str = "workstream",
    scope: str | None = None,
    level: str = "all",
    limit: int | None = 50,
    ascii_only: bool = False,
) -> str:
    """Render a terminal-safe macro/micro progress view."""

    lines: list[str] = [
        f"Limen work universe — {snapshot['generated_at']}",
        "Bars show terminal closure or lifecycle stage, never estimated effort.",
        "",
    ]
    summary = snapshot["summary"]
    if level in {"macro", "all"}:
        metrics = (
            (
                "BOARD CLOSURE",
                summary["closure_pct"],
                f"{summary['complete']}/{summary['total']} terminal",
            ),
            (
                "ACTIVE CONTRACT",
                summary["contract_coverage_pct"],
                f"{summary['contract_ready_active']}/{summary['active_debt']} predicate + receipt",
            ),
            (
                "WORK LOANS",
                summary["underwriting_coverage_pct"],
                f"{summary['underwritten_active']}/{summary['active_debt']} fully underwritten",
            ),
            (
                "CAPITAL DEBITS",
                summary["debit_underwriting_coverage_pct"],
                f"{summary['underwritten_active_debit_runs']}/{summary['requested_active_debit_runs']} run-debits underwritten",
            ),
            (
                "CREDIT FORECAST",
                summary["forecast_credit_coverage_pct"],
                f"{summary['forecast_credit_active']}/{summary['active_debt']} active leaves name expected credit",
            ),
            (
                "ORIGIN COVERAGE",
                summary["origin_coverage_pct"],
                "due vs prompt vs recommendation vs debt",
            ),
            (
                "HORIZON COVERAGE",
                summary["horizon_coverage_pct"],
                "past vs present vs future",
            ),
            (
                "DUE COVERAGE",
                summary["due_metadata_coverage_pct"],
                "active tasks with explicit due metadata",
            ),
            (
                "SOURCE FRESHNESS",
                summary["source_freshness_pct"],
                "required estate sensors fresh",
            ),
        )
        for label, pct, note in metrics:
            lines.append(f"{label:<16} {progress_bar(pct, ascii_only=ascii_only)} {pct:>5.1f}%  {note}")
        lines.extend(["", f"{view.upper()} ZOOM"])
        for group in snapshot["dimensions"][view]:
            name = str(group[view])
            if scope and name != scope:
                continue
            lines.append(
                f"  {_short(name, 22):<22} {progress_bar(group['closure_pct'], width=14, ascii_only=ascii_only)}"
                f" {group['closure_pct']:>5.1f}%  debt={group['active_debt']:<4} blocked={group['blocked']:<4}"
            )
        lines.extend(["", "SOURCE COVERAGE"])
        for source in snapshot["source_coverage"]:
            marker = {
                "ready": "OK",
                "stale": "STALE",
                "undated": "DATE?",
                "dark": "DARK",
            }[source["status"]]
            age = "unknown age" if source["age_hours"] is None else f"{source['age_hours']}h old"
            lines.append(f"  {marker:<5} {_short(source['label'], 38):<38} {age}")

    if level in {"micro", "all"}:
        tasks = [row for row in snapshot["tasks"] if not row["complete"]]
        if scope:
            tasks = [row for row in tasks if str(row.get(view) or "unknown") == scope]
        tasks.sort(
            key=lambda row: (
                PRIORITY_ORDER.get(str(row["priority"]), 99),
                0 if row["due"] else 1,
                str(row["due"] or ""),
                str(row["id"]),
            )
        )
        shown = tasks if limit is None else tasks[: max(0, limit)]
        lines.extend(["", f"MICRO DEBT — {len(shown)} shown / {len(tasks)} matching"])
        for row in shown:
            pct = float(row["lifecycle_stage_pct"])
            flags = []
            if row["blocked"]:
                flags.append("BLOCKED")
            if not row["contract_ready"]:
                flags.append("NO-CONTRACT")
            if not row["underwriting_ready"]:
                flags.append("NO-UNDERWRITE")
            if row["due"]:
                flags.append(f"DUE:{row['due']}")
            suffix = " " + ",".join(flags) if flags else ""
            lines.append(
                f"  {progress_bar(pct, width=10, ascii_only=ascii_only)} {pct:>3.0f}%"
                f" {_short(row['id'], 30):<30} {_short(row['status'], 14):<14}"
                f" {_short(row['title'], 54)}{suffix}"
            )
        if limit is not None and len(tasks) > len(shown):
            lines.append(f"  … {len(tasks) - len(shown)} more; use --all to print every matching debt leaf")
    return "\n".join(lines) + "\n"
