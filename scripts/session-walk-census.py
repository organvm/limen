#!/usr/bin/env python3
"""Classify one explicitly authorized current-session artifact.

This tool does not enumerate ``~/.claude`` or ``~/.codex`` and never resumes a session.
The old whole-estate ``--walk`` interface is retained only as a fail-closed compatibility
error.  A caller must export the current invocation to a file outside both vendor runtime
roots, pass that file with ``--session-artifact``, and bind the same resolved path through
``LIMEN_CURRENT_SESSION_ARTIFACT``.  That two-part capability makes an accidental scan of a
concurrent peer's private runtime impossible through this entrypoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
LOGS = ROOT / "logs"

HEAD_BYTES = 96_000
TAIL_BYTES = 256_000

# Terminal-delivery markers in the FINAL assistant text — the session closed itself out.
WALKED_RX = re.compile(
    r"(^|\n)\s*result:|closeout complete|CLOSEOUT COMPLETE|fully done|"
    r"whole-system verification passed|nothing (left|remains) (open|dangling)|"
    r"idempotent fixed point",
    re.I,
)
# The session parked itself on the human.
NEEDS_RX = re.compile(
    r"needs input:|want me to\b|should i\b|shall i\b|let me know (which|if|how|when)|"
    r"waiting on (permission|your)|which (option|approach|one) (do you|would you)|\?\s*$",
    re.I,
)
DISPATCH_PROMPT_RX = re.compile(r"^\s*(Complete task |You are dispatched|\[dispatch\])")


def _read_edges(path: Path) -> tuple[list[str], list[str]]:
    """First/last JSONL lines without loading multi-MB transcripts whole."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(min(size, HEAD_BYTES)).decode("utf-8", errors="ignore")
        if size > HEAD_BYTES + TAIL_BYTES:
            fh.seek(size - TAIL_BYTES)
            tail = fh.read().decode("utf-8", errors="ignore")
            tail_lines = tail.splitlines()[1:]  # first line is likely truncated
        else:
            tail_lines = head.splitlines()
    return head.splitlines(), tail_lines


def _jloads(line: str):
    try:
        return json.loads(line)
    except Exception:
        return None


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def classify_claude(path: Path) -> dict:
    head, tail = _read_edges(path)
    first_prompt, cwd, sid = "", "", path.stem
    for ln in head:
        e = _jloads(ln)
        if not e:
            continue
        cwd = cwd or e.get("cwd") or ""
        if not first_prompt and e.get("type") == "user":
            t = _text_of((e.get("message") or {}).get("content"))
            if t and not t.startswith("<"):
                first_prompt = t.strip()[:160]
    last_role, last_asst_text = "", ""
    for ln in tail:
        e = _jloads(ln)
        if not e:
            continue
        t = e.get("type")
        if t == "assistant":
            txt = _text_of((e.get("message") or {}).get("content"))
            if txt.strip():
                last_asst_text = txt
            last_role = "assistant"
        elif t == "user":
            # tool_results ride user-typed lines; only real text counts as a human turn
            txt = _text_of((e.get("message") or {}).get("content"))
            last_role = "user" if txt.strip() else last_role
    if not first_prompt:
        verdict = "empty"
    elif DISPATCH_PROMPT_RX.search(first_prompt) or "/.limen-worktrees/" in cwd:
        verdict = "dispatch"
    elif last_role == "assistant" and WALKED_RX.search(last_asst_text or ""):
        verdict = "walked"
    elif last_role == "assistant" and NEEDS_RX.search((last_asst_text or "").strip()[-400:]):
        verdict = "needs_input"
    elif last_role == "assistant":
        verdict = "walked_soft"  # delivered a final message; no explicit closeout marker
    else:
        verdict = "mid_flight"
    return {
        "vendor": "claude",
        "sid": sid,
        "cwd": cwd,
        "purpose": first_prompt,
        "verdict": verdict,
        "mtime": int(path.stat().st_mtime),
    }


