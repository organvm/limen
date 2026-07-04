#!/usr/bin/env python3
"""Koinonia fleet triage dashboard generator.

Reads engagement YAML records and produces a reviewable relationship dashboard.
It stages attention, gates, owed replies, and care posture; it never sends or
authorizes outbound action.

Usage:
  python organs/social/scripts/triage-dashboard.py
  python organs/social/scripts/triage-dashboard.py --out organs/social/engagements/triage-dashboard.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)


FMT = "%Y-%m-%dT%H:%M:%SZ"
STANDING_ORDER = {
    "STRAINED": 0,
    "BROKEN": 1,
    "PROTECTED": 2,
    "ACTIVE": 3,
    "WARM": 4,
    "DORMANT": 5,
}
STANDING_LABELS = {
    "STRAINED": "repair needed",
    "BROKEN": "closed or repair-gated",
    "PROTECTED": "boundary active",
    "ACTIVE": "current",
    "WARM": "maintain",
    "DORMANT": "reconnect only if appropriate",
}


def _generated_at(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return datetime.now(timezone.utc).strftime(FMT)


def _clip(value: str, limit: int = 72) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _read_engagements(engagements_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(engagements_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue

        member = _as_dict(doc.get("member"))
        mandate = _as_dict(doc.get("mandate"))
        standing = _as_dict(doc.get("standing"))
        standard = _as_dict(doc.get("standard"))
        governance = _as_dict(doc.get("governance"))
        artifacts = _as_dict(doc.get("artifacts"))

        current = str(standing.get("current", "")).upper()
        rows.append(
            {
                "source": path.name,
                "identifier": member.get("identifier") or path.stem,
                "name": member.get("name") or member.get("identifier") or path.stem,
                "relationship": mandate.get("relationship", ""),
                "standing": current,
                "label": STANDING_LABELS.get(current, "review standing"),
                "rank": STANDING_ORDER.get(current, 99),
                "warmth": standing.get("warmth", ""),
                "owed_replies": _as_list(standard.get("owed_replies")),
                "care_pattern": standard.get("care_pattern", ""),
                "next_output": artifacts.get("next_reviewable_output", ""),
                "manual_mode": governance.get("manual_mode") is True,
                "human": governance.get("human", ""),
                "human_gates": _as_list(governance.get("human_gates")),
                "never_autonomous": _as_list(governance.get("never_autonomous")),
                "updated": doc.get("updated", ""),
            }
        )
    return sorted(rows, key=lambda row: (row["rank"], str(row["name"]).lower()))


def generate_dashboard(base: Path, generated_at: str | None = None) -> str:
    engagements_dir = base / "engagements"
    if not engagements_dir.is_dir():
        raise FileNotFoundError(f"engagements directory not found: {engagements_dir}")

    rows = _read_engagements(engagements_dir)
    if not rows:
        return "No engagement records found.\n"

    lines: list[str] = []
    lines.append("# Koinonia - Triage Dashboard")
    lines.append("")
    lines.append(f"**Generated:** {_generated_at(generated_at)}")
    lines.append(f"**Engagements:** {len(rows)}")
    lines.append("**Outbound status:** draft-only; no autonomous messages, introductions, or care acts.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Fleet Overview")
    lines.append("")
    lines.append("| Person | Relationship | Standing | Owed Replies | Next Human Gate |")
    lines.append("|---|---|---|---|---|")
    for row in rows:
        owed = "; ".join(str(item) for item in row["owed_replies"]) or "-"
        gates = ", ".join(str(item) for item in row["human_gates"]) or "-"
        lines.append(
            "| {name} | {relationship} | **{standing}** ({label}) | {owed} | {gates} |".format(
                name=row["name"],
                relationship=row["relationship"],
                standing=row["standing"] or "UNKNOWN",
                label=row["label"],
                owed=_clip(owed),
                gates=_clip(gates),
            )
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Review Queue")
    lines.append("")
    for row in rows:
        lines.append(f"### {row['name']} - {row['standing'] or 'UNKNOWN'}")
        lines.append("")
        lines.append(f"- **Source:** `engagements/{row['source']}`")
        lines.append(f"- **Relationship:** {row['relationship']}")
        lines.append(f"- **Standing:** {row['standing'] or 'UNKNOWN'} - {row['label']}")
        if row["warmth"]:
            lines.append(f"- **Warmth:** {row['warmth']}")
        if row["owed_replies"]:
            lines.append("- **Owed replies:**")
            for item in row["owed_replies"]:
                lines.append(f"  - {item}")
        if row["care_pattern"]:
            lines.append(f"- **Care pattern:** {row['care_pattern']}")
        if row["next_output"]:
            lines.append(f"- **Next reviewable output:** {row['next_output']}")
        lines.append(
            f"- **Human gate held:** {'yes' if row['manual_mode'] else 'NO - REVIEW REQUIRED'}"
        )
        if row["human_gates"]:
            lines.append(f"- **Gate owner:** {row['human'] or 'human'}")
            lines.append("- **Gate list:**")
            for gate in row["human_gates"]:
                lines.append(f"  - {gate}")
        if row["never_autonomous"]:
            lines.append("- **Never autonomous:**")
            for item in row["never_autonomous"]:
                lines.append(f"  - {item}")
        if row["updated"]:
            lines.append(f"- **Last updated:** {row['updated']}")
        lines.append("")

    lines.append("## Boundary")
    lines.append("")
    lines.append(
        "This dashboard is an internal review surface. It stages attention; Anthony reviews, "
        "edits, sends, withholds, or archives every real social act."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Koinonia triage dashboard")
    parser.add_argument(
        "--base",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Social organ base directory; defaults to organs/social",
    )
    parser.add_argument("--out", type=Path, help="Write output to file instead of stdout")
    parser.add_argument(
        "--generated-at",
        help="Use an explicit ISO-8601 UTC timestamp for reproducible committed artifacts",
    )
    args = parser.parse_args()

    try:
        dashboard = generate_dashboard(args.base, generated_at=args.generated_at)
    except (OSError, yaml.YAMLError) as exc:
        print(f"ERROR: could not generate dashboard: {exc}", file=sys.stderr)
        return 1

    if args.out:
        args.out.write_text(dashboard, encoding="utf-8")
        print(f"Dashboard written to {args.out}")
    else:
        print(dashboard)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
