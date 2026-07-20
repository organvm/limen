"""Canonical report rendering, validation, and seal generation."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

TITLE = "Seven-Agent Whole-Estate Session Review"
PREFIX = {
    "codex": "CX",
    "claude": "CL",
    "agy": "AG",
    "opencode": "OC",
    "gemini": "GM",
    "copilot": "CP",
    "jules": "JL",
}
LOCAL_PATH_RE = re.compile(r"(?:^|[\"'\s])(?:~/|/Users/|/Volumes/|file://)")


def stable_json(value: Any) -> bytes:
    """Return canonical, newline-terminated public JSON bytes."""

    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Hash bytes for deterministic output and seal receipts."""

    return hashlib.sha256(value).hexdigest()


def _source(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "frozen_snapshot",
        "label": "Frozen seven-agent estate snapshot",
        "path": "docs/reviews/seven-agent-whole-estate-2026-07-19/snapshot.json",
        "query": {
            "description": (
                "Canonical native sessions joined to exact prompt atoms and timestamped exact-head GitHub evidence."
            ),
            "language": "python",
            "sql": ("SELECT * FROM read_json_auto('docs/reviews/seven-agent-whole-estate-2026-07-19/snapshot.json');"),
            "tables_used": [
                "canonical native session records",
                "prompt atom projection",
                "GitVS estate registry",
                "GitHub pull request exact-head contexts",
            ],
            "filters": [
                f"snapshot_at < {snapshot['snapshot_at']}",
                "half-open completed-week and rolling-seven-day windows",
                "exact prompt atom linkage only",
                "private identifiers and local paths excluded",
            ],
            "metric_definitions": [
                (
                    "Canonical session count: unique provider-native root or child "
                    "identity after fragment and token-event deduplication."
                ),
                (
                    "Verified done: exact prompt atom or owner-specific predicate, "
                    "default-reachable receipt, exact head, and a predicate completed "
                    "no later than snapshot_at."
                ),
                (
                    "Coverage unknown: source, identity, token/duration meter, atom "
                    "binding, or historical check timing is unavailable."
                ),
            ],
            "executed_at": snapshot["snapshot_at"],
        },
    }


def _table(
    ident: str,
    title: str,
    dataset: str,
    columns: list[tuple[str, str, str]],
    sort_field: str,
    direction: str = "desc",
    *,
    subtitle: str | None = None,
) -> dict[str, Any]:
    return {
        "id": ident,
        "title": title,
        "dataset": dataset,
        "columns": [{"field": field, "label": label, "type": kind} for field, label, kind in columns],
        "defaultSort": {"field": sort_field, "direction": direction},
        "density": "compact",
        "sourceId": "frozen_snapshot",
        **({"subtitle": subtitle} if subtitle else {}),
    }


def _compact_sessions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for agent, rows in snapshot.get("session_appendix", {}).items():
        grouped: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = collections.defaultdict(list)
        for index, row in enumerate(rows, start=1):
            grouped[
                (
                    str(row.get("role") or "?"),
                    str(row.get("time_basis") or "unknown"),
                    "mapped" if row.get("source_atom_ids") else "coverage-gap",
                )
            ].append((index, row))
        for (role, basis, coverage), members in sorted(grouped.items()):
            indices = [index for index, _ in members]
            result.append(
                {
                    "agent": agent,
                    "role": role,
                    "time_basis": basis,
                    "atom_coverage": coverage,
                    "session_range": (
                        f"{PREFIX.get(agent, 'UN')}{min(indices):04d}-{PREFIX.get(agent, 'UN')}{max(indices):04d}"
                    ),
                    "sessions": len(members),
                    "events": sum(int(row.get("events") or 0) for _, row in members),
                    "first_start": min(str(row.get("start") or "") for _, row in members),
                    "last_end": max(str(row.get("end") or "") for _, row in members),
                }
            )
    return result


