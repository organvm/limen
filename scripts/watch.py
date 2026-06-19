#!/usr/bin/env python3
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "cli" / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))

from limen.watch import main  # noqa: E402


if __name__ == "__main__":
    main()
