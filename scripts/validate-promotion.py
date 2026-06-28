#!/usr/bin/env python3
"""validate-promotion — Cvrsvs Honorvm promotion-state validator.

Operationalizes the first cvrsvs-honorvm rule: every seed.yaml's
metadata.promotion_status must be a known state in the canonical promotion
ladder (organs/governance/promotion-ladder.yaml).

Usage:
    python scripts/validate-promotion.py path/to/seed.yaml [...]
    python scripts/validate-promotion.py --all          # scan repo for seed.yaml files
    python scripts/validate-promotion.py --with-ladder  # also check organ-ladder.json consistency

Exit codes:
    0  all files pass every rule
    1  one or more violations found (errors only; warnings are printed but do not fail)
    2  usage / IO error
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML is required — pip install pyyaml", file=sys.stderr)
    sys.exit(2)

_ROOT = Path(__file__).resolve().parent.parent
_LADDER_PATH = _ROOT / "organs" / "governance" / "promotion-ladder.yaml"
_ORGAN_LADDER_PATH = _ROOT / "organ-ladder.json"

_REQUIRED_FIELDS = ["schema_version", "organ", "repo", "org"]
_REQUIRED_META = ["promotion_status"]


def _load_yaml(path: Path) -> dict:
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except yaml.YAMLError as exc:
        print(f"error: invalid YAML in {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def _load_organ_ladder() -> dict[str, dict]:
    """Return organ-ladder data keyed by repo+pillar for maturity cross-check."""
    import json
    try:
        with open(_ORGAN_LADDER_PATH) as f:
            data = json.load(f)
        return {entry["pillar"]: entry for entry in data.get("organs", [])}
    except Exception:
        return {}


class Violation:
    def __init__(self, rule_id: str, severity: str, message: str) -> None:
        self.rule_id = rule_id
        self.severity = severity
        self.message = message

    def __str__(self) -> str:
        return f"  [{self.severity.upper()}] {self.rule_id}: {self.message}"


def _validate_seed(seed: dict, path: Path, ladder: dict, organ_entries: dict, with_ladder: bool) -> list[Violation]:
    violations: list[Violation] = []
    valid_states: set[str] = set(ladder.get("states", {}).keys())

    # Rule: required-fields
    for field in _REQUIRED_FIELDS:
        if not seed.get(field):
            violations.append(Violation(
                "required-fields", "error",
                f"missing top-level field '{field}'"
            ))

    meta = seed.get("metadata", {})
    if not isinstance(meta, dict):
        violations.append(Violation("required-fields", "error", "metadata must be a mapping"))
        return violations

    for field in _REQUIRED_META:
        if not meta.get(field):
            violations.append(Violation(
                "required-fields", "error",
                f"missing metadata.{field}"
            ))

    # Rule: valid-promotion-status (the ONE cvrsvs-honorvm rule)
    status = meta.get("promotion_status")
    if status is not None:
        if status not in valid_states:
            violations.append(Violation(
                "valid-promotion-status", "error",
                f"promotion_status '{status}' is not a known state; "
                f"valid states: {', '.join(sorted(valid_states))}"
            ))
    # (if status is None it was already caught by required-fields)

    # Rule: maturity-range-consistency (warning only, requires --with-ladder)
    if with_ladder and status in valid_states:
        state_def = ladder["states"][status]
        lo, hi = state_def.get("maturity_range", [0, 100])
        repo = seed.get("repo", "")
        # Match organ-ladder entry by repo name (best-effort)
        matched = next(
            (e for e in organ_entries.values() if e.get("home", "").endswith(repo + "/") or repo in e.get("repo", "")),
            None,
        )
        if matched:
            maturity = matched.get("maturity")
            if maturity is not None and not (lo <= maturity <= hi):
                violations.append(Violation(
                    "maturity-range-consistency", "warning",
                    f"organ-ladder maturity {maturity}% is outside the expected range "
                    f"[{lo}%–{hi}%] for state '{status}'"
                ))

    return violations


def _find_seed_files(root: Path) -> list[Path]:
    return sorted(root.rglob("seed.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate seed.yaml files against the Cvrsvs Honorvm promotion ladder."
    )
    parser.add_argument("files", nargs="*", help="seed.yaml file(s) to validate")
    parser.add_argument("--all", action="store_true", dest="scan_all",
                        help="scan the repo root for all seed.yaml files")
    parser.add_argument("--with-ladder", action="store_true",
                        help="also check organ-ladder.json maturity consistency (warning-only)")
    args = parser.parse_args()

    if not args.files and not args.scan_all:
        parser.print_help()
        return 2

    ladder = _load_yaml(_LADDER_PATH)
    organ_entries = _load_organ_ladder() if args.with_ladder else {}

    if args.scan_all:
        paths = _find_seed_files(_ROOT)
        if not paths:
            print("no seed.yaml files found under repo root")
            return 0
    else:
        paths = [Path(f) for f in args.files]

    total_errors = 0
    total_warnings = 0
    results: list[tuple[Path, list[Violation]]] = []

    for path in paths:
        seed = _load_yaml(path)
        viols = _validate_seed(seed, path, ladder, organ_entries, args.with_ladder)
        results.append((path, viols))
        total_errors += sum(1 for v in viols if v.severity == "error")
        total_warnings += sum(1 for v in viols if v.severity == "warning")

    # Print report
    for path, viols in results:
        rel = path.relative_to(_ROOT) if path.is_relative_to(_ROOT) else path
        errors = [v for v in viols if v.severity == "error"]
        if not viols:
            print(f"PASS  {rel}")
        else:
            status = "FAIL" if errors else "WARN"
            print(f"{status}  {rel}")
            for v in viols:
                print(str(v))

    # Summary
    print()
    checked = len(results)
    failed = sum(1 for _, viols in results if any(v.severity == "error" for v in viols))
    print(f"checked {checked} file(s): {failed} failed, {total_warnings} warning(s)")

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
