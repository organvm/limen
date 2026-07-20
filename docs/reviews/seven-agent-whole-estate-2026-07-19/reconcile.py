#!/usr/bin/env python3
"""Compatibility entrypoint for canonical frozen reconciliation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.estate_review.pipeline import main

raise SystemExit(
    main(
        [
            "--root",
            str(ROOT),
            "--snapshot-at",
            "2026-07-19T15:11:00Z",
            "--write",
        ]
    )
)
