#!/usr/bin/env python3
"""Build the prompt acceptance ledger.

This layer sits above the prompt lifecycle, priority, batch, and packet ledgers.
It does not read raw prompt bodies. Public output stays redacted; the ignored
private index keeps the hash/session membership needed to reproduce the receipt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)

BATCH_REVIEW_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"
PRIORITY_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
PACKET_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
LIFECYCLE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
AUG1_VIEW_PATH = ROOT / "logs" / "aug1-view.json"
OUTWARD_RECIPROCITY_PATH = ROOT / "state" / "outward-reciprocity.json"
DOC_PATH = ROOT / "docs" / "prompt-acceptance-ledger.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-acceptance-ledger.json"

ACCEPTANCE_FRAME = (
    "prompt_receipt",
    "evolved_intent",
    "owner_outcome",
    "august_runway_impact",
    "outward_reciprocity",
)

RECORDED_PACKET_STATUSES = {
    "owner-recorded",
    "current-state-recorded",
    "non-source-recorded",
    "superseded-recorded",
}

RECORDED_BATCH_STATUSES = {
    "owner-recorded",
    "current-state-recorded",
    "non-source-recorded",
    "superseded-recorded",
    "parked-secret",
}

VALID_RECIPROCITY_STATUSES = {
    "observed",
    "absorbed",
    "staged",
    "gated",
    "delivered",
    "not_applicable",
}

RECIPROCITY_PRIORITY = {
    "gated": 0,
    "staged": 1,
    "observed": 2,
    "absorbed": 3,
    "delivered": 4,
    "not_applicable": 5,
}

AUGUST_OPERATIONAL_CHECKPOINT = "2026-08-01"
LATE_AUGUST_HARD_RUNWAY_PREMISE = "late-August unemployment runway"
LATE_AUGUST_RUNWAY_NOTE = (
    "Aug-1 remains the operational checkpoint; late-August unemployment remains the hard runway premise."
)


def load_json(path: Path, default: Any | None = None) -> Any:
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return default


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    raw = str(value)
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def ts_sort_value(value: Any) -> float:
    parsed = parse_ts(value)
    return parsed.timestamp() if parsed else -1.0


def recency_label(value: Any, now: dt.datetime) -> str:
    parsed = parse_ts(value)
    if parsed is None:
        return "unknown"
    age = now - parsed
    if age.total_seconds() < 0:
        return "future/clock-skew"
    days = age.total_seconds() / 86400
    if days <= 1:
        return "<=1d"
    if days <= 7:
        return "<=7d"
    if days <= 30:
        return "<=30d"
    if days <= 120:
        return "<=120d"
    return ">120d lineage"


def session_lookup(priority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["session_key"]): item
        for item in priority.get("session_items") or []
        if isinstance(item, dict) and item.get("session_key")
    }


def compact_counts(counter: Counter[str], *, limit: int = 8) -> dict[str, int]:
    return dict(counter.most_common(limit))


def render_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in counts.items()) or "none"


def packet_is_closed(packet: dict[str, Any]) -> bool:
    return str(packet.get("status") or "") in RECORDED_PACKET_STATUSES


def batch_is_closed(batch: dict[str, Any]) -> bool:
    return str(batch.get("status") or "") in RECORDED_BATCH_STATUSES


def session_span(
    session_keys: list[str],
    sessions_by_key: dict[str, dict[str, Any]],
    *,
    fallback_prompt_events: int = 0,
) -> dict[str, Any]:
    rows = [sessions_by_key[key] for key in session_keys if key in sessions_by_key]
    first_values = [row.get("first_event") for row in rows if row.get("first_event")]
    last_values = [row.get("last_event") for row in rows if row.get("last_event")]
    prompt_events = sum(int(row.get("prompt_events") or row.get("prompt_event_count") or 0) for row in rows)
    if not prompt_events:
        prompt_events = int(fallback_prompt_events or 0)
    prompt_hashes: list[str] = []
    for row in rows:
        prompt_hashes.extend(str(value) for value in row.get("prompt_hashes") or [] if value)
    lineage_weight = len(session_keys) + len(set(prompt_hashes)) + prompt_events
    return {
        "first_event": min(first_values) if first_values else None,
        "last_event": max(last_values) if last_values else None,
        "prompt_events": prompt_events,
        "prompt_hashes": prompt_hashes,
        "unique_prompt_hashes": len(set(prompt_hashes)),
        "lineage_weight": lineage_weight,
    }


def load_reciprocity(path: Path = OUTWARD_RECIPROCITY_PATH) -> dict[str, Any]:
    obj = load_json(path, {"receipts": []})
    if not isinstance(obj, dict):
        obj = {"receipts": []}
    receipts = [item for item in obj.get("receipts") or [] if isinstance(item, dict)]
    invalid = sorted(
        {
            str(receipt.get("status") or "")
            for receipt in receipts
            if str(receipt.get("status") or "") not in VALID_RECIPROCITY_STATUSES
        }
    )
    if invalid:
        raise ValueError(f"invalid outward reciprocity status: {', '.join(invalid)}")
    obj["receipts"] = receipts
    return obj


def reciprocity_matches(packet: dict[str, Any], receipt: dict[str, Any]) -> bool:
    packet_id = str(packet.get("id") or "")
    source_batch = str(packet.get("source_batch") or "")
    family = str(packet.get("family") or "")
    return (
        packet_id in {str(value) for value in receipt.get("related_packets") or []}
        or source_batch in {str(value) for value in receipt.get("related_batches") or []}
        or family in {str(value) for value in receipt.get("related_families") or []}
    )


def reciprocity_for_packet(packet: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    related = [receipt for receipt in receipts if reciprocity_matches(packet, receipt)]
    if not related:
        return {
            "status": "not_applicable",
            "receipt_ids": [],
            "summary": "No outward reciprocity receipt is required for this packet.",
            "human_gate_required": False,
        }
    statuses = sorted(
        {str(receipt.get("status") or "not_applicable") for receipt in related},
        key=lambda item: RECIPROCITY_PRIORITY.get(item, 99),
    )
    status = statuses[0]
    summaries = [
        str(receipt.get("public_safe_summary") or receipt.get("summary") or receipt.get("id") or "").strip()
        for receipt in related
    ]
    summaries = [item for item in summaries if item]
    return {
        "status": status,
        "receipt_ids": [str(receipt.get("id") or "") for receipt in related if receipt.get("id")],
        "summary": summaries[0] if summaries else "Outward reciprocity receipt attached.",
        "human_gate_required": any(bool(receipt.get("human_gate_required")) for receipt in related),
    }


def acceptance_status(owner_status: str, reciprocity: dict[str, Any], *, source_kind: str) -> str:
    if reciprocity.get("status") in {"staged", "gated"}:
        return "needs_reciprocity_gate"
    if source_kind == "prompt_batch":
        if owner_status in {"needs-private-review", "needs-private-inspection"}:
            return "needs_private_review"
        if owner_status in {"needs-owner-route", "needs-remote-proof", "needs-packetization"}:
            return "needs_owner_outcome"
        return "closed" if owner_status in RECORDED_BATCH_STATUSES else "needs_owner_outcome"
    return "closed" if owner_status in RECORDED_PACKET_STATUSES else "needs_owner_outcome"


def runway_impact_for_family(family: str) -> str:
    if family == "session_lifecycle":
        return "Closes repeated session residue so August work is not re-prompted as fresh work."
    if family == "worktree_lifecycle":
        return "Protects August execution time by preserving or closing local worktree residue."
    if family == "github_review":
        return "Only advances the runway after owner repo, branch or PR, predicate, and receipt are explicit."
    if family == "agent_coordination":
        return "Prevents broad delegation churn from spending runway without owner receipts."
    if family == "technical_debt_ci":
        return "Must reduce a named blocker or shorten the path to a revenue-facing artifact."
    return "Accepted only after it records an owner outcome that changes the August path."


def build_packet_receipt(
    packet: dict[str, Any],
    sessions_by_key: dict[str, dict[str, Any]],
    reciprocity_receipts: list[dict[str, Any]],
    now: dt.datetime,
) -> dict[str, Any]:
    session_keys = [str(value) for value in packet.get("session_keys") or [] if value]
    span = session_span(
        session_keys,
        sessions_by_key,
        fallback_prompt_events=int(packet.get("prompt_events") or 0),
    )
    family = str(packet.get("family") or "uncategorized")
    owner_status = str(packet.get("status") or "packetized")
    reciprocity = reciprocity_for_packet(packet, reciprocity_receipts)
    status = acceptance_status(owner_status, reciprocity, source_kind="prompt_packet")
    last_event = span.get("last_event")
    return {
        "id": f"accept-{packet.get('id')}",
        "source_kind": "prompt_packet",
        "source_ref": str(packet.get("id") or ""),
        "source_batch": str(packet.get("source_batch") or ""),
        "family": family,
        "acceptance_status": status,
        "prompt_receipt": {
            "covered": bool(session_keys or packet.get("prompt_events")),
            "source_batch": packet.get("source_batch"),
            "session_count": len(session_keys),
            "prompt_events": int(packet.get("prompt_events") or span["prompt_events"] or 0),
            "unique_prompt_hashes": int(packet.get("unique_prompt_hashes") or span["unique_prompt_hashes"] or 0),
            "session_keys": session_keys,
            "prompt_hashes": [str(value) for value in packet.get("prompt_hashes") or span["prompt_hashes"]],
            "first_event": span.get("first_event"),
            "last_event": last_event,
            "recency": recency_label(last_event, now),
            "lineage_weight": span["lineage_weight"],
        },
        "evolved_intent": {
            "covered": True,
            "rule": "newer form wins; earlier repeats count as lineage evidence",
            "summary": "The packet carries older prompt lineage without letting older wording outrank the current owner outcome.",
        },
        "owner_outcome": {
            "covered": packet_is_closed(packet),
            "status": owner_status,
            "owner": packet.get("owner") or "unassigned",
            "outcome": (packet.get("resolution") or {}).get("next_action") or packet.get("route") or "",
        },
        "august_runway_impact": {
            "covered": True,
            "operational_checkpoint": AUGUST_OPERATIONAL_CHECKPOINT,
            "hard_runway_premise": LATE_AUGUST_HARD_RUNWAY_PREMISE,
            "note": LATE_AUGUST_RUNWAY_NOTE,
            "impact": runway_impact_for_family(family),
        },
        "outward_reciprocity": reciprocity,
    }


def build_batch_receipt(
    batch: dict[str, Any],
    sessions_by_key: dict[str, dict[str, Any]],
    reciprocity_receipts: list[dict[str, Any]],
    now: dt.datetime,
) -> dict[str, Any]:
    session_keys = [str(value) for value in batch.get("session_keys") or [] if value]
    span = session_span(
        session_keys,
        sessions_by_key,
        fallback_prompt_events=int(batch.get("prompt_events") or 0),
    )
    family_counts = batch.get("families") if isinstance(batch.get("families"), dict) else {}
    family = next(iter(family_counts), "uncategorized")
    owner_status = str(batch.get("status") or "needs-private-review")
    packet_shape = {"id": batch.get("id"), "source_batch": batch.get("id"), "family": family}
    reciprocity = reciprocity_for_packet(packet_shape, reciprocity_receipts)
    status = acceptance_status(owner_status, reciprocity, source_kind="prompt_batch")
    last_event = span.get("last_event")
    return {
        "id": f"accept-{batch.get('id')}",
        "source_kind": "prompt_batch",
        "source_ref": str(batch.get("id") or ""),
        "source_batch": str(batch.get("id") or ""),
        "family": family,
        "acceptance_status": status,
        "prompt_receipt": {
            "covered": bool(session_keys or batch.get("prompt_events")),
            "source_batch": batch.get("id"),
            "session_count": len(session_keys),
            "prompt_events": int(batch.get("prompt_events") or span["prompt_events"] or 0),
            "unique_prompt_hashes": int(batch.get("unique_prompt_hashes") or span["unique_prompt_hashes"] or 0),
            "session_keys": session_keys,
            "prompt_hashes": [str(value) for value in batch.get("prompt_hashes") or span["prompt_hashes"]],
            "first_event": span.get("first_event"),
            "last_event": last_event,
            "recency": recency_label(last_event, now),
            "lineage_weight": span["lineage_weight"],
        },
        "evolved_intent": {
            "covered": True,
            "rule": "newer form wins; earlier repeats count as lineage evidence",
            "summary": "The batch is accepted only after its newest owner route supersedes older repeated wording.",
        },
        "owner_outcome": {
            "covered": batch_is_closed(batch),
            "status": owner_status,
            "owner": batch.get("owner") or "unassigned",
            "outcome": batch.get("next_action") or batch.get("gate") or "",
        },
        "august_runway_impact": {
            "covered": True,
            "operational_checkpoint": AUGUST_OPERATIONAL_CHECKPOINT,
            "hard_runway_premise": LATE_AUGUST_HARD_RUNWAY_PREMISE,
            "note": LATE_AUGUST_RUNWAY_NOTE,
            "impact": runway_impact_for_family(str(family)),
        },
        "outward_reciprocity": reciprocity,
    }


def acceptance_sort_key(row: dict[str, Any]) -> tuple[int, float, int, str]:
    status_rank = {
        "needs_reciprocity_gate": 0,
        "needs_owner_outcome": 1,
        "needs_private_review": 2,
        "closed": 3,
    }.get(str(row.get("acceptance_status") or ""), 4)
    receipt = row.get("prompt_receipt") or {}
    # Newer evolved forms win before lineage weight. Lineage is the tiebreaker.
    return (
        status_rank,
        -ts_sort_value(receipt.get("last_event")),
        -int(receipt.get("lineage_weight") or 0),
        str(row.get("id") or ""),
    )


def august_panel() -> dict[str, Any]:
    view = load_json(AUG1_VIEW_PATH, {})
    gate = view.get("gate") if isinstance(view, dict) else {}
    legs = gate.get("legs", []) if isinstance(gate, dict) else []
    return {
        "operational_checkpoint": AUGUST_OPERATIONAL_CHECKPOINT,
        "deadline": view.get("deadline") or AUGUST_OPERATIONAL_CHECKPOINT,
        "gate_pass": bool(gate.get("pass")) if isinstance(gate, dict) else False,
        "legs_total": len(legs),
        "legs_met": sum(1 for leg in legs if isinstance(leg, dict) and leg.get("ok")),
        "next_act": view.get("next_act"),
        "hard_runway_premise": LATE_AUGUST_HARD_RUNWAY_PREMISE,
        "late_august_runway_note": LATE_AUGUST_RUNWAY_NOTE,
    }


def build_snapshot(limit: int) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    review = load_json(BATCH_REVIEW_INDEX, {})
    priority = load_json(PRIORITY_INDEX, {})
    packets_index = load_json(PACKET_INDEX, {})
    lifecycle = load_json(LIFECYCLE_INDEX, {})
    reciprocity = load_reciprocity(OUTWARD_RECIPROCITY_PATH)
    reciprocity_receipts = reciprocity.get("receipts") or []
    sessions_by_key = session_lookup(priority)

    packets = [item for item in packets_index.get("packets") or [] if isinstance(item, dict)]
    rows = [
        build_packet_receipt(packet, sessions_by_key, reciprocity_receipts, now)
        for packet in packets
    ]

    packet_batches = {str(packet.get("source_batch")) for packet in packets if packet.get("source_batch")}
    batch_candidates = []
    for batch in (review.get("review_queue") or []) + (review.get("batches") or []):
        if not isinstance(batch, dict) or not batch.get("id"):
            continue
        if str(batch["id"]) in packet_batches:
            continue
        if batch_is_closed(batch) and str(batch.get("status")) != "parked-secret":
            continue
        batch_candidates.append(batch)
    seen_batches: set[str] = set()
    for batch in batch_candidates:
        batch_id = str(batch["id"])
        if batch_id in seen_batches:
            continue
        seen_batches.add(batch_id)
        rows.append(build_batch_receipt(batch, sessions_by_key, reciprocity_receipts, now))

    rows.sort(key=acceptance_sort_key)
    acceptance_counts = Counter(str(row["acceptance_status"]) for row in rows)
    packet_status_counts = Counter(str(packet.get("status") or "unknown") for packet in packets)
    reciprocity_counts = Counter(str(receipt.get("status") or "not_applicable") for receipt in reciprocity_receipts)
    closed_packets = sum(1 for packet in packets if packet_is_closed(packet))
    open_packets = len(packets) - closed_packets
    generated_at = now.isoformat(timespec="seconds")
    snapshot = {
        "generated_at": generated_at,
        "acceptance_frame": list(ACCEPTANCE_FRAME),
        "privacy": {
            "public_contains_raw_prompt_text": False,
            "private_contains_hash_session_evidence": True,
            "raw_prompt_bodies_read": False,
        },
        "inputs": {
            "prompt_batch_review_ledger": {"path": str(BATCH_REVIEW_INDEX), "present": bool(review)},
            "prompt_priority_map": {"path": str(PRIORITY_INDEX), "present": bool(priority)},
            "prompt_packet_ledger": {"path": str(PACKET_INDEX), "present": bool(packets_index)},
            "prompt_lifecycle_index": {"path": str(LIFECYCLE_INDEX), "present": bool(lifecycle)},
            "outward_reciprocity": {"path": str(OUTWARD_RECIPROCITY_PATH), "present": bool(reciprocity_receipts)},
        },
        "coverage": {
            "acceptance_packets": len(rows),
            "prompt_packets_total": len(packets),
            "prompt_packets_open": open_packets,
            "prompt_packets_closed": closed_packets,
            "source_review_batches": len(review.get("batches") or []),
            "unpacketed_review_batches": len(seen_batches),
            "prompt_events": sum(int((row.get("prompt_receipt") or {}).get("prompt_events") or 0) for row in rows),
            "unique_prompt_hash_refs": sum(int((row.get("prompt_receipt") or {}).get("unique_prompt_hashes") or 0) for row in rows),
            "reciprocity_receipts": len(reciprocity_receipts),
        },
        "counts": {
            "acceptance_statuses": compact_counts(acceptance_counts),
            "packet_statuses": compact_counts(packet_status_counts),
            "reciprocity_statuses": compact_counts(reciprocity_counts),
        },
        "august": august_panel(),
        "reciprocity": {
            "valid_statuses": sorted(VALID_RECIPROCITY_STATUSES),
            "counts": compact_counts(reciprocity_counts),
            "receipts": reciprocity_receipts,
        },
        "acceptance_packets": rows,
        "public_packets": redact_packets_for_public(rows[:limit]),
        "private_index": str(PRIVATE_INDEX),
    }
    validate_redacted_markdown(render_markdown(snapshot, limit=limit))
    return snapshot


def redact_packets_for_public(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public_rows = []
    for row in rows:
        receipt = row.get("prompt_receipt") or {}
        owner = row.get("owner_outcome") or {}
        owner_public_outcome = (
            "Owner outcome recorded in the private acceptance index."
            if owner.get("covered")
            else "Owner outcome still pending in the private acceptance index."
        )
        public_rows.append(
            {
                "id": row.get("id"),
                "source_kind": row.get("source_kind"),
                "source_ref": row.get("source_ref"),
                "family": row.get("family"),
                "acceptance_status": row.get("acceptance_status"),
                "prompt_receipt": {
                    "covered": receipt.get("covered"),
                    "session_count": receipt.get("session_count"),
                    "prompt_events": receipt.get("prompt_events"),
                    "unique_prompt_refs": receipt.get("unique_prompt_hashes"),
                    "first_event": receipt.get("first_event"),
                    "last_event": receipt.get("last_event"),
                    "recency": receipt.get("recency"),
                    "lineage_weight": receipt.get("lineage_weight"),
                },
                "evolved_intent": row.get("evolved_intent"),
                "owner_outcome": {
                    "covered": owner.get("covered"),
                    "status": owner.get("status"),
                    "owner": owner.get("owner"),
                    "outcome": owner_public_outcome,
                },
                "august_runway_impact": row.get("august_runway_impact"),
                "outward_reciprocity": row.get("outward_reciprocity"),
            }
        )
    return public_rows


def validate_redacted_markdown(markdown: str) -> None:
    forbidden = [
        "prompt_hashes",
        "session_keys",
        "private_source_path",
        "private_display_path",
        str(PRIVATE_ROOT),
        "RAW_PRIVATE_PROMPT",
        "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR",
    ]
    hits = [item for item in forbidden if item and item in markdown]
    if hits:
        raise ValueError(f"prompt acceptance markdown leaks private evidence: {hits}")


def render_bool(value: Any) -> str:
    return "yes" if value else "no"


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    coverage = snapshot["coverage"]
    august = snapshot["august"]
    lines = [
        "# Prompt Acceptance Ledger",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Acceptance Frame",
        "",
        "- `prompt_receipt`: What did we prompt, represented only by redacted ids/counts in tracked output.",
        "- `evolved_intent`: What got addressed now; older repeats carry lineage weight, newer forms win.",
        "- `owner_outcome`: What remains owner-recorded, closed, parked, or still needing a route.",
        "- `august_runway_impact`: Whether this helps the Aug-1 operating checkpoint and late-August runway.",
        "- `outward_reciprocity`: What was observed, absorbed, staged, gated, delivered, or not applicable.",
        "",
        "Tracked output contains no raw prompt bodies, private session paths, full prompt hashes, or session ids.",
        "",
        "## Coverage",
        "",
        f"- Acceptance packets: `{coverage['acceptance_packets']}`.",
        f"- Prompt packets: `{coverage['prompt_packets_closed']}` closed / `{coverage['prompt_packets_open']}` open / `{coverage['prompt_packets_total']}` total.",
        f"- Unpacketed review batches represented: `{coverage['unpacketed_review_batches']}`.",
        f"- Prompt events covered: `{coverage['prompt_events']}`.",
        f"- Unique prompt hash refs covered privately: `{coverage['unique_prompt_hash_refs']}`.",
        f"- Acceptance status mix: {render_counts(snapshot['counts']['acceptance_statuses'])}.",
        f"- Packet status mix: {render_counts(snapshot['counts']['packet_statuses'])}.",
        "",
        "## August Runway",
        "",
        f"- Operational checkpoint: `{august['operational_checkpoint']}`.",
        f"- Aug-1 gate: `{'pass' if august.get('gate_pass') else 'false'}`; legs `{august.get('legs_met')}` / `{august.get('legs_total')}`.",
        f"- Hard runway premise: {august['hard_runway_premise']}.",
        f"- Runway note: {august['late_august_runway_note']}",
        "",
        "## Outward Reciprocity",
        "",
        f"- Status values: {', '.join(f'`{item}`' for item in sorted(VALID_RECIPROCITY_STATUSES))}.",
        f"- Receipt count: `{coverage['reciprocity_receipts']}`.",
        f"- Status mix: {render_counts(snapshot['counts']['reciprocity_statuses'])}.",
        "- Identity-bearing outbound action stays human-gated; staged receipts are not sent automatically.",
        "",
        "## Acceptance Queue",
        "",
        "| Rank | Receipt | Status | Source | Prompt Coverage | Evolved Intent | Owner Outcome | August Impact | Reciprocity |",
        "|---:|---|---|---|---|---|---|---|---|",
    ]
    for rank, row in enumerate(snapshot["public_packets"][:limit], start=1):
        prompt = row["prompt_receipt"]
        owner = row["owner_outcome"]
        august_impact = row["august_runway_impact"]
        reciprocity = row["outward_reciprocity"]
        coverage_bit = (
            f"{prompt.get('session_count', 0)} sessions; "
            f"{prompt.get('prompt_events', 0)} events; {prompt.get('recency')}; "
            f"lineage {prompt.get('lineage_weight', 0)}"
        )
        owner_bit = f"`{owner.get('status')}`; {owner.get('outcome') or 'no owner outcome yet'}"
        reciprocity_bit = f"`{reciprocity.get('status')}`"
        if reciprocity.get("human_gate_required"):
            reciprocity_bit += "; human gate"
        lines.append(
            f"| {rank} | `{row['source_ref']}` | `{row['acceptance_status']}` | "
            f"{row['source_kind']} / `{row['family']}` | {coverage_bit} | "
            f"{row['evolved_intent']['rule']} | {owner_bit} | {august_impact['impact']} | {reciprocity_bit} |"
        )
    if not snapshot["public_packets"]:
        lines.append("| 0 | none | n/a | n/a | none | n/a | n/a | n/a | n/a |")

    lines += [
        "",
        "## Private Output",
        "",
        f"- Private acceptance index: `{relpath(PRIVATE_INDEX)}`.",
        "- The private index keeps packet membership, full prompt hashes, session keys, and reciprocity links.",
        "",
        "## Commands",
        "",
        "- Refresh prerequisite packet ledger: `python3 scripts/prompt-packet-ledger.py --write`",
        "- Refresh acceptance ledger: `python3 scripts/prompt-acceptance-ledger.py --write`",
        "- Show a wider tracked slice: `python3 scripts/prompt-acceptance-ledger.py --write --limit 80`",
        "",
    ]
    markdown = "\n".join(lines)
    validate_redacted_markdown(markdown)
    return markdown


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build redacted prompt acceptance ledger.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--limit", type=int, default=40, help="acceptance rows to show in tracked docs")
    args = parser.parse_args()

    snapshot = build_snapshot(limit=max(1, args.limit))
    markdown = render_markdown(snapshot, limit=max(1, args.limit))
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = (
        "prompt-acceptance-ledger: "
        f"{snapshot['coverage']['acceptance_packets']} acceptance packets, "
        f"{snapshot['coverage']['prompt_packets_closed']} closed prompt packets, "
        f"{snapshot['coverage']['prompt_packets_open']} open prompt packets"
    )
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
