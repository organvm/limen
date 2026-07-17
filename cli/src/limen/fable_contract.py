"""Provider-neutral validation for the bounded Fable planning contract.

This module validates authority and evidence; it never chooses a provider model.
Fable is an opaque execution role supplied by the caller. A valid Fable launch
requires a current plan-only acceptance, a fresh reconciled balance, and an
automatic non-Fable builder handoff with no encoded model or tier identifier.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path, PurePosixPath
from typing import Any

ACCEPTANCE_SCHEMA = "limen.fable_acceptance.v1"
BALANCE_SCHEMA = "limen.fable_balance.v1"
PACKET_SCHEMA = "limen.fable_build_packet.v1"
PACKET_RECEIPT_SCHEMA = "limen.fable_packet_receipt.v1"
MOTION_RECEIPT_DEADLINE_SECONDS = 5_400
DEFAULT_BALANCE_MAX_AGE_SECONDS = 900
FUTURE_SKEW_SECONDS = 300
ACCEPTANCE_CATEGORIES = frozenset({"substrate", "prompt-corpus", "governance", "adversarial-review", "reserve"})


class ContractError(ValueError):
    """A Fable authority or evidence receipt is missing, stale, or incoherent."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def current_week(moment: dt.datetime | None = None) -> str:
    moment = (moment or _now()).astimezone(dt.timezone.utc)
    return (moment - dt.timedelta(days=moment.weekday())).date().isoformat()


def _timestamp(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field}-missing")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise ContractError(f"{field}-invalid") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field}-timezone-missing")
    return parsed.astimezone(dt.timezone.utc)


def _finite_number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ContractError(f"{field}-invalid")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field}-invalid") from exc
    if not math.isfinite(parsed) or (minimum is not None and parsed < minimum):
        raise ContractError(f"{field}-invalid")
    return parsed


def builder_handoff() -> dict[str, Any]:
    """Return the sole accepted provider-neutral implementation handoff."""

    return {
        "provider_selection": "auto",
        "requirements": {
            "planning_only": False,
            "build_allowed": True,
            "fable_allowed": False,
        },
    }


def _validate_builder_handoff(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"provider_selection", "requirements"}:
        raise ContractError("builder-handoff-invalid")
    if value.get("provider_selection") != "auto":
        raise ContractError("builder-provider-selection-not-auto")
    requirements = value.get("requirements")
    if not isinstance(requirements, dict) or set(requirements) != {
        "planning_only",
        "build_allowed",
        "fable_allowed",
    }:
        raise ContractError("builder-requirements-invalid")
    if requirements != {
        "planning_only": False,
        "build_allowed": True,
        "fable_allowed": False,
    }:
        raise ContractError("builder-requirements-invalid")


def validate_acceptance_receipt(
    receipt: Any,
    *,
    moment: dt.datetime | None = None,
    require_current_week: bool = True,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ContractError("acceptance-not-object")
    if receipt.get("schema") != ACCEPTANCE_SCHEMA:
        raise ContractError("acceptance-schema-invalid")
    created_at = _timestamp(receipt.get("created_at"), "acceptance-created-at")
    if receipt.get("week") != current_week(created_at):
        raise ContractError("acceptance-created-at-week-mismatch")
    now = (moment or _now()).astimezone(dt.timezone.utc)
    if created_at > now + dt.timedelta(seconds=FUTURE_SKEW_SECONDS):
        raise ContractError("acceptance-created-at-future")
    if require_current_week and receipt.get("week") != current_week(now):
        raise ContractError("acceptance-week-stale")
    if receipt.get("category") not in ACCEPTANCE_CATEGORIES:
        raise ContractError("acceptance-category-invalid")
    _finite_number(receipt.get("percent"), "acceptance-percent", minimum=0.0000001)
    if receipt.get("category") == "reserve" and receipt.get("reserve_unlocked") is not True:
        raise ContractError("acceptance-reserve-locked")
    if receipt.get("mode") != "plan-only":
        raise ContractError("acceptance-mode-not-plan-only")
    if receipt.get("deliverable") != "continuation-capsule":
        raise ContractError("acceptance-deliverable-invalid")
    if receipt.get("motion_receipt_deadline_seconds") != MOTION_RECEIPT_DEADLINE_SECONDS:
        raise ContractError("acceptance-motion-deadline-invalid")
    _validate_builder_handoff(receipt.get("builder_handoff"))

    sources = receipt.get("sources") or []
    redacted = receipt.get("redacted_packets") or []
    if not isinstance(sources, list) or not isinstance(redacted, list):
        raise ContractError("acceptance-sources-invalid")
    if not sources and not redacted:
        raise ContractError("acceptance-sources-missing")
    if any(not isinstance(item, str) or not item.strip() for item in [*sources, *redacted]):
        raise ContractError("acceptance-sources-invalid")
    verification = receipt.get("verification")
    if (
        not isinstance(verification, list)
        or not verification
        or any(not isinstance(item, str) or not item.strip() for item in verification)
    ):
        raise ContractError("acceptance-verification-invalid")
    return receipt


def _root() -> Path:
    return Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[3])


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        if not path.is_file():
            raise ContractError(f"{label}-missing")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ContractError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label}-unreadable") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{label}-not-object")
    return payload


