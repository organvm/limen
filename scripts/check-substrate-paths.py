#!/usr/bin/env python3
"""Reject executable/config consumers of the pre-container Workspace layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.substrate_paths import find_legacy_references  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    findings = find_legacy_references(root)
    report = {
        "schema": "limen.substrate_path_contract.v1",
        "ok": not findings,
        "root": str(root),
        "legacy_reference_count": len(findings),
        "findings": findings,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"substrate-paths: state={'converged' if report['ok'] else 'drift'} legacy_references={len(findings)}")
        for item in findings:
            print(f"  {item['path']}:{item['line']}: {item['reference']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
