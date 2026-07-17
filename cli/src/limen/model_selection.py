"""Single source of truth for the Claude-lane model vocabulary + the non-bypassable shim's
per-spawn floor sort.

Two callers share this ONE module so the model decision never drifts across copies:

  * ``dispatch.py``'s per-TASK earned-tier ladder (``_claude_tier_for`` / ``_bump_tier`` /
    ``_claude_model``) imports the shared primitives below — it owns the rich sort, keyed on a
    task's classes/labels, and passes ``--model`` explicitly.
  * ``scripts/shims/claude`` — the non-bypassable chokepoint prepended onto the FLEET PATH —
    calls :func:`model_for_argv` to decide what ``--model`` to inject when a fleet spawn carries
    NONE. It owns the per-SPAWN floor: nothing escapes the sort to the account default (Opus 4.8 +
    auto-1M context, which drove the 2026-06-25 usage bleed) WITHOUT a declaration.

Design note — this module is PURE stdlib (only ``os``) and imports nothing from the ``limen``
package, so the shim can ``importlib``-load it by file path without triggering ``limen``'s package
``__init__`` or depending on ``PYTHONPATH``. ([[fleet-model-floor-bleed]] [[derive-never-pin-hardcodes]])
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os

# The ladder rungs, cheapest-first. Shared with dispatch's earned-tier ladder. Fable is a
# reserved top tier above Opus, not a new default escalation target.
_CLAUDE_TIER_ORDER = ("haiku", "sonnet", "opus", "fable")

# Reserved-Opus classes: the doctrine's small principled set whose failure is BOTH undetectable
# AND high-stakes (final/canon synthesis, irreversible go-live reasoning, kernel abstraction). A
# stated principle, env-overridable (comma-separated LIMEN_CLAUDE_OPUS_CLASSES) — not inherited config.
_CLAUDE_OPUS_CLASSES_DEFAULT = ("canon", "synthesis", "kernel", "go-live", "irreversible")

# Fable classes are narrower than reserved-Opus classes and still require an explicit acceptance
# receipt before model selection is allowed to return the Fable rung.
_CLAUDE_FABLE_CLASSES_DEFAULT = (
    "fable",
    "long-horizon",
    "huge-context",
    "ambiguous-root-cause",
    "final-canonical-decision",
)

_FABLE_ACCEPTANCE_CATEGORIES = {
    "substrate",
    "prompt-corpus",
    "governance",
    "adversarial-review",
    "reserve",
}
_FABLE_ACCEPTANCE_CATEGORY_CAPS = {
    "substrate": 15.0,
    "prompt-corpus": 10.0,
    "governance": 10.0,
    "adversarial-review": 5.0,
    "reserve": 10.0,
}
_FABLE_BALANCE_SCHEMA = "limen.fable_balance.v1"
_FABLE_ACCEPTANCE_SCHEMA = "limen.fable_acceptance.v1"
_FABLE_BALANCE_MAX_AGE_SECONDS_DEFAULT = 900


def _claude_opus_classes() -> set[str]:
    """The reserved-Opus class set — env override (LIMEN_CLAUDE_OPUS_CLASSES, comma-separated)
    wins, else the stated default. Shared by dispatch's per-task ladder."""
    raw = os.environ.get("LIMEN_CLAUDE_OPUS_CLASSES")
    if raw is not None:
        return {c.strip() for c in raw.split(",") if c.strip()}
    return set(_CLAUDE_OPUS_CLASSES_DEFAULT)


def _claude_fable_classes() -> set[str]:
    """The reserved-Fable class set — env override (LIMEN_CLAUDE_FABLE_CLASSES,
    comma-separated) wins, else the stated default. A class match alone is not enough;
    :func:`_claude_fable_acceptance_present` must also pass."""
    raw = os.environ.get("LIMEN_CLAUDE_FABLE_CLASSES")
    if raw is not None:
        return {c.strip() for c in raw.split(",") if c.strip()}
    return set(_CLAUDE_FABLE_CLASSES_DEFAULT)


def _current_week(now: dt.datetime | None = None) -> str:
    moment = now or dt.datetime.now(dt.timezone.utc)
    return (moment - dt.timedelta(days=moment.weekday())).date().isoformat()


