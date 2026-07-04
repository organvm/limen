#!/usr/bin/env python3
"""Validate legal-organ matter packets.

The legal organ may organize matter operations, evidence indexes, and draft review
packets. It must not practice law, give legal advice, file, serve, send, or make
legal judgments. This validator checks the local matter-packet surface that proves
those boundaries in executable form.

Usage:
  python organs/legal/validate-legal.py path/to/matter.yaml
  python organs/legal/validate-legal.py --fleet
  python organs/legal/validate-legal.py --fleet --quiet
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent

STANDINGS = ["INTAKE", "INDEXED", "COUNSEL_REVIEW", "ACTIVE", "HOLD", "CLOSED"]
REQUIRED_PRIMITIVES = ["member", "mandate", "standing", "standard", "governance"]
REQUIRED_ARTIFACTS = [
    "posture",
    "evidence_index",
    "chain_of_custody",
    "elements_map",
    "deadlines",
    "ethics_log",
    "review_note",
    "framework_deck",
]
REQUIRED_CSV_COLUMNS = [
    "evidence_id",
    "title",
    "source_path",
    "source_type",
    "record_date",
    "ingested_at",
    "provenance_owner",
    "custody_status",
    "custody_entry",
    "evidence_role",
    "linked_elements",
    "confidentiality",
    "review_status",
    "notes",
]
FORBIDDEN_ACTS = {
    "legal advice",
    "filing",
    "service",
    "sending external communications",
    "settlement authority",
    "legal judgment",
}
REQUIRED_GOVERNANCE_FLAGS = [
    "counsel_review_required",
    "draft_only",
    "no_autonomous_external_action",
    "no_independent_attorney_client_relationship",
]
OVERREACH_PATTERNS = [
    "we will file",
    "will be filed",
    "send this to",
    "serve this on",
    "you should sue",
    "you should file",
    "is liable",
    "guaranteed outcome",
    "legal advice provided",
    "attorney-client relationship is created",
]
PLACEHOLDER_PATTERNS = ["todo", "tbd", "fixme", "placeholder", "to be determined"]


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text(v) for v in value)
    return str(value or "")


def _standing(doc: dict[str, Any]) -> str:
    raw = doc.get("standing")
    if isinstance(raw, dict):
        return str(raw.get("current", "")).upper()
    return str(raw or "").upper()


def _resolve_artifact(matter_path: Path, value: Any) -> Path:
    raw = Path(str(value))
    if raw.is_absolute():
        return raw
    return (matter_path.parent / raw).resolve()


def _validate_markdown(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    violations: list[str] = []
    if "draft" not in lowered:
        violations.append(f"{path}: missing DRAFT marker")
    if "not legal advice" not in lowered and "no legal advice" not in lowered:
        violations.append(f"{path}: missing no-legal-advice marker")
    for pattern in OVERREACH_PATTERNS:
        if pattern in lowered:
            violations.append(f"{path}: overreach pattern present: {pattern!r}")
    return violations


def _validate_evidence_index(path: Path, custody_text: str) -> list[str]:
    violations: list[str] = []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != REQUIRED_CSV_COLUMNS:
                return [
                    f"{path}: evidence-index columns must be {REQUIRED_CSV_COLUMNS}; got {reader.fieldnames}"
                ]
            rows = list(reader)
    except csv.Error as exc:
        return [f"{path}: CSV parse error: {exc}"]

    if not rows:
        violations.append(f"{path}: evidence index must contain at least one source-backed row")

    seen: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        eid = str(row.get("evidence_id") or "").strip()
        if not eid:
            violations.append(f"{path}:{row_number}: evidence_id is required")
            continue
        if eid in seen:
            violations.append(f"{path}:{row_number}: duplicate evidence_id {eid!r}")
        seen.add(eid)

        for column in REQUIRED_CSV_COLUMNS:
            value = str(row.get(column) or "").strip()
            if not value:
                violations.append(f"{path}:{row_number}: {column} is required")
            lowered = value.lower()
            for pattern in PLACEHOLDER_PATTERNS:
                if pattern in lowered:
                    violations.append(
                        f"{path}:{row_number}: {column} contains placeholder marker {pattern!r}"
                    )

        source_path = ROOT / str(row.get("source_path") or "")
        if not source_path.exists():
            violations.append(f"{path}:{row_number}: source_path does not exist: {source_path}")

        custody_entry = str(row.get("custody_entry") or "")
        if custody_entry and custody_entry not in custody_text:
            violations.append(
                f"{path}:{row_number}: custody_entry {custody_entry!r} not found in chain-of-custody.md"
            )

    return violations


def _claim_doc(doc: dict[str, Any]) -> dict[str, Any]:
    claim = {key: value for key, value in doc.items() if key != "governance"}
    governance = doc.get("governance")
    if isinstance(governance, dict):
        claim["governance"] = {
            key: value for key, value in governance.items() if key != "forbidden_acts"
        }
    return claim


def _validate_one(path: Path) -> list[str]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"cannot read file: {exc}"]
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]

    if not isinstance(doc, dict):
        return ["document is not a YAML mapping"]

    violations: list[str] = []

    for primitive in REQUIRED_PRIMITIVES:
        if not doc.get(primitive):
            violations.append(f"Rule #3 violation: missing required primitive {primitive!r}")

    standing = _standing(doc)
    if standing not in STANDINGS:
        violations.append(f"Rule #1 violation: standing {standing!r} is not in {' -> '.join(STANDINGS)}")

    governance = doc.get("governance")
    if not isinstance(governance, dict):
        violations.append("Rule #2 violation: governance must be a mapping")
    else:
        for flag in REQUIRED_GOVERNANCE_FLAGS:
            if governance.get(flag) is not True:
                violations.append(f"Rule #2 violation: governance.{flag} must be true")

        forbidden = set(governance.get("forbidden_acts") or [])
        missing_forbidden = sorted(FORBIDDEN_ACTS - forbidden)
        if missing_forbidden:
            violations.append(
                "Rule #2 violation: governance.forbidden_acts missing "
                + ", ".join(repr(item) for item in missing_forbidden)
            )

    gates = doc.get("human_gates")
    if not isinstance(gates, list) or not gates:
        violations.append("Rule #2 violation: human_gates must name counsel/client gates")
    else:
        gates_text = _text(gates).lower()
        if "micah" not in gates_text and "counsel" not in gates_text:
            violations.append("Rule #2 violation: human_gates must include counsel review")
        if "anthony" not in gates_text and "client" not in gates_text:
            violations.append("Rule #2 violation: human_gates must include client control")

    artifacts = doc.get("artifacts")
    resolved: dict[str, Path] = {}
    if not isinstance(artifacts, dict):
        violations.append("Rule #6 violation: artifacts must map named outputs to paths")
    else:
        for key in REQUIRED_ARTIFACTS:
            value = artifacts.get(key)
            if not value:
                violations.append(f"Rule #6 violation: artifacts.{key} is required")
                continue
            artifact_path = _resolve_artifact(path, value)
            resolved[key] = artifact_path
            if not artifact_path.exists():
                violations.append(f"Rule #6 violation: artifact does not exist: {artifact_path}")
            elif artifact_path.stat().st_size == 0:
                violations.append(f"Rule #6 violation: artifact is empty: {artifact_path}")

    markdown_keys = [
        "posture",
        "chain_of_custody",
        "elements_map",
        "deadlines",
        "ethics_log",
        "review_note",
        "framework_deck",
    ]
    for key in markdown_keys:
        artifact = resolved.get(key)
        if artifact and artifact.exists():
            violations.extend(_validate_markdown(artifact))

    custody_path = resolved.get("chain_of_custody")
    evidence_path = resolved.get("evidence_index")
    if custody_path and custody_path.exists() and evidence_path and evidence_path.exists():
        custody_text = custody_path.read_text(encoding="utf-8")
        violations.extend(_validate_evidence_index(evidence_path, custody_text))

    claim_text = _text(_claim_doc(doc)).lower()
    for pattern in OVERREACH_PATTERNS:
        if pattern in claim_text:
            violations.append(f"Rule #5 violation: overreach pattern present: {pattern!r}")

    return violations


def _fleet_paths(base: Path) -> list[Path]:
    return sorted((base / "matters").glob("*/matter.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--fleet", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    paths = _fleet_paths(BASE) if args.fleet else args.paths
    if not paths:
        parser.error("provide path(s) or --fleet")

    failures = 0
    for path in paths:
        violations = _validate_one(path)
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
