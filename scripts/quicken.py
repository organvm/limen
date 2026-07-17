#!/usr/bin/env python3
"""Classify one explicitly authorized current-invocation artifact.

Canonical agents are co-equal peers. This entrypoint never enumerates a provider's
session estate and never resumes, retunes, closes, signals, or reclaims a session.
The caller may provide only an exported artifact for its own current invocation,
outside vendor runtime roots, bound to ``LIMEN_CURRENT_SESSION_ARTIFACT`` and the
current ``CLAUDE_SESSION_ID`` (or explicit ``--self``).

The default path is zero-write. ``--apply`` writes one redacted receipt containing
only hashes and a coarse lifecycle state. It cannot mutate the task board, tracked
residue, worktrees, branches, or provider runtime state. Historical QUICKEN census,
resumption, residue, and reclaim interfaces are unsupported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
RECEIPT_OUT = ROOT / "logs" / "quicken-current-artifact-check.json"


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


STALE_MIN = positive_int_env("LIMEN_QUICKEN_STALE_MIN", 20)
HORIZON_DAYS = positive_int_env("LIMEN_QUICKEN_HORIZON_DAYS", 3)
CLOSED_HRS = positive_int_env("LIMEN_QUICKEN_CLOSED_HRS", 18)
_CLOSED = re.compile(r"prompt relay handoff|relay handoff|session report|full session report", re.I)


class SessionAccessError(RuntimeError):
    """The caller did not prove access to its own exported current-session artifact."""


class SessionControlUnsupported(RuntimeError):
    """Cross-session census and resumption are intentionally unavailable."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def authorized_artifact(path_arg: str | None, self_sid: str | None) -> Path:
    if not path_arg:
        raise SessionAccessError(
            "an explicit --session-artifact is required; broad Claude-session census is unsupported"
        )
    if not self_sid:
        raise SessionAccessError("the current invocation id is required through CLAUDE_SESSION_ID or --self")
    path = Path(path_arg).expanduser().resolve(strict=True)
    if not path.is_file():
        raise SessionAccessError("the authorized current-session artifact must be a regular file")
    for vendor_root in (HOME / ".claude", HOME / ".codex"):
        if _inside(path, vendor_root.resolve()):
            raise SessionAccessError(
                "raw ~/.claude and ~/.codex runtime artifacts are private peer state; "
                "export the current invocation first"
            )
    bound = os.environ.get("LIMEN_CURRENT_SESSION_ARTIFACT")
    if not bound:
        raise SessionAccessError("LIMEN_CURRENT_SESSION_ARTIFACT authorization binding is required")
    try:
        bound_path = Path(bound).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SessionAccessError("the authorized current-session artifact binding is unavailable") from exc
    if path != bound_path:
        raise SessionAccessError("the explicit artifact does not match LIMEN_CURRENT_SESSION_ARTIFACT")
    if path.stem != self_sid:
        raise SessionAccessError("the artifact identity does not match the current invocation id")
    return path


def _read_jsonl(path: Path):
    try:
        for line in path.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (TypeError, ValueError):
                continue
    except OSError:
        return


def load_session(stream: Path) -> dict:
    last_prompt = ""
    last_ts = 0.0
    for event in _read_jsonl(stream):
        if event.get("type") == "last-prompt":
            last_prompt = event.get("lastPrompt") or last_prompt
        timestamp = event.get("timestamp")
        if isinstance(timestamp, str):
            try:
                last_ts = max(last_ts, datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
            except ValueError:
                pass
    return {
        "session_id": stream.stem,
        "last_prompt": last_prompt,
        "moved": max(last_ts, stream.stat().st_mtime),
    }


def classify_state(session: dict, now: float) -> str:
    idle_min = (now - session["moved"]) / 60.0 if session["moved"] else 1e9
    if idle_min < STALE_MIN:
        return "ALIVE"
    if _CLOSED.search(session["last_prompt"]) or idle_min > CLOSED_HRS * 60:
        return "CLOSED"
    return "STALLED"


def gather(now: float, self_sid: str | None, artifact: str | None = None) -> list[dict]:
    """Classify exactly one authorized current-invocation export."""

    stream = authorized_artifact(artifact, self_sid)
    session = load_session(stream)
    session["state"] = classify_state(session, now)
    return [session]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redacted_receipt(rows: list[dict], artifact: Path, checked_at: int) -> dict:
    if len(rows) != 1:
        raise SessionAccessError("exactly one current-invocation artifact is required")
    row = rows[0]
    return {
        "schema": "limen.current_session_artifact_check.v1",
        "producer": "quicken",
        "vendor": "claude",
        "checked_at": checked_at,
        "session_ref_sha256": _sha256_text(row["session_id"]),
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "state": row["state"],
    }


def write_receipt(receipt: dict) -> None:
    RECEIPT_OUT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def breathe(*_args, **_kwargs) -> None:
    raise SessionControlUnsupported("cross-session resumption is unsupported")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--session-artifact",
        help="exported current-invocation JSONL outside ~/.claude and ~/.codex",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write only the redacted current-artifact receipt",
    )
    parser.add_argument("--breathe", metavar="SID|all", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--dry-breathe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--self",
        dest="self_sid",
        default=os.environ.get("CLAUDE_SESSION_ID"),
        help="current invocation id; used only to prove artifact identity",
    )
    args = parser.parse_args()

    if args.breathe is not None or args.dry_breathe:
        print("UNSUPPORTED: cross-session resumption is disabled", file=sys.stderr)
        return 64

    checked_at = int(time.time())
    try:
        artifact = authorized_artifact(args.session_artifact, args.self_sid)
        rows = gather(checked_at, args.self_sid, str(artifact))
        receipt = redacted_receipt(rows, artifact, checked_at)
    except (OSError, SessionAccessError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 64

    print(json.dumps(receipt, sort_keys=True))
    if args.apply:
        write_receipt(receipt)
        print("redacted receipt written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
