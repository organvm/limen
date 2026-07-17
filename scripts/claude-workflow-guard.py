#!/usr/bin/env python3
"""Guardrails for Claude dynamic workflows used by the Limen conductor.

This script exists because the b7efae9c session burned a large Opus fanout on
unparsed JSON-string args, producing 134 `undefined#undefined` verifier agents.

It gives the conductor three fail-closed checks:
  * normalize-candidates: parse JSON payloads, including accidental JSON strings,
    and reject any PR candidate without a real repo + PR number.
  * audit-workflow: inspect a saved Claude workflow JSON for unsafe fanout,
    undefined targets, hidden agent failures, or string args used without parsing.
  * audit-session: apply the workflow audit to every workflow in a Claude session.

Read-only. It writes no repo state unless --out is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BAD_TARGET_RE = re.compile(r"\bundefined#undefined\b|repo[=:]\\?\"?undefined|number[=:]\\?\"?undefined")
FAILED_LOG_RE = re.compile(r"\bfailed:|agent died|monthly spend limit|rate[_ -]?limit", re.IGNORECASE)

# pytest at command position, in any of its shapes (mirrors scripts/hooks/pytest-scope-guard.sh).
_PYTEST_CMD_RE = re.compile(
    r"(?:^|[;&|(]\s*|`\s*)\s*(?:command\s+)?"
    r"(?:env\s+(?:-u\s+\S+\s+|[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
    r"(?:uv\s+run\s+(?:--\S+\s+)*)?"
    r"(?:\S*python3?(?:\.\d+)?\s+-m\s+)?"
    r"(?:\S*/)?pytest\b"
)
_VERIFY_WRAPPER_RE = re.compile(r"verify\.py|verify-scoped\.sh|verify-whole\.sh")
_PYTEST_SUITE_ROOTS = {"tests", "cli/tests", "web/api/tests"}
_PYTEST_VALUE_FLAGS = {
    "-k",
    "-m",
    "-p",
    "-o",
    "-W",
    "-c",
    "-n",
    "--tb",
    "--maxfail",
    "--durations",
    "--ignore",
    "--deselect",
    "--rootdir",
    "--confcutdir",
}


def _full_suite_pytest(cmd: str) -> bool:
    """Transcript-side heuristic for the scoped-verification law: a pytest invocation whose
    positional args are suite roots (or absent) is a full collection. The PreToolUse hook
    (scripts/hooks/pytest-scope-guard.sh) is the enforcement, with filesystem resolution;
    this audit is the backstop for shapes the hook structurally misses (heredocs, nested
    shells, daemon lanes). No cwd, no filesystem — suite roots by name only, advisory-grade.
    2026-07-15 host-thrash incident: two concurrent full cli suites from one session."""
    if not cmd or "pytest" not in cmd or _VERIFY_WRAPPER_RE.search(cmd):
        return False
    for m in _PYTEST_CMD_RE.finditer(cmd):
        tail = re.split(r"\d*>|<|;|\||&", cmd[m.end() :], maxsplit=1)[0]
        try:
            tokens = shlex.split(tail)
        except ValueError:
            continue
        paths, skip = [], False
        for tok in tokens:
            if skip:
                skip = False
                continue
            if tok.startswith("-"):
                skip = tok in _PYTEST_VALUE_FLAGS
                continue
            paths.append(tok.rstrip("/"))
        if any(".py" in os.path.basename(p.split("::")[0]) or "::" in p for p in paths):
            continue
        if not paths:
            return True
        if all(p in _PYTEST_SUITE_ROOTS or p.endswith(("/cli/tests", "/web/api/tests")) for p in paths):
            return True
    return False


def _fable_contract() -> Any:
    """Load the provider-neutral authority validator without importing limen package state."""

    try:
        import importlib.util

        root = Path(__file__).resolve().parents[1]
        path = root / "cli" / "src" / "limen" / "fable_contract.py"
        if not path.exists():
            path = Path(__file__).resolve().parents[1] / "cli" / "src" / "limen" / "fable_contract.py"
        spec = importlib.util.spec_from_file_location("_limen_fable_workflow_contract", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


_FABLE_ROLE = "fable-planner"


def _model_selection() -> Any:
    try:
        import importlib.util

        path = Path(__file__).resolve().parents[1] / "cli" / "src" / "limen" / "model_selection.py"
        spec = importlib.util.spec_from_file_location("_limen_fable_workflow_selection", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _read_text(path: str | None) -> str:
    if path and path != "-":
        return Path(path).read_text()
    return sys.stdin.read()


def _json_loads_nested(text: str) -> Any:
    data = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return data


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _execution_role(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    containers = (
        value,
        value.get("message"),
        value.get("metadata"),
        value.get("executionProfile"),
        value.get("execution_profile"),
    )
    for container in containers:
        if not isinstance(container, dict):
            continue
        role = container.get("executionRole") or container.get("execution_role") or container.get("role")
        if isinstance(role, str) and role:
            return role
    return ""


def _aware_moment(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _structured_fable_authority(
    value: Any,
    profile: Any,
    *,
    moment: datetime | None = None,
) -> dict[str, Any] | None:
    """Validate evidence at its execution time, never against current live authority."""

    selector = _model_selection()
    contract = _fable_contract()
    if selector is None or contract is None or not isinstance(profile, dict):
        return None
    try:
        evidence_moment = moment
        if evidence_moment is None and isinstance(value, dict):
            evidence_moment = _aware_moment(value.get("observed_at"))
        selection = selector.validate_selection_receipt(value, moment=evidence_moment)
        return contract.validate_authority_bundle(
            selection.get("fable_authority"),
            execution_profile_value=profile,
            moment=evidence_moment,
        )
    except Exception:
        return None


def _fable_cap_closed(balance: dict[str, Any], acceptance: dict[str, Any]) -> bool:
    mod = _fable_contract()
    try:
        if mod is None:
            return True
        closed, _reason = mod.cap_status(balance, acceptance)
        return bool(closed)
    except Exception:
        return True


def _fable_packet_metadata_valid(value: Any) -> bool:
    mod = _fable_contract()
    try:
        if mod is None:
            return False
        mod.validate_packet_metadata(value)
        return True
    except Exception:
        return False


def _fable_packet_receipt_valid(value: Any) -> bool:
    mod = _fable_contract()
    try:
        if mod is None:
            return False
        mod.validate_packet_receipt(value)
        return True
    except Exception:
        return False


def _fable_execution_profile_valid(value: Any) -> bool:
    mod = _fable_contract()
    try:
        if mod is None:
            return False
        mod.validate_execution_profile(value)
        return True
    except Exception:
        return False


def normalize_candidates(data: Any, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError(f"candidate payload must be a JSON list, got {type(data).__name__}")
    if not data and not allow_empty:
        raise ValueError("candidate payload is empty")

    seen: set[tuple[str, int]] = set()
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"[{i}] candidate must be an object")
            continue
        repo = item.get("repo")
        number = item.get("number")
        title = item.get("title", "")
        if not isinstance(repo, str) or not REPO_RE.match(repo) or "undefined" in repo.lower():
            errors.append(f"[{i}] invalid repo: {repo!r}")
        if not isinstance(number, int) or number <= 0:
            errors.append(f"[{i}] invalid PR number: {number!r}")
        if isinstance(title, str) and title.lower() == "undefined":
            errors.append(f"[{i}] invalid title: {title!r}")
        if isinstance(repo, str) and isinstance(number, int):
            key = (repo, number)
            if key in seen:
                errors.append(f"[{i}] duplicate PR target: {repo}#{number}")
            seen.add(key)
        out.append(dict(item))

    if errors:
        raise ValueError("; ".join(errors))
    return out


def _workflow_violations(
    path: Path,
    wf: dict[str, Any],
    *,
    max_opus_agents: int,
    max_fable_agents: int,
) -> list[str]:
    violations: list[str] = []
    name = wf.get("workflowName") or wf.get("summary") or path.name
    progress = wf.get("workflowProgress") or []
    int(wf.get("agentCount") or len(progress) or 0)
    fable_agents = sum(1 for item in progress if _execution_role(item) == _FABLE_ROLE)
    fable_workflow = _execution_role(wf) == _FABLE_ROLE or fable_agents > 0

    if fable_agents > max_fable_agents:
        violations.append(f"{name}: Fable fanout blocked ({fable_agents} Fable agents; max {max_fable_agents})")

    scan_parts = [
        wf.get("args"),
        wf.get("script"),
        wf.get("logs"),
        wf.get("result"),
        wf.get("error"),
    ]
    for p in progress:
        if isinstance(p, dict):
            scan_parts.extend(
                [
                    p.get("label"),
                    p.get("promptPreview"),
                    p.get("resultPreview"),
                    p.get("lastToolSummary"),
                ]
            )
    scan = "\n".join(_as_text(x) for x in scan_parts)
    workflow_moment = next(
        (
            parsed
            for parsed in (
                _aware_moment(wf.get("startedAt")),
                _aware_moment(wf.get("started_at")),
                _aware_moment(wf.get("createdAt")),
                _aware_moment(wf.get("created_at")),
            )
            if parsed is not None
        ),
        None,
    )
    authority = _structured_fable_authority(
        wf.get("modelSelectionReceipt"),
        wf.get("executionProfile"),
        moment=workflow_moment,
    )
    fable_acceptance = authority.get("acceptance") if authority is not None else None
    if fable_workflow and authority is None:
        violations.append(f"{name}: Fable run lacks prelaunch signed selection/authority evidence")
    if fable_workflow:
        balance = authority.get("balance") if authority is not None else None
        if balance is not None and fable_acceptance is not None and _fable_cap_closed(balance, fable_acceptance):
            violations.append(f"{name}: Fable balance/cap contract is closed")
        if not _fable_execution_profile_valid(wf.get("executionProfile")):
            violations.append(f"{name}: Fable workflow is not bound to a plan-only execution profile")
        if not _fable_packet_metadata_valid(wf.get("fablePacket")):
            violations.append(f"{name}: Fable workflow lacks a bounded provider-neutral builder packet")
    if BAD_TARGET_RE.search(scan):
        violations.append(f"{name}: undefined PR target detected")

    args = wf.get("args")
    script = str(wf.get("script") or "")
    if isinstance(args, str):
        try:
            parsed = _json_loads_nested(args)
            normalize_candidates(parsed, allow_empty=True)
            candidate_like = True
        except Exception:
            candidate_like = False
        if candidate_like and "JSON.parse(args)" not in script and "typeof args === 'string'" not in script:
            violations.append(f"{name}: candidate args are a JSON string but script does not parse args")

    states = [str(p.get("state", "")) for p in progress if isinstance(p, dict)]
    if wf.get("status") == "completed" and any(s == "error" for s in states):
        violations.append(f"{name}: completed workflow contains errored agents")
    logs_text = _as_text(wf.get("logs"))
    result_text = _as_text(wf.get("result"))
    if wf.get("status") == "completed" and (
        FAILED_LOG_RE.search(logs_text) or re.search(r"agent died", result_text, re.IGNORECASE)
    ):
        violations.append(f"{name}: completed workflow contains failure/dead-agent evidence")

    return violations


def audit_workflow(
    path: Path,
    *,
    max_opus_agents: int,
    max_fable_agents: int,
    live_merged: bool = False,
) -> dict[str, Any]:
    wf = json.loads(path.read_text())
    violations = _workflow_violations(
        path,
        wf,
        max_opus_agents=max_opus_agents,
        max_fable_agents=max_fable_agents,
    )
    live = None
    if live_merged:
        live = verify_claimed_merged(wf)
        if live["bad"]:
            violations.append(f"{path.name}: live merged verification failed for {len(live['bad'])} PRs")
    return {
        "path": str(path),
        "workflowName": wf.get("workflowName"),
        "status": wf.get("status"),
        "agentCount": wf.get("agentCount", 0),
        "totalTokens": wf.get("totalTokens", 0),
        "violations": violations,
        "liveMerged": live,
    }


def _find_session_dir(session: str) -> Path:
    root = Path.home() / ".claude" / "projects"
    matches = list(root.glob(f"*/{session}"))
    if not matches:
        raise FileNotFoundError(f"no Claude session directory found for {session}")
    return matches[0]


def _find_session_jsonl(session_or_path: str) -> Path:
    p = Path(session_or_path).expanduser()
    if p.exists():
        return p
    root = Path.home() / ".claude" / "projects"
    matches = list(root.glob(f"*/{session_or_path}.jsonl"))
    if not matches:
        raise FileNotFoundError(f"no Claude transcript found for {session_or_path}")
    return matches[0]


def _iter_jsonl(path: Path):
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return
    for line_no, line in enumerate(lines, start=1):
        try:
            yield line_no, json.loads(line)
        except Exception:
            continue


def _billable_usage(usage: dict[str, Any]) -> int:
    return (
        int(usage.get("input_tokens", 0))
        + int(usage.get("output_tokens", 0))
        + int(usage.get("cache_creation_input_tokens", 0))
    )


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _as_text(content)
    out: list[str] = []
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "text":
                out.append(str(item.get("text", "")))
            elif item.get("type") == "tool_use":
                out.append(str(item.get("name", "")))
        elif isinstance(item, str):
            out.append(item)
    return "\n".join(out)


def audit_transcript(
    session_or_path: str,
    *,
    max_billable_tokens: int,
    max_opus_billable_tokens: int,
    max_fable_billable_tokens: int,
    max_agent_calls: int,
    max_opus_agents: int,
    max_fable_agents: int,
) -> dict[str, Any]:
    """Audit a Claude transcript for unbounded, expensive session shape.

    This intentionally ignores cache-read tokens for the budget gate; it counts the
    billable-ish part Claude exposes in transcripts: input + output + cache creation.
    """
    main = _find_session_jsonl(session_or_path)
    session_id = main.stem
    files = [main]
    subagents = main.with_suffix("") / "subagents"
    if subagents.exists():
        files.extend(sorted(p for p in subagents.rglob("*.jsonl") if p.is_file()))

    total_billable = 0
    cache_read_tokens = 0
    output_tokens = 0
    usage_messages = 0
    agent_calls = 0
    fable_billable = 0
    user_unbounded: list[dict[str, Any]] = []
    full_suite_pytest: list[dict[str, Any]] = []
    fable_tool_violations: list[dict[str, Any]] = []
    fable_packet_writes: list[dict[str, Any]] = []
    fable_receipt_seen = False
    fable_first_ts: datetime | None = None
    fable_last_ts: datetime | None = None
    models: dict[str, int] = {}
    fable_subagent_files: set[str] = set()
    fable_acceptance = None
    fable_balance = None
    fable_acceptance_seen = False
    fable_prelaunch_missing = False

    unbounded_re = re.compile(
        r"\b(no stopping|indefinite|indefinitely|until ideal form|keep going until ideal form)\b",
        re.IGNORECASE,
    )

    for path in files:
        for line_no, row in _iter_jsonl(path):
            msg = row.get("message") or {}
            row_profile = (
                row.get("execution_profile")
                or row.get("executionProfile")
                or (msg.get("execution_profile") if isinstance(msg, dict) else None)
                or (msg.get("executionProfile") if isinstance(msg, dict) else None)
            )
            row_selection = row.get("modelSelectionReceipt") or (
                msg.get("modelSelectionReceipt") if isinstance(msg, dict) else None
            )
            row_authority = _structured_fable_authority(
                row_selection,
                row_profile,
                moment=_aware_moment(row.get("timestamp")),
            )
            if row_authority is not None:
                fable_acceptance = row_authority["acceptance"]
                fable_balance = row_authority["balance"]
                fable_acceptance_seen = True
            receipt = row.get("fableReceipt") or (msg.get("fableReceipt") if isinstance(msg, dict) else None)
            if _fable_packet_receipt_valid(receipt):
                fable_receipt_seen = True
            if row.get("type") == "user":
                text = _content_text(msg.get("content"))
                if unbounded_re.search(text):
                    user_unbounded.append(
                        {
                            "path": str(path),
                            "line": line_no,
                            "textSha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
                            "chars": len(text),
                        }
                    )
            if row.get("type") != "assistant":
                continue
            if _execution_role(row) == _FABLE_ROLE and not fable_acceptance_seen:
                fable_prelaunch_missing = True
            model = str(msg.get("model") or "unknown")
            fable_turn = _execution_role(row) == _FABLE_ROLE
            if fable_turn:
                try:
                    stamp = datetime.fromisoformat(str(row.get("timestamp") or "").replace("Z", "+00:00"))
                except ValueError:
                    stamp = None
                if stamp is not None and stamp.tzinfo is not None:
                    fable_first_ts = stamp if fable_first_ts is None else min(fable_first_ts, stamp)
                    fable_last_ts = stamp if fable_last_ts is None else max(fable_last_ts, stamp)
            if path != main and fable_turn:
                fable_subagent_files.add(str(path))
            content = msg.get("content") or []
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict) or item.get("type") != "tool_use":
                        continue
                    tool_name = str(item.get("name") or "")
                    contract = _fable_contract()
                    allowed_tools = contract.FABLE_READ_ONLY_TOOLS if contract is not None else frozenset()
                    if fable_turn and tool_name not in allowed_tools:
                        fable_tool_violations.append({"path": str(path), "line": line_no, "tool": tool_name})
                    if item.get("name") in {"Agent", "Workflow"}:
                        agent_calls += 1
                    elif item.get("name") == "Bash":
                        bash_cmd = str((item.get("input") or {}).get("command") or "")
                        if _full_suite_pytest(bash_cmd):
                            full_suite_pytest.append({"path": str(path), "line": line_no, "command": bash_cmd[:200]})
            usage = msg.get("usage") or {}
            if not usage:
                continue
            usage_messages += 1
            billable = _billable_usage(usage)
            total_billable += billable
            cache_read_tokens += int(usage.get("cache_read_input_tokens", 0))
            output_tokens += int(usage.get("output_tokens", 0))
            models[model] = models.get(model, 0) + billable
            if fable_turn:
                fable_billable += billable

    violations: list[str] = []
    if total_billable > max_billable_tokens and os.environ.get("LIMEN_ALLOW_EXPENSIVE_SESSION") != "1":
        violations.append(f"billable token budget exceeded ({total_billable} > {max_billable_tokens})")
    if fable_billable > max_fable_billable_tokens:
        violations.append(f"Fable billable budget exceeded ({fable_billable} > {max_fable_billable_tokens})")
    if agent_calls > max_agent_calls and os.environ.get("LIMEN_ALLOW_AGENT_FANOUT") != "1":
        violations.append(f"agent/workflow fanout exceeded ({agent_calls} > {max_agent_calls})")
    fable_subagents = len(fable_subagent_files)
    if fable_subagents > max_fable_agents:
        violations.append(
            f"Fable subagent fanout ({fable_subagents} subagents in role {_FABLE_ROLE}; max {max_fable_agents})"
        )
    if fable_billable and (not fable_acceptance_seen or fable_prelaunch_missing):
        violations.append("Fable run lacks prelaunch signed selection/authority evidence")
    if fable_billable:
        if (
            fable_balance is not None
            and fable_acceptance is not None
            and _fable_cap_closed(fable_balance, fable_acceptance)
        ):
            violations.append("Fable balance/cap contract is closed")
        if fable_tool_violations:
            violations.append(
                "Fable used mutation-capable or unclassified tools outside its explicit read-only surface "
                f"({len(fable_tool_violations)} call(s))"
            )
        if not fable_receipt_seen:
            violations.append("Fable run produced no bounded continuation-capsule evidence")
    fable_motion_seconds = 0
    if fable_first_ts is not None and fable_last_ts is not None:
        fable_motion_seconds = max(0, int((fable_last_ts - fable_first_ts).total_seconds()))
    contract = _fable_contract()
    motion_deadline = int(contract.MOTION_RECEIPT_DEADLINE_SECONDS) if contract is not None else 5_400
    if fable_motion_seconds >= motion_deadline and not fable_receipt_seen:
        violations.append(f"Fable motion exceeded {motion_deadline} seconds without a durable packet receipt")
    if user_unbounded and os.environ.get("LIMEN_ALLOW_UNBOUNDED_GOAL") != "1":
        violations.append(f"unbounded goal phrase detected ({len(user_unbounded)} occurrence(s))")
    if full_suite_pytest and os.environ.get("LIMEN_ALLOW_FULL_PYTEST") != "1":
        violations.append(
            f"full-suite pytest invoked directly ({len(full_suite_pytest)} call(s)) — "
            "scoped-verification law: run scripts/verify-scoped.sh "
            "(2026-07-15 host-thrash incident; the PreToolUse hook is the gate, this audit is the backstop)"
        )

    return {
        "ok": not violations,
        "session": session_id,
        "files": [str(p) for p in files],
        "usageMessages": usage_messages,
        "billableTokens": total_billable,
        "cacheReadTokens": cache_read_tokens,
        "outputTokens": output_tokens,
        # Compatibility fields remain explicit unknowns. Provider IDs are opaque runtime
        # outputs, so this observer cannot honestly infer a price/capability class from a name.
        "opusBillableTokens": None,
        "fableBillableTokens": fable_billable,
        "agentCalls": agent_calls,
        "expensiveSubagents": None,
        "fableSubagents": fable_subagents,
        "fableAcceptanceSeen": fable_acceptance_seen,
        "fablePacketWrites": len(fable_packet_writes),
        "fablePacketWriteEvidence": fable_packet_writes[:10],
        "fableToolViolations": fable_tool_violations[:10],
        "fableDurableReceiptSeen": fable_receipt_seen,
        "fableMotionSeconds": fable_motion_seconds,
        "expensiveTier": None,
        "providerCostClassified": False,
        "fableRole": _FABLE_ROLE,
        "modelsBillable": models,
        "unboundedGoalEvidence": user_unbounded[:10],
        "fullSuitePytestCalls": len(full_suite_pytest),
        "fullSuitePytestEvidence": full_suite_pytest[:10],
        "violations": violations,
    }


def verify_claimed_merged(wf: dict[str, Any]) -> dict[str, Any]:
    merged = (wf.get("result") or {}).get("merged") or []
    ok: list[dict[str, Any]] = []
    bad: list[dict[str, Any]] = []
    for item in merged:
        repo = item.get("repo")
        num = item.get("number")
        if not repo or not num:
            bad.append({"repo": repo, "number": num, "state": "invalid"})
            continue
        proc = subprocess.run(
            ["gh", "pr", "view", str(num), "-R", str(repo), "--json", "state,mergedAt"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            bad.append({"repo": repo, "number": num, "state": "gh-error", "error": proc.stderr[:200]})
            continue
        data = json.loads(proc.stdout)
        state = "MERGED" if data.get("mergedAt") else data.get("state")
        target = {"repo": repo, "number": num, "state": state}
        (ok if state == "MERGED" else bad).append(target)
    return {"checked": len(merged), "ok": ok, "bad": bad}


def _emit(report: Any, out: str | None) -> None:
    text = json.dumps(report, indent=2, sort_keys=True)
    if out:
        Path(out).write_text(text + "\n")
    print(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    norm = sub.add_parser("normalize-candidates")
    norm.add_argument("input", nargs="?", default="-")
    norm.add_argument("--allow-empty", action="store_true")
    norm.add_argument("--out")

    aw = sub.add_parser("audit-workflow")
    aw.add_argument("workflow", nargs="+")
    aw.add_argument("--max-opus-agents", type=int, default=1)
    aw.add_argument("--max-fable-agents", type=int, default=1)
    aw.add_argument("--live-merged", action="store_true")
    aw.add_argument("--out")

    ases = sub.add_parser("audit-session")
    ases.add_argument("session")
    ases.add_argument("--max-opus-agents", type=int, default=1)
    ases.add_argument("--max-fable-agents", type=int, default=1)
    ases.add_argument("--live-merged", action="store_true")
    ases.add_argument("--out")

    at = sub.add_parser("audit-transcript")
    at.add_argument("session_or_jsonl")
    at.add_argument(
        "--max-billable-tokens", type=int, default=int(os.environ.get("LIMEN_MAX_CLAUDE_SESSION_TOKENS", "2000000"))
    )
    at.add_argument(
        "--max-opus-billable-tokens", type=int, default=int(os.environ.get("LIMEN_MAX_OPUS_SESSION_TOKENS", "750000"))
    )
    at.add_argument(
        "--max-fable-billable-tokens",
        type=int,
        default=int(os.environ.get("LIMEN_MAX_FABLE_SESSION_TOKENS", "1000000")),
    )
    at.add_argument("--max-agent-calls", type=int, default=int(os.environ.get("LIMEN_MAX_AGENT_CALLS", "8")))
    at.add_argument("--max-opus-agents", type=int, default=1)
    at.add_argument("--max-fable-agents", type=int, default=1)
    at.add_argument("--out")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "normalize-candidates":
            candidates = normalize_candidates(
                _json_loads_nested(_read_text(args.input)),
                allow_empty=args.allow_empty,
            )
            _emit(candidates, args.out)
            return 0

        if args.cmd == "audit-workflow":
            reports = [
                audit_workflow(
                    Path(p),
                    max_opus_agents=args.max_opus_agents,
                    max_fable_agents=args.max_fable_agents,
                    live_merged=args.live_merged,
                )
                for p in args.workflow
            ]
        elif args.cmd == "audit-session":
            session_dir = _find_session_dir(args.session)
            reports = [
                audit_workflow(
                    p,
                    max_opus_agents=args.max_opus_agents,
                    max_fable_agents=args.max_fable_agents,
                    live_merged=args.live_merged,
                )
                for p in sorted((session_dir / "workflows").glob("*.json"))
            ]
            summary = {
                "ok": not any(r["violations"] for r in reports),
                "workflowCount": len(reports),
                "reports": reports,
            }
            _emit(summary, args.out)
            return 0 if summary["ok"] else 2

        if args.cmd == "audit-transcript":
            report = audit_transcript(
                args.session_or_jsonl,
                max_billable_tokens=args.max_billable_tokens,
                max_opus_billable_tokens=args.max_opus_billable_tokens,
                max_fable_billable_tokens=args.max_fable_billable_tokens,
                max_agent_calls=args.max_agent_calls,
                max_opus_agents=args.max_opus_agents,
                max_fable_agents=args.max_fable_agents,
            )
            _emit(report, args.out)
            return 0 if report["ok"] else 2

        summary = {
            "ok": not any(r["violations"] for r in reports),
            "workflowCount": len(reports),
            "reports": reports,
        }
        _emit(summary, args.out)
        return 0 if summary["ok"] else 2
    except Exception as e:
        print(f"claude-workflow-guard: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
