#!/usr/bin/env python3
"""Validate the VLTIMA universal kernel and each organ's institutional projection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

UNIVERSAL_TERMS = (
    "Object",
    "Subject",
    "Agent",
    "Actor",
    "System",
    "Event",
    "Record",
    "Covenant",
    "Member",
    "Mandate",
    "Standing",
    "Standard",
    "Governance",
    "Exchange",
    "Entitlement",
    "Obligation",
)

ORGAN_TERMS = ("Member", "Mandate", "Standing", "Standard", "Governance")


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term.lower() not in text.lower()]


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    kernel = root / "organs" / "vltima" / "KERNEL.md"
    if not kernel.exists():
        errors.append("organs/vltima/KERNEL.md is missing")
    else:
        missing = _missing_terms(kernel.read_text(), UNIVERSAL_TERMS)
        if missing:
            errors.append(f"organs/vltima/KERNEL.md is missing term(s): {', '.join(missing)}")

    ladder_path = root / "organ-ladder.json"
    try:
        ladder = json.loads(ladder_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return errors + [f"organ-ladder.json is unreadable: {exc}"]

    seen_homes: set[str] = set()
    for organ in ladder.get("organs") or []:
        if not isinstance(organ, dict):
            continue
        pillar = str(organ.get("pillar") or "<missing-pillar>")
        home = str(organ.get("home") or "")
        if not home or home in seen_homes:
            continue
        seen_homes.add(home)

        for field in ("domain_map", "macro", "micro", "first_artifact"):
            if not str(organ.get(field) or "").strip():
                errors.append(f"{pillar}: organ-ladder.json missing {field}")

        organ_kernel = root / home / "KERNEL.md"
        if not organ_kernel.exists():
            errors.append(f"{pillar}: {home}KERNEL.md is missing")
            continue
        text = organ_kernel.read_text()
        missing = _missing_terms(text, ORGAN_TERMS)
        if missing:
            errors.append(f"{pillar}: {home}KERNEL.md missing primitive(s): {', '.join(missing)}")
        if "macro" not in text.lower():
            errors.append(f"{pillar}: {home}KERNEL.md missing MACRO deployment")
        if "micro" not in text.lower():
            errors.append(f"{pillar}: {home}KERNEL.md missing MICRO deployment")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    errors = validate(root)
    if errors:
        print(f"vltima-kernel: blocked with {len(errors)} issue(s)", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if not args.quiet:
        print("vltima-kernel: universal kernel and organ projections valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
