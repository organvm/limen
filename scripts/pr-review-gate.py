#!/usr/bin/env python3
"""Thin entrypoint for :mod:`limen.review_gate`."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.review_gate.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
