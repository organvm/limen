#!/usr/bin/env python3
"""Build redacted owner packets from a full Codex session JSONL.

The planner reads the whole session stream and records hashes, paths, tool
families, output markers, criteria, and predicates. It never stores raw prompt
or plan bodies in either the public markdown or private JSON receipt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "current-session-fanout.json"
DOC_PATH = ROOT / "docs" / "current-session-fanout.md"

HEX12_RE = re.compile(r"\b[0-9a-f]{12}\b")
HEX24_RE = re.compile(r"\b[0-9a-f]{24}\b")
PATH_RE = re.compile(r"[\w./~$-]+\.(?:py|md|json|yaml|yml|toml|js|ts|tsx|sh|rb|txt)")
PATCH_FILE_RE = re.compile(r"\*\*\* (?:Add|Update|Delete) File: (.+)")

OUTPUT_MARKERS = (
    "blocked",
    "failed",
    "error",
    "permission",
    "not found",
    "no such file",
    "rate limit",
    "warning",
    "passed",
    "success",
)

DOWN_USAGE_STATES = {"exhausted", "rate-limited", "low"}
DEFAULT_EXECUTOR_LANES = ("codex", "opencode", "github_actions", "jules", "ollama")

PACKET_DEFS: tuple[dict[str, Any], ...] = (
    {
        "key": "current-session-fanout-planner",
        "title": "Current-session fanout planner",
        "owner": "limen control plane",
        "agent_fit": "codex",
        "keywords": (
            "fanout",
            "owner packet",
            "executor criteria",
            "verification predicate",
            "current-session",
            "planner",
        ),
        "paths": (
            "current-session-fanout.py",
            "current-session-fanout.md",
            "test_current_session_fanout.py",
            "test_substrate_repo_product_fanout.py",
        ),
        "executor_criteria": (
            "derive packet evidence from every session record, not only the final turn",
            "store only hashes, counts, paths, tool families, and markers",
            "emit a public receipt plus an ignored private JSON index",
        ),
        "verification_predicates": (
            "python3 -m py_compile scripts/current-session-fanout.py",
            "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_current_session_fanout.py -q",
            "python3 scripts/current-session-fanout.py --session \"$LIMEN_CURRENT_SESSION_JSONL\" --packet-id \"$PACKET_ID\" --theme \"$PACKET_THEME\" --write",
        ),
    },
    {
        "key": "dynamic-substrate-control-plane",
        "title": "Dynamic substrate control plane",
        "owner": "limen dispatch and capacity routing",
        "agent_fit": "codex first; opencode/jules only after a narrow predicate exists",
        "keywords": (
            "dynamic-substrate",
            "substrate",
            "dispatch",
            "route",
            "router",
            "lane",
            "usage",
            "quota",
            "rate",
            "model",
            "provider",
            "capacity",
            "heartbeat",
        ),
        "paths": (
            "dispatch-async.py",
            "dispatch-parallel.py",
            "dispatch-health.py",
            "heartbeat-loop.sh",
            "heartbeat.sh",
            "route.py",
            "full-fleet-lanes.py",
            "capacity.py",
            "dispatch.py",
            "model_selection.py",
            "overnight-doctor.py",
            "DISPATCH-ARCHITECTURE.md",
        ),
        "executor_criteria": (
            "derive live substrate and lane health at run time",
            "cap or skip exhausted/rate-limited lanes before fanout",
            "never spend resets, credits, or overages without a fresh human gate",
        ),
        "verification_predicates": (
            "python3 scripts/dispatch-health.py --write",
            "python3 scripts/session-blockers-ledger.py --write",
            "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_usage_gate.py cli/tests/test_dispatch.py -q",
        ),
    },
    {
        "key": "blocked-local-work",
        "title": "Blocked local substrate work",
        "owner": "local substrate owner",
        "agent_fit": "codex records blocker; human or local owner clears gate",
        "keywords": (
            "blocked",
            "blocker",
            "permission",
            "not found",
            "no such file",
            "domus",
            "homebrew",
            "atuin",
            "cursor position",
            "local",
        ),
        "paths": (
            "/Users/4jp/.local",
            "domus-genoma",
            ".config/zsh",
            "DOMUS_CLI.md",
            "test-domus-cli.bats",
        ),
        "markers": ("blocked", "failed", "error", "permission", "not found", "no such file"),
        "executor_criteria": (
            "record exact local blocker class without copying private output",
            "do not turn a local filesystem/auth/preflight failure into a global product stop",
            "resume only after a scoped local owner packet or human gate clears the blocker",
        ),
        "verification_predicates": (
            "python3 scripts/current-session-fanout.py --session \"$LIMEN_CURRENT_SESSION_JSONL\" --packet-id \"$PACKET_ID\" --theme \"$PACKET_THEME\" --write",
            "rg -n \"blocked-local-work\" docs/current-session-fanout.md",
            "rg -ni \"global product selection remains active\" docs/current-session-fanout.md",
        ),
        "local_blocker": True,
    },
    {
        "key": "global-product-selection",
        "title": "Global product selection",
        "owner": "revenue/product selection",
        "agent_fit": "codex packetization; executor lanes after owner repo and predicate are explicit",
        "keywords": (
            "product",
            "selection",
            "global",
            "revenue",
            "money",
            "value",
            "positioning",
            "surface",
            "seo",
            "inbound",
            "backlog",
        ),
        "paths": (
            "value-repos.json",
            "positioning-seeds.json",
            "generate-revenue-backlog.py",
            "generate-positioning.py",
            "discover-value.py",
            "product-ledger.py",
            "repo-surface-ledger.py",
            "aug1-view.py",
            "august-pipeline-scoreboard.md",
        ),
        "executor_criteria": (
            "rank product work from current evidence, not a stale allowlist",
            "emit owner repo, acceptance predicate, and expected receipt before delegation",
            "continue selection while unrelated local substrate blockers are recorded",
        ),
        "verification_predicates": (
            "python3 scripts/generate-revenue-backlog.py",
            "python3 scripts/generate-positioning.py",
            "python3 scripts/current-session-fanout.py --session \"$LIMEN_CURRENT_SESSION_JSONL\" --packet-id \"$PACKET_ID\" --theme \"$PACKET_THEME\" --write",
        ),
        "global_product": True,
    },
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_hash(text: str, length: int = 24) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def compact_counts(counter: Counter[str], limit: int = 8) -> dict[str, int]:
    return dict(counter.most_common(limit))


def text_from_content(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
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


def message_texts(payload: dict[str, Any]) -> list[str]:
    if payload.get("type") == "message":
        return text_from_content(payload.get("content"))
    if payload.get("type") == "user_message":
        return text_from_content(payload.get("message")) + text_from_content(
            payload.get("text_elements")
        )
    return []


def parse_json(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def path_refs_from_text(text: str) -> list[str]:
    paths = {match.group(0) for match in PATH_RE.finditer(text)}
    for match in PATCH_FILE_RE.finditer(text):
        paths.add(match.group(1).strip())
    return sorted(paths)


def event_packet_hits(blob: str, paths: list[str], markers: list[str]) -> list[str]:
    haystack = " ".join([blob, *paths, *markers]).casefold()
    hits: list[str] = []
    for spec in PACKET_DEFS:
        keyword_hit = any(str(keyword).casefold() in haystack for keyword in spec["keywords"])
        path_hit = any(str(path).casefold() in haystack for path in spec["paths"])
        marker_hit = any(str(marker).casefold() in haystack for marker in spec.get("markers", ()))
        if keyword_hit or path_hit or marker_hit:
            hits.append(str(spec["key"]))
    return hits


def safe_event_ref(
    *,
    line: int,
    kind: str,
    digest: str,
    packets: list[str],
    role: str | None = None,
    paths: list[str] | None = None,
    markers: list[str] | None = None,
) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "line": line,
        "kind": kind,
        "hash": digest,
        "packets": packets,
    }
    if role:
        ref["role"] = role
    if paths:
        ref["paths"] = paths[:12]
    if markers:
        ref["markers"] = markers[:12]
    return ref


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
    path = Path(path_arg).expanduser() if path_arg else latest_codex_session()
    if path is None or not path.exists():
        raise FileNotFoundError(
            "no Codex session JSONL found; set LIMEN_CURRENT_SESSION_JSONL or pass --session"
        )
    return path


def scan_session(path: Path) -> dict[str, Any]:
    records = 0
    line_errors = 0
    line_first: int | None = None
    line_last = 0
    payload_types: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    tool_names: Counter[str] = Counter()
    command_families: Counter[str] = Counter()
    path_refs: Counter[str] = Counter()
    output_markers: Counter[str] = Counter()
    user_prompt_hashes: list[str] = []
    referenced_plan_hashes: Counter[str] = Counter()
    referenced_prompt_hashes: Counter[str] = Counter()
    derived_plan_hashes: Counter[str] = Counter()
    events: list[dict[str, Any]] = []
    packet_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    turn_count = 0

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if line_first is None:
                line_first = line_no
            line_last = line_no
            records += 1
            try:
                record = json.loads(raw_line)
            except ValueError:
                line_errors += 1
                continue
            if record.get("type") == "turn_context":
                turn_count += 1
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            payload_type = str(payload.get("type") or record.get("type") or "unknown")
            payload_types[payload_type] += 1
            role = str(payload.get("role") or "")
            if role:
                roles[role] += 1

            if payload_type in {"message", "user_message"}:
                for text in message_texts(payload):
                    digest = stable_hash(text)
                    paths = path_refs_from_text(text)
                    markers = [marker for marker in OUTPUT_MARKERS if marker in text.casefold()]
                    packets = event_packet_hits(text, paths, markers)
                    if role == "user" or payload_type == "user_message":
                        user_prompt_hashes.append(digest)
                    for value in HEX12_RE.findall(text.casefold()):
                        referenced_plan_hashes[value] += 1
                    for value in HEX24_RE.findall(text.casefold()):
                        referenced_prompt_hashes[value] += 1
                    for path_ref in paths:
                        path_refs[path_ref] += 1
                    event = safe_event_ref(
                        line=line_no,
                        kind="message",
                        digest=digest,
                        packets=packets,
                        role=role or None,
                        paths=paths,
                        markers=markers,
                    )
                    events.append(event)
                    for packet in packets:
                        packet_events[packet].append(event)

            elif payload_type == "function_call":
                name = str(payload.get("name") or "")
                tool_names[name] += 1
                arguments = str(payload.get("arguments") or "")
                arg_hash = stable_hash(arguments, 18)
                paths = path_refs_from_text(arguments)
                blob = f"{name} {arguments}"
                markers = [marker for marker in OUTPUT_MARKERS if marker in blob.casefold()]
                command = parse_json(arguments).get("cmd") if name == "exec_command" else None
                if isinstance(command, str) and command.strip():
                    command_families[command.split()[0]] += 1
                    paths.extend(path_refs_from_text(command))
                if name == "update_plan":
                    data = parse_json(arguments)
                    for item in data.get("plan") or []:
                        if isinstance(item, dict) and item.get("step"):
                            derived_plan_hashes[stable_hash(str(item["step"]), 12)] += 1
                for path_ref in paths:
                    path_refs[path_ref] += 1
                packets = event_packet_hits(blob, sorted(set(paths)), markers)
                event = safe_event_ref(
                    line=line_no,
                    kind=f"function_call:{name}",
                    digest=arg_hash,
                    packets=packets,
                    paths=sorted(set(paths)),
                    markers=markers,
                )
                events.append(event)
                for packet in packets:
                    packet_events[packet].append(event)

            elif payload_type == "custom_tool_call":
                name = str(payload.get("name") or "")
                tool_names[name] += 1
                input_text = str(payload.get("input") or "")
                paths = path_refs_from_text(input_text)
                for path_ref in paths:
                    path_refs[path_ref] += 1
                packets = event_packet_hits(f"{name} {input_text}", paths, [])
                event = safe_event_ref(
                    line=line_no,
                    kind=f"custom_tool_call:{name}",
                    digest=stable_hash(input_text, 18),
                    packets=packets,
                    paths=paths,
                )
                events.append(event)
                for packet in packets:
                    packet_events[packet].append(event)

            elif payload_type in {"function_call_output", "custom_tool_call_output"}:
                output = str(payload.get("output") or "")
                markers = [marker for marker in OUTPUT_MARKERS if marker in output.casefold()]
                for marker in markers:
                    output_markers[marker] += 1
                paths = path_refs_from_text(output)
                for path_ref in paths:
                    path_refs[path_ref] += 1
                packets = event_packet_hits(output, paths, markers)
                event = safe_event_ref(
                    line=line_no,
                    kind=payload_type,
                    digest=stable_hash(output, 18),
                    packets=packets,
                    paths=paths,
                    markers=markers,
                )
                events.append(event)
                for packet in packets:
                    packet_events[packet].append(event)

    return {
        "records_read": records,
        "line_errors": line_errors,
        "line_span": [line_first or 0, line_last],
        "turn_count": turn_count,
        "payload_types": compact_counts(payload_types, 16),
        "roles": compact_counts(roles, 8),
        "tool_names": compact_counts(tool_names, 12),
        "command_families": compact_counts(command_families, 12),
        "path_refs": compact_counts(path_refs, 30),
        "output_markers": compact_counts(output_markers, 12),
        "user_prompt_hashes": sorted(set(user_prompt_hashes)),
        "referenced_plan_hashes": dict(referenced_plan_hashes.most_common(40)),
        "referenced_prompt_hashes": dict(referenced_prompt_hashes.most_common(40)),
        "derived_plan_hashes": dict(derived_plan_hashes.most_common(40)),
        "events": events,
        "packet_events": {key: value for key, value in packet_events.items()},
    }


def read_down_lanes(root: Path) -> set[str]:
    lanes: set[str] = set()
    try:
        for line in (root / "logs" / "lanes-down.txt").read_text().splitlines():
            value = line.split("#", 1)[0].strip()
            if value:
                lanes.add(value)
    except OSError:
        pass
    try:
        vendors = json.loads((root / "logs" / "usage.json").read_text()).get("vendors", {})
    except (OSError, ValueError, AttributeError):
        vendors = {}
    if isinstance(vendors, dict):
        for lane, info in vendors.items():
            if isinstance(info, dict) and info.get("health") in DOWN_USAGE_STATES:
                lanes.add(str(lane))
    return lanes


def lane_selection(selector: str, root: Path | None = None) -> list[str]:
    root = root or ROOT
    if selector and selector != "auto":
        lanes = [item.strip() for item in selector.split(",") if item.strip()]
    else:
        lanes = list(DEFAULT_EXECUTOR_LANES)
    down = read_down_lanes(root)
    active = [lane for lane in lanes if lane not in down]
    return active or ["codex"]


def env_predicate(value: str, packet_id: str, theme: str) -> str:
    return value.replace("$PACKET_ID", packet_id).replace("$PACKET_THEME", theme)


def build_owner_packets(
    scan: dict[str, Any],
    packet_id: str,
    theme: str,
    executor_lanes: list[str],
) -> list[dict[str, Any]]:
    local_blockers_present = "blocked-local-work" in scan["packet_events"]
    packets: list[dict[str, Any]] = []
    for spec in PACKET_DEFS:
        key = str(spec["key"])
        evidence = scan["packet_events"].get(key, [])
        if not evidence and key != "global-product-selection":
            continue
        if key == "global-product-selection" and not evidence and theme != "global-product-selection":
            continue
        local_blocker = bool(spec.get("local_blocker"))
        global_product = bool(spec.get("global_product"))
        if local_blocker and evidence:
            status = "blocked-local-recorded"
            dispatchability = "blocked-until-local-owner-gate"
        elif global_product:
            status = "active"
            dispatchability = "ready-for-owner-selection"
        else:
            status = "packetized"
            dispatchability = "ready-for-codex-owner-work"
        predicates = [
            env_predicate(predicate, packet_id=packet_id, theme=theme)
            for predicate in spec["verification_predicates"]
        ]
        packets.append(
            {
                "id": f"{packet_id}-{key}",
                "packet_key": key,
                "title": spec["title"],
                "status": status,
                "owner": spec["owner"],
                "agent_fit": spec["agent_fit"],
                "executor_lanes": executor_lanes,
                "dispatchability": dispatchability,
                "executor_criteria": list(spec["executor_criteria"]),
                "verification_predicates": predicates,
                "evidence_count": len(evidence),
                "evidence_line_span": [
                    min((int(item["line"]) for item in evidence), default=0),
                    max((int(item["line"]) for item in evidence), default=0),
                ],
                "evidence_hashes": sorted({str(item["hash"]) for item in evidence})[:24],
                "evidence_paths": sorted(
                    {path for item in evidence for path in item.get("paths", [])}
                )[:30],
                "evidence_markers": sorted(
                    {marker for item in evidence for marker in item.get("markers", [])}
                ),
                "blocks_global_product_selection": False,
                "continues_despite_local_blockers": bool(global_product and local_blockers_present),
            }
        )
    return packets


def parse_hash_args(values: list[str] | None, expected_len: int) -> list[str]:
    out: list[str] = []
    for value in values or []:
        for item in re.split(r"[\s,]+", value.strip()):
            if len(item) == expected_len and re.fullmatch(r"[0-9a-f]+", item):
                out.append(item)
    return sorted(set(out))


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    session = find_session(args.session)
    scan = scan_session(session)
    executor_lanes = lane_selection(args.executor_lanes)
    owner_packets = build_owner_packets(scan, args.packet_id, args.theme, executor_lanes)
    local_blocker_ids = [
        packet["id"] for packet in owner_packets if packet["status"] == "blocked-local-recorded"
    ]
    global_packets = [
        packet["id"] for packet in owner_packets if packet["packet_key"] == "global-product-selection"
    ]
    provided_plan_hashes = parse_hash_args(args.source_plan_hash, 12)
    provided_prompt_hashes = parse_hash_args(args.source_prompt_hash, 24)
    source_prompt_hashes = sorted(set(scan["user_prompt_hashes"]) | set(provided_prompt_hashes))
    source_plan_hashes = sorted(
        set(scan["referenced_plan_hashes"]) | set(scan["derived_plan_hashes"]) | set(provided_plan_hashes)
    )
    global_active = bool(global_packets)
    status = "ready_with_local_blockers" if local_blocker_ids and global_active else "ready"
    if not owner_packets:
        status = "blocked"
    return {
        "version": 1,
        "generated_at": now_iso(),
        "packet_id": args.packet_id,
        "theme": args.theme,
        "source_session_path": str(session),
        "source_session_hash": stable_hash(str(session), 24),
        "privacy": {
            "raw_prompt_bodies_stored": False,
            "raw_plan_bodies_stored": False,
            "public_receipt": str(DOC_PATH),
            "private_index": str(PRIVATE_INDEX),
        },
        "coverage": {
            "records_read": scan["records_read"],
            "line_errors": scan["line_errors"],
            "line_span": scan["line_span"],
            "turn_count": scan["turn_count"],
            "payload_types": scan["payload_types"],
            "roles": scan["roles"],
            "tool_names": scan["tool_names"],
            "command_families": scan["command_families"],
            "path_refs": scan["path_refs"],
            "output_markers": scan["output_markers"],
            "source_prompt_hash_count": len(source_prompt_hashes),
            "source_plan_hash_count": len(source_plan_hashes),
        },
        "provenance": {
            "source_prompt_hashes": source_prompt_hashes,
            "source_plan_hashes": source_plan_hashes,
            "provided_source_prompt_hashes": provided_prompt_hashes,
            "provided_source_plan_hashes": provided_plan_hashes,
        },
        "executor_lanes": executor_lanes,
        "owner_packets": owner_packets,
        "local_blocker_packet_ids": local_blocker_ids,
        "global_product_packet_ids": global_packets,
        "continuation_policy": {
            "global_product_selection_remains_active": global_active,
            "local_blockers_do_not_stop_global_selection": bool(local_blocker_ids and global_active),
            "blocked_local_work_recorded": bool(local_blocker_ids),
        },
        "status": status,
        "private_evidence": {
            "events": scan["events"],
            "packet_events": scan["packet_events"],
        },
    }


def render_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in counts.items()) or "none"


def render_hashes(values: list[str], limit: int = 24) -> str:
    shown = values[:limit]
    suffix = f" (+{len(values) - limit} more)" if len(values) > limit else ""
    return ", ".join(f"`{value}`" for value in shown) + suffix if shown else "none"


def render_markdown(snapshot: dict[str, Any]) -> str:
    coverage = snapshot["coverage"]
    lines = [
        "# Current Session Fanout",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Packet id: `{snapshot['packet_id']}`",
        f"Theme: `{snapshot['theme']}`",
        f"Status: `{snapshot['status']}`",
        f"Source session hash: `{snapshot['source_session_hash']}`",
        "",
        "## Canonical Decision",
        "",
        "- Owner packets are derived from the full session JSONL stream, not the latest turn.",
        "- This receipt stores hashes, counts, paths, tool families, and markers only; it stores no raw prompt or plan bodies.",
        "- Blocked local substrate work is recorded as its own packet; global product selection remains active when product evidence exists.",
        "",
        "## Coverage",
        "",
        f"- Records read: `{coverage['records_read']}` across line span `{coverage['line_span'][0]}-{coverage['line_span'][1]}`.",
        f"- Turn contexts: `{coverage['turn_count']}`.",
        f"- Source prompt hashes: `{coverage['source_prompt_hash_count']}`.",
        f"- Source plan hashes: `{coverage['source_plan_hash_count']}`.",
        f"- Payload mix: {render_counts(coverage['payload_types'])}.",
        f"- Tool mix: {render_counts(coverage['tool_names'])}.",
        f"- Command families: {render_counts(coverage['command_families'])}.",
        f"- Output markers: {render_counts(coverage['output_markers'])}.",
        "",
        "## Provenance",
        "",
        f"- Source prompt hashes: {render_hashes(snapshot['provenance']['source_prompt_hashes'])}.",
        f"- Source plan hashes: {render_hashes(snapshot['provenance']['source_plan_hashes'])}.",
        "",
        "## Owner Packets",
        "",
        "| Packet | Status | Owner | Agent Fit | Evidence | Verification |",
        "|---|---|---|---|---:|---|",
    ]
    for packet in snapshot["owner_packets"]:
        predicate = packet["verification_predicates"][0] if packet["verification_predicates"] else "n/a"
        lines.append(
            f"| `{packet['id']}` | `{packet['status']}` | {packet['owner']} | "
            f"{packet['agent_fit']} | {packet['evidence_count']} | `{predicate}` |"
        )
    if not snapshot["owner_packets"]:
        lines.append("| none | n/a | n/a | n/a | 0 | n/a |")

    lines += [
        "",
        "## Executor Criteria",
        "",
    ]
    for packet in snapshot["owner_packets"]:
        lines.append(f"### `{packet['id']}`")
        lines.append("")
        for criterion in packet["executor_criteria"]:
            lines.append(f"- Criteria: {criterion}.")
        for predicate in packet["verification_predicates"]:
            lines.append(f"- Predicate: `{predicate}`.")
        if packet["evidence_paths"]:
            lines.append(f"- Evidence paths: {render_hashes(packet['evidence_paths'], limit=10)}.")
        if packet["evidence_markers"]:
            lines.append(f"- Evidence markers: {render_hashes(packet['evidence_markers'], limit=10)}.")
        lines.append(
            f"- Continuation: blocks global product selection = `{packet['blocks_global_product_selection']}`; "
            f"continues despite local blockers = `{packet['continues_despite_local_blockers']}`."
        )
        lines.append("")

    policy = snapshot["continuation_policy"]
    lines += [
        "## Continuation Policy",
        "",
        f"- Blocked local work recorded: `{policy['blocked_local_work_recorded']}`.",
        f"- Global product selection remains active: `{policy['global_product_selection_remains_active']}`.",
        f"- Local blockers do not stop global selection: `{policy['local_blockers_do_not_stop_global_selection']}`.",
        "",
        "## Private Output",
        "",
        f"- Private fanout index: `{PRIVATE_INDEX.relative_to(ROOT)}`.",
        "- The private index keeps redacted event hashes and packet membership only.",
        "",
        "## Commands",
        "",
        "- Refresh this receipt: `python3 scripts/current-session-fanout.py --session \"$LIMEN_CURRENT_SESSION_JSONL\" --packet-id \"$PACKET_ID\" --theme \"$PACKET_THEME\" --write`",
        "- Test this planner: `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_current_session_fanout.py -q`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown + "\n", encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build redacted current-session fanout packets.")
    parser.add_argument("--session", help="Codex session JSONL path; defaults to latest session")
    parser.add_argument("--packet-id", default="PLAN-03-f0b8bc86")
    parser.add_argument("--theme", default="dynamic-substrate")
    parser.add_argument("--executor-lanes", default=os.environ.get("LIMEN_LANES", "auto"))
    parser.add_argument("--source-plan-hash", action="append", default=[])
    parser.add_argument("--source-prompt-hash", action="append", default=[])
    parser.add_argument("--write", action="store_true", help="write tracked markdown and private JSON")
    args = parser.parse_args()

    snapshot = build_snapshot(args)
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
        print(f"current-session-fanout: {snapshot['status']}; wrote {DOC_PATH} and {PRIVATE_INDEX}")
    else:
        print(markdown)
        print(f"current-session-fanout: {snapshot['status']}; dry-run")
    return 0 if snapshot["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
