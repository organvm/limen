#!/usr/bin/env python3
"""Compatibility imports for the frozen review's synthetic tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.estate_review.model import *  # noqa: F403
