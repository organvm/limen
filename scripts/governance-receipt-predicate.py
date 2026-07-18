#!/usr/bin/env python3
"""Independently and read-only verify Limen's governance receipt owner."""

from __future__ import annotations

import argparse
import sys

from governance_receipt_contract import (
    ReceiptContractError,
    add_owner_arguments,
    build_receipt_plan,
    cadence_runtime,
    paths_from_args,
    require_path_below,
    validate_metrics,
    validate_output,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_owner_arguments(parser)
    args = parser.parse_args(argv)
    try:
        runtime = cadence_runtime(predicate=True)
        output = require_path_below(args.output, runtime.run_root, "receipt output")
        metrics = require_path_below(runtime.metrics_path, runtime.run_root, "receipt metrics")
        plan = build_receipt_plan(
            paths=paths_from_args(args),
            runtime=runtime,
            snapshot_digest=args.snapshot_digest,
            cadence_id=args.cadence_id,
        )
        validate_output(output, plan)
        validate_metrics(metrics, plan, runtime)
        return 0
    except ReceiptContractError as exc:
        print(f"receipt predicate failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
