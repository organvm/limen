#!/usr/bin/env python3
"""Report the current interactive invocation's Fable planning-contract state.

Fleet-owned child launchers enforce the Fable contract before spawn. A SessionStart
hook cannot reliably block a session, so this observer is deliberately report-only:
it never chooses a model, emits a model-switch command, signals a process, enumerates
peer sessions, or changes another invocation's continuation state.

The model label is treated only as opaque hook context for deciding whether to show
the Fable report. Authority comes from the plan-only acceptance and fresh balance
receipts, never from the label.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))


def _contract() -> Any | None:
    try:
        path = ROOT / "cli" / "src" / "limen" / "fable_contract.py"
        if not path.exists():
            path = Path(__file__).resolve().parents[1] / "cli" / "src" / "limen" / "fable_contract.py"
        spec = importlib.util.spec_from_file_location("_limen_fable_session_contract", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _read_stdin_payload() -> dict[str, Any]:
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_model(payload: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    for key in ("model", "model_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    model = payload.get("model")
    if isinstance(model, dict):
        for key in ("id", "name"):
            value = model.get(key)
            if isinstance(value, str) and value:
                return value
    for env_key in ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "LIMEN_SESSION_MODEL"):
        value = os.environ.get(env_key)
        if value:
            return value
    return ""


def _is_fable_context(payload: dict[str, Any]) -> bool:
    profile = payload.get("execution_profile") or payload.get("executionProfile")
    roles = [
        profile.get("execution_role") if isinstance(profile, dict) else None,
        payload.get("execution_role"),
        payload.get("role"),
    ]
    if any(isinstance(role, str) and role.lower() == "fable-planner" for role in roles):
        return True
    # Provider model labels are opaque runtime output. A renamed ID containing
    # "fable" cannot create or imply the explicit planner role.
    return False


def _execution_profile(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("execution_profile") or payload.get("executionProfile")
    if isinstance(value, dict):
        return dict(value)
    return {
        "execution_role": payload.get("execution_role") or payload.get("role"),
        "planning_only": payload.get("planning_only"),
        "build_allowed": payload.get("build_allowed"),
        "fanout_allowed": payload.get("fanout_allowed"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="override the opaque session model label for inspection")
    args = parser.parse_args(argv)

    payload = _read_stdin_payload()
    model = _resolve_model(payload, args.model)
    if not _is_fable_context(payload):
        return 0

    contract = _contract()
    if contract is None:
        print(
            "[fable-session-guard] CONTRACT RED observed for this invocation: "
            "contract-validator-unavailable. This hook is report-only and does not direct "
            "or control the live session.",
            file=sys.stderr,
        )
        return 0

    authority, reason = contract.authorization_status(execution_profile_value=_execution_profile(payload))
    balance = authority.get("balance") if authority is not None else None
    if balance is None:
        balance, _balance_reason = contract.balance_status()
    if balance is not None:
        print(
            f"[fable-session-guard] Current Fable planning context ({model or 'role-bound'}). "
            f"Weekly spend: {balance.get('spent_pct')}% "
            f"(deliberate cap {balance.get('deliberate_cap')}%, "
            f"hard cap {balance.get('hard_cap')}%).",
            file=sys.stderr,
        )

    if reason != "ok":
        print(
            f"[fable-session-guard] CONTRACT RED observed for this invocation: {reason}. "
            "This interactive hook is report-only and does not direct or control the live session. "
            "Fleet-owned child launchers enforce the PLAN-ONLY contract before spawn.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
