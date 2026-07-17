"""Provider-Auto shim contract and temporary Fable-authority compatibility.

This module is deliberately free of provider model names, tier ladders, capability
guesses, and fallback tables. Dispatch validates any explicit override against a
non-executing live provider catalog; without one, the provider owns selection.

The Fable receipt helper remains only so this lane stays independently usable
before the provider-neutral Fable contract lands. It authorizes a planning role,
never a model identifier.
"""

from __future__ import annotations

import datetime as dt
import json
import os


def _claude_fable_acceptance_present() -> bool:
    """Validate the legacy current-week planning receipt without selecting a model."""

    raw = os.environ.get("LIMEN_FABLE_ACCEPTANCE", "").strip()
    if not raw:
        return False
    if raw == "1":
        return "PYTEST_CURRENT_TEST" in os.environ
    try:
        with open(os.path.expanduser(raw)) as handle:
            receipt = json.load(handle)
        now = dt.datetime.now(dt.timezone.utc)
        current_week = (now - dt.timedelta(days=now.weekday())).date().isoformat()
        return receipt.get("schema") == "limen.fable_acceptance.v1" and receipt.get("week") == current_week
    except (OSError, TypeError, ValueError):
        return False


def model_for_argv(args: list[str]) -> None:
    """Never inject a model into a provider invocation.

    The argument is retained for the installed shim API. Explicit model arguments
    were already validated at dispatch; invocations without one remain provider
    Auto.
    """

    del args
    return None


def main(argv: list[str] | None = None) -> int:
    """Inspection entrypoint; provider-Auto emits no model identifier."""

    import sys

    model_for_argv(list(argv if argv is not None else sys.argv[1:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