def _receipt_path(raw: str | os.PathLike[str] | None, *, default: Path | None = None) -> Path:
    if raw is None:
        if default is None:
            raise ContractError("receipt-path-missing")
        return default
    text = os.fspath(raw).strip()
    if not text or text == "1":
        raise ContractError("receipt-path-missing")
    path = Path(text).expanduser()
    return path if path.is_absolute() else _root() / path


def acceptance_status(
    raw: str | os.PathLike[str] | None = None,
    *,
    moment: dt.datetime | None = None,
) -> tuple[dict[str, Any] | None, str]:
    try:
        configured = raw if raw is not None else os.environ.get("LIMEN_FABLE_ACCEPTANCE")
        if configured is None or not os.fspath(configured).strip() or os.fspath(configured).strip() == "1":
            raise ContractError("acceptance-missing")
        path = _receipt_path(configured)
        receipt = _read_object(path, "acceptance")
        validate_acceptance_receipt(receipt, moment=moment)
        return receipt, "ok"
    except ContractError as exc:
        return None, str(exc)


def acceptance_present(
    raw: str | os.PathLike[str] | None = None,
    *,
    moment: dt.datetime | None = None,
) -> bool:
    receipt, _reason = acceptance_status(raw, moment=moment)
    return receipt is not None


def _positive_age_limit() -> int:
    raw = os.environ.get("LIMEN_FABLE_BALANCE_MAX_AGE_SECONDS")
    if raw is None:
        return DEFAULT_BALANCE_MAX_AGE_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ContractError("balance-max-age-invalid") from exc
    if value <= 0:
        raise ContractError("balance-max-age-invalid")
    return value


