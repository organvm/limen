#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import yaml

from limen.capacity import capacity_census, format_capacity_census

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
DOC_PATH = ROOT / "docs" / "capacity-fill.md"
LOG_PATH = ROOT / "logs" / "capacity-fill-ledger.json"
TASKS_PATH = ROOT / "tasks.yaml"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    board = None
    if TASKS_PATH.exists():
        with open(TASKS_PATH, "r") as f:
            try:
                board = yaml.safe_load(f)
            except Exception:
                pass

    rows = capacity_census(board)
    formatted = format_capacity_census(rows)

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    doc_content = f"# Capacity Fill Ledger\n\nGenerated: `{now}`\n\n```\n{formatted}\n```\n"

    if args.write:
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DOC_PATH, "w") as f:
            f.write(doc_content)
        
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "w") as f:
            json.dump({"timestamp": now, "rows": rows}, f, indent=2)
        
        print(f"capacity-fill-ledger: wrote {DOC_PATH.relative_to(ROOT)} and {LOG_PATH.relative_to(ROOT)}")
    else:
        print(doc_content)
        print("Run with --write to save.")

if __name__ == "__main__":
    main()
