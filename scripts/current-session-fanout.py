#!/usr/bin/env python3
"""Derive redacted owner packets from a full Codex session.

This is a planner, not a dispatcher. It reads a local Codex JSONL session,
keeps prompt and plan bodies out of tracked output, and emits a public-safe
fanout packet with executor criteria, predicates, and local blockers.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
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

THEMES: list[tuple[str, tuple[str, ...]]] = [
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


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stable_hash(text: str, length: int) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def relpath(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser().absolute()
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        return str(resolved)


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                obj["_line"] = line_no
                rows.append(obj)
    return rows


def user_texts_from_obj(obj: dict[str, Any]) -> list[str]:
    payload = obj.get("payload")
    if isinstance(payload, dict):
        if payload.get("type") == "message" and payload.get("role") == "user":
            return text_from_content(payload.get("content"))
        if payload.get("type") == "user_message":
            return text_from_content(payload.get("message")) + text_from_content(payload.get("text_elements"))
    if obj.get("type") == "message" and obj.get("role") == "user":
        return text_from_content(obj.get("content"))
    return []


def extract_user_messages(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for obj in rows:
        for text in user_texts_from_obj(obj):
            # Response items and event_msg often mirror the same prompt at the same timestamp.
            prompt_hash = stable_hash(text, 24)
            if messages and messages[-1]["hash"] == prompt_hash and messages[-1]["timestamp"] == obj.get("timestamp"):
                continue
            messages.append(
                {
                    "line": obj.get("_line"),
                    "timestamp": obj.get("timestamp"),
                    "hash": prompt_hash,
                    "bytes": len(text.encode("utf-8", errors="replace")),
                    "theme_hits": matched_themes_for_text(text),
                }
            )
    return messages


def matched_themes_for_text(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name, needles in THEMES if any(needle in lowered for needle in needles)]


def extract_plan_updates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for obj in rows:
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        if payload.get("type") != "function_call" or payload.get("name") != "update_plan":
            continue
        try:
            args = json.loads(str(payload.get("arguments") or "{}"))
        except ValueError:
            args = {}
        items = []
        for item in args.get("plan") or []:
            if not isinstance(item, dict):
                continue
            step = str(item.get("step") or "")
            items.append({"hash": stable_hash(step, 12), "status": str(item.get("status") or "")})
        plans.append({"line": obj.get("_line"), "timestamp": obj.get("timestamp"), "items": items})
    return plans


def first_word(cmd: str) -> str:
    return cmd.strip().split(maxsplit=1)[0] if cmd.strip() else ""


def command_category(cmd: str) -> str:
    if "verify-whole.sh" in cmd:
        return "whole-verify"
    if "pytest" in cmd:
        return "tests"
    if "dispatch-async.py" in cmd:
        return "dispatch-dry-run"
    if "current-session-fanout.py" in cmd:
        return "current-session-fanout"
    if "product-ledger.py" in cmd:
        return "product-ledger"
    if "repo-surface-ledger.py" in cmd:
        return "repo-surface-ledger"
    if "substrate-ledger.py" in cmd:
        return "substrate-ledger"
    if "domus up" in cmd:
        return "domus-preflight"
    if "check-params.py" in cmd:
        return "parameter-check"
    if cmd.startswith("rg "):
        return "search"
    if cmd.startswith("sed "):
        return "read"
    return first_word(cmd) or "command"


def extract_commands(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for obj in rows:
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        if payload.get("type") == "function_call" and payload.get("name") == "exec_command":
            try:
                args = json.loads(str(payload.get("arguments") or "{}"))
            except ValueError:
                args = {}
            cmd = str(args.get("cmd") or "")
            row = {
                "line": obj.get("_line"),
                "timestamp": obj.get("timestamp"),
                "call_id": payload.get("call_id"),
                "hash": stable_hash(cmd, 16),
                "category": command_category(cmd),
                "program": first_word(cmd),
                "exit_code": None,
                "output_hash": None,
            }
            calls[str(payload.get("call_id"))] = row
            ordered.append(row)
        elif payload.get("type") == "function_call_output":
            call = calls.get(str(payload.get("call_id")))
            if not call:
                continue
            output = str(payload.get("output") or "")
            match = re.search(r"Process exited with code (\d+)", output)
            if match:
                call["exit_code"] = int(match.group(1))
            call["output_hash"] = stable_hash(output, 16)
            call["blocker_signals"] = blocker_signals(output, str(call.get("category") or ""))
            call["success_signals"] = success_signals(output)
    return ordered


def extract_patches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    for obj in rows:
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        if payload.get("type") != "custom_tool_call" or payload.get("name") != "apply_patch":
            continue
        patch = str(payload.get("input") or "")
        files = re.findall(r"\*\*\* (?:Add|Update|Delete) File: (.+)", patch)
        patches.append(
            {
                "line": obj.get("_line"),
                "timestamp": obj.get("timestamp"),
                "hash": stable_hash(patch, 16),
                "files": files,
                "owners": sorted({owner_for_path(path) for path in files}),
            }
        )
    return patches


def owner_for_path(path: str) -> str:
    if path.startswith("/Users/4jp/.config") or path.startswith("/Users/4jp/.local"):
        return "domus-local-shell"
    if "domus-genoma" in path:
        return "domus-genoma"
    if path.startswith("scripts/current-session-fanout.py") or path.startswith(
        ("scripts/substrate-ledger.py", "scripts/repo-surface-ledger.py", "scripts/product-ledger.py")
    ):
        return "limen-current-session-fanout"
    if path.startswith("cli/tests/test_substrate_repo_product_fanout.py"):
        return "limen-current-session-fanout"
    if path.startswith(("cli/src/limen/", "scripts/dispatch", "scripts/heartbeat", "scripts/route.py")):
        return "limen-dispatch-control"
    if path.startswith(("mcp/", "web/", "AGENTS.md", "container/launchd/", "scripts/conductor-tranche.py")):
        return "limen-dispatch-control"
    if path.startswith("tasks.yaml"):
        return "limen-task-board"
    return "limen-repo"


def blocker_signals(output: str, category: str) -> list[str]:
    signals = []
    if "Storage lifecycle preflight blocked" in output or "/Volumes/4444-iivii is not mounted" in output:
        signals.append("domus-storage-preflight-blocked")
    if "internal free space" in output or "internal usage" in output:
        signals.append("local-disk-pressure")
    if "reopened after a done transition" in output or "CAPFILL-opencode-20260629-07" in output:
        signals.append("limen-task-board-reopened-after-done")
    if "Agent-instruction doc drift detected" in output:
        signals.append("agent-doc-drift")
    if category == "tests" and ("FAILED " in output or re.search(r"\b\d+ failed\b", output)):
        signals.append("test-failure")
    return signals


def success_signals(output: str) -> list[str]:
    signals = []
    if "product-ledger: active products=" in output:
        signals.append("product-ledger-active")
    if "current-session-fanout: ready" in output:
        signals.append("current-session-fanout-ready")
    if "passed" in output and "pytest" not in output:
        signals.append("predicate-passed")
    return signals


def event_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    payload_counts: Counter[str] = Counter()
    for obj in rows:
        counts[str(obj.get("type") or "unknown")] += 1
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        if payload.get("type"):
            payload_counts[str(payload["type"])] += 1
    return {"types": dict(counts.most_common()), "payload_types": dict(payload_counts.most_common())}


def derive_themes(messages: list[dict[str, Any]]) -> list[str]:
    counts: Counter[str] = Counter()
    for msg in messages:
        for theme in msg.get("theme_hits") or []:
            counts[theme] += 1
    return [theme for theme, _count in counts.most_common()] or ["current-session-intake"]


def derive_blockers(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_success_by_category: dict[str, int] = {}
    for index, command in enumerate(commands):
        if command.get("exit_code") == 0:
            latest_success_by_category[str(command.get("category"))] = index

    blockers: dict[str, dict[str, Any]] = {}
    for index, command in enumerate(commands):
        for signal in command.get("blocker_signals") or []:
            if signal == "test-failure" and latest_success_by_category.get("tests", -1) > index:
                status = "resolved-later"
            elif signal == "agent-doc-drift" and latest_success_by_category.get("whole-verify", -1) > index:
                status = "resolved-later"
            else:
                status = "blocked-local"
            row = blockers.setdefault(
                signal,
                {
                    "id": signal,
                    "status": status,
                    "scope": "local",
                    "global_product_selection": "continue",
                    "evidence_command_hashes": [],
                    "owner": blocker_owner(signal),
                    "next_action": blocker_next_action(signal),
                },
            )
            if status == "blocked-local":
                row["status"] = status
            row["evidence_command_hashes"].append(command["hash"])
    return sorted(blockers.values(), key=lambda row: (row["status"] != "blocked-local", row["id"]))


def local_environment_blockers() -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    package_json = ROOT / "web" / "app" / "package.json"
    node_modules = ROOT / "web" / "app" / "node_modules"
    if package_json.exists() and not node_modules.exists():
        blockers.append(
            {
                "id": "web-app-node-modules-missing",
                "status": "blocked-local",
                "scope": "local",
                "global_product_selection": "continue",
                "evidence_command_hashes": ["web-app-package-manifest"],
                "owner": "limen web/app dependency install",
                "next_action": "Run the web/app package install in this worktree before claiming whole-system verified.",
            }
        )
    return blockers


def blocker_owner(signal: str) -> str:
    if signal.startswith("domus") or signal == "local-disk-pressure":
        return "domus-genoma/storage lifecycle"
    if signal.startswith("limen-task-board"):
        return "limen task board"
    if signal == "agent-doc-drift":
        return "limen agent docs"
    if signal == "test-failure":
        return "repo predicate"
    return "local owner"


def blocker_next_action(signal: str) -> str:
    if signal.startswith("domus") or signal == "local-disk-pressure":
        return "Record in the Domus/storage owner lane; do not block unrelated product selection."
    if signal.startswith("limen-task-board"):
        return "Fix or explicitly owner-record the reopened task before claiming whole-system verified."
    if signal == "agent-doc-drift":
        return "Keep AGENTS.md aligned with canonical agent/status vocabulary."
    if signal == "test-failure":
        return "Use later focused predicate output before treating the failure as live."
    return "Record in the owning ledger and continue other packets."


def owner_file_counts(patches: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for patch in patches:
        for owner in patch.get("owners") or []:
            counts[owner] += len([path for path in patch.get("files") or [] if owner_for_path(path) == owner])
    return dict(counts.most_common())


def packet(
    *,
    packet_id: str,
    owner: str,
    target_agent: str,
    theme: str,
    purpose: str,
    criteria: list[str],
    predicates: list[str],
    stop_before: list[str],
    receipt: str,
    status: str = "ready",
) -> dict[str, Any]:
    return {
        "id": packet_id,
        "owner": owner,
        "target_agent": target_agent,
        "theme": theme,
        "purpose": purpose,
        "status": status,
        "executor_criteria": criteria,
        "verification_predicates": predicates,
        "stop_before": stop_before,
        "receipt": receipt,
    }


def build_owner_packets(
    *,
    packet_id: str,
    theme: str,
    session_display: str,
    blockers: list[dict[str, Any]],
    themes: list[str],
    file_counts: dict[str, int],
) -> list[dict[str, Any]]:
    source_arg = f"--session {session_display}" if not session_display.startswith("~") else f"--session {session_display}"
    packets = [
        packet(
            packet_id=packet_id,
            owner="limen current-session fanout",
            target_agent="codex",
            theme=theme,
            purpose="Turn the full current session into Codex planner worktree packets and downstream executor packets.",
            criteria=[
                "Use every user-turn prompt hash and every update_plan step hash from the source session.",
                "Keep planner packets Codex-only until an owner repo, allowed path set, predicate, and receipt are explicit.",
                "Executor packets must name target_agent, owner, stop condition, expected receipt, and verification predicate.",
                "Do not consume reset/credit spend, mutate credentials, send mail, deploy, force-push, or delete data.",
                "Treat local blockers as owner-scoped records; they cannot halt unrelated product selection.",
            ],
            predicates=[
                f"python3 scripts/current-session-fanout.py {source_arg} --packet-id {packet_id} --theme {theme} --write",
                f"rg -n \"{re.escape(packet_id)}|{re.escape(theme)}|Executor Criteria|Verification Predicates\" docs/current-session-fanout.md",
                "python3 -m py_compile scripts/current-session-fanout.py",
            ],
            stop_before=[
                "external dispatch",
                "paid reset or credit mutation",
                "outbound identity-bearing action",
                "credential, deploy, delete, merge, or force-push action",
            ],
            receipt="docs/current-session-fanout.md plus .limen-private/session-corpus/lifecycle/current-session-fanout.json",
        )
    ]
    if file_counts.get("limen-dispatch-control") or "full-fleet-overnight" in themes:
        packets.append(
            packet(
                packet_id="OWNER-limen-dispatch-control",
                owner="limen dispatch control plane",
                target_agent="codex",
                theme="full-fleet-overnight",
                purpose="Preserve the registry-derived lane cascade and dry-run fanout behavior before executor dispatch.",
                criteria=[
                    "Lanes are derived from the canonical registry, not hardcoded per call site.",
                    "Down or metered-exhausted lanes are skipped before launch.",
                    "Dry-run shows planned launch count and lane mix without creating external work.",
                ],
                predicates=[
                    "PYTHONPATH=cli/src pytest -q cli/tests/test_dispatch.py cli/tests/test_async_dispatch.py",
                    "PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --dry-run",
                    "python3 scripts/check-params.py",
                ],
                stop_before=["live dispatch", "credential work", "spend escalation"],
                receipt="dispatch dry-run output and focused predicate output",
            )
        )
    if file_counts.get("limen-current-session-fanout") or "dynamic-substrate" in themes:
        packets.append(
            packet(
                packet_id="OWNER-product-selection",
                owner="limen product selection",
                target_agent="codex",
                theme="dynamic-substrate",
                purpose="Keep global product selection active while local substrate or product-specific blockers are recorded.",
                criteria=[
                    "A blocked local product or storage root records an owner blocker instead of setting global_status blocked.",
                    "Selection prefers unblocked product/revenue/contrib paths with an explicit proof command.",
                    "Private product/session details stay in .limen-private; tracked docs keep counts and hashes.",
                ],
                predicates=[
                    "python3 scripts/current-session-fanout.py --write",
                    "python3 scripts/product-ledger.py --refresh --private --redacted-summary",
                    "python3 scripts/substrate-ledger.py --write",
                ],
                stop_before=["deleting local roots", "spending money", "publishing private product/source data"],
                receipt="product/substrate ledger docs and private JSON indexes",
            )
        )
    if any(row["status"] == "blocked-local" for row in blockers):
        packets.append(
            packet(
                packet_id="OWNER-local-blockers",
                owner="blocking local owner ledgers",
                target_agent="codex",
                theme="blocked-local-work",
                purpose="Route unresolved local blockers to their owners without stopping the global fanout stream.",
                criteria=[
                    "Each blocker names its owner and cheapest next action.",
                    "Resolved transient test/doc failures are not treated as live blockers.",
                    "Whole-system verified is not claimed while task-board or storage blockers remain live.",
                ],
                predicates=[
                    "python3 scripts/validate-task-board.py",
                    "domus up --dry-run",
                    "bash scripts/verify-whole.sh",
                ],
                stop_before=["global dead-stop", "silent reopen of completed work", "storage mutation without owner gate"],
                receipt="Blocked Local Work section in docs/current-session-fanout.md",
                status="blocked-local-recorded",
            )
        )
    return packets


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    session = Path(args.session).expanduser()
    rows = load_jsonl(session)
    messages = extract_user_messages(rows)
    plans = extract_plan_updates(rows)
    commands = extract_commands(rows)
    patches = extract_patches(rows)
    themes = derive_themes(messages)
    blockers = derive_blockers(commands) + local_environment_blockers()
    file_counts = owner_file_counts(patches)
    plan_hashes = sorted({item["hash"] for plan_row in plans for item in plan_row.get("items") or []})
    prompt_hashes = [msg["hash"] for msg in messages]
    product_active = any(
        "product-ledger-active" in (command.get("success_signals") or []) for command in commands
    )
    source_display = relpath(session)
    owner_packets = build_owner_packets(
        packet_id=args.packet_id,
        theme=args.theme,
        session_display=source_display,
        blockers=blockers,
        themes=themes,
        file_counts=file_counts,
    )
    return {
        "version": 1,
        "generated_at": utc_now(),
        "packet_id": args.packet_id,
        "theme": args.theme,
        "source_session": {
            "path": str(session),
            "display_path": source_display,
            "path_hash": stable_hash(str(session), 24),
        },
        "coverage": {
            "jsonl_rows": len(rows),
            "user_message_occurrences": len(messages),
            "unique_prompt_hashes": len(set(prompt_hashes)),
            "plan_update_calls": len(plans),
            "unique_plan_hashes": len(plan_hashes),
            "commands": len(commands),
            "patches": len(patches),
            "patched_file_owners": file_counts,
            "events": event_counts(rows),
        },
        "provenance": {
            "provided_plan_hashes": sorted(set(args.source_plan_hash or [])),
            "provided_prompt_hashes": sorted(set(args.source_prompt_hash or [])),
            "derived_plan_hashes": plan_hashes,
            "derived_prompt_hashes": sorted(set(prompt_hashes)),
            "first_prompt_hash": prompt_hashes[0] if prompt_hashes else None,
            "last_prompt_hash": prompt_hashes[-1] if prompt_hashes else None,
        },
        "themes": themes,
        "owner_packets": owner_packets,
        "blocked_local_work": blockers,
        "global_product_selection": {
            "status": "active" if product_active or "money-inbound-seo" in themes else "ready-for-selection",
            "blocked_local_work_stops_global_selection": False,
            "evidence_command_hashes": [
                command["hash"]
                for command in commands
                if "product-ledger-active" in (command.get("success_signals") or [])
            ],
        },
        "command_counts": dict(Counter(str(command.get("category")) for command in commands).most_common()),
        "patch_file_counts": dict(Counter(path for patch in patches for path in patch.get("files") or []).most_common()),
        "public_safety": {
            "raw_prompt_bodies_written": False,
            "raw_plan_bodies_written": False,
            "tracked_output": str(DOC_PATH.relative_to(ROOT)),
            "private_output": str(PRIVATE_INDEX),
        },
    }


def render_count_map(counts: dict[str, Any]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in counts.items()) or "none"


def render_hashes(values: list[str], *, limit: int = 12) -> str:
    if not values:
        return "none"
    shown = values[:limit]
    suffix = f", ... +{len(values) - limit}" if len(values) > limit else ""
    return ", ".join(f"`{value}`" for value in shown) + suffix


def render_markdown(snapshot: dict[str, Any]) -> str:
    cov = snapshot["coverage"]
    prov = snapshot["provenance"]
    gps = snapshot["global_product_selection"]
    lines = [
        "# Current Session Fanout",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Packet: `{snapshot['packet_id']}`",
        f"Theme: `{snapshot['theme']}`",
        f"Source session: `{snapshot['source_session']['display_path']}`",
        "",
        "## Safety",
        "",
        "- This artifact contains no raw prompt bodies and no raw plan bodies.",
        "- Prompt and plan provenance is hash-only; private JSON keeps metadata only.",
        "- This is a planner receipt, not an external dispatch or spend action.",
        "",
        "## Full Session Coverage",
        "",
        f"- JSONL rows read: `{cov['jsonl_rows']}`.",
        f"- User message occurrences: `{cov['user_message_occurrences']}`; unique prompt hashes: `{cov['unique_prompt_hashes']}`.",
        f"- Plan update calls: `{cov['plan_update_calls']}`; unique derived plan hashes: `{cov['unique_plan_hashes']}`.",
        f"- Exec commands observed: `{cov['commands']}`; patch calls observed: `{cov['patches']}`.",
        f"- Command mix: {render_count_map(snapshot['command_counts'])}.",
        f"- Patched owner mix: {render_count_map(cov['patched_file_owners'])}.",
        "",
        "## Provenance Hashes",
        "",
        f"- Provided plan hashes: {render_hashes(prov['provided_plan_hashes'])}.",
        f"- Provided prompt hashes: {render_hashes(prov['provided_prompt_hashes'])}.",
        f"- Derived plan hashes: {render_hashes(prov['derived_plan_hashes'])}.",
        f"- Derived prompt hashes: {render_hashes(prov['derived_prompt_hashes'])}.",
        f"- First / last prompt hash: `{prov.get('first_prompt_hash')}` / `{prov.get('last_prompt_hash')}`.",
        "",
        "## Themes",
        "",
    ]
    for theme in snapshot["themes"]:
        lines.append(f"- `{theme}`")

    lines += [
        "",
        "## Owner Packets",
        "",
        "| Packet | Owner | Agent | Theme | Status | Receipt |",
        "|---|---|---|---|---|---|",
    ]
    for row in snapshot["owner_packets"]:
        lines.append(
            f"| `{row['id']}` | {row['owner']} | `{row['target_agent']}` | `{row['theme']}` | "
            f"`{row['status']}` | {row['receipt']} |"
        )

    for row in snapshot["owner_packets"]:
        lines += [
            "",
            f"## {row['id']}",
            "",
            f"Purpose: {row['purpose']}",
            "",
            "Executor Criteria:",
        ]
        lines.extend(f"- {item}" for item in row["executor_criteria"])
        lines += ["", "Verification Predicates:"]
        lines.extend(f"- `{item}`" for item in row["verification_predicates"])
        lines += ["", "Stop Before:"]
        lines.extend(f"- {item}" for item in row["stop_before"])

    lines += [
        "",
        "## Blocked Local Work",
        "",
        "| Blocker | Owner | Status | Global Product Selection | Next Action | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    blockers = snapshot["blocked_local_work"]
    if blockers:
        for row in blockers:
            evidence = render_hashes(row["evidence_command_hashes"], limit=4)
            lines.append(
                f"| `{row['id']}` | {row['owner']} | `{row['status']}` | "
                f"`{row['global_product_selection']}` | {row['next_action']} | {evidence} |"
            )
    else:
        lines.append("| none | n/a | n/a | `continue` | n/a | none |")

    lines += [
        "",
        "## Global Product Selection",
        "",
        f"- Status: `{gps['status']}`.",
        f"- Blocked local work stops global selection: `{gps['blocked_local_work_stops_global_selection']}`.",
        f"- Product selection evidence command hashes: {render_hashes(gps['evidence_command_hashes'])}.",
        "",
        "## Outputs",
        "",
        f"- Public fanout packet: `{snapshot['public_safety']['tracked_output']}`.",
        f"- Private metadata index: `{relpath(Path(snapshot['public_safety']['private_output']))}`.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown + "\n", encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_session() -> str:
    root = HOME / ".codex" / "sessions"
    if not root.exists():
        return ""
    files = sorted(root.rglob("*.jsonl"), key=lambda path: path.stat().st_mtime if path.exists() else 0)
    return str(files[-1]) if files else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a redacted current-session fanout packet.")
    parser.add_argument("--session", default=os.environ.get("LIMEN_CURRENT_SESSION_JSONL") or default_session())
    parser.add_argument("--packet-id", default="PLAN-11-f3f5e6a4")
    parser.add_argument("--theme", default="codex-planner-worktrees")
    parser.add_argument("--source-plan-hash", action="append", default=[])
    parser.add_argument("--source-prompt-hash", action="append", default=[])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not args.session:
        print("current-session-fanout: no session supplied or found", file=sys.stderr)
        return 2
    session = Path(args.session).expanduser()
    if not session.exists():
        print(f"current-session-fanout: session not found: {session}", file=sys.stderr)
        return 2

    snapshot = build_snapshot(args)
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
        print(f"current-session-fanout: ready; wrote {DOC_PATH} and {PRIVATE_INDEX}")
    else:
        print(markdown)
        print("current-session-fanout: ready; dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
