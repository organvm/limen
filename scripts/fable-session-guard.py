#!/usr/bin/env python3
"""fable-session-guard.py — SessionStart guard that closes the INTERACTIVE Fable bypass.

The non-bypassable model shim (`scripts/shims/claude`, the #328 fix) governs only daemon / `claude -p`
spawns. INTERACTIVE Claude Code sessions bypass it entirely and use the account default model — which
was Fable when the weekly allotment blew out on 2026-07-09. This guard is the only control that reaches
an interactive session:

  * If the session model is `claude-fable-5`, it prints the live weekly Fable balance loudly.
  * If the week is over cap, the meter is absent/stale/malformed, or no live acceptance receipt is
    present, it emits a hard failure for this invocation's own plan contract.
  * On any non-Fable model, it is a clean no-op.

Wired as a SessionStart hook in settings.json (staged, human-armed — see
`docs/keys/fable-guard-settings-snippet.json`). A SessionStart hook cannot block a session, so fleet
launch enforcement remains in dispatch; this read-only hook never retunes or signals any session.
The model is resolved from the hook stdin payload when the
harness provides it, else from ANTHROPIC_MODEL / an explicit --model, so the guard is testable.

Exit codes (for the verify harness, NOT to block a live session):
  0 — non-Fable model, or Fable under cap with a live receipt (clean).
  2 — Fable model AND (over_cap OR no live acceptance receipt) — the hard-warn case.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))


def _read_stdin_payload() -> dict:
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


def _resolve_model(payload: dict, explicit: str | None) -> str:
    if explicit:
        return explicit
    # SessionStart payloads may carry the model under a few shapes; be permissive.
    for key in ("model", "model_id"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v
    m = payload.get("model")
    if isinstance(m, dict):
        for key in ("id", "name"):
            v = m.get(key)
            if isinstance(v, str) and v:
                return v
    for env_key in ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "LIMEN_SESSION_MODEL"):
        v = os.environ.get(env_key)
        if v:
            return v
    return ""


def _is_fable(model: str) -> bool:
    return "fable" in (model or "").lower()


def _model_selection():
    try:
        import importlib.util

        path = ROOT / "cli" / "src" / "limen" / "model_selection.py"
        spec = importlib.util.spec_from_file_location("_limen_fable_session_contract", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _load_balance() -> tuple[dict | None, str]:
    module = _model_selection()
    if module is None:
        return None, "balance-validator-unavailable"
    try:
        return module._fable_balance_status()
    except Exception:
        return None, "balance-validator-failed"


def _live_acceptance_present() -> bool:
    module = _model_selection()
    try:
        return bool(module is not None and module._claude_fable_acceptance_present())
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", help="override the resolved session model (test/inspection)")
    args = ap.parse_args(argv)

    payload = _read_stdin_payload()
    model = _resolve_model(payload, args.model)

    if not _is_fable(model):
        return 0  # clean no-op on any non-Fable model

    bal, balance_reason = _load_balance()
    accept = _live_acceptance_present()
    if bal is not None:
        pct = bal.get("spent_pct")
        over = bool(bal.get("over_cap"))
        print(
            f"[fable-session-guard] Interactive session model is Fable ({model}). "
            f"Weekly Fable spend: {pct}% (deliberate cap {bal.get('deliberate_cap')}%, "
            f"hard cap {bal.get('hard_cap')}%; over_cap={over}).",
            file=sys.stderr,
        )
    else:
        print(
            f"[fable-session-guard] Interactive session model is Fable ({model}). "
            f"Weekly balance contract is unavailable ({balance_reason}).",
            file=sys.stderr,
        )

    if bal is None or over or not accept:
        reason = (
            balance_reason
            if bal is None
            else ("over the weekly cap" if over else "missing a current plan-only acceptance receipt")
        )
        print(
            f"[fable-session-guard] CONTRACT RED observed for this invocation: {reason}. "
            "This interactive hook is report-only and does not direct or control the live session. "
            "Dispatcher-owned child launches enforce the Fable PLAN-ONLY contract independently.",
            file=sys.stderr,
        )
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