def classify_codex(path: Path) -> dict:
    head, tail = _read_edges(path)
    meta = next((e for e in (_jloads(x) for x in head) if e and e.get("type") == "session_meta"), None)
    payload = (meta or {}).get("payload") or {}
    sid = payload.get("id") or payload.get("session_id") or path.stem
    cwd = payload.get("cwd") or ""
    originator = payload.get("originator") or ""
    first_prompt = ""
    for ln in head:
        e = _jloads(ln)
        if not e:
            continue
        p = e.get("payload") or {}
        if e.get("type") == "event_msg" and p.get("type") == "user_message":
            first_prompt = str(p.get("message") or "")[:160]
            break
        if e.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "user":
            first_prompt = _text_of(p.get("content"))[:160] or first_prompt
            if first_prompt:
                break
    last_complete_msg, saw_complete = "", False
    for ln in tail:
        e = _jloads(ln)
        if not e:
            continue
        p = e.get("payload") or {}
        if e.get("type") == "event_msg" and p.get("type") == "task_complete":
            saw_complete = True
            last_complete_msg = str(p.get("last_agent_message") or "")
    if originator in ("codex_exec",) or "/.limen-worktrees/" in cwd:
        verdict = "dispatch"
    elif not first_prompt:
        verdict = "empty"
    elif saw_complete and NEEDS_RX.search(last_complete_msg.strip()[-400:]):
        verdict = "needs_input"
    elif saw_complete:
        verdict = "walked_soft" if not WALKED_RX.search(last_complete_msg) else "walked"
    else:
        verdict = "mid_flight"
    return {
        "vendor": "codex",
        "sid": sid,
        "cwd": cwd,
        "purpose": first_prompt,
        "verdict": verdict,
        "mtime": int(path.stat().st_mtime),
    }


class SessionAccessError(RuntimeError):
    """The caller did not prove a current, isolated artifact capability."""


class SessionControlUnsupported(RuntimeError):
    """Cross-session census and resumption are intentionally unavailable."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def authorized_artifact(path_arg: str | None) -> Path:
    if not path_arg:
        raise SessionAccessError(
            "an explicit --session-artifact is required; broad vendor-session census is unsupported"
        )
    path = Path(path_arg).expanduser().resolve(strict=True)
    if not path.is_file():
        raise SessionAccessError("the authorized current-session artifact must be a regular file")
    for vendor_root in (HOME / ".claude", HOME / ".codex"):
        if _inside(path, vendor_root.resolve()):
            raise SessionAccessError(
                "raw ~/.claude and ~/.codex runtime artifacts are private peer state; export the current invocation first"
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
    return path


def sweep(*_args, **_kwargs) -> list[dict]:
    raise SessionControlUnsupported("broad cross-session census is unsupported")


def walk(*_args, **_kwargs) -> None:
    raise SessionControlUnsupported("cross-session resumption is unsupported")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session-artifact", help="exported current-invocation JSONL outside vendor runtime roots")
    ap.add_argument("--vendor", choices=("claude", "codex"), help="format of the authorized artifact")
    ap.add_argument("--check", action="store_true", help="exit 1 if this artifact ends with unresolved input")
    ap.add_argument("--write", action="store_true", help="write a redacted single-artifact receipt")
    ap.add_argument("--walk", nargs="?", const="1", help=argparse.SUPPRESS)
    ap.add_argument("--dry-walk", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--allow-old-codex-resume", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.walk is not None or args.dry_walk or args.allow_old_codex_resume:
        print("UNSUPPORTED: cross-session census/resumption is disabled", file=sys.stderr)
        return 64
    if not args.vendor:
        print("BLOCKED: --vendor is required for the authorized artifact", file=sys.stderr)
        return 64
    try:
        artifact = authorized_artifact(args.session_artifact)
        row = classify_claude(artifact) if args.vendor == "claude" else classify_codex(artifact)
    except (OSError, SessionAccessError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 64
    receipt = {
        "schema": "limen.current_session_artifact_check.v1",
        "vendor": row["vendor"],
        "session_ref_sha256": hashlib.sha256(str(row["sid"]).encode("utf-8")).hexdigest(),
        "verdict": row["verdict"],
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }
    print(json.dumps(receipt, sort_keys=True))
    if args.write:
        LOGS.mkdir(parents=True, exist_ok=True)
        (LOGS / "current-session-artifact-check.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if args.check and row["verdict"] in {"needs_input", "mid_flight"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
