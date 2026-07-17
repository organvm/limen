#!/usr/bin/env python3
"""Validate and record bounded Fable planning-role acceptances.

Fable is an opaque, provider-supplied planning role for a small set of high-leverage jobs.
This tool is the written acceptance command required before a Fable run starts. It records only metadata:
category, percent of the weekly allotment, sources by path/URL, and verification commands.
Do not put raw private prompts, secrets, or personal data in the receipt.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
DEFAULT_RECEIPTS = ROOT / "logs" / "fable-acceptance"


def _load_contract() -> Any:
    path = ROOT / "cli" / "src" / "limen" / "fable_contract.py"
    if not path.exists():
        path = Path(__file__).resolve().parents[1] / "cli" / "src" / "limen" / "fable_contract.py"
    spec = importlib.util.spec_from_file_location("_limen_fable_contract_allotment", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Fable contract validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRACT = _load_contract()

PLAN: dict[str, dict[str, Any]] = {
    "substrate": {
        "cap_percent": 15,
        "purpose": "Fable operating substrate audit and patch plan",
    },
    "prompt-corpus": {
        "cap_percent": 10,
        "purpose": "redacted prompt-corpus and session-lifecycle compression",
    },
    "governance": {
        "cap_percent": 10,
        "purpose": "canon/governance synthesis with validator-backed policy",
    },
    "adversarial-review": {
        "cap_percent": 5,
        "purpose": "skeptical review of recent high-impact changes",
    },
    "reserve": {
        "cap_percent": 10,
        "purpose": "single bounded follow-up repair exposed by a first-pass run",
        "reserve": True,
    },
}

DELIBERATE_CAP = 40
HARD_CAP = 50
SENSITIVE_RE = re.compile(
    r"\b(secret|token|credential|password|raw transcript|private personal data)\b",
    re.IGNORECASE,
)


class PolicyError(ValueError):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _week_key(moment: dt.datetime) -> str:
    monday = (moment - dt.timedelta(days=moment.weekday())).date()
    return monday.isoformat()


def _slug(value: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    if not out:
        raise PolicyError("slug must contain at least one alphanumeric character")
    return out[:80]


def _load_receipts(receipts_dir: Path, week: str) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    if not receipts_dir.exists():
        return receipts
    for path in sorted(receipts_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("week") == week:
            receipts.append(data)
    return receipts


def _spent(receipts: list[dict[str, Any]]) -> tuple[float, float]:
    deliberate = 0.0
    total = 0.0
    for receipt in receipts:
        percent = float(receipt.get("percent", 0))
        total += percent
        if receipt.get("category") != "reserve":
            deliberate += percent
    return deliberate, total


def _validate_sources(sources: list[str], redacted_packets: list[str]) -> None:
    text = "\n".join(sources + redacted_packets)
    if SENSITIVE_RE.search(text):
        raise PolicyError("receipt text mentions sensitive raw material; use source-indexed redacted packets")
    if not sources and not redacted_packets:
        raise PolicyError("at least one --source or --redacted-packet is required")


def _validate_receipt(
    receipt: dict[str, Any],
    *,
    receipts_dir: Path | None = None,
    include_existing: bool = True,
) -> None:
    try:
        CONTRACT.validate_acceptance_receipt(receipt, require_current_week=False)
    except CONTRACT.ContractError as exc:
        if str(exc) == "acceptance-reserve-locked":
            raise PolicyError("reserve spend requires --reserve-unlock") from exc
        raise PolicyError(str(exc)) from exc

    category = str(receipt.get("category", ""))
    if category not in PLAN:
        raise PolicyError(f"unknown category {category!r}; choose one of {', '.join(sorted(PLAN))}")

    try:
        percent = float(receipt.get("percent"))
    except (TypeError, ValueError):
        raise PolicyError("percent must be numeric") from None
    if percent <= 0:
        raise PolicyError("percent must be positive")
    cap = float(PLAN[category]["cap_percent"])
    if percent > cap:
        raise PolicyError(f"{category} request is {percent:g}%, above category cap {cap:g}%")

    if category == "reserve" and not receipt.get("reserve_unlocked"):
        raise PolicyError("reserve spend requires --reserve-unlock")

    verifications = receipt.get("verification") or []
    if not verifications:
        raise PolicyError("at least one --verification command is required")
    if any(not isinstance(v, str) or not v.strip() for v in verifications):
        raise PolicyError("verification commands must be non-empty strings")

    _validate_sources(
        [str(s) for s in (receipt.get("sources") or [])],
        [str(s) for s in (receipt.get("redacted_packets") or [])],
    )

    if include_existing and receipts_dir is not None:
        week = str(receipt.get("week"))
        existing = _load_receipts(receipts_dir, week)
        deliberate, total = _spent(existing)
        category_total = sum(float(r.get("percent", 0)) for r in existing if r.get("category") == category)
        if category_total + percent > cap:
            raise PolicyError(
                f"{category} weekly spend would be {category_total + percent:g}%, above category cap {cap:g}%"
            )
        if category == "reserve":
            total += percent
        else:
            deliberate += percent
            total += percent
        if deliberate > DELIBERATE_CAP:
            raise PolicyError(f"deliberate Fable spend would be {deliberate:g}%, above {DELIBERATE_CAP}%")
        if total > HARD_CAP:
            raise PolicyError(f"total Fable spend would be {total:g}%, above {HARD_CAP}%")


def _receipt_from_args(args: argparse.Namespace) -> dict[str, Any]:
    created = _now()
    slug = _slug(args.slug)
    receipt = {
        "schema": "limen.fable_acceptance.v1",
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "week": _week_key(created),
        "category": args.category,
        "percent": float(args.percent),
        "slug": slug,
        "why": args.why,
        "sources": args.source or [],
        "redacted_packets": args.redacted_packet or [],
        "verification": args.verification or [],
        "reserve_unlocked": bool(getattr(args, "reserve_unlock", False)),
        "mode": "plan-only",
        "deliverable": "continuation-capsule",
        "builder_handoff": CONTRACT.builder_handoff(),
        "motion_receipt_deadline_seconds": CONTRACT.MOTION_RECEIPT_DEADLINE_SECONDS,
        "acceptance_command": " ".join(sys.argv),
    }
    return receipt


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def cmd_plan(_: argparse.Namespace) -> int:
    print(json.dumps({"plan": PLAN, "deliberate_cap": DELIBERATE_CAP, "hard_cap": HARD_CAP}, indent=2))
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    receipts_dir = Path(args.receipts_dir)
    receipt = _receipt_from_args(args)
    _validate_receipt(receipt, receipts_dir=receipts_dir, include_existing=not args.no_existing)

    stamp = receipt["created_at"].replace(":", "").replace("-", "")
    out = Path(args.out) if args.out else receipts_dir / f"{stamp}-{receipt['slug']}.json"
    _atomic_json_write(out, receipt)
    print(json.dumps({"ok": True, "receipt": str(out)}, indent=2))
    print(f"export LIMEN_FABLE_ACCEPTANCE={out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    receipt = json.loads(Path(args.receipt).read_text())
    _validate_receipt(receipt, receipts_dir=Path(args.receipts_dir), include_existing=False)
    print(json.dumps({"ok": True, "receipt": str(args.receipt)}, indent=2))
    return 0


# ── Live weekly Fable balance (the runtime backstop meter) ───────────────────────────────
# The receipt ledger above records INTENDED spend. Authorization also needs an ACTUAL current-week
# observation. A direct owner adapter may publish a fresh role-bound used-percent receipt. The
# transcript fallback counts only usage rows explicitly tagged execution_role=fable-planner; it
# never infers capability from a provider model name. Any unbound current-week usage makes that
# fallback dark, and a dark meter cannot authorize a launch.

_BALANCE_REFRESH_SECONDS = 60
_USAGE_METER_SCHEMA = "limen.fable_usage_meter.v1"


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _transcripts_dir() -> Path | None:
    raw = os.environ.get("LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR")
    return Path(raw).expanduser() if raw else None


def _iso_ts(value: str) -> float | None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


def _owner_used_pct() -> float | None:
    """Read one fresh owner-adapter used-percent receipt, never a bare cached number."""

    raw = os.environ.get("LIMEN_FABLE_USAGE_METER_PATH")
    if not raw:
        return None
    p = Path(raw).expanduser()
    try:
        d = json.loads(p.read_text())
    except Exception:
        return None
    if (
        d.get("schema") != _USAGE_METER_SCHEMA
        or d.get("execution_role") != "fable-planner"
        or d.get("meter_ready") is not True
        or d.get("week") != _week_key(_now())
    ):
        return None
    observed = _iso_ts(str(d.get("observed_at") or ""))
    if observed is None:
        return None
    try:
        max_age = int(
            os.environ.get(
                "LIMEN_FABLE_BALANCE_MAX_AGE_SECONDS",
                str(CONTRACT.DEFAULT_BALANCE_MAX_AGE_SECONDS),
            )
        )
    except ValueError:
        return None
    age = _now().timestamp() - observed
    if max_age <= 0 or age > max_age or age < -CONTRACT.FUTURE_SKEW_SECONDS:
        return None
    for key in ("weekly_used_percent", "used_percent"):
        v = d.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)) and v >= 0:
            return float(v)
    return None


def _execution_role(value: dict[str, Any], message: dict[str, Any]) -> str:
    containers = (
        value,
        message,
        value.get("metadata"),
        message.get("metadata"),
        value.get("execution_profile"),
        message.get("execution_profile"),
    )
    for container in containers:
        if not isinstance(container, dict):
            continue
        role = container.get("execution_role") or container.get("role")
        if isinstance(role, str) and role:
            return role
    return ""


def _fable_weekly_tokens(root: Path | None) -> tuple[int, int]:
    """Return role-bound tokens and the number of unbound current-week usage rows."""

    import glob

    if root is None or not root.is_dir():
        return 0, 0
    now_dt = _now()
    week_start = (now_dt - dt.timedelta(days=now_dt.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    now = now_dt.timestamp()
    week_start_ts = week_start.timestamp()
    total = 0
    unbound = 0
    try:
        for f in glob.glob(str(root / "**" / "*.jsonl"), recursive=True):
            try:
                if os.path.getmtime(f) < week_start_ts:
                    continue
            except OSError:
                continue
            with open(f, errors="ignore") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    msg = o.get("message") or {}
                    ts = _iso_ts(o.get("timestamp", "")) if o.get("timestamp") else None
                    if ts is None:
                        unbound += 1
                        continue
                    if ts < week_start_ts:
                        continue
                    if ts > now + CONTRACT.FUTURE_SKEW_SECONDS:
                        unbound += 1
                        continue
                    u = msg.get("usage") or o.get("usage")
                    if not isinstance(u, dict):
                        continue
                    billable = (
                        int(u.get("input_tokens", 0) or 0)
                        + int(u.get("output_tokens", 0) or 0)
                        + int(u.get("cache_creation_input_tokens", 0) or 0)
                    )
                    if billable <= 0:
                        continue
                    if _execution_role(o, msg) == "fable-planner":
                        total += billable
                    else:
                        unbound += 1
    except Exception:
        return total, max(unbound, 1)
    return total, unbound


def compute_balance() -> dict[str, Any]:
    """Compute an owner-evidenced balance without inventing a weekly denominator."""

    observed = _now()
    week = _week_key(observed)
    pct = _owner_used_pct()
    if pct is not None and (not math.isfinite(pct) or pct < 0):
        pct = None
    transcripts_root = _transcripts_dir()
    spent_tokens, unbound_usage_rows = _fable_weekly_tokens(transcripts_root)
    source = "owner-used-percent"
    denominator_tokens: int | None = None
    meter_ready = pct is not None
    measurement: dict[str, Any] = {
        "method": "owner-used-percent",
        "owner_observed_pct": float(pct) if pct is not None else None,
    }
    if pct is None:
        denominator_tokens = _positive_int(os.environ.get("LIMEN_FABLE_WEEKLY_TOKENS"))
        source = "transcript-token-sum"
        meter_ready = (
            transcripts_root is not None
            and transcripts_root.is_dir()
            and denominator_tokens is not None
            and unbound_usage_rows == 0
        )
        pct = round(100.0 * spent_tokens / denominator_tokens, 2) if meter_ready and denominator_tokens else None
        measurement = {
            "method": "token-ratio",
            "numerator_tokens": spent_tokens,
            "denominator_tokens": denominator_tokens,
            "unbound_usage_rows": unbound_usage_rows,
            "role_binding": "execution_role:fable-planner",
        }
    return {
        "schema": CONTRACT.BALANCE_SCHEMA,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "week": week,
        "spent_tokens": spent_tokens,
        "spent_pct": float(pct) if pct is not None else None,
        "deliberate_cap": DELIBERATE_CAP,
        "hard_cap": HARD_CAP,
        "over_cap": float(pct) >= HARD_CAP if pct is not None else None,
        "source": source,
        "meter_ready": meter_ready,
        "measurement": measurement,
    }


def cmd_balance(args: argparse.Namespace) -> int:
    balance = compute_balance()
    out = Path(args.out) if args.out else ROOT / "logs" / "fable-allotment.json"
    try:
        prior = json.loads(out.read_text())
        prior_observed = _iso_ts(str(prior.get("observed_at") or ""))
        same = {key: value for key, value in prior.items() if key != "observed_at"} == {
            key: value for key, value in balance.items() if key != "observed_at"
        }
        if same and prior_observed is not None and _now().timestamp() - prior_observed < _BALANCE_REFRESH_SECONDS:
            balance["observed_at"] = prior["observed_at"]
    except Exception:
        pass
    if not args.no_write:
        _atomic_json_write(out, balance)
    print(json.dumps(balance, indent=2, sort_keys=True))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    receipts_dir = Path(args.receipts_dir)
    week = args.week or _week_key(_now())
    receipts = _load_receipts(receipts_dir, week)
    deliberate, total = _spent(receipts)
    category_spend: dict[str, float] = {key: 0.0 for key in PLAN}
    errors: list[str] = []
    for receipt in receipts:
        try:
            _validate_receipt(receipt, include_existing=False)
        except PolicyError as exc:
            errors.append(f"{receipt.get('slug', '<unknown>')}: {exc}")
        category = str(receipt.get("category", ""))
        if category in category_spend:
            category_spend[category] += float(receipt.get("percent", 0))
    for category, spent in sorted(category_spend.items()):
        cap = float(PLAN[category]["cap_percent"])
        if spent > cap:
            errors.append(f"{category} spend {spent:g}% exceeds category cap {cap:g}%")
    if deliberate > DELIBERATE_CAP:
        errors.append(f"deliberate spend {deliberate:g}% exceeds {DELIBERATE_CAP}%")
    if total > HARD_CAP:
        errors.append(f"total spend {total:g}% exceeds {HARD_CAP}%")
    report = {
        "ok": not errors,
        "week": week,
        "receipt_count": len(receipts),
        "deliberate_percent": deliberate,
        "total_percent": total,
        "category_percent": category_spend,
        "errors": errors,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("plan").set_defaults(func=cmd_plan)

    accept = sub.add_parser("accept")
    accept.add_argument("--category", required=True, choices=sorted(PLAN))
    accept.add_argument("--percent", required=True, type=float)
    accept.add_argument("--slug", required=True)
    accept.add_argument("--why", required=True)
    accept.add_argument("--source", action="append", default=[])
    accept.add_argument("--redacted-packet", action="append", default=[])
    accept.add_argument("--verification", action="append", default=[])
    accept.add_argument("--reserve-unlock", action="store_true")
    accept.add_argument("--receipts-dir", default=str(DEFAULT_RECEIPTS))
    accept.add_argument("--out")
    accept.add_argument("--no-existing", action="store_true")
    accept.set_defaults(func=cmd_accept)

    validate = sub.add_parser("validate")
    validate.add_argument("receipt")
    validate.add_argument("--receipts-dir", default=str(DEFAULT_RECEIPTS))
    validate.set_defaults(func=cmd_validate)

    audit = sub.add_parser("audit")
    audit.add_argument("--receipts-dir", default=str(DEFAULT_RECEIPTS))
    audit.add_argument("--week")
    audit.set_defaults(func=cmd_audit)

    balance = sub.add_parser("balance")
    balance.add_argument("--out")
    balance.add_argument("--no-write", action="store_true")
    balance.set_defaults(func=cmd_balance)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PolicyError as exc:
        print(f"fable-allotment: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
