"""Dynamic provider selection from task needs and live capability catalogs.

Limen owns safety, budget, and the requested execution shape. Providers own their
changing model catalogs. Model IDs are runtime outputs and never appear as defaults.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Any, Iterable, Sequence, get_type_hints
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _as_number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _optional_nonnegative_number(value: object) -> float | None:
    """Preserve unknown provider metadata instead of coercing it to free."""

    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


@dataclass(frozen=True)
class ExecutionProfile:
    """A provider-neutral request that can evolve without adding model names."""

    requested_hint: str | None
    reasoning_depth: float
    cost_pressure: float
    latency_pressure: float
    min_context: int
    min_output: int
    tools_required: bool
    attachments_required: bool
    planning_only: bool
    build_allowed: bool
    verification_strength: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def _numeric_profile_overrides(labels: Sequence[str]) -> dict[str, float | int]:
    """Read typed numeric constraints without maintaining a label-name table.

    The dataclass is the schema: adding another numeric profile dimension makes it
    label-addressable automatically as ``profile:<field>:<value>``. Float profile
    dimensions are normalized to ``0..1``; integer dimensions are positive minima.
    """

    hints = get_type_hints(ExecutionProfile)
    overrides: dict[str, float | int] = {}
    for label in labels:
        prefix, separator, raw = label.rpartition(":")
        if not separator or not prefix.startswith("profile:"):
            continue
        field_name = prefix.removeprefix("profile:").replace("-", "_")
        field_type = hints.get(field_name)
        if field_type not in {float, int}:
            continue
        value = _as_number(raw, math.nan)
        if not math.isfinite(value):
            continue
        overrides[field_name] = max(1, int(value)) if field_type is int else _clamp(value)
    return overrides


def execution_profile_for(task: object | None) -> ExecutionProfile:
    """Derive a request profile from the task's current evidence.

    ``tier:*`` is opaque receipt/prompt context, never a routing instruction. New
    profiles derive from quantitative task shape and generic numeric constraints.
    Unknown hints survive without requiring a code change or changing selection.
    """

    if task is None:
        return ExecutionProfile(None, 0.5, 0.5, 0.5, 8192, 2048, True, False, False, True, 0.5)

    labels = [str(item).strip().lower() for item in (getattr(task, "labels", None) or [])]
    requested_hint = next((label.split(":", 1)[1] for label in labels if label.startswith("tier:")), None)
    planning_only = "mode:plan-only" in labels
    attachments_required = "capability:attachments" in labels
    overrides = _numeric_profile_overrides(labels)

    priority = str(getattr(task, "priority", "medium") or "medium").lower()
    priority_weight = {"critical": 1.0, "high": 0.75, "medium": 0.45, "low": 0.2}.get(priority, 0.1)
    budget = max(1, int(getattr(task, "budget_cost", 1) or 1))
    dependencies = len(getattr(task, "depends_on", None) or [])
    text_size = sum(len(str(getattr(task, field, "") or "")) for field in ("title", "description", "context"))
    attempts = 0
    for entry in getattr(task, "dispatch_log", None) or []:
        status = str(getattr(entry, "status", "") or "")
        route_to = str(getattr(entry, "route_to", "") or "")
        if status in {"failed", "failed_blocked"} or route_to or "->" in status:
            attempts += 1

    complexity = _clamp(
        0.15
        + priority_weight * 0.25
        + min(1.0, dependencies / 4) * 0.15
        + min(1.0, text_size / 8000) * 0.2
        + min(1.0, attempts / 3) * 0.25
    )
    complexity = float(overrides.get("reasoning_depth", complexity))

    # Estimate prompt room from the actual packet, then round to a power of two.
    required_tokens = max(4096, text_size * 2 + dependencies * 1024)
    min_context = 1 << max(13, (required_tokens - 1).bit_length())
    min_output = max(2048, min(32768, min_context // 4))
    min_context = max(min_context, int(overrides.get("min_context", 0)))
    min_output = max(min_output, int(overrides.get("min_output", 0)))
    cost_pressure = float(overrides.get("cost_pressure", _clamp(1.0 / math.sqrt(float(budget)))))
    latency_pressure = float(overrides.get("latency_pressure", priority_weight))
    verification_strength = float(overrides.get("verification_strength", _clamp(0.4 + complexity * 0.6)))

    return ExecutionProfile(
        requested_hint=requested_hint,
        reasoning_depth=complexity,
        cost_pressure=cost_pressure,
        latency_pressure=latency_pressure,
        min_context=min_context,
        min_output=min_output,
        tools_required=True,
        attachments_required=attachments_required,
        planning_only=planning_only,
        build_allowed=not planning_only,
        verification_strength=verification_strength,
    )


def effective_profile(profile: ExecutionProfile, *, plan_accepted: bool) -> ExecutionProfile:
    """Without current plan acceptance, request maximally verified executable work."""

    if profile.planning_only and not plan_accepted:
        return replace(
            profile,
            reasoning_depth=1.0,
            planning_only=False,
            build_allowed=True,
            verification_strength=1.0,
        )
    return profile


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    active: bool
    text_input: bool
    text_output: bool
    toolcall: bool
    reasoning: bool
    attachment: bool
    context_limit: int
    output_limit: int
    input_cost: float | None
    output_cost: float | None
    variant_count: int
    release_ordinal: int

    @property
    def zero_cost(self) -> bool:
        return self.price_known and self.input_cost == 0 and self.output_cost == 0

    @property
    def price_known(self) -> bool:
        return self.input_cost is not None and self.output_cost is not None

    def satisfies(self, profile: ExecutionProfile) -> bool:
        return (
            self.active
            and self.text_input
            and self.text_output
            and (self.toolcall or not profile.tools_required)
            and (self.attachment or not profile.attachments_required)
            and self.context_limit >= profile.min_context
            and self.output_limit >= profile.min_output
        )


def _release_ordinal(value: object) -> int:
    try:
        return date.fromisoformat(str(value)).toordinal()
    except (TypeError, ValueError):
        return 0


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _capability_from_payload(payload: dict[str, Any], reported_id: str = "") -> ModelCapability | None:
    provider = str(payload.get("providerID") or "").strip()
    local_id = str(payload.get("id") or "").strip()
    model_id = reported_id.strip() or (f"{provider}/{local_id}" if provider and local_id else local_id)
    if not model_id:
        return None
    capabilities = _dict_value(payload, "capabilities")
    input_caps = _dict_value(capabilities, "input")
    output_caps = _dict_value(capabilities, "output")
    limits = _dict_value(payload, "limit")
    costs = _dict_value(payload, "cost")
    variants = _dict_value(payload, "variants")
    status = str(payload.get("status") or "active").strip().lower()
    return ModelCapability(
        model_id=model_id,
        active=status in {"active", "available", "ready"},
        text_input=bool(input_caps.get("text", True)),
        text_output=bool(output_caps.get("text", True)),
        toolcall=bool(capabilities.get("toolcall")),
        reasoning=bool(capabilities.get("reasoning")),
        attachment=bool(capabilities.get("attachment")),
        context_limit=max(0, int(_as_number(limits.get("context")))),
        output_limit=max(0, int(_as_number(limits.get("output")))),
        input_cost=_optional_nonnegative_number(costs.get("input")),
        output_cost=_optional_nonnegative_number(costs.get("output")),
        variant_count=len(variants),
        release_ordinal=_release_ordinal(payload.get("release_date")),
    )


def parse_opencode_catalog(output: str) -> list[ModelCapability]:
    """Parse ``opencode models --verbose`` alternating IDs and JSON objects."""

    decoder = json.JSONDecoder()
    cursor = 0
    models: list[ModelCapability] = []
    while True:
        start = output.find("{", cursor)
        if start < 0:
            break
        try:
            payload, consumed = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        prefix = output[cursor:start]
        reported = next((line.strip() for line in reversed(prefix.splitlines()) if "/" in line), "")
        if isinstance(payload, dict):
            model = _capability_from_payload(payload, reported)
            if model is not None:
                models.append(model)
        cursor = start + consumed
    return list({model.model_id: model for model in models}.values())


def discover_opencode_models(binary: str = "opencode", *, timeout: int = 30) -> list[ModelCapability]:
    try:
        result = subprocess.run(
            [binary, "models", "--verbose"],
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_opencode_catalog(result.stdout) if result.returncode == 0 else []


_MODEL_ID_FIELDS = ("slug", "id", "model_id", "modelId", "name", "baseModelId")
_MODEL_COLLECTION_FIELDS = ("models", "data", "availableModels", "items")


def parse_model_id_catalog(output: str) -> list[str]:
    """Extract exact provider-reported identifiers from a JSON model catalog.

    Identifier-only catalogs are sufficient to validate a human override, but not
    sufficient to infer capabilities or rank a default. Callers therefore leave
    selection to provider Auto unless richer metadata is available.
    """

    text = _ANSI.sub("", output).strip()
    if not text:
        return []
    try:
        roots: list[object] = [json.loads(text)]
    except json.JSONDecodeError:
        roots = []
        for line in text.splitlines():
            try:
                roots.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    identifiers: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        for field in _MODEL_ID_FIELDS:
            reported = value.get(field)
            if isinstance(reported, str) and reported.strip():
                identifiers.add(reported.strip())
        for field in _MODEL_COLLECTION_FIELDS:
            nested = value.get(field)
            if isinstance(nested, (dict, list)):
                visit(nested)

    for root in roots:
        visit(root)
    return sorted(identifiers)


def discover_model_ids(command: Sequence[str], *, timeout: int = 30) -> list[str]:
    """Run a provider-owned catalog command and return its exact live IDs."""

    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_model_id_catalog(result.stdout) if result.returncode == 0 else []


def discover_codex_models(binary: str = "codex", *, timeout: int = 30) -> list[str]:
    """Read the current Codex CLI catalog without selecting a model."""

    return discover_model_ids([binary, "debug", "models"], timeout=timeout)


def discover_anthropic_models(client: object, *, max_pages: int = 100) -> list[str]:
    """Read exact IDs from Anthropic's non-executing, paginated model catalog.

    The API catalog is identifier-only for Limen's purposes: it may validate an
    explicit operator override, but it is not treated as capability metadata and
    cannot select a default. Missing, malformed, cyclic, or failing pagination
    returns an empty catalog so callers fail closed on an explicit override.
    """

    models = getattr(client, "models", None)
    list_models = getattr(models, "list", None)
    if not callable(list_models):
        return []
    try:
        try:
            page = list_models(limit=1000)
        except TypeError:
            # Small fixture clients and older SDKs may not accept ``limit``.
            page = list_models()
    except Exception:
        return []

    identifiers: set[str] = set()
    seen_pages: set[int] = set()
    for _ in range(max(1, max_pages)):
        identity = id(page)
        if identity in seen_pages:
            return []
        seen_pages.add(identity)

        rows = getattr(page, "data", None)
        if rows is None and isinstance(page, dict):
            rows = page.get("data")
        if rows is None and isinstance(page, (list, tuple)):
            rows = page
        try:
            iterator = iter(rows or ())
        except TypeError:
            return []
        for row in iterator:
            identifier = row.get("id") if isinstance(row, dict) else getattr(row, "id", None)
            if isinstance(identifier, str) and identifier.strip():
                identifiers.add(identifier.strip())

        has_next = getattr(page, "has_next_page", None)
        get_next = getattr(page, "get_next_page", None)
        if not callable(has_next):
            return sorted(identifiers)
        try:
            if not has_next():
                return sorted(identifiers)
            if not callable(get_next):
                return []
            page = get_next()
        except Exception:
            return []
    return []


def discover_gemini_models(*, api_key: str | None = None, timeout: int = 30) -> list[str]:
    """Read Gemini's live API catalog when provider credentials are reachable."""

    key = (
        api_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY")
    )
    if not key:
        return []
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    identifiers: set[str] = set()
    page_token = ""
    seen_tokens: set[str] = set()
    for _page in range(100):
        url = base_url
        if page_token:
            url += "?" + urlparse.urlencode({"pageToken": page_token})
        request = urlrequest.Request(url, headers={"x-goog-api-key": key})
        try:
            with urlrequest.urlopen(request, timeout=max(1, timeout)) as response:
                payload = response.read().decode("utf-8")
            decoded = json.loads(payload)
        except (OSError, TimeoutError, UnicodeError, ValueError, urlerror.URLError):
            return []
        if not isinstance(decoded, dict):
            return []
        identifiers.update(parse_model_id_catalog(payload))
        raw_next = decoded.get("nextPageToken")
        next_token = raw_next.strip() if isinstance(raw_next, str) else ""
        if not next_token:
            return sorted(identifiers)
        if next_token in seen_tokens:
            return []
        seen_tokens.add(next_token)
        page_token = next_token
    return []