def _parse_utc(value: object) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _fable_acceptance_receipt(value: str | None = None) -> dict | None:
    """Load a current, explicitly plan-only Fable acceptance receipt."""

    raw = (value if value is not None else os.environ.get("LIMEN_FABLE_ACCEPTANCE", "")).strip()
    if not raw:
        return None
    if raw == "1":
        if "PYTEST_CURRENT_TEST" not in os.environ:
            return None
        return {
            "schema": _FABLE_ACCEPTANCE_SCHEMA,
            "week": _current_week(),
            "category": "governance",
            "percent": 1.0,
            "sources": ["pytest"],
            "verification": ["pytest"],
            "mode": "plan-only",
            "deliverable": "continuation-capsule",
            "builder_tier_max": "opus",
            "motion_receipt_deadline_seconds": 5400,
        }
    try:
        with open(os.path.expanduser(raw)) as fh:
            receipt = json.load(fh)
    except Exception:
        return None
    if not isinstance(receipt, dict):
        return None
    try:
        percent = float(receipt.get("percent"))
    except (TypeError, ValueError):
        return None
    sources = receipt.get("sources") or []
    packets = receipt.get("redacted_packets") or []
    verification = receipt.get("verification") or []
    if not math.isfinite(percent) or percent <= 0:
        return None
    if receipt.get("schema") != _FABLE_ACCEPTANCE_SCHEMA or receipt.get("week") != _current_week():
        return None
    category = receipt.get("category")
    if category not in _FABLE_ACCEPTANCE_CATEGORIES:
        return None
    if percent > _FABLE_ACCEPTANCE_CATEGORY_CAPS[str(category)]:
        return None
    if category == "reserve" and receipt.get("reserve_unlocked") is not True:
        return None
    if receipt.get("mode") != "plan-only" or receipt.get("deliverable") != "continuation-capsule":
        return None
    if receipt.get("builder_tier_max") not in {"haiku", "sonnet", "opus"}:
        return None
    if receipt.get("motion_receipt_deadline_seconds") != 5400:
        return None
    source_ok = (
        isinstance(sources, list) and bool(sources) and all(isinstance(item, str) and item.strip() for item in sources)
    )
    packet_ok = (
        isinstance(packets, list) and bool(packets) and all(isinstance(item, str) and item.strip() for item in packets)
    )
    if not source_ok and not packet_ok:
        return None
    if (
        not isinstance(verification, list)
        or not verification
        or not all(isinstance(item, str) and item.strip() for item in verification)
    ):
        return None
    return receipt


def _claude_fable_acceptance_present() -> bool:
    """True only for a current receipt that binds Fable to a plan-only capsule."""

    return _fable_acceptance_receipt() is not None


def _fable_balance_status() -> tuple[dict | None, str]:
    """Return a fresh, internally coherent weekly balance or a fail-closed reason."""

    raw = os.environ.get("LIMEN_FABLE_BALANCE_PATH")
    if raw:
        path = raw
    else:
        root = os.environ.get("LIMEN_ROOT")
        base = root if root else os.path.join(os.path.expanduser("~"), "Workspace", "limen")
        path = os.path.join(base, "logs", "fable-allotment.json")
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None, "balance-absent"
    except Exception:
        return None, "balance-unreadable"
    if not isinstance(data, dict) or data.get("schema") != _FABLE_BALANCE_SCHEMA:
        return None, "balance-malformed"
    numeric_fields = (data.get("spent_pct"), data.get("deliberate_cap"), data.get("hard_cap"), data.get("spent_tokens"))
    if any(isinstance(value, bool) for value in numeric_fields):
        return None, "balance-malformed-numbers"
    if data.get("week") != _current_week():
        return None, "balance-stale-week"
    observed = _parse_utc(data.get("observed_at"))
    if observed is None:
        return None, "balance-missing-observation-time"
    now = dt.datetime.now(dt.timezone.utc)
    try:
        max_age = max(
            1,
            int(
                os.environ.get(
                    "LIMEN_FABLE_BALANCE_MAX_AGE_SECONDS",
                    str(_FABLE_BALANCE_MAX_AGE_SECONDS_DEFAULT),
                )
            ),
        )
    except ValueError:
        max_age = _FABLE_BALANCE_MAX_AGE_SECONDS_DEFAULT
    age = (now - observed).total_seconds()
    if age < -60:
        return None, "balance-from-future"
    if age > max_age:
        return None, "balance-stale-observation"
    if data.get("meter_ready") is not True:
        return None, "balance-source-unready"
    if data.get("source") not in {"ratelimit-header", "transcript-token-sum"}:
        return None, "balance-unknown-source"
    try:
        spent = float(data.get("spent_pct"))
        deliberate = float(data.get("deliberate_cap"))
        hard = float(data.get("hard_cap"))
        spent_tokens = int(data.get("spent_tokens"))
    except (TypeError, ValueError):
        return None, "balance-malformed-numbers"
    if not all(math.isfinite(value) for value in (spent, deliberate, hard)):
        return None, "balance-nonfinite"
    if spent < 0 or deliberate <= 0 or hard < deliberate or hard > 100 or spent_tokens < 0:
        return None, "balance-invalid-range"
    if not isinstance(data.get("over_cap"), bool) or data["over_cap"] != (spent >= hard):
        return None, "balance-incoherent-cap-state"
    return data, "ok"


