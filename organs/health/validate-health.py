#!/usr/bin/env python3
"""Health Organism vertical-slice validator.

This validator checks the repo-tracked health organ surfaces only. It never reads a private
health chart and never validates clinical correctness. Its job is narrower: prove that the
first recovery/access artifact exists, is review-only, carries the required post-injury/ADA
context, and preserves the medical/legal/privacy/outbound guardrails.

Usage:
  python organs/health/validate-health.py
  python organs/health/validate-health.py --quiet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
PROTOCOL = BASE / "RECOVERY-ACCESS-PROTOCOL.md"
KERNEL = BASE / "KERNEL.md"
CHARTER = BASE / "CHARTER.md"
LADDER = ROOT / "organ-ladder.json"

REQUIRED_PROTOCOL_PHRASES = [
    "First vertical slice",
    "review-only",
    "not medical advice",
    "not legal advice",
    "no outbound action",
    "unnamed",
    "4th-story fall (~2024)",
    "ADA accommodation matter",
    "organs/legal/",
    "Member",
    "Mandate",
    "Standing",
    "Standard",
    "Governance",
    "Intake -> posture",
    "State -> record",
    "Protocol -> adherence",
    "Appointments -> calendar",
    "Accommodation -> documentation",
    "Safety sentinel",
    "DRAFT - NOT SENT",
    "Safety certification",
]

REQUIRED_KERNEL_PHRASES = [
    "No diagnosis, no prescription, no medical advice output",
    "Accommodation records feed the legal organ",
    "post-injury recovery and disability-access case",
]

REQUIRED_CHARTER_PHRASES = [
    "Accommodation Clerk",
    "Safety Sentinel",
    "The workflows it runs",
    "First proof: the micro instance",
]

FORBIDDEN_PROTOCOL_PHRASES = [
    "you should take ",
    "you should stop taking ",
    "you should change your dose",
    "diagnosis is ",
    "we will send",
    "system will send",
    "auto-send",
    "file this with",
]


def _read(path: Path) -> tuple[str, list[str]]:
    try:
        return path.read_text(encoding="utf-8"), []
    except OSError as exc:
        return "", [f"cannot read {path}: {exc}"]


def _missing(text: str, phrases: list[str]) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in phrases if phrase.lower() not in lowered]


def _forbidden(text: str, phrases: list[str]) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in phrases if phrase.lower() in lowered]


def _validate_ladder(text: str) -> list[str]:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"organ-ladder.json is not valid JSON: {exc}"]

    organs = doc.get("organs") if isinstance(doc, dict) else None
    health = None
    if isinstance(organs, list):
        health = next((organ for organ in organs if isinstance(organ, dict) and organ.get("pillar") == "health"), None)
    if health is None:
        return ["organ-ladder.json does not contain the health pillar"]

    violations: list[str] = []
    if health.get("maturity") != 15:
        violations.append("health organ maturity must be 15 after the first vertical slice")
    if health.get("stage") != "scaffold":
        violations.append("health organ stage must remain scaffold at 15% maturity")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    for path in (KERNEL, CHARTER, PROTOCOL, LADDER):
        if not path.exists():
            failures.append(f"missing required file: {path}")

    kernel, errors = _read(KERNEL)
    failures.extend(errors)
    charter, errors = _read(CHARTER)
    failures.extend(errors)
    protocol, errors = _read(PROTOCOL)
    failures.extend(errors)
    ladder, errors = _read(LADDER)
    failures.extend(errors)

    for phrase in _missing(kernel, REQUIRED_KERNEL_PHRASES):
        failures.append(f"KERNEL.md missing required phrase: {phrase!r}")
    for phrase in _missing(charter, REQUIRED_CHARTER_PHRASES):
        failures.append(f"CHARTER.md missing required phrase: {phrase!r}")
    for phrase in _missing(protocol, REQUIRED_PROTOCOL_PHRASES):
        failures.append(f"RECOVERY-ACCESS-PROTOCOL.md missing required phrase: {phrase!r}")
    for phrase in _forbidden(protocol, FORBIDDEN_PROTOCOL_PHRASES):
        failures.append(f"RECOVERY-ACCESS-PROTOCOL.md contains forbidden phrase: {phrase!r}")
    failures.extend(_validate_ladder(ladder))

    if failures:
        print("FAIL  organs/health")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    if not args.quiet:
        print("PASS  organs/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