def validate_model_override(catalog: Iterable[str], override: str | None) -> str | None:
    """Accept an explicit override only when the exact ID is live now."""

    available = {str(item).strip() for item in catalog if str(item).strip()}
    candidate = override.strip() if override else ""
    return candidate if candidate and candidate in available else None


def model_id_catalog_hash(catalog: Iterable[str]) -> str:
    """Stable receipt fingerprint independent of provider response order."""

    identifiers = sorted({str(item).strip() for item in catalog if str(item).strip()})
    return hashlib.sha256(json.dumps(identifiers, separators=(",", ":")).encode()).hexdigest()


def _model_score(model: ModelCapability, profile: ExecutionProfile) -> tuple[float, str]:
    if not model.price_known:
        raise ValueError("unknown provider price cannot be ranked")
    assert model.input_cost is not None and model.output_cost is not None
    cost = model.input_cost + model.output_cost
    context_headroom = math.log2(max(1, model.context_limit / max(1, profile.min_context)))
    output_headroom = math.log2(max(1, model.output_limit / max(1, profile.min_output)))
    score = (
        (1.0 if model.reasoning else 0.0) * profile.reasoning_depth * 8.0
        + min(4.0, model.variant_count / 2) * profile.reasoning_depth
        + min(4.0, context_headroom) * 0.8
        + min(4.0, output_headroom) * 0.6
        + (5.0 if model.zero_cost else -min(5.0, cost)) * profile.cost_pressure
        + (model.release_ordinal / 1_000_000)
    )
    return score, model.model_id


