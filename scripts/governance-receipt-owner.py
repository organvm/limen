#!/usr/bin/env python3
"""Emit Limen's deterministic pre-proof governance snapshot bundle."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

from governance_receipt_contract import (
    ReceiptContractError,
    add_owner_arguments,
    build_receipt_plan,
    cadence_runtime,
    canonical_bytes,
    expected_metrics,
    paths_from_args,
    require_path_below,
    validate_output,
)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary.replace(path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_owner_arguments(parser)
    args = parser.parse_args(argv)
    try:
        runtime = cadence_runtime()
        output = require_path_below(args.output, runtime.run_root, "receipt output")
        metrics = require_path_below(runtime.metrics_path, runtime.run_root, "receipt metrics")
        plan = build_receipt_plan(
            paths=paths_from_args(args),
            runtime=runtime,
            snapshot_digest=args.snapshot_digest,
            cadence_id=args.cadence_id,
        )
        if runtime.proof_mode:
            validate_output(output, plan)
        elif not output.exists() or output.read_bytes() != plan.document_bytes:
            _atomic_write(output, plan.document_bytes)
        _atomic_write(metrics, canonical_bytes(expected_metrics(plan, runtime)) + b"\n")
        return 0
    except ReceiptContractError as exc:
        print(f"receipt owner failed: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"receipt owner failed: bounded artifact write error: {exc.strerror}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
