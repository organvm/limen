#!/usr/bin/env python3
"""Validate legal-organ matter packets.

Usage:
  python organs/legal/validate-legal.py path/to/matter
  python organs/legal/validate-legal.py --fleet
  python organs/legal/validate-legal.py --fleet --quiet
  python organs/legal/validate-legal.py --checklist
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


REQUIRED_FILES = [
    "README.md",
    "intake.md",
    "posture.md",
    "evidence-index.csv",
    "chain-of-custody.md",
    "deadlines.md",
    "ethics-log.md",
    "MICAH-FRAMEWORK-DECK.md",
]
REQUIRED_EVIDENCE_COLUMNS = [
    "evidence_id",
    "date_or_range",
    "source_kind",
    "source_or_location",
    "custodian_or_source",
    "artifact_type",
    "provenance",
    "chain_of_custody",
    "operational_use",
    "review_status",
    "privilege_confidentiality",
    "notes",
]
REVIEW_STATUSES = {
    "structure_ready",
    "counsel_review_needed",
    "missing_input",
    "attorney_work_product_needed",
}
BOUNDARY_PHRASES = [
    "does not give legal advice",
    "counsel",
]
OUTBOUND_DRAFT_MARKER = "DRAFT - NOT SENT"
OVERREACH_PATTERNS = [
    "we will file",
    "the system will send",
    "guaranteed outcome",
    "you should sue",
    "claim is valid",
    "settlement demand is approved",
]
RULES: list[tuple[int, str]] = [
    (1, "Matter packet has all first-slice artifacts"),
    (2, "Boundary language keeps legal judgment with counsel"),
    (3, "Evidence index has required custody columns and stable IDs"),
    (4, "Evidence rows distinguish ready structure from missing private inputs"),
    (5, "Outbound-facing drafts are watermarked staged-only"),
    (6, "Deck links the live matter packet and evidence surface"),
]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _markdown_files(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*.md") if p.is_file())


def _validate_required_files(path: Path, violations: list[str]) -> None:
    for rel in REQUIRED_FILES:
        if not (path / rel).is_file():
            violations.append(f"Rule #1 violation: missing required artifact {rel!r}")


def _validate_boundaries(path: Path, violations: list[str]) -> None:
    required_markdown = [
        "README.md",
        "intake.md",
        "posture.md",
        "deadlines.md",
        "ethics-log.md",
        "MICAH-FRAMEWORK-DECK.md",
    ]
    for rel in required_markdown:
        text = _read_text(path / rel).lower()
        if not text:
            continue
        for phrase in BOUNDARY_PHRASES:
            if phrase not in text:
                violations.append(
                    f"Rule #2 violation: {rel} missing boundary phrase {phrase!r}"
                )

    all_text = "\n".join(_read_text(p) for p in _markdown_files(path)).lower()
    for pattern in OVERREACH_PATTERNS:
        if pattern in all_text:
            violations.append(f"Rule #2 violation: overreach pattern present: {pattern!r}")


def _validate_evidence_index(path: Path, violations: list[str]) -> None:
    evidence_path = path / "evidence-index.csv"
    try:
        with evidence_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    except OSError as exc:
        violations.append(f"Rule #3 violation: cannot read evidence-index.csv: {exc}")
        return
    except csv.Error as exc:
        violations.append(f"Rule #3 violation: CSV parse error: {exc}")
        return

    fieldnames = reader.fieldnames or []
    for column in REQUIRED_EVIDENCE_COLUMNS:
        if column not in fieldnames:
            violations.append(f"Rule #3 violation: missing evidence column {column!r}")

    if not rows:
        violations.append("Rule #3 violation: evidence-index.csv has no rows")
        return

    seen_ids: set[str] = set()
    ready_rows = 0
    missing_rows = 0
    for idx, row in enumerate(rows, start=2):
        evidence_id = (row.get("evidence_id") or "").strip()
        if not evidence_id:
            violations.append(f"Rule #3 violation: row {idx} missing evidence_id")
        elif evidence_id in seen_ids:
            violations.append(f"Rule #3 violation: duplicate evidence_id {evidence_id!r}")
        else:
            seen_ids.add(evidence_id)

        for column in REQUIRED_EVIDENCE_COLUMNS:
            if not (row.get(column) or "").strip():
                violations.append(
                    f"Rule #3 violation: row {idx} ({evidence_id or 'unknown'}) "
                    f"has empty {column!r}"
                )

        status = (row.get("review_status") or "").strip()
        if status not in REVIEW_STATUSES:
            violations.append(
                f"Rule #4 violation: row {idx} ({evidence_id or 'unknown'}) "
                f"has unknown review_status {status!r}"
            )
        if status == "structure_ready":
            ready_rows += 1
        if status == "missing_input":
            missing_rows += 1

    if ready_rows == 0:
        violations.append("Rule #4 violation: index has no structure_ready rows")
    if missing_rows == 0:
        violations.append("Rule #4 violation: index has no missing_input rows")


def _validate_drafts(path: Path, violations: list[str]) -> None:
    drafts_dir = path / "drafts"
    if not drafts_dir.exists():
        return
    for draft in sorted(drafts_dir.glob("*.md")):
        text = _read_text(draft)
        if OUTBOUND_DRAFT_MARKER not in text:
            violations.append(
                f"Rule #5 violation: outbound draft {draft.relative_to(path)} "
                f"missing {OUTBOUND_DRAFT_MARKER!r}"
            )
        lowered = text.lower()
        if "not send" not in lowered and "not sent" not in lowered:
            violations.append(
                f"Rule #5 violation: outbound draft {draft.relative_to(path)} "
                "does not say it is not sent"
            )


def _validate_deck(path: Path, violations: list[str]) -> None:
    deck = _read_text(path / "MICAH-FRAMEWORK-DECK.md")
    if not deck:
        return
    required_refs = [
        "organs/legal/matters/anthony-ada-employment/",
        "posture.md",
        "evidence-index.csv",
        "chain-of-custody.md",
        "ethics-log.md",
    ]
    for ref in required_refs:
        if ref not in deck:
            violations.append(f"Rule #6 violation: deck missing reference {ref!r}")


def validate_one(path: Path) -> list[str]:
    violations: list[str] = []
    if not path.is_dir():
        return [f"matter path is not a directory: {path}"]

    _validate_required_files(path, violations)
    _validate_boundaries(path, violations)
    _validate_evidence_index(path, violations)
    _validate_drafts(path, violations)
    _validate_deck(path, violations)
    return violations


def _fleet_paths(base: Path) -> list[Path]:
    matters = base / "matters"
    if not matters.exists():
        return []
    return sorted(p for p in matters.iterdir() if p.is_dir())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate legal-organ matter packets against review-first guardrails."
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--fleet", action="store_true", help="validate all legal matter packets")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--checklist", action="store_true", help="print executable rules and exit")
    args = parser.parse_args()

    if args.checklist:
        for number, rule in RULES:
            print(f"Rule #{number}: {rule}")
        return 0

    base = Path(__file__).resolve().parent
    paths = _fleet_paths(base) if args.fleet else args.paths
    if not paths:
        parser.error("provide path(s) or --fleet")

    failures = 0
    for path in paths:
        violations = validate_one(path)
        if violations:
            failures += 1
            print(f"FAIL  {path}")
            for violation in violations:
                print(f"  - {violation}")
        elif not args.quiet:
            print(f"PASS  {path}")

    if not args.quiet:
        print()
        print(f"{len(paths) - failures}/{len(paths)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