def validate_balance_receipt(
    receipt: Any,
    *,
    moment: dt.datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ContractError("balance-not-object")
    if receipt.get("schema") != BALANCE_SCHEMA:
        raise ContractError("balance-schema-invalid")
    now = (moment or _now()).astimezone(dt.timezone.utc)
    if receipt.get("week") != current_week(now):
        raise ContractError("balance-week-stale")
    observed_at = _timestamp(receipt.get("observed_at"), "balance-observed-at")
    age = (now - observed_at).total_seconds()
    if age < -FUTURE_SKEW_SECONDS:
        raise ContractError("balance-future-observation")
    if age > _positive_age_limit():
        raise ContractError("balance-stale-observation")
    if receipt.get("meter_ready") is not True:
        raise ContractError("balance-meter-dark")
    if not isinstance(receipt.get("source"), str) or not receipt["source"].strip():
        raise ContractError("balance-source-missing")

    spent_tokens = _finite_number(receipt.get("spent_tokens"), "balance-spent-tokens", minimum=0)
    if not spent_tokens.is_integer():
        raise ContractError("balance-spent-tokens-invalid")
    spent_pct = _finite_number(receipt.get("spent_pct"), "balance-spent-pct", minimum=0)
    deliberate = _finite_number(receipt.get("deliberate_cap"), "balance-deliberate-cap", minimum=0)
    hard = _finite_number(receipt.get("hard_cap"), "balance-hard-cap", minimum=0)
    if not deliberate < hard <= 100:
        raise ContractError("balance-caps-invalid")
    measurement = receipt.get("measurement")
    if not isinstance(measurement, dict):
        raise ContractError("balance-measurement-missing")
    method = measurement.get("method")
    if method == "token-ratio":
        numerator = _finite_number(
            measurement.get("numerator_tokens"),
            "balance-measurement-numerator",
            minimum=0,
        )
        denominator = _finite_number(
            measurement.get("denominator_tokens"),
            "balance-measurement-denominator",
            minimum=0.0000001,
        )
        if (
            not numerator.is_integer()
            or not denominator.is_integer()
            or numerator != spent_tokens
            or measurement.get("unbound_usage_rows") != 0
            or measurement.get("role_binding") != "execution_role:fable-planner"
        ):
            raise ContractError("balance-measurement-incoherent")
        expected_pct = round(100.0 * numerator / denominator, 2)
        if not math.isclose(spent_pct, expected_pct, abs_tol=0.0000001):
            raise ContractError("balance-measurement-incoherent")
    elif method == "owner-used-percent":
        owner_pct = _finite_number(
            measurement.get("owner_observed_pct"),
            "balance-owner-observed-pct",
            minimum=0,
        )
        if not math.isclose(spent_pct, owner_pct, abs_tol=0.0000001):
            raise ContractError("balance-measurement-incoherent")
    else:
        raise ContractError("balance-measurement-method-invalid")
    expected_over_cap = spent_pct >= hard
    if receipt.get("over_cap") is not expected_over_cap:
        raise ContractError("balance-over-cap-incoherent")
    return receipt


def balance_status(
    raw: str | os.PathLike[str] | None = None,
    *,
    moment: dt.datetime | None = None,
) -> tuple[dict[str, Any] | None, str]:
    try:
        default = _root() / "logs" / "fable-allotment.json"
        configured = raw if raw is not None else os.environ.get("LIMEN_FABLE_BALANCE_PATH")
        path = _receipt_path(configured, default=default)
        receipt = _read_object(path, "balance")
        validate_balance_receipt(receipt, moment=moment)
        return receipt, "ok"
    except ContractError as exc:
        return None, str(exc)


def cap_status(
    balance: dict[str, Any],
    acceptance: dict[str, Any],
) -> tuple[bool, str]:
    spent = float(balance["spent_pct"])
    deliberate = float(balance["deliberate_cap"])
    hard = float(balance["hard_cap"])
    if spent >= hard:
        return True, "hard-cap"
    if spent >= deliberate and not (
        acceptance.get("category") == "reserve" and acceptance.get("reserve_unlocked") is True
    ):
        return True, "reserve-required"
    return False, "open"


def authorization_status(
    *,
    acceptance_path: str | os.PathLike[str] | None = None,
    balance_path: str | os.PathLike[str] | None = None,
    moment: dt.datetime | None = None,
) -> tuple[dict[str, Any] | None, str]:
    acceptance, acceptance_reason = acceptance_status(acceptance_path, moment=moment)
    if acceptance is None:
        return None, acceptance_reason
    balance, balance_reason = balance_status(balance_path, moment=moment)
    if balance is None:
        return None, balance_reason
    closed, reason = cap_status(balance, acceptance)
    if closed:
        return None, reason
    return {"acceptance": acceptance, "balance": balance}, "ok"


def validate_execution_profile(value: Any) -> None:
    if not isinstance(value, dict) or value != {
        "execution_role": "fable-planner",
        "planning_only": True,
        "build_allowed": False,
        "fanout_allowed": False,
    }:
        raise ContractError("fable-execution-profile-invalid")


def validate_packet_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("fable-packet-missing")
    if value.get("schema") != PACKET_SCHEMA:
        raise ContractError("fable-packet-schema-invalid")
    if value.get("mode") != "plan-only" or value.get("implementation_by_fable") != "prohibited":
        raise ContractError("fable-packet-mode-invalid")
    _validate_builder_handoff(value.get("builder_handoff"))
    raw_path = value.get("path")
    if not isinstance(raw_path, str):
        raise ContractError("fable-packet-path-invalid")
    path = PurePosixPath(raw_path)
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(path.parts) != 4
        or path.parts[:3] != ("docs", "continuations", "fable")
        or path.suffix != ".md"
        or path.name in {".md", "..md"}
    ):
        raise ContractError("fable-packet-path-invalid")
    return value
