#!/usr/bin/env python3
"""Records the capacity-fill pulse into docs/capacity-fill.md and logs/capacity-fill-ledger.json."""

import argparse
import datetime
import json
import os
from pathlib import Path
import sys

# Add cli/src to path to import limen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
try:
    from limen.capacity import capacity_census, format_capacity_census
except ImportError:
    capacity_census = None

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not args.write:
        return

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    census = capacity_census() if capacity_census else []
    
    docs_path = ROOT / "docs" / "capacity-fill.md"
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    logs_path = logs_dir / "capacity-fill-ledger.json"

    formatted = format_capacity_census(census) if capacity_census else ""

    md_content = f"# Capacity Fill Ledger\n\nGenerated: {now}\n\n```text\n{formatted}\n```\n"
    docs_path.write_text(md_content)

    logs_path.write_text(json.dumps({"generated": now, "census": census}, indent=2) + "\n")

if __name__ == "__main__":
    main()