def select_opencode_model(models: Iterable[ModelCapability], profile: ExecutionProfile) -> ModelCapability | None:
    eligible = [model for model in models if model.satisfies(profile)]
    if any(not model.price_known for model in eligible):
        # Auto owns the choice when the live catalog cannot support an honest
        # cost comparison. Never promote an unknown price as zero-cost.
        return None
    return max(eligible, key=lambda model: _model_score(model, profile)) if eligible else None


def catalog_hash(models: Iterable[ModelCapability]) -> str:
    rows = [asdict(model) for model in sorted(models, key=lambda item: item.model_id)]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_warp_catalog(output: str) -> list[str]:
    text = _ANSI.sub("", output).strip()
    if not text:
        return []
    payloads: Sequence[object]
    try:
        decoded = json.loads(text)
        payloads = decoded if isinstance(decoded, list) else [decoded]
    except json.JSONDecodeError:
        payloads = []
        for line in text.splitlines():
            try:
                payloads.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return sorted(
        {
            str(item.get("id") or "").strip()
            for item in payloads
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
    )


def validate_warp_override(catalog: Iterable[str], override: str | None) -> str | None:
    available = {str(item).strip() for item in catalog if str(item).strip()}
    return override if override and override in available else None


def discover_warp_override(binary: str = "oz", *, override: str | None, timeout: int = 30) -> str | None:
    if not override:
        return None
    try:
        result = subprocess.run(
            [binary, "model", "list", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return validate_warp_override(parse_warp_catalog(result.stdout), override)


_PAID_SERVICE_RISK = re.compile(
    r"\b(credential|secret|api[ _-]?key|password|personal[ _-]?data|pii|"
    r"irreversible|delete|wipe|purge|paid[ _-]?overage|public[ _-]?identity|"
    r"claim[ _-]?(?:account|profile))\b",
    re.IGNORECASE,
)


def paid_service_block_reason(task: object) -> str | None:
    """Reject human-gated risk before a prompt reaches Warp/Oz."""

    labels = [str(item) for item in (getattr(task, "labels", None) or [])]
    if any(label.strip().lower() == "needs-human" for label in labels):
        return "task is human-gated"
    public_fields = " ".join([str(getattr(task, "title", "") or ""), str(getattr(task, "type", "") or ""), *labels])
    match = _PAID_SERVICE_RISK.search(public_fields)
    return f"paid-service safety gate matched {match.group(1).lower()}" if match else None
