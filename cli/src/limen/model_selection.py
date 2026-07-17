"""Fail-closed Claude override validation from live owner metadata.

Provider model identifiers are opaque runtime outputs. Limen does not infer cost,
context, or execution role from an identifier and does not maintain a provider
tier ladder. A bare invocation stays on provider Auto. An explicit override is
accepted only when a fresh owner selection receipt binds the exact identifier to
the live catalog and current execution profile.

This module is stdlib-only because ``scripts/shims/claude`` loads it directly by
file path before every fleet Claude invocation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any

CLAUDE_MODEL_SELECTION_SCHEMA = "limen.claude_model_selection.v1"
DEFAULT_SELECTION_MAX_AGE_SECONDS = 300
FUTURE_SKEW_SECONDS = 60
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_FABLE_ROLE = "fable-planner"
_SELECTION_NAMESPACE = "limen-claude-model-selection"
_FABLE_LAUNCH_SCHEMA = "limen.fable_preservation_launch.v1"
_FABLE_ORCHESTRATOR = "limen.preservation-orchestrator"
_FABLE_REQUIRED_DENIALS = frozenset(
    {
        "Agent",
        "AskUserQuestion",
        "Bash",
        "Edit",
        "NotebookEdit",
        "Workflow",
        "Write",
        "mcp__*",
    }
)


class ModelSelectionBlocked(RuntimeError):
    """The requested provider override lacks current owner evidence."""


def _owner_authority() -> Any | None:
    try:
        from limen import owner_authority

        return owner_authority
    except Exception:
        try:
            path = Path(__file__).with_name("owner_authority.py")
            spec = importlib.util.spec_from_file_location("_limen_model_selection_owner_authority", path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception:
            return None


def _fable_contract() -> Any | None:
    try:
        path = Path(__file__).with_name("fable_contract.py")
        spec = importlib.util.spec_from_file_location("_limen_model_selection_fable_contract", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _fable_authorization_status(
    execution_profile_value: Any = None,
) -> tuple[dict[str, Any] | None, str]:
    contract = _fable_contract()
    if contract is None:
        return None, "fable-contract-validator-unavailable"
    try:
        receipt = load_selection_receipt()
        if receipt.get("execution_profile") != execution_profile_value:
            return None, "fable-authority-profile-mismatch"
        authority = contract.validate_authority_bundle(
            receipt.get("fable_authority"),
            execution_profile_value=execution_profile_value,
        )
        return authority, "ok"
    except Exception as exc:
        return None, str(exc) or "fable-contract-validator-failed"


def _timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ModelSelectionBlocked("Claude model selection receipt lacks observed_at")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise ModelSelectionBlocked("Claude model selection observed_at is invalid") from exc
    if parsed.tzinfo is None:
        raise ModelSelectionBlocked("Claude model selection observed_at lacks a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _selection_age_limit() -> int:
    return DEFAULT_SELECTION_MAX_AGE_SECONDS


def _normalized_models(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ModelSelectionBlocked("Claude model selection receipt has no live catalog")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ModelSelectionBlocked("Claude model catalog row is invalid")
        model_id = item.get("id")
        active = item.get("active")
        roles = item.get("execution_roles")
        if (
            not isinstance(model_id, str)
            or not model_id.strip()
            or active is not True
            or not isinstance(roles, list)
            or any(not isinstance(role, str) or not role.strip() for role in roles)
        ):
            raise ModelSelectionBlocked("Claude model catalog row is invalid")
        model_id = model_id.strip()
        if model_id in seen:
            raise ModelSelectionBlocked("Claude model catalog contains a duplicate identifier")
        seen.add(model_id)
        normalized.append(
            {
                "id": model_id,
                "active": True,
                "execution_roles": sorted(set(roles)),
            }
        )
    return sorted(normalized, key=lambda row: row["id"])


def _catalog_hash(models: list[dict[str, Any]]) -> str:
    payload = json.dumps(models, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _selection_path(raw: str | os.PathLike[str] | None = None) -> Path:
    if raw is not None:
        raise ModelSelectionBlocked("caller-selected Claude selection receipt paths are prohibited")
    authority = _owner_authority()
    if authority is None:
        raise ModelSelectionBlocked("Claude owner authority is unprovisioned")
    try:
        return authority.receipt_path("claude-model-selection.json")
    except Exception as exc:
        raise ModelSelectionBlocked("Claude owner authority is unprovisioned") from exc


def _validate_launch_contract(value: Any, *, attempt_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value != {
        "schema": _FABLE_LAUNCH_SCHEMA,
        "orchestrator": _FABLE_ORCHESTRATOR,
        "attempt_id": attempt_id,
        "mode": "noninteractive-print",
        "resume_allowed": False,
        "direct_launch_allowed": False,
    }:
        raise ModelSelectionBlocked("Fable selection lacks the canonical preservation-orchestrator launch contract")
    return dict(value)


def _verify_owner_selection(value: Any) -> None:
    authority = _owner_authority()
    if authority is None:
        raise ModelSelectionBlocked("Claude owner authority is unprovisioned")
    try:
        authority.verify_receipt(value, namespace=_SELECTION_NAMESPACE)
    except Exception as exc:
        raise ModelSelectionBlocked(f"Claude owner attestation is invalid: {str(exc) or 'invalid'}") from exc


def _require_fable_orchestrator() -> None:
    authority = _owner_authority()
    if authority is None:
        raise ModelSelectionBlocked("Fable preservation orchestrator is unprovisioned")
    try:
        authority.require_canonical_orchestrator_parent()
    except Exception as exc:
        raise ModelSelectionBlocked(f"Fable direct launch is prohibited: {str(exc) or 'invalid'}") from exc


def validate_selection_receipt(
    value: Any,
    *,
    moment: dt.datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != CLAUDE_MODEL_SELECTION_SCHEMA:
        raise ModelSelectionBlocked("Claude model selection receipt schema is invalid")
    if value.get("authority_status") != "owner-signed":
        raise ModelSelectionBlocked("Claude model selection receipt is not owner-signed authority")
    observed_at = _timestamp(value.get("observed_at"))
    now = (moment or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    age = (now - observed_at).total_seconds()
    if age < -FUTURE_SKEW_SECONDS:
        raise ModelSelectionBlocked("Claude model selection receipt is future-dated")
    if age > _selection_age_limit():
        raise ModelSelectionBlocked("Claude model selection receipt is stale")
    if not isinstance(value.get("source"), str) or not value["source"].strip():
        raise ModelSelectionBlocked("Claude model selection receipt lacks an owner source")
    if not isinstance(value.get("attempt_id"), str) or not value["attempt_id"].strip():
        raise ModelSelectionBlocked("Claude model selection receipt lacks an attempt identity")
    if not isinstance(value.get("task_id"), str) or not value["task_id"].strip():
        raise ModelSelectionBlocked("Claude model selection receipt lacks a task identity")
    if not isinstance(value.get("selection_source"), str) or not value["selection_source"].strip().endswith(
        "_live_catalog"
    ):
        raise ModelSelectionBlocked("Claude model selection source is not live-catalog evidence")
    selected = value.get("selected_model")
    if not isinstance(selected, str) or not selected.strip():
        raise ModelSelectionBlocked("Claude model selection receipt lacks a selected model")
    models = _normalized_models(value.get("models"))
    digest = value.get("catalog_hash")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None or digest != _catalog_hash(models):
        raise ModelSelectionBlocked("Claude model selection catalog hash is invalid")
    matching = [row for row in models if row["id"] == selected]
    if len(matching) != 1:
        raise ModelSelectionBlocked("selected Claude model is absent from the live catalog")
    profile = value.get("execution_profile")
    if not isinstance(profile, dict):
        raise ModelSelectionBlocked("Claude model selection receipt lacks an execution profile")
    role = profile.get("execution_role")
    selected_row = matching[0]
    if role is not None:
        if not isinstance(role, str) or not role.strip() or role.strip() not in selected_row["execution_roles"]:
            raise ModelSelectionBlocked("Claude execution role is absent from the selected live-catalog row")
    if role == _FABLE_ROLE:
        _validate_launch_contract(value.get("launch_contract"), attempt_id=value["attempt_id"])
        contract = _fable_contract()
        if contract is None:
            raise ModelSelectionBlocked("Fable contract validator is unavailable")
        try:
            contract.validate_authority_bundle(
                value.get("fable_authority"),
                execution_profile_value=profile,
                moment=now,
            )
        except Exception as exc:
            raise ModelSelectionBlocked(f"Fable planner authority is closed: {str(exc) or 'invalid'}") from exc
    elif value.get("fable_authority") is not None or value.get("launch_contract") is not None:
        raise ModelSelectionBlocked("non-Fable Claude selection carries Fable-only authority")
    _verify_owner_selection(value)
    return {**value, "selected_model": selected.strip(), "models": models}


def load_selection_receipt(
    raw: str | os.PathLike[str] | None = None,
    *,
    moment: dt.datetime | None = None,
) -> dict[str, Any]:
    path = _selection_path(raw)
    try:
        if path.is_symlink() or not path.is_file():
            raise ModelSelectionBlocked("Claude model selection receipt is unavailable")
        value = json.loads(path.read_text(encoding="utf-8"))
    except ModelSelectionBlocked:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelSelectionBlocked("Claude model selection receipt is unreadable") from exc
    return validate_selection_receipt(value, moment=moment)


def _option_values(args: list[str], *names: str) -> list[str]:
    values: list[str] = []
    for index, arg in enumerate(args):
        for name in names:
            if arg == name:
                if index + 1 < len(args):
                    values.append(args[index + 1])
            elif arg.startswith(f"{name}="):
                values.append(arg.split("=", 1)[1])
    return values


def _tool_rules(values: list[str]) -> set[str]:
    return {item.strip() for value in values for item in value.split(",") if item.strip()}


def _validate_fable_argv(args: list[str]) -> None:
    contract = _fable_contract()
    if contract is None:
        raise ModelSelectionBlocked("Fable contract validator is unavailable")
    tools = _tool_rules(_option_values(args, "--tools"))
    allowed = _tool_rules(_option_values(args, "--allowedTools", "--allowed-tools"))
    disallowed = _tool_rules(_option_values(args, "--disallowedTools", "--disallowed-tools"))
    permission_modes = _option_values(args, "--permission-mode")
    print_flags = [arg for arg in args if arg in {"-p", "--print"}]
    resume_flags = {
        "-c",
        "--continue",
        "--resume",
        "--session-id",
        "--fork-session",
        "--teleport",
    }
    if (
        not tools
        or tools != allowed
        or not tools <= set(contract.FABLE_READ_ONLY_TOOLS)
        or not _FABLE_REQUIRED_DENIALS <= disallowed
        or permission_modes != ["dontAsk"]
        or "--no-chrome" not in args
        or "--dangerously-skip-permissions" in args
        or len(print_flags) != 1
        or any(
            arg in resume_flags or any(arg.startswith(f"{flag}=") for flag in resume_flags if flag.startswith("--"))
            for arg in args
        )
    ):
        raise ModelSelectionBlocked(
            "Fable model identity cannot run outside the exact plan-only read-only tool surface"
        )


def validate_claude_model_override(
    model: str,
    *,
    execution_profile_value: Any = None,
    args: list[str] | None = None,
    receipt_path: str | os.PathLike[str] | None = None,
    moment: dt.datetime | None = None,
) -> str:
    """Validate an opaque explicit model against current catalog and role evidence."""

    if not isinstance(model, str) or not model.strip():
        raise ModelSelectionBlocked("explicit Claude model override is empty")
    model = model.strip()
    receipt = load_selection_receipt(receipt_path, moment=moment)
    if receipt["selected_model"] != model:
        raise ModelSelectionBlocked("explicit Claude model override differs from the owner selection")
    if execution_profile_value is not None and receipt["execution_profile"] != execution_profile_value:
        raise ModelSelectionBlocked("Claude model selection execution profile does not match this launch")
    row = next(item for item in receipt["models"] if item["id"] == model)
    roles = set(row["execution_roles"])
    receipt_profile = receipt["execution_profile"]
    role = receipt_profile.get("execution_role")
    if _FABLE_ROLE in roles or role == _FABLE_ROLE:
        if _FABLE_ROLE not in roles or role != _FABLE_ROLE:
            raise ModelSelectionBlocked("Fable model identity and execution role are not mutually bound")
        if args is not None:
            _require_fable_orchestrator()
            _validate_fable_argv(args)
    return model


def selected_model_for_profile(
    execution_profile_value: Any,
    *,
    explicit_model: str | None = None,
) -> str:
    """Return the receipt-selected opaque model for an owner-bound profile."""

    receipt = load_selection_receipt()
    candidate = explicit_model or receipt["selected_model"]
    return validate_claude_model_override(
        candidate,
        execution_profile_value=execution_profile_value,
    )


def _explicit_model(args: list[str]) -> str | None:
    values: list[str] = []
    for index, arg in enumerate(args):
        if arg == "--model":
            if index + 1 >= len(args) or args[index + 1].startswith("-"):
                raise ModelSelectionBlocked("explicit Claude --model override lacks a value")
            values.append(args[index + 1])
        elif arg.startswith("--model="):
            values.append(arg.split("=", 1)[1])
    if len(values) > 1:
        raise ModelSelectionBlocked("Claude invocation contains multiple model overrides")
    return values[0] if values else None


def model_for_argv(args: list[str]) -> str | None:
    """Validate every explicit override; leave an unpinned invocation on provider Auto."""

    explicit = _explicit_model(args)
    configured = [
        value.strip()
        for name in ("LIMEN_CLAUDE_MODEL", "ANTHROPIC_MODEL", "CLAUDE_MODEL")
        if (value := os.environ.get(name)) and value.strip()
    ]
    if explicit is None and len(set(configured)) > 1:
        raise ModelSelectionBlocked("Claude invocation contains conflicting environment model overrides")
    pin = configured[0] if configured else None
    requested = explicit or pin
    if requested:
        validate_claude_model_override(requested, args=args)
        if explicit is None and ("-p" in args or "--print" in args):
            return requested
    return None


# Compatibility surfaces for older readers. They deliberately expose no fixed
# provider tiers/classes; selection now comes only from live owner metadata.
_CLAUDE_TIER_ORDER: tuple[str, ...] = ()


def _claude_opus_classes() -> set[str]:
    return {value.strip() for value in os.environ.get("LIMEN_CLAUDE_OPUS_CLASSES", "").split(",") if value.strip()}


def _claude_fable_classes() -> set[str]:
    return set()


def _resolve_claude_model(_tier: str, *, fable_authorized: bool = False) -> str | None:
    del fable_authorized
    return None


def _guard_fable_model_pin(
    model: str | None,
    execution_profile_value: Any = None,
) -> str | None:
    if not model:
        return None
    return validate_claude_model_override(
        model,
        execution_profile_value=execution_profile_value,
    )


def _claude_fable_acceptance_present(execution_profile_value: Any = None) -> bool:
    authority, _reason = _fable_authorization_status(execution_profile_value)
    return authority is not None


def main(argv: list[str] | None = None) -> int:
    import sys

    try:
        model = model_for_argv(list(argv if argv is not None else sys.argv[1:]))
    except ModelSelectionBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 78
    if model:
        print(model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
