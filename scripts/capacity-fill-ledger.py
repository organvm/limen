#!/usr/bin/env python3
"""capacity-fill-ledger.py — Track the capacity-fill pulse.

Writes structured and human-readable capacity census updates to docs/capacity-fill.md
and logs/capacity-fill-ledger.json.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add cli/src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import capacity_census, format_capacity_census
from limen.io import load_limen_file

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = ROOT / "tasks.yaml"
DOCS_MD = ROOT / "docs" / "capacity-fill.md"
LOGS_JSON = ROOT / "logs" / "capacity-fill-ledger.json"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write to files")
    args = parser.parse_args()

    board = load_limen_file(TASKS) if TASKS.exists() else None
    census = capacity_census(board)
    formatted = format_capacity_census(census)
    
    if args.write:
        DOCS_MD.parent.mkdir(parents=True, exist_ok=True)
        now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
        
        md_content = f"# Capacity Fill Ledger\n\nGenerated: `{now_str}`\n\n{formatted}\n"
        DOCS_MD.write_text(md_content)
        
        # Build JSON
        data = {
            "generated": now_str,
            "lanes": []
        }
        for row in census:
            data["lanes"].append({
                "agent": row.get("agent"),
                "kind": row.get("kind"),
                "reachable": row.get("reachable"),
                "detail": row.get("detail"),
                "limit": row.get("limit"),
                "spent": row.get("spent"),
                "remaining": row.get("remaining")
            })
            
        LOGS_JSON.parent.mkdir(parents=True, exist_ok=True)
        LOGS_JSON.write_text(json.dumps(data, indent=2) + "\n")
        print(f"capacity-fill-ledger: Wrote {DOCS_MD} and {LOGS_JSON}")
    else:
        print(formatted)

if __name__ == "__main__":
    main()
