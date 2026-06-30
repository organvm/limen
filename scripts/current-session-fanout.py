#!/usr/bin/env python3
"""Turn the whole current Codex session into planner and executor packets.

This does not launch paid agents. It writes receipts/packet specs when asked,
and defaults to dry-run so banked resets or credits cannot be consumed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "current-session-fanout.json"
DOC_PATH = ROOT / "docs" / "current-session-fanout.md"
sys.path.insert(0, str(ROOT / "cli" / "src"))

try:
    from limen.capacity import resolve_lane_selector  # noqa: E402
    from limen.dispatch import _down_lanes  # noqa: E402
    from limen.io import load_limen_file  # noqa: E402
except Exception:  # pragma: no cover - import fallback for hermetic tests
    resolve_lane_selector = None
    _down_lanes = None
    load_limen_file = None

THEMES = [
    ("alpha-omega-product-ledger", ("1000", "alpha", "omega", "product", "shipped")),
    ("full-fleet-overnight", ("fleet", "overnight", "all night", "lane", "jules")),
    ("dynamic-substrate", ("drive", "mounted", "hard-coded", "archive", "substrate")),
    ("repo-salvage-consolidation", ("400 repos", "repo", "consolidated", "same app", "salvage")),
    ("money-inbound-seo", ("money", "cash", "seo", "organic", "lead", "sell")),
    ("contrib-mirror", ("contrib", "external", "community", "github contrib", "mirror")),
    ("quota-reset-guard", ("reset", "weekly limit", "free reset", "credits", "usage")),
    ("current-session-intake", ("this session", "beginning of this session", "hold everything")),
    ("domus-preflight-noise", ("domus", "homebrew", "preflight", "atuin", "cursor position")),
    ("private-sauce-boundary", ("private", "secret", "sauce", "hide")),
    ("codex-planner-worktrees", ("10 worktrees", "codex only", "planner", "worktree")),
    ("autopoietic-conductor", ("autopoetic", "autopoietic", "forever", "tokens")),
]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_hash(text: str, length: int = 18) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def text_from_content(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(text_from_content(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for key in ("text", "content", "message", "input"):
            if key in value:
                out.extend(text_from_content(value[key]))
        return out
    return []


def user_texts_from_obj(obj: dict[str, Any]) -> list[str]:
    if obj.get("role") == "user":
        return text_from_content(obj.get("content") or obj.get("text"))
    payload = obj.get("payload")
    if isinstance(payload, dict):
        if payload.get("type") == "user_message":
            return text_from_content(payload.get("message")) + text_from_content(payload.get("text_elements"))
        if payload.get("type") == "message" and payload.get("role") == "user":
            return text_from_content(payload.get("content"))
    if obj.get("type") == "message" and obj.get("role") == "user":
        return text_from_content(obj.get("content"))
    return []


def read_session_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return messages
    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        timestamp = obj.get("timestamp")
        for text in user_texts_from_obj(obj):
            messages.append(
                {
                    "line": idx,
                    "timestamp": timestamp,
                    "hash": stable_hash(text, 24),
                    "bytes": len(text.encode("utf-8", errors="replace")),
                    "text": text,
                }
            )
    return messages


def latest_codex_session() -> Path | None:
    explicit = os.environ.get("LIMEN_CURRENT_SESSION_JSONL")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.exists() else None
    root = HOME / ".codex" / "sessions"
    if not root.exists():
        return None
    try:
        files = [path for path in root.rglob("*.jsonl") if path.is_file()]
    except OSError:
        return None
    return max(files, key=lambda path: path.stat().st_mtime) if files else None


def find_session(path_arg: str | None) -> Path:
    if path_arg:
        path = Path(path_arg).expanduser()
    else:
        path = latest_codex_session()
    if path is None or not path.exists():
        raise FileNotFoundError("no Codex session JSONL found; set LIMEN_CURRENT_SESSION_JSONL or pass --session")
    return path


def matched_themes(messages: list[dict[str, Any]]) -> list[str]:
    body = "\n".join(str(msg["text"]).lower() for msg in messages)
    found = [name for name, needles in THEMES if any(needle in body for needle in needles)]
    return found or ["current-session-intake"]


def lane_selection(selector: str) -> list[str]:
    if resolve_lane_selector is None or load_limen_file is None or _down_lanes is None:
        return ["codex"]
    try:
        board = load_limen_file(ROOT / "tasks.yaml")
        return list(resolve_lane_selector(selector, board=board, down_lanes=_down_lanes()))
    except Exception:
        return ["codex"]


def packet_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-")
    return slug or "packet"


def planner_packets(themes: list[str], messages: list[dict[str, Any]], min_codex: int, no_reset_spend: bool) -> list[dict[str, Any]]:
    seed_themes = list(themes)
    idx = 1
    while len(seed_themes) < min_codex:
        seed_themes.append(f"product-factory-{idx:02d}")
        idx += 1
    prompt_hashes = [msg["hash"] for msg in messages]
    packets: list[dict[str, Any]] = []
    for idx, theme in enumerate(seed_themes, start=1):
        packets.append(
            {
                "id": f"PLAN-{idx:02d}-{stable_hash(theme, 8)}",
                "packet_type": "planner_packet",
                "target_agent": "codex",
                "theme": theme,
                "worktree_slug": packet_slug(f"planner-{idx:02d}-{theme}")[:80],
                "spend_guard": "no-reset-spend" if no_reset_spend else "operator-allowed-reset-spend",
                "source_prompt_hashes": prompt_hashes,
                "acceptance": [
                    "derive owner packets from the full session, not just the latest turn",
                    "emit executor criteria and verification predicates",
                    "record blocked local work without stopping global product selection",
                ],
            }
        )
    return packets


def executor_packets(themes: list[str], lanes: list[str], include_contrib: bool, no_reset_spend: bool) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    work_themes = list(themes)
    if include_contrib and "contrib-mirror" not in work_themes:
        work_themes.append("contrib-mirror")
    for lane in lanes:
        if lane == "codex":
            continue
        theme = work_themes[len(packets) % len(work_themes)] if work_themes else "product-factory"
        packets.append(
            {
                "id": f"EXEC-{lane}-{stable_hash(theme, 8)}",
                "packet_type": "executor_packet",
                "target_agent": lane,
                "theme": theme,
                "spend_guard": "no-reset-spend" if no_reset_spend and lane == "codex" else "lane-policy",
                "acceptance": [
                    "bounded reversible work only",
                    "return changed paths, predicate, PR/deploy/receipt, and blocker if any",
                    "do not perform outbound sends or credential/credit mutations",
                ],
            }
        )
    return packets


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    session = find_session(args.session)
    messages = read_session_messages(session)
    themes = matched_themes(messages)
    lanes = lane_selection(args.executor_lanes)
    no_reset_spend = not args.allow_reset_spend
    planners = planner_packets(themes, messages, args.min_codex_planners, no_reset_spend)
    executors = executor_packets(themes, lanes, args.include_contrib, no_reset_spend)
    return {
        "generated_at": now_iso(),
        "session_path": str(session),
        "session_hash": stable_hash(str(session), 24),
        "user_messages": len(messages),
        "prompt_bytes": sum(int(msg["bytes"]) for msg in messages),
        "prompt_hashes": [msg["hash"] for msg in messages],
        "themes": themes,
        "executor_lanes": lanes,
        "no_reset_spend": no_reset_spend,
        "planner_packets": planners,
        "executor_packets": executors,
        "status": "ready" if messages and planners else "blocked",
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Current Session Fanout",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        f"User messages: `{snapshot['user_messages']}`",
        f"Prompt bytes: `{snapshot['prompt_bytes']}`",
        f"No reset spend: `{snapshot['no_reset_spend']}`",
        "",
        "## Themes",
        "",
    ]
    for theme in snapshot["themes"]:
        lines.append(f"- `{theme}`")
    lines += [
        "",
        "## Planner Packets",
        "",
        "| Packet | Agent | Worktree | Theme |",
        "|---|---|---|---|",
    ]
    for packet in snapshot["planner_packets"]:
        lines.append(
            f"| `{packet['id']}` | `{packet['target_agent']}` | `{packet['worktree_slug']}` | `{packet['theme']}` |"
        )
    lines += [
        "",
        "## Executor Packets",
        "",
        "| Packet | Agent | Theme |",
        "|---|---|---|",
    ]
    for packet in snapshot["executor_packets"]:
        lines.append(f"| `{packet['id']}` | `{packet['target_agent']}` | `{packet['theme']}` |")
    lines += [
        "",
        "## Contract",
        "",
        "- Planner packets are Codex conductor work; executor packets go to active fleet lanes.",
        "- This command never applies Codex resets, credits, top-ups, or paid overages.",
        "- Outbound identity-bearing actions remain human-gated.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create current-session planner and executor fanout packets.")
    parser.add_argument("--session", help="Codex session JSONL path; defaults to latest session")
    parser.add_argument("--min-codex-planners", type=int, default=int(os.environ.get("LIMEN_MIN_CODEX_PLANNERS", "10")))
    parser.add_argument("--executor-lanes", default=os.environ.get("LIMEN_LANES", "auto"))
    parser.add_argument("--include-contrib", action="store_true")
    parser.add_argument("--no-reset-spend", dest="allow_reset_spend", action="store_false", default=False)
    parser.add_argument("--allow-reset-spend", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", help="print only; never write")
    parser.add_argument("--write", action="store_true", help="write packet receipts")
    args = parser.parse_args()
    snapshot = build_snapshot(args)
    markdown = render_markdown(snapshot)
    if args.write and not args.dry_run:
        write_outputs(snapshot, markdown)
        print(f"current-session-fanout: {snapshot['status']}; wrote {DOC_PATH} and {PRIVATE_INDEX}")
    else:
        print(markdown, end="")
        print(f"current-session-fanout: {snapshot['status']}; dry-run")
    return 0 if snapshot["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
