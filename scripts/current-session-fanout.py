#!/usr/bin/env python3
"""Build redacted owner/executor packets from a full current Codex session.

The planner reads the session JSONL as private input, hashes prompt/plan text,
and writes only routing metadata. It does not launch agents, mutate credits,
send outbound traffic, or copy raw prompt bodies into tracked files.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

def repository_root() -> Path:
    script_path = Path(__file__).resolve()
    script_root = script_path.parents[1]
    env_root = os.environ.get("LIMEN_ROOT")
    if not env_root:
        return script_root
    candidate = Path(env_root).expanduser()
    try:
        if (candidate / "scripts" / script_path.name).resolve() == script_path:
            return candidate
    except OSError:
        pass
    return script_root


ROOT = repository_root()
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "current-session-fanout.json"
DOC_PATH = ROOT / "docs" / "current-session-fanout.md"


@dataclass(frozen=True)
class Theme:
    name: str
    owner: str
    category: str
    agent_fit: str
    dispatch_gate: str
    keywords: tuple[str, ...]
    route: str
    executor_criteria: tuple[str, ...]
    verification_predicates: tuple[str, ...]
    blocked_local: bool = False


THEMES: tuple[Theme, ...] = (
    Theme(
        name="current-session-intake",
        owner="organvm/limen session intake",
        category="conductor",
        agent_fit="codex",
        dispatch_gate="ready",
        keywords=("current-session", "this session", "beginning of this session", "hold everything"),
        route=(
            "Regenerate the redacted current-session fanout receipt from the full JSONL, then "
            "keep downstream work bounded by owner packet, predicate, and receipt."
        ),
        executor_criteria=(
            "Read every JSONL line and every turn_context before deriving packets.",
            "Hash prompt and plan bodies; do not write raw prompt text to public files.",
            "Emit owner packets with source turn spans, executor criteria, predicates, and stop gates.",
        ),
        verification_predicates=(
            "python3 scripts/current-session-fanout.py --session <session.jsonl> --theme current-session-intake --write",
            "python3 -m pytest cli/tests/test_current_session_fanout.py -q",
        ),
    ),
    Theme(
        name="alpha-omega-product-ledger",
        owner="global product ledger",
        category="product_selection",
        agent_fit="codex -> opencode/jules after owner repo is explicit",
        dispatch_gate="ready-after-predicate",
        keywords=("1000", "alpha", "omega", "product", "shipped"),
        route="Select product surfaces from measured repo/value evidence, not from the latest prompt alone.",
        executor_criteria=(
            "Candidate must name an owner repo or tracked owner ledger.",
            "Candidate must expose one buyer/user-facing predicate before broad build-out.",
            "Candidate must be reversible until a human opens deployment, spend, or outbound gates.",
        ),
        verification_predicates=(
            "python3 scripts/generate-positioning.py --frontdoor --discoverability",
            "python3 scripts/generate-revenue-backlog.py --floor 3 --max-new 0",
        ),
    ),
    Theme(
        name="money-inbound-seo",
        owner="revenue and inbound discovery",
        category="product_selection",
        agent_fit="codex -> opencode/jules after repo and audience are explicit",
        dispatch_gate="ready-after-predicate",
        keywords=("money", "cash", "seo", "organic", "lead", "sell", "first-dollar", "revenue"),
        route="Convert revenue intent into discoverability and first-dollar predicates for unblocked repos.",
        executor_criteria=(
            "Name the exact product/repo and the buyer/user query being served.",
            "Prefer dry-run positioning and backlog generation before queue mutation.",
            "Do not send email, publish pricing, or spend money without a human gate.",
        ),
        verification_predicates=(
            "python3 scripts/generate-positioning.py --discoverability",
            "python3 scripts/generate-revenue-backlog.py --floor 3 --max-new 0",
        ),
    ),
    Theme(
        name="repo-salvage-consolidation",
        owner="repo surface consolidation",
        category="product_selection",
        agent_fit="codex first; cheaper lanes after repo/path narrowing",
        dispatch_gate="ready-after-owner-route",
        keywords=("400 repos", "repo", "consolidated", "same app", "salvage"),
        route="Route repo sprawl into owner surfaces and receipts before executor fanout.",
        executor_criteria=(
            "Owner repo or workspace root must be explicit.",
            "No deletion, transfer, force-push, or mass merge without a human gate.",
            "Packet must say whether the output is product, preservation, or non-source residue.",
        ),
        verification_predicates=(
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ),
    ),
    Theme(
        name="contrib-mirror",
        owner="external contribution mirror",
        category="product_selection",
        agent_fit="codex planning; opencode/jules only for named repo predicates",
        dispatch_gate="ready-after-owner-route",
        keywords=("contrib", "external", "community", "github contrib", "mirror"),
        route="Separate external-contrib value from private corpus work before dispatch.",
        executor_criteria=(
            "Name the public repo or contribution target.",
            "Separate private prompt/context evidence from public contribution text.",
            "Require a local predicate or PR receipt before claiming completion.",
        ),
        verification_predicates=(
            "python3 scripts/session-attack-paths.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ),
    ),
    Theme(
        name="full-fleet-overnight",
        owner="fleet dispatch substrate",
        category="dispatch",
        agent_fit="codex conductor; active lanes only after usage gates",
        dispatch_gate="ready-after-usage-census",
        keywords=("fleet", "overnight", "all night", "lane", "jules"),
        route="Keep dispatch work behind live lane health, usage ceilings, and bounded predicates.",
        executor_criteria=(
            "Lane must be reachable and not marked exhausted, rate-limited, or low.",
            "Packet must include repo, branch/worktree, predicate, and expected receipt.",
            "Local/free floor is fallback, not a reason for speculative fanout.",
        ),
        verification_predicates=(
            "python3 scripts/usage-telemetry.py --write",
            "python3 scripts/dispatch-health.py --write",
            "python3 scripts/conductor-tranche.py --write",
        ),
    ),
    Theme(
        name="dynamic-substrate",
        owner="storage and capability substrate",
        category="substrate",
        agent_fit="codex",
        dispatch_gate="ready",
        keywords=("drive", "mounted", "hard-coded", "archive", "substrate", "hardcoded"),
        route="Derive roots and capability availability at use-time; record missing roots as substrate facts.",
        executor_criteria=(
            "Do not pin a stale drive/path/version when an env/config probe can derive it.",
            "Record unavailable local roots as blockers, not global product stops.",
            "Never copy secrets or private prompt bodies into public receipts.",
        ),
        verification_predicates=(
            "python3 scripts/capability-substrate-ledger.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
        ),
    ),
    Theme(
        name="quota-reset-guard",
        owner="usage and reset governance",
        category="blocked_local",
        agent_fit="codex/human-prep",
        dispatch_gate="blocked-local-recorded",
        keywords=("reset", "weekly limit", "free reset", "credits", "usage", "quota"),
        route="Record reset/credit constraints as local spend guards; continue unblocked product selection.",
        executor_criteria=(
            "Do not consume resets, credits, top-ups, or paid overages from this packet.",
            "Use live usage telemetry before expanding lane fanout.",
            "Surface the cheapest human action once, then route other work around it.",
        ),
        verification_predicates=(
            "python3 scripts/usage-telemetry.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
        ),
        blocked_local=True,
    ),
    Theme(
        name="domus-preflight-noise",
        owner="domus local preflight",
        category="blocked_local",
        agent_fit="codex/human-prep",
        dispatch_gate="blocked-local-recorded",
        keywords=("domus", "homebrew", "preflight", "atuin", "cursor position"),
        route="Keep local Domus/preflight noise as a separate blocked-local packet.",
        executor_criteria=(
            "Stay in the Domus owner checkout named by the packet.",
            "Do not turn shell noise into global product or revenue blocking.",
            "Return a local predicate and blocker receipt if the environment is not repairable in-scope.",
        ),
        verification_predicates=(
            "domus-packages review --json",
            "storage-lifecycle-audit --quick",
        ),
        blocked_local=True,
    ),
    Theme(
        name="private-sauce-boundary",
        owner="private/public boundary",
        category="governance",
        agent_fit="codex",
        dispatch_gate="ready",
        keywords=("private", "secret", "sauce", "hide"),
        route="Route private context through hashes and owner ledgers before public artifacts.",
        executor_criteria=(
            "Public files may contain hashes, paths, counts, criteria, and receipts only.",
            "Raw private prompt or plan bodies stay out of commits, PRs, task logs, and outbound systems.",
            "If public copy is needed, write a redacted derivation and keep the source hash lineage.",
        ),
        verification_predicates=(
            "python3 scripts/censor.py --help",
            "git diff --check",
        ),
    ),
    Theme(
        name="codex-planner-worktrees",
        owner="codex planner worktree fanout",
        category="planner",
        agent_fit="codex",
        dispatch_gate="ready-after-clean-worktree",
        keywords=("10 worktrees", "codex only", "planner", "worktree"),
        route="Keep planner worktrees as planning lanes until executor packets meet owner/predicate gates.",
        executor_criteria=(
            "Planner packet must have a unique worktree/branch and no dirty inherited state.",
            "Executor handoff requires owner repo, criteria, predicate, and receipt target.",
            "Do not broad-dispatch from a planner packet that only names a theme.",
        ),
        verification_predicates=(
            "git status --short --branch",
            "python3 scripts/current-session-fanout.py --session <session.jsonl> --theme current-session-intake",
        ),
    ),
    Theme(
        name="autopoietic-conductor",
        owner="conductor governance",
        category="governance",
        agent_fit="codex",
        dispatch_gate="ready-after-governor",
        keywords=("autopoetic", "autopoietic", "forever", "tokens", "never stop"),
        route="Keep the system breathing through bounded local work, not unbounded spend or broad fanout.",
        executor_criteria=(
            "Expand only after cheap local checks identify a real executor packet.",
            "Stop outward/irreversible work at the human gate.",
            "Record blockers and select the next unblocked owner/product packet.",
        ),
        verification_predicates=(
            "python3 scripts/autonomy-governor.py explain",
            "python3 scripts/session-value-review.py --gate --hours 1.5",
        ),
    ),
)

THEME_BY_NAME = {theme.name: theme for theme in THEMES}
PRODUCT_SELECTION_THEMES = {theme.name for theme in THEMES if theme.category == "product_selection"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_hash(text: str, length: int = 24) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "packet"


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


def add_text_record(
    records: list[dict[str, Any]],
    *,
    role: str,
    text: str,
    line: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int | None,
    source: str,
) -> None:
    if not text.strip():
        return
    records.append(
        {
            "role": role,
            "hash": stable_hash(text, 24),
            "bytes": len(text.encode("utf-8", errors="replace")),
            "line": line,
            "timestamp": timestamp,
            "turn_id": turn_id,
            "turn_index": turn_index,
            "source": source,
            "_text": text,
        }
    )


def message_texts(payload: dict[str, Any]) -> tuple[str | None, list[str]]:
    role = payload.get("role")
    if role:
        return str(role), text_from_content(payload.get("content") or payload.get("text"))
    if payload.get("type") == "message":
        role = payload.get("role")
        if role:
            return str(role), text_from_content(payload.get("content"))
    if payload.get("type") == "user_message":
        return "user", text_from_content(payload.get("message")) + text_from_content(payload.get("text_elements"))
    return None, []


def parse_plan_hashes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("name") != "update_plan":
        return []
    raw = payload.get("arguments")
    try:
        args = json.loads(raw or "{}") if isinstance(raw, str) else raw
    except ValueError:
        return []
    if not isinstance(args, dict):
        return []
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(args.get("plan") or [], start=1):
        if not isinstance(item, dict):
            continue
        step = str(item.get("step") or "")
        if not step:
            continue
        rows.append(
            {
                "hash": stable_hash(step, 12),
                "status": str(item.get("status") or "unknown"),
                "step_bytes": len(step.encode("utf-8", errors="replace")),
                "index": idx,
            }
        )
    return rows


def read_session(path: Path) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    turn_by_id: dict[str, int] = {}
    text_records: list[dict[str, Any]] = []
    plan_records: list[dict[str, Any]] = []
    item_counts = Counter()
    tool_counts = Counter()
    parse_errors = 0
    current_turn_index: int | None = None

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {
            "path": str(path),
            "present": False,
            "error": str(exc),
            "turns": [],
            "text_records": [],
            "plan_records": [],
            "item_counts": {},
            "tool_counts": {},
            "line_count": 0,
        }

    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            parse_errors += 1
            continue
        obj_type = str(obj.get("type") or "unknown")
        item_counts[obj_type] += 1
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        timestamp = obj.get("timestamp")

        if obj_type == "turn_context":
            turn_id = str(payload.get("turn_id") or f"line-{line_no}")
            current_turn_index = len(turns) + 1
            turn_by_id[turn_id] = current_turn_index
            turns.append(
                {
                    "index": current_turn_index,
                    "turn_id": turn_id,
                    "timestamp": timestamp,
                    "cwd_hash": stable_hash(str(payload.get("cwd") or ""), 12),
                    "model": payload.get("model"),
                }
            )
            continue

        if obj_type == "response_item":
            meta = payload.get("internal_chat_message_metadata_passthrough")
            meta = meta if isinstance(meta, dict) else {}
            turn_id = meta.get("turn_id")
            turn_index = turn_by_id.get(str(turn_id)) if turn_id else current_turn_index
            payload_type = str(payload.get("type") or "unknown")
            item_counts[f"response_item:{payload_type}"] += 1
            if payload.get("name"):
                tool_counts[str(payload["name"])] += 1
            role, texts = message_texts(payload)
            if role:
                for text in texts:
                    add_text_record(
                        text_records,
                        role=role,
                        text=text,
                        line=line_no,
                        timestamp=timestamp,
                        turn_id=str(turn_id) if turn_id else None,
                        turn_index=turn_index,
                        source="response_item",
                    )
            for plan in parse_plan_hashes(payload):
                plan_records.append({**plan, "line": line_no, "turn_index": turn_index, "source": "update_plan"})
            continue

        if obj_type == "compacted":
            replacement = payload.get("replacement_history") or []
            if isinstance(replacement, list):
                for item in replacement:
                    if not isinstance(item, dict):
                        continue
                    role, texts = message_texts(item)
                    if not role:
                        continue
                    for text in texts:
                        add_text_record(
                            text_records,
                            role=role,
                            text=text,
                            line=line_no,
                            timestamp=timestamp,
                            turn_id=None,
                            turn_index=current_turn_index,
                            source="compacted",
                        )

    return {
        "path": str(path),
        "present": True,
        "content_sha256": sha256_file(path),
        "path_hash": stable_hash(str(path), 24),
        "line_count": len(lines),
        "parse_errors": parse_errors,
        "turns": turns,
        "text_records": text_records,
        "plan_records": plan_records,
        "item_counts": dict(item_counts.most_common()),
        "tool_counts": dict(tool_counts.most_common()),
    }


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


def unique_records(records: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        if record.get("role") != role:
            continue
        h = str(record.get("hash") or "")
        if not h or h in seen:
            continue
        seen.add(h)
        out.append(record)
    return out


def matching_records(theme: Theme, user_records: list[dict[str, Any]], *, use_all: bool = False) -> list[dict[str, Any]]:
    if use_all:
        return list(user_records)
    matches = []
    for record in user_records:
        text = str(record.get("_text") or "").lower()
        if any(keyword.lower() in text for keyword in theme.keywords):
            matches.append(record)
    return matches


def matched_theme_names(user_records: list[dict[str, Any]], focus_theme: str | None) -> list[str]:
    names: list[str] = []
    for theme in THEMES:
        if matching_records(theme, user_records):
            names.append(theme.name)
    if focus_theme and focus_theme not in names:
        names.append(focus_theme)
    if not names:
        names.append("current-session-intake")
    return sorted(dict.fromkeys(names), key=lambda name: [t.name for t in THEMES].index(name) if name in THEME_BY_NAME else 999)


def packet_source(theme: Theme, user_records: list[dict[str, Any]], focus_theme: str | None) -> dict[str, Any]:
    use_all = theme.name == focus_theme == "current-session-intake"
    records = matching_records(theme, user_records, use_all=use_all)
    if not records and theme.name == focus_theme:
        records = list(user_records)
    prompt_hashes = sorted({str(record["hash"]) for record in records})
    turns = sorted({int(record["turn_index"]) for record in records if record.get("turn_index")})
    lines = sorted({int(record["line"]) for record in records if record.get("line")})
    return {
        "prompt_hashes": prompt_hashes,
        "prompt_occurrences": len(records),
        "turns": turns,
        "line_span": [lines[0], lines[-1]] if lines else [],
    }


def build_owner_packet(theme: Theme, source: dict[str, Any]) -> dict[str, Any]:
    packet_kind = "blocked_local_work" if theme.blocked_local else "owner_packet"
    return {
        "id": f"{'BLOCKED' if theme.blocked_local else 'OWNER'}-{slugify(theme.name)}-{stable_hash(theme.name, 8)}",
        "packet_kind": packet_kind,
        "theme": theme.name,
        "owner": theme.owner,
        "category": theme.category,
        "agent_fit": theme.agent_fit,
        "dispatch_gate": theme.dispatch_gate,
        "route": theme.route,
        "executor_criteria": list(theme.executor_criteria),
        "verification_predicates": list(theme.verification_predicates),
        "blocked_local": theme.blocked_local,
        "does_not_block": ["global-product-selection"] if theme.blocked_local else [],
        "source": source,
    }


def executor_packet_for(owner_packet: dict[str, Any]) -> dict[str, Any]:
    theme = str(owner_packet["theme"])
    target = "codex"
    if owner_packet["category"] == "product_selection":
        target = "opencode/jules after codex narrows owner repo"
    elif owner_packet["category"] == "dispatch":
        target = "active lane selected by usage census"
    return {
        "id": f"EXEC-{slugify(theme)}-{stable_hash(theme, 8)}",
        "source_owner_packet": owner_packet["id"],
        "target_agent": target,
        "dispatch_gate": owner_packet["dispatch_gate"],
        "criteria": owner_packet["executor_criteria"],
        "verification_predicates": owner_packet["verification_predicates"],
    }


def public_text_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in record.items() if key != "_text"}
        for record in records
    ]


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    session = find_session(args.session)
    parsed = read_session(session)
    if not parsed.get("present"):
        return {
            "generated_at": now_iso(),
            "status": "blocked",
            "error": parsed.get("error"),
            "session": parsed,
            "owner_packets": [],
            "executor_packets": [],
        }

    unique_user = unique_records(parsed["text_records"], "user")
    focus_theme = args.theme or "current-session-intake"
    theme_names = matched_theme_names(unique_user, focus_theme)
    owner_packets = []
    for name in theme_names:
        theme = THEME_BY_NAME.get(name)
        if theme is None:
            continue
        source = packet_source(theme, unique_user, focus_theme)
        owner_packets.append(build_owner_packet(theme, source))

    blocked_local = [packet for packet in owner_packets if packet["blocked_local"]]
    product_packets = [packet for packet in owner_packets if packet["category"] == "product_selection"]
    executor_packets = [executor_packet_for(packet) for packet in owner_packets if not packet["blocked_local"]]
    prompt_occurrences = [record for record in parsed["text_records"] if record.get("role") == "user"]
    plan_hashes = sorted({str(record["hash"]) for record in parsed["plan_records"]})
    turns = parsed["turns"]
    first_turn = turns[0] if turns else {}
    last_turn = turns[-1] if turns else {}
    global_product_status = "active" if product_packets else "ready-for-selection"

    return {
        "generated_at": now_iso(),
        "status": "ready" if owner_packets else "blocked",
        "packet_id": f"PLAN-08-{stable_hash('current-session-intake', 8)}",
        "focus_theme": focus_theme,
        "session": {
            "path_hash": parsed["path_hash"],
            "content_sha256": parsed["content_sha256"],
            "line_count": parsed["line_count"],
            "parse_errors": parsed["parse_errors"],
            "turn_count": len(turns),
            "first_turn": first_turn,
            "last_turn": last_turn,
            "item_counts": parsed["item_counts"],
            "tool_counts": parsed["tool_counts"],
        },
        "coverage": {
            "user_prompt_occurrences": len(prompt_occurrences),
            "unique_user_prompt_hashes": len(unique_user),
            "prompt_hashes": [record["hash"] for record in unique_user],
            "plan_hashes": plan_hashes,
            "plan_hash_count": len(plan_hashes),
            "themes": theme_names,
            "owner_packets": len(owner_packets),
            "executor_packets": len(executor_packets),
            "blocked_local_packets": len(blocked_local),
        },
        "global_product_selection": {
            "status": global_product_status,
            "reason": (
                "blocked local work is recorded separately and does not stop product selection"
                if blocked_local
                else "no blocked local work in the derived packet set"
            ),
            "candidate_themes": [packet["theme"] for packet in product_packets],
            "verification_predicates": sorted(
                {
                    predicate
                    for packet in product_packets
                    for predicate in packet["verification_predicates"]
                }
            ),
        },
        "owner_packets": owner_packets,
        "executor_packets": executor_packets,
        "blocked_local_work": blocked_local,
        "redacted_sources": {
            "text_records": public_text_records(parsed["text_records"]),
            "plan_records": parsed["plan_records"],
        },
        "private_index": str(PRIVATE_INDEX),
        "public_doc": str(DOC_PATH),
    }


def render_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in counts.items()) or "none"


def render_list(values: list[str], *, limit: int = 12) -> str:
    if not values:
        return "none"
    shown = values[:limit]
    suffix = f", ... +{len(values) - limit}" if len(values) > limit else ""
    return ", ".join(f"`{value}`" for value in shown) + suffix


def render_source(source: dict[str, Any]) -> str:
    turns = source.get("turns") or []
    if turns:
        turn_text = f"turns {turns[0]}-{turns[-1]}" if len(turns) > 1 else f"turn {turns[0]}"
    else:
        turn_text = "turns n/a"
    return f"{turn_text}; prompts {source.get('prompt_occurrences', 0)}"


def render_markdown(snapshot: dict[str, Any]) -> str:
    coverage = snapshot["coverage"]
    product = snapshot["global_product_selection"]
    session = snapshot["session"]
    lines = [
        "# Current Session Fanout",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Packet: `{snapshot['packet_id']}`",
        f"Focus theme: `{snapshot['focus_theme']}`",
        f"Status: `{snapshot['status']}`",
        "",
        "## Canonical Decision",
        "",
        "- PLAN-08 is the current-session-intake planner: it routes the whole source session into owner packets before executor fanout.",
        "- Packet derivation reads all parsed turns, not only the latest turn.",
        "- Public output contains prompt/plan hashes, counts, criteria, predicates, and receipt targets only.",
        "- Blocked local work is recorded as a local packet; it is not a global product-selection stop.",
        "",
        "## Coverage",
        "",
        f"- Source session hash: `{session.get('content_sha256')}`.",
        f"- JSONL lines: `{session.get('line_count')}`; parse errors: `{session.get('parse_errors')}`.",
        f"- Parsed turns: `{session.get('turn_count')}`.",
        f"- First turn: `{(session.get('first_turn') or {}).get('timestamp', 'n/a')}`.",
        f"- Last turn: `{(session.get('last_turn') or {}).get('timestamp', 'n/a')}`.",
        f"- User prompt occurrences: `{coverage['user_prompt_occurrences']}`.",
        f"- Unique user prompt hashes: `{coverage['unique_user_prompt_hashes']}`.",
        f"- Plan hashes: `{coverage['plan_hash_count']}`.",
        f"- Derived themes: {render_list(coverage['themes'], limit=20)}.",
        f"- Item mix: {render_counts(session.get('item_counts') or {})}.",
        f"- Tool mix: {render_counts(session.get('tool_counts') or {})}.",
        "",
        "## Full-Session Provenance",
        "",
        f"- Prompt hashes: {render_list(coverage['prompt_hashes'], limit=24)}.",
        f"- Plan hashes: {render_list(coverage['plan_hashes'], limit=24)}.",
        "",
        "## Owner Packets",
        "",
        "| Packet | Owner | Gate | Agent Fit | Source | Primary Predicate |",
        "|---|---|---|---|---|---|",
    ]
    for packet in snapshot["owner_packets"]:
        predicate = packet["verification_predicates"][0] if packet["verification_predicates"] else "n/a"
        lines.append(
            f"| `{packet['id']}` | {packet['owner']} | `{packet['dispatch_gate']}` | "
            f"{packet['agent_fit']} | {render_source(packet['source'])} | `{predicate}` |"
        )

    lines += [
        "",
        "## Executor Criteria",
        "",
    ]
    for packet in snapshot["owner_packets"]:
        lines.append(f"### `{packet['id']}`")
        lines.append("")
        lines.append(f"- Route: {packet['route']}")
        lines.append("- Criteria:")
        for criterion in packet["executor_criteria"]:
            lines.append(f"  - {criterion}")
        lines.append("- Verification predicates:")
        for predicate in packet["verification_predicates"]:
            lines.append(f"  - `{predicate}`")
        if packet["blocked_local"]:
            lines.append("- Local blocker: recorded here; does not block `global-product-selection`.")
        lines.append("")

    lines += [
        "## Blocked Local Work",
        "",
        "| Packet | Owner | Gate | Does Not Block | Predicate |",
        "|---|---|---|---|---|",
    ]
    if snapshot["blocked_local_work"]:
        for packet in snapshot["blocked_local_work"]:
            predicate = packet["verification_predicates"][0] if packet["verification_predicates"] else "n/a"
            lines.append(
                f"| `{packet['id']}` | {packet['owner']} | `{packet['dispatch_gate']}` | "
                f"{render_list(packet['does_not_block'])} | `{predicate}` |"
            )
    else:
        lines.append("| none | n/a | n/a | n/a | n/a |")

    lines += [
        "",
        "## Product Selection Continuity",
        "",
        f"- Status: `{product['status']}`.",
        f"- Reason: {product['reason']}.",
        f"- Candidate themes: {render_list(product['candidate_themes'], limit=20)}.",
        f"- Predicates: {render_list(product['verification_predicates'], limit=20)}.",
        "",
        "## Private Output",
        "",
        f"- Private redacted index: `{PRIVATE_INDEX.relative_to(ROOT)}`.",
        "- The private index stores hash lineage and packet membership only; it does not store raw prompt text.",
        "",
        "## Commands",
        "",
        "- Refresh this receipt: `python3 scripts/current-session-fanout.py --session <session.jsonl> --theme current-session-intake --write`",
        "- Test this planner: `python3 -m pytest cli/tests/test_current_session_fanout.py -q`",
        "- Whole gate: `bash scripts/verify-whole.sh`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create redacted current-session fanout owner packets.")
    parser.add_argument("--session", help="Codex session JSONL path; defaults to latest session")
    parser.add_argument("--theme", default="current-session-intake", help="focus planner theme")
    parser.add_argument("--write", action="store_true", help="write tracked doc and ignored private index")
    args = parser.parse_args()

    snapshot = build_snapshot(args)
    markdown = render_markdown(snapshot) if snapshot.get("status") == "ready" else json.dumps(snapshot, indent=2)
    if args.write and snapshot.get("status") == "ready":
        write_outputs(snapshot, markdown)
        print(
            "current-session-fanout: "
            f"{snapshot['status']}; {snapshot['coverage']['owner_packets']} owner packets; "
            f"wrote {DOC_PATH} and {PRIVATE_INDEX}"
        )
    else:
        print(markdown)
        print(f"current-session-fanout: {snapshot.get('status', 'blocked')}; dry-run")
    return 0 if snapshot.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
