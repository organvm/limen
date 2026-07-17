"""Validated, provider-neutral contract for a conducted workstream.

The contract is copied into each continuation capsule so the launch surface can
admit a session without depending on the Limen checkout that rendered it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = "limen.workstream.contract.v1"
DEFAULT_RUNWAY = "1d"
MIN_RUNWAY_SECONDS = 15 * 60
MAX_RUNWAY_SECONDS = 30 * 24 * 60 * 60
_DURATION_RE = re.compile(r"^([1-9][0-9]*)([mhd])$")

AUTHORIZATION = {
    "mode": "full_non_destructive",
    "approval_mode": "never",
    "sandbox": "workspace-write",
    "reversible_in_scope": "proceed_without_confirmation",
    "retained_gates": [
        "destructive",
        "credential",
        "paid_spend",
        "public_send",
        "runtime_or_host_mutation",
    ],
}

CONDUCTOR = {
    "mode": "route_bounded_packets",
    "lane_selection": "derive_from_live_capabilities",
    "provider_and_model": "provider_neutral",
    "boundary_rule": "recheck_remaining_runway_before_each_packet",
    "expiry_rule": "stop_or_emit_successor_before_zero",
}


class ContractError(ValueError):
    """The workstream contract cannot be trusted."""


class RunwayExpired(ContractError):
    """No new session may be admitted at or after the deadline."""


def parse_runway(raw: str) -> tuple[str, int]:
    value = str(raw or "").strip().lower()
    match = _DURATION_RE.fullmatch(value)
    if not match:
        raise ContractError("runway must be a bounded duration such as 90m, 8h, or 7d")
    count = int(match.group(1))
    multiplier = {"m": 60, "h": 3600, "d": 86400}[match.group(2)]
    seconds = count * multiplier
    if not MIN_RUNWAY_SECONDS <= seconds <= MAX_RUNWAY_SECONDS:
        raise ContractError(
            f"runway must be between {MIN_RUNWAY_SECONDS // 60}m and {MAX_RUNWAY_SECONDS // 86400}d"
        )
    return value, seconds


def new_contract(runway: str = DEFAULT_RUNWAY) -> dict[str, Any]:
    normalized, seconds = parse_runway(runway)
    return {
        "schema": SCHEMA,
        "runway": {
            "requested": normalized,
            "duration_seconds": seconds,
            "started_at": None,
            "started_epoch": None,
            "deadline_at": None,
            "deadline_epoch": None,
        },
        "authorization": dict(AUTHORIZATION),
        "conductor": dict(CONDUCTOR),
    }


def validate_contract(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema", "runway", "authorization", "conductor"}:
        raise ContractError("workstream contract has unknown or missing top-level fields")
    if value.get("schema") != SCHEMA:
        raise ContractError("workstream contract schema is unsupported")
    runway = value.get("runway")
    if not isinstance(runway, dict) or set(runway) != {
        "requested",
        "duration_seconds",
        "started_at",
        "started_epoch",
        "deadline_at",
        "deadline_epoch",
    }:
        raise ContractError("workstream runway has unknown or missing fields")
    requested, seconds = parse_runway(str(runway.get("requested") or ""))
    raw_seconds = runway.get("duration_seconds")
    if isinstance(raw_seconds, bool) or not isinstance(raw_seconds, int) or raw_seconds != seconds:
        raise ContractError("workstream runway duration does not match its requested value")

    started_epoch = runway.get("started_epoch")
    deadline_epoch = runway.get("deadline_epoch")
    started_at = runway.get("started_at")
    deadline_at = runway.get("deadline_at")
    if started_epoch is None:
        if any(item is not None for item in (deadline_epoch, started_at, deadline_at)):
            raise ContractError("unstarted workstream runway carries partial timing state")
    else:
        if (
            isinstance(started_epoch, bool)
            or not isinstance(started_epoch, int)
            or isinstance(deadline_epoch, bool)
            or not isinstance(deadline_epoch, int)
            or not isinstance(started_at, str)
            or not isinstance(deadline_at, str)
            or deadline_epoch != started_epoch + seconds
            or started_at != _iso(started_epoch)
            or deadline_at != _iso(deadline_epoch)
        ):
            raise ContractError("started workstream runway timing state is invalid")

    if value.get("authorization") != AUTHORIZATION:
        raise ContractError("workstream authorization contract is invalid")
    if value.get("conductor") != CONDUCTOR:
        raise ContractError("workstream conductor contract is invalid")
    return value


def validate_packet_contract(value: object) -> dict[str, Any]:
    """Validate the immutable workstream subset carried by a dispatch packet."""

    if not isinstance(value, dict) or set(value) != {"schema", "runway", "authorization", "conductor"}:
        raise ContractError("workstream packet contract has unknown or missing top-level fields")
    if value.get("schema") != SCHEMA:
        raise ContractError("workstream packet contract schema is unsupported")
    runway = value.get("runway")
    if not isinstance(runway, dict) or set(runway) != {
        "requested",
        "duration_seconds",
        "started_epoch",
        "deadline_epoch",
    }:
        raise ContractError("workstream packet runway has unknown or missing fields")
    _requested, seconds = parse_runway(str(runway.get("requested") or ""))
    raw_seconds = runway.get("duration_seconds")
    if isinstance(raw_seconds, bool) or not isinstance(raw_seconds, int) or raw_seconds != seconds:
        raise ContractError("workstream packet runway duration does not match its requested value")
    started_epoch = runway.get("started_epoch")
    deadline_epoch = runway.get("deadline_epoch")
    if (
        isinstance(started_epoch, bool)
        or not isinstance(started_epoch, int)
        or started_epoch < 0
        or isinstance(deadline_epoch, bool)
        or not isinstance(deadline_epoch, int)
        or deadline_epoch != started_epoch + seconds
    ):
        raise ContractError("workstream packet timing does not match its admitted duration")
    if value.get("authorization") != AUTHORIZATION:
        raise ContractError("workstream packet authorization contract is invalid")
    if value.get("conductor") != CONDUCTOR:
        raise ContractError("workstream packet conductor contract is invalid")
    return value


def read_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"workstream contract not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise ContractError(f"workstream contract is unreadable: {path}") from exc
    return validate_contract(value)


def _write_if_changed(path: Path, value: dict[str, Any]) -> bool:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    try:
        if path.read_bytes() == payload:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return True


def configure_contract(path: Path, requested: str | None = None) -> tuple[dict[str, Any], bool]:
    if path.exists():
        contract = read_contract(path)
        if requested is None:
            return contract, False
        normalized, seconds = parse_runway(requested)
        runway = contract["runway"]
        if runway["duration_seconds"] == seconds:
            return contract, False
        if runway["started_epoch"] is not None:
            raise ContractError("cannot change an admitted runway; emit a successor workstream")
        contract = new_contract(normalized)
    else:
        contract = new_contract(requested or DEFAULT_RUNWAY)
    return contract, _write_if_changed(path, contract)


def _iso(epoch: int) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat(timespec="seconds")


def admit_contract(path: Path, *, now_epoch: int | None = None) -> tuple[dict[str, Any], int]:
    contract = read_contract(path)
    runway = contract["runway"]
    now = int(time.time()) if now_epoch is None else int(now_epoch)
    if runway["started_epoch"] is None:
        runway["started_epoch"] = now
        runway["started_at"] = _iso(now)
        runway["deadline_epoch"] = now + int(runway["duration_seconds"])
        runway["deadline_at"] = _iso(int(runway["deadline_epoch"]))
        _write_if_changed(path, contract)
    remaining = int(runway["deadline_epoch"]) - now
    if remaining <= 0:
        raise RunwayExpired("workstream runway is exhausted; emit a successor capsule")
    return contract, remaining


def packet_contract(
    runway: str,
    *,
    now_epoch: int | None = None,
    started_epoch: int | None = None,
    deadline_epoch: int | None = None,
) -> dict[str, Any]:
    """Return one admitted immutable packet contract consumed by dispatch."""

    contract = new_contract(runway)
    seconds = int(contract["runway"]["duration_seconds"])
    if (started_epoch is None) != (deadline_epoch is None):
        raise ContractError("workstream packet timing requires both started and deadline epochs")
    if started_epoch is None:
        if isinstance(now_epoch, bool):
            raise ContractError("workstream packet admission epoch must be an integer")
        admitted_start = int(time.time()) if now_epoch is None else int(now_epoch)
        admitted_deadline = admitted_start + seconds
    else:
        admitted_start = started_epoch
        admitted_deadline = deadline_epoch
    value = {
        "schema": contract["schema"],
        "runway": {
            "requested": contract["runway"]["requested"],
            "duration_seconds": seconds,
            "started_epoch": admitted_start,
            "deadline_epoch": admitted_deadline,
        },
        "authorization": contract["authorization"],
        "conductor": contract["conductor"],
    }
    return validate_packet_contract(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser("normalize")
    normalize.add_argument("runway")

    configure = subparsers.add_parser("configure")
    configure.add_argument("--path", type=Path, required=True)
    configure.add_argument("--runway")

    admit = subparsers.add_parser("admit")
    admit.add_argument("--path", type=Path, required=True)
    admit.add_argument("--now-epoch", type=int)

    args = parser.parse_args(argv)
    try:
        if args.command == "normalize":
            requested, seconds = parse_runway(args.runway)
            print(f"{requested}:{seconds}")
        elif args.command == "configure":
            _contract, changed = configure_contract(args.path, args.runway)
            print("changed" if changed else "unchanged")
        else:
            contract, remaining = admit_contract(args.path, now_epoch=args.now_epoch)
            runway = contract["runway"]
            print(
                f"{runway['requested']}:{runway['duration_seconds']}:{runway['started_epoch']}:"
                f"{runway['deadline_epoch']}:{remaining}"
            )
    except RunwayExpired as exc:
        print(f"workstream contract expired: {exc}", file=os.sys.stderr)
        return 3
    except ContractError as exc:
        print(f"invalid workstream contract: {exc}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