def build_artifact(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build the complete technical report artifact from reviewed rows."""

    source = _source(snapshot)
    asks = snapshot.get("asks") or []
    outcomes = collections.Counter(str(row.get("outcome")) for row in asks)
    mapped_sessions = sum(
        bool(row.get("source_atom_ids")) for rows in snapshot.get("session_appendix", {}).values() for row in rows
    )
    total_sessions = sum(len(rows) for rows in snapshot.get("session_appendix", {}).values())
    unknown_metrics = sum(row.get("token_basis") == "unknown" for row in snapshot.get("comparison") or [])
    comparison = snapshot.get("comparison") or []
    findings = []
    for agent in sorted({str(row.get("agent")) for row in asks} | set(PREFIX)):
        agent_asks = [row for row in asks if row.get("agent") == agent]
        findings.append(
            {
                "agent": agent,
                "asks": len(agent_asks),
                "verified_done": sum(row.get("outcome") == "verified_done" for row in agent_asks),
                "verified_partial": sum(row.get("outcome") == "verified_partial" for row in agent_asks),
                "open": sum(row.get("outcome") == "durably_homed_open" for row in agent_asks),
                "coverage_unknown": sum(row.get("outcome") == "coverage_unknown" for row in agent_asks),
            }
        )
    datasets = {
        "comparison": comparison,
        "root_session_volume": snapshot.get("root_session_volume") or [],
        "outcome_distribution": snapshot.get("outcome_distribution") or [],
        "agent_findings": findings,
        "deliverables": snapshot.get("deliverables") or [],
        "session_appendix": _compact_sessions(snapshot),
    }
    blocks = [
        {"id": "title", "type": "markdown", "body": f"# {TITLE}"},
        {
            "id": "technical_summary",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## The prior completion split was not decision-grade\n\n"
                f"The corrected v2 model contains **{len(asks):,} exact or explicitly "
                f"coverage-unknown asks**, not 820 task rows relabeled as prompts. "
                f"It canonicalizes **{total_sessions:,} unique native sessions**; "
                f"{mapped_sessions:,} carry an exact prompt-atom binding and the rest "
                "remain visible coverage gaps. "
                f"Only {outcomes['verified_done']:,} asks satisfy semantic lineage plus "
                "timestamped exact-head proof. These figures replace—not preserve—the "
                "provisional v1 totals."
            ),
        },
        {
            "id": "session_finding",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Canonical identity removes provider-fragment inflation\n\n"
                "Root and child records are counted after native-ID fragment merging and "
                "token-event deduplication. Claude child `agentId` values remain children "
                "of their root `sessionId`; Codex file fragments with the same native ID "
                "become one session. The grouped chart shows both windows as overlapping, "
                "non-additive views."
            ),
        },
        {"id": "session_chart_block", "type": "chart", "chartId": "session_chart"},
        {
            "id": "outcome_finding",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Receipt proximity no longer proves an ask\n\n"
                "A PR changes an ask outcome only through an exact prompt atom or an "
                "owner-specific predicate. Cross-repository control-plane work is "
                "assistance; it cannot close unrelated repository asks. Bars therefore "
                "show conservative outcomes, with unknown lineage retained rather than "
                "converted into completion."
            ),
        },
        {"id": "outcome_chart_block", "type": "chart", "chartId": "outcome_chart"},
        {
            "id": "scope_definitions",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Scope and metric definitions\n\n"
                "The completed calendar week is the prior Monday-to-Monday interval in "
                "America/New_York. The rolling seven-day view ends at the frozen snapshot; "
                "the views overlap and are never summed. Session time is observed span, "
                "not active labor. Native token components remain provider-specific. "
                f"Unknown token bases appear in {unknown_metrics:,} agent-window rows."
            ),
        },
        {"id": "comparison_table_block", "type": "table", "tableId": "comparison_table"},
        {
            "id": "methodology",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Methodology uses exact authority and historical proof\n\n"
                "Collection reads bounded native stores, merges provider fragments, and "
                "loads the exact prompt-atom projection. Reconciliation derives GitHub "
                "owners from GitVS, unions evidence-linked repositories, resolves "
                "redirects, and queries the exact head's timestamped check contexts. "
                "Executor, verifier, integrator, and lander roles stay separate."
            ),
        },
        {"id": "role_table_block", "type": "table", "tableId": "role_table"},
        {"id": "appendix_table_block", "type": "table", "tableId": "appendix_table"},
        {
            "id": "limitations",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Coverage gaps remain explicit\n\n"
                "Missing native duration or token meters remain null. Sessions without an "
                "exact atom binding remain coverage gaps. Missing historical check timing "
                "can prove only `verified_partial`. A live registry census is useful for "
                "canonicalization but does not retroactively describe repository existence "
                "at the snapshot."
            ),
        },
        {
            "id": "next_steps",
            "type": "markdown",
            "body": (
                "## Recommended next step\n\n"
                "Use this seal as the recurrent review source, keep unresolved atoms in "
                "their single durable owner, and run trend comparisons only across "
                "completed calendar weeks. Estate execution is a separate campaign."
            ),
        },
        {
            "id": "questions",
            "type": "markdown",
            "body": (
                "## Further questions\n\n"
                "- Which providers can expose historically timestamped native meters?\n"
                "- Which remaining coverage gaps can be bound to an exact prompt atom "
                "without text inference?\n"
                "- Which owner-specific predicates should become reusable dispatch "
                "contracts?"
            ),
        },
    ]
    charts = [
        {
            "id": "session_chart",
            "title": "Canonical root-session volume by review window",
            "subtitle": ("Completed week and rolling seven-day views overlap and are non-additive."),
            "type": "bar",
            "dataset": "root_session_volume",
            "encodings": {
                "x": {"field": "agent", "type": "nominal"},
                "y": {"field": "root_sessions", "type": "quantitative"},
                "color": {"field": "window", "type": "nominal"},
            },
            "options": {"orientation": "vertical", "grouping": "grouped"},
            "sourceId": "frozen_snapshot",
        },
        {
            "id": "outcome_chart",
            "title": "Prompt-atom outcome distribution by agent",
            "subtitle": ("Unknown and partial outcomes remain visible when semantic or historical proof is absent."),
            "type": "bar",
            "dataset": "outcome_distribution",
            "encodings": {
                "x": {"field": "agent", "type": "nominal"},
                "y": {"field": "ask_count", "type": "quantitative"},
                "color": {"field": "outcome", "type": "nominal"},
            },
            "options": {"orientation": "vertical", "grouping": "stacked"},
            "sourceId": "frozen_snapshot",
        },
    ]
    tables = [
        _table(
            "comparison_table",
            "Agent and window evidence",
            "comparison",
            [
                ("window", "Window", "string"),
                ("agent", "Agent", "string"),
                ("root_sessions", "Root sessions", "number"),
                ("child_sessions", "Child sessions", "number"),
                ("union_wall_hours", "Union wall hours", "number"),
                ("asks_observed", "Exact asks", "number"),
                ("verified_done", "Verified done", "number"),
                ("open_or_unknown", "Open or unknown", "number"),
                ("token_basis", "Native token basis", "string"),
            ],
            "root_sessions",
        ),
        _table(
            "role_table",
            "Receipt role credit",
            "deliverables",
            [
                ("title", "Deliverable", "string"),
                ("outcome", "Outcome", "string"),
                ("executor", "Executor", "string"),
                ("verifiers", "Verifiers", "string"),
                ("integrator", "Integrator", "string"),
                ("lander", "Lander", "string"),
                ("receipt", "Receipt", "string"),
            ],
            "outcome",
            "asc",
            subtitle=("Unknown actors remain blank; one role is never substituted for another."),
        ),
        _table(
            "appendix_table",
            "Grouped canonical session appendix",
            "session_appendix",
            [
                ("agent", "Agent", "string"),
                ("role", "Role", "string"),
                ("time_basis", "Time basis", "string"),
                ("atom_coverage", "Atom coverage", "string"),
                ("session_range", "Report-local range", "string"),
                ("sessions", "Sessions", "number"),
                ("events", "Events", "number"),
                ("first_start", "First start", "datetime"),
                ("last_end", "Last end", "datetime"),
            ],
            "agent",
            "asc",
        ),
    ]
    reconciliation_ready = snapshot.get("reconciliation", {}).get("state") == "complete"
    access_issues = []
    if not reconciliation_ready:
        access_issues.append(
            {
                "sourceId": "frozen_snapshot",
                "issue": (
                    "Required prompt-authority or historical receipt evidence is "
                    "incomplete; affected outcomes remain coverage_unknown or "
                    "verified_partial."
                ),
            }
        )
    return {
        "surface": "report",
        "manifest": {
            # Data Analytics artifact runtime schema remains v1. The analytical
            # record carried inside the datasets is the public review schema v2.
            "version": 1,
            "title": TITLE,
            "generatedAt": snapshot["snapshot_at"],
            "blocks": blocks,
            "charts": charts,
            "tables": tables,
            "sources": [source],
        },
        "snapshot": {
            "version": 1,
            "status": "ready" if reconciliation_ready else "partial",
            "generatedAt": snapshot["snapshot_at"],
            "datasets": datasets,
            **({"accessIssues": access_issues} if access_issues else {}),
        },
        "sources": [source],
        "package_info": {
            "snapshot_at": snapshot["snapshot_at"],
            "live": False,
            "description": "Frozen, redacted, canonical whole-estate session review.",
        },
    }


def validate_artifact_contract(artifact: dict[str, Any]) -> list[str]:
    """Run local structural, boundedness, and privacy validation."""

    errors: list[str] = []
    manifest = artifact.get("manifest") or {}
    snapshot = artifact.get("snapshot") or {}
    blocks = manifest.get("blocks") or []
    if artifact.get("surface") != "report":
        errors.append("surface must be report")
    if not manifest.get("title"):
        errors.append("manifest title is required")
    expected_heading = f"# {manifest.get('title')}"
    if not blocks or str(blocks[0].get("body") or "").strip() != expected_heading:
        errors.append("first block must be a matching title heading")
    datasets = snapshot.get("datasets")
    if not isinstance(datasets, dict):
        errors.append("snapshot.datasets must be an object")
        datasets = {}
    if len(datasets) > 50:
        errors.append("snapshot exceeds 50 datasets")
    for dataset_id, rows in datasets.items():
        if not isinstance(rows, list):
            errors.append(f"dataset {dataset_id} must be a row list")
        elif len(rows) > 2000:
            errors.append(f"dataset {dataset_id} exceeds 2000 rows")
    text = stable_json(artifact).decode("utf-8")
    if LOCAL_PATH_RE.search(text):
        errors.append("artifact contains a machine-local path")
    chart_ids = {chart.get("id") for chart in manifest.get("charts") or []}
    for block in blocks:
        if block.get("type") == "chart" and block.get("chartId") not in chart_ids:
            errors.append(f"chart block {block.get('id')} has no declared chart")
    return errors


def run_synthetic_tests(test_path: Path) -> dict[str, Any]:
    """Run the implicated synthetic gate and derive its factual receipt."""

    try:
        result = subprocess.run(
            ["python3", "-B", "-m", "unittest", "-v", str(test_path)],
            cwd=test_path.parent,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "tests": None,
            "result": "failed",
            "detail": type(exc).__name__,
        }
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    match = re.search(r"Ran ([0-9]+) tests?", output)
    return {
        "tests": int(match.group(1)) if match else None,
        "result": "passed" if result.returncode == 0 else "failed",
        "detail": "unittest exit 0" if result.returncode == 0 else f"unittest exit {result.returncode}",
    }


def build_validation(
    snapshot: dict[str, Any],
    artifact: dict[str, Any],
    *,
    test_path: Path,
) -> dict[str, Any]:
    """Build validation.json from actual tests and local artifact validation."""

    tests = run_synthetic_tests(test_path)
    errors = validate_artifact_contract(artifact)
    return {
        "snapshot_at": snapshot["snapshot_at"],
        "synthetic_tests": tests["tests"],
        "synthetic_tests_result": tests["result"],
        "synthetic_tests_detail": tests["detail"],
        "remote_reconciliation": snapshot.get("reconciliation") or {},
        "dataset_count": len(artifact["snapshot"]["datasets"]),
        "rows_by_dataset": {key: len(value) for key, value in artifact["snapshot"]["datasets"].items()},
        "artifact_bytes": len(stable_json(artifact)),
        "validator": "passed" if not errors else "failed",
        "validation_errors": errors,
        "hosting": {
            "project": "existing owner-only Sites project",
            "corrected_version": "pending default-reachable implementation",
            "allowed_groups": 0,
        },
    }


def build_seal(
    snapshot: dict[str, Any],
    report_files: dict[str, bytes],
    *,
    implementation_digest: str,
) -> dict[str, Any]:
    """Build the recurrent partial-source seal over exact report bytes."""

    asks = snapshot.get("asks") or []
    sessions = [row for values in snapshot.get("session_appendix", {}).values() for row in values]
    prompt_coverage = (snapshot.get("coverage") or {}).get("prompt_atoms") or {}
    scope = prompt_coverage.get("source_scope") or {}
    prompt_exact = bool(
        prompt_coverage.get("available") is True
        and prompt_coverage.get("coverage") != "coverage_unknown"
        and scope.get("scope") == "all"
        and scope.get("target_scope") == "all"
        and scope.get("all_baseline_complete") is True
    )
    session_coverage_complete = all(row.get("source_atom_ids") for row in sessions)
    owner_links = snapshot.get("owner_link_index") or {}
    return {
        "schema": "limen.estate_session_review_seal.v1",
        "generated_at": snapshot["snapshot_at"],
        "status": ("ready" if snapshot.get("reconciliation", {}).get("state") == "complete" else "partial"),
        "complete": snapshot.get("reconciliation", {}).get("state") == "complete",
        "scope": "partial",
        "windows": snapshot.get("windows") or [],
        "implementation_digest": implementation_digest,
        "source_coverage": snapshot.get("coverage") or {},
        "outcome_counts": dict(sorted(collections.Counter(row.get("outcome") for row in asks).items())),
        "unknown_metrics": {
            "sessions_without_atom": sum(not row.get("source_atom_ids") for row in sessions),
            "asks_with_coverage_unknown": sum(row.get("outcome") == "coverage_unknown" for row in asks),
            "agent_window_token_basis_unknown": sum(
                row.get("token_basis") == "unknown" for row in snapshot.get("comparison") or []
            ),
        },
        "reconciliation": snapshot.get("reconciliation") or {},
        "report_hashes": {name: sha256_bytes(content) for name, content in sorted(report_files.items())},
        "owner_only_delivery": {
            "project_id": "appgprj_6a5cf0df9a508191b5b5713da97e4481",
            "historical_version": 1,
            "historical_version_analytical_status": "superseded_provisional",
            "corrected_version": None,
            "allowed_accounts": 1,
            "allowed_groups": 0,
            "public_access": False,
        },
        "production_readiness": "pending_corrected_sites_version",
        "coverage_completeness": ("complete" if prompt_exact and session_coverage_complete else "partial"),
        "freshness": "frozen",
        "owner_reconciliation": (
            "complete" if owner_links.get("state") == "complete" else "pending_owner_link_fixed_point"
        ),
    }
