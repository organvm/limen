#!/usr/bin/env python3
"""Read-only predicate for the root-custodied execution-owner service."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.execution_trajectory_github import load_system_owner_configuration  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail closed unless the fixed owner service passes custody")
    parser.add_argument("--json", action="store_true", help="emit a bounded machine-readable result")
    args = parser.parse_args()

    try:
        configuration = load_system_owner_configuration()
    except (OSError, TypeError, ValueError) as exc:
        result = {
            "schema": "limen.execution_owner_service_check.v1",
            "status": "unprovisioned",
            "passed": False,
            "blocker": str(exc)[:400],
            "owner_contract": "docs/execution-owner-service.md",
            "next_command": "python3 scripts/check-execution-owner-service.py --check",
        }
        print(json.dumps(result, sort_keys=True) if args.json else f"BLOCKED: {result['blocker']}")
        return 2

    result = {
        "schema": "limen.execution_owner_service_check.v1",
        "status": "provisioned",
        "passed": True,
        "trajectory_repository": configuration.trajectory_owner["repository"],
        "trajectory_ref": configuration.trajectory_owner["ref"],
        "receipt_authority_count": len(configuration.receipt_authorities),
    }
    print(json.dumps(result, sort_keys=True) if args.json else "execution owner service: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