def _fable_balance() -> dict | None:
    """Return only a fresh authoritative balance; all missing/bad states fail closed."""

    return _fable_balance_status()[0]


def _fable_capped_tier(reserve_ok: bool) -> str | None:
    """The live-cap decision for a would-be Fable selection whose acceptance receipt already
    passed. Returns None when Fable is still allowed, else the fallback tier to use instead:

      * spent_pct < deliberate_cap (40)         → None (Fable allowed).
      * deliberate_cap ≤ spent_pct < hard_cap   → only a current-week ``reserve`` receipt passes;
                                                   every other Fable route → Opus.
      * spent_pct ≥ hard_cap (50)               → hard downgrade to Opus, NO exception.

    ``reserve_ok`` marks that the caller's authorization is a fresh ``reserve``-category receipt.
    Missing, stale, malformed, or source-dark balance state fails closed to the cap downgrade.
    HARD_CAP is a hard cap. The cap
    downgrade lands on Opus (an over-cap Fable job was legitimately high-value; Opus is the nearest
    tier down), distinct from the acceptance-ABSENT fallback which stays at ``_fable_fallback_tier``.
    """
    bal = _fable_balance()
    if bal is None:
        return _fable_cap_downgrade_tier()
    try:
        spent = float(bal.get("spent_pct"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _fable_cap_downgrade_tier()
    deliberate_cap = float(bal.get("deliberate_cap", 40) or 40)
    hard_cap = float(bal.get("hard_cap", 50) or 50)
    if spent >= hard_cap:
        return _fable_cap_downgrade_tier()
    if spent >= deliberate_cap:
        return None if reserve_ok else _fable_cap_downgrade_tier()
    return None


def _fable_cap_downgrade_tier() -> str:
    """Where an OVER-CAP (but acceptance-valid) Fable selection lands: Opus by default, capped to
    the ladder, env-overridable via ``LIMEN_CLAUDE_FABLE_CAP_TIER``."""
    return _cap_tier(os.environ.get("LIMEN_CLAUDE_FABLE_CAP_TIER", "opus"), "opus")


def _fable_reserve_receipt_present() -> bool:
    """True only when the current acceptance receipt is a fresh (current-ISO-week) ``reserve``
    category receipt — the single exception that passes the 40–50% band. Reuses the same receipt
    file the acceptance gate reads; a test ``LIMEN_FABLE_ACCEPTANCE=1`` is NOT a reserve receipt."""
    receipt = _fable_acceptance_receipt()
    return bool(receipt is not None and receipt.get("category") == "reserve")


def _fable_or_downgrade(fable_tier: str = "fable") -> str:
    """Resolve a Fable-authorized selection against the LIVE weekly cap. Precondition: the caller
    has already confirmed a valid acceptance receipt is present. Returns ``fable_tier`` when the
    cap still allows Fable, else the fallback tier (Opus). This is the runtime backstop layered on
    top of the accept-time receipt gate."""
    downgrade = _fable_capped_tier(_fable_reserve_receipt_present())
    return downgrade if downgrade is not None else fable_tier


def _claude_model_is_fable(model: str | None) -> bool:
    return bool(model and "fable" in str(model).lower())


def _claude_model_is_opus(model: str | None) -> bool:
    return bool(model and "opus" in str(model).lower())


def _claude_model_uses_large_context(model: str | None) -> bool:
    text = str(model or "").lower()
    return bool("1m" in text or "1000000" in text or "1,000,000" in text)


def _tier_index(tier: str) -> int:
    try:
        return _CLAUDE_TIER_ORDER.index(tier)
    except ValueError:
        return 0


def _cap_tier(tier: str, cap: str) -> str:
    """Return ``tier`` capped to ``cap`` in the shared cheap→expensive ladder."""
    if tier not in _CLAUDE_TIER_ORDER:
        tier = "haiku"
    if cap not in _CLAUDE_TIER_ORDER:
        cap = "sonnet"
    return _CLAUDE_TIER_ORDER[min(_tier_index(tier), _tier_index(cap))]


def _max_inherited_tier() -> str:
    """The highest tier allowed for inherited/default fleet choices.

    This applies to unclassed shim floors and global ``LIMEN_CLAUDE_MODEL`` pins. Task-specific
    declaration sites can still earn Opus/Fable through the ladder and acceptance gates.
    """
    hard_cap = "fable" if _expensive_model_pin_allowed() else "sonnet"
    return _cap_tier(os.environ.get("LIMEN_CLAUDE_MAX_INHERITED_TIER", "sonnet"), hard_cap)


def _fable_fallback_tier() -> str:
    return _cap_tier(os.environ.get("LIMEN_CLAUDE_FABLE_FALLBACK_TIER", "sonnet"), "opus")


def _expensive_model_pin_allowed() -> bool:
    return os.environ.get("LIMEN_ALLOW_EXPENSIVE_CLAUDE_MODEL_PIN") == "1"


def _large_context_allowed() -> bool:
    return os.environ.get("LIMEN_ALLOW_CLAUDE_1M_CONTEXT") == "1" or _claude_fable_acceptance_present()


def _resolve_claude_model(tier: str) -> str:
    """tier → the ``claude --model`` value. Env pin wins (LIMEN_CLAUDE_<TIER>_MODEL); else the
    bare CLI tier alias, which the ``claude`` CLI resolves to the current dated model itself
    (nothing pinned, survives renames). ([[derive-never-pin-hardcodes]])"""
    model = os.environ.get(f"LIMEN_CLAUDE_{tier.upper()}_MODEL") or tier
    # A lower-tier env alias must not smuggle a Fable model through a fallback/cap decision. Only
    # the explicitly selected ``fable`` rung may resolve to a Fable-bearing provider value.
    if tier != "fable" and _claude_model_is_fable(model):
        return tier if tier in _CLAUDE_TIER_ORDER else "sonnet"
    if _claude_model_is_fable(model) and not _claude_fable_acceptance_present():
        return _resolve_claude_model(_fable_fallback_tier()) if tier == "fable" else tier
    # Live weekly-cap backstop: a valid receipt is necessary-not-sufficient. When the week's Fable
    # spend is at/over cap, downgrade to Opus even for an accepted Fable selection (reserve receipts
    # pass only in the 40–50% band). Fail-open when no balance meter is present.
    if _claude_model_is_fable(model):
        capped = _fable_capped_tier(_fable_reserve_receipt_present())
        if capped is not None:
            return _resolve_claude_model(capped)
    if _claude_model_uses_large_context(model) and not _large_context_allowed():
        return tier if tier in _CLAUDE_TIER_ORDER else _max_inherited_tier()
    return model


def _guard_claude_model_pin(model: str | None) -> str | None:
    """Prevent global model pins from turning every inherited fleet spawn expensive.

    Per-task declaration sites still pass explicit ``--model`` values through the shim; those are
    audited by transcript/workflow guards. This guard covers the global default pin
    ``LIMEN_CLAUDE_MODEL``, which otherwise becomes inherited fan-out for unrelated cheap work.
    """
    # A global pin has no task/capsule boundary, so it cannot prove plan-only execution. Accepted
    # task-scoped dispatch declares Fable explicitly after validating that boundary.
    if _claude_model_is_fable(model):
        return _resolve_claude_model(_fable_fallback_tier())
    if (_claude_model_is_opus(model) or _claude_model_uses_large_context(model)) and not _expensive_model_pin_allowed():
        return _resolve_claude_model(_max_inherited_tier())
    if _claude_model_uses_large_context(model) and not _large_context_allowed():
        return _resolve_claude_model(_max_inherited_tier())
    return model


def _guard_fable_model_pin(model: str | None) -> str | None:
    """Backward-compatible name for the global Claude model-pin guard."""
    return _guard_claude_model_pin(model)


# ── The non-bypassable shim's per-spawn floor sort ──────────────────────────────────────────
# The shim sits FIRST on the fleet PATH, so every fleet-spawned `claude` resolves to it. It is the
# ENFORCEMENT half of the tiering chain: the rich, per-task SORT happens at the declaration sites
# (dispatch's ladder, converge's tier factory) which pass --model explicitly; the shim GUARANTEES
# nothing escapes that sort to the account default WITHOUT a declaration. The rule:
#
#   • --model already present  → leave it (the declaration site already sorted this spawn);
#   • not a `-p` / `--print` run → leave it (interactive / `claude mcp …` / etc. — never re-tier);
#   • else                      → inject the FLOOR: LIMEN_CLAUDE_SHIM_FLOOR (default "haiku" — the
#                                 SAME tier dispatch's ladder assigns to unclassed work, so this is
#                                 the ladder's own default, NOT a blanket downgrade).
#
# Subagents default to `inherit`, so this one top-level injection governs the ENTIRE fan-out tree.
# CAVEAT: `claude --resume` ignores --model (a resumed session keeps its BIRTH model), so a resume
# is governed by the tier it was born at — which this shim sets for every NEW session. Fail-open to
# None in every branch (→ bare invocation under the ANTHROPIC_MODEL seatbelt), never block a spawn.


def _shim_floor_tier() -> str:
    """The floor tier for an unclassed fleet spawn.

    ``LIMEN_CLAUDE_SHIM_FLOOR`` tunes it, but inherited/default floors are capped by
    ``LIMEN_CLAUDE_MAX_INHERITED_TIER`` (default Sonnet) so a shell export cannot make trivial
    workers inherit Opus/Fable or 1M context by default.
    """
    tier = os.environ.get("LIMEN_CLAUDE_SHIM_FLOOR", "haiku")
    if tier not in _CLAUDE_TIER_ORDER:
        return "haiku"
    return _cap_tier(tier, _max_inherited_tier())


def model_for_argv(args: list[str]) -> str | None:
    """The ``--model`` value to INJECT for a fleet ``claude`` invocation, or None to leave the
    spawn untouched.

    ``args`` is argv WITHOUT the program name (i.e. ``sys.argv[1:]``). Returns a model string to
    splice in as ``--model <value>``, or None when the spawn must not be touched: it already
    carries --model (a declaration site sorted it), it is not a print/headless run, tiering is
    deliberately gated off, or anything errors (fail-open). Mirrors the precedence of
    ``dispatch._claude_model``: explicit pin > feature gate > derived floor.
    """
    try:
        if any(arg == "--model" or arg.startswith("--model=") for arg in args):
            return None  # the declaration site already sorted this spawn — respect it
        if not ("-p" in args or "--print" in args):
            return None  # interactive / `claude mcp …` / any non-print — never re-tier
        pin = os.environ.get("LIMEN_CLAUDE_MODEL")
        if pin:
            return _guard_claude_model_pin(pin)  # a manual pin wins only inside the expensive gates
        if os.environ.get("LIMEN_CLAUDE_TIER_SELECT", "1") != "1":
            return None  # tiering deliberately disabled → bare invocation (account default)
        return _resolve_claude_model(_shim_floor_tier())
    except Exception:
        return None  # never block a spawn on a sort hiccup


def main(argv: list[str] | None = None) -> int:
    """Debug/inspection entrypoint: print the model :func:`model_for_argv` would inject for the
    given args (nothing if it would leave the spawn untouched). Example:
    ``python -m limen.model_selection -p hello`` → ``haiku``."""
    import sys

    model = model_for_argv(list(argv if argv is not None else sys.argv[1:]))
    if model:
        print(model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
