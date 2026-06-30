import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

# Need to make sure limen is in path to import capacity
sys.path.insert(0, str(Path(__file__).parent.parent / "cli" / "src"))
from limen.capacity import capacity_census, format_capacity_census


def load_tasks() -> dict:
    tasks_path = Path("tasks.yaml")
    if not tasks_path.exists():
        return {}
    try:
        with tasks_path.open() as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_board() -> dict:
    return load_tasks().get("board", {})


def write_ledger():
    now = datetime.now(timezone.utc).isoformat()
    board = load_board()
    census_rows = capacity_census(board=board)

    # 1. Update docs/capacity-fill.md
    docs_path = Path("docs/capacity-fill.md")
    docs_path.parent.mkdir(parents=True, exist_ok=True)

    human_readable = ["# Capacity Fill Ledger", "", f"Generated: `{now}`", "", format_capacity_census(census_rows), ""]
    docs_path.write_text("\n".join(human_readable))

    # 2. Update logs/capacity-fill-ledger.json
    logs_path = Path("logs/capacity-fill-ledger.json")
    logs_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {"timestamp": now, "census": census_rows}

    ledger = []
    if logs_path.exists():
        try:
            with logs_path.open() as f:
                ledger = json.load(f)
                if not isinstance(ledger, list):
                    ledger = []
        except Exception:
            pass

    ledger.append(entry)
    with logs_path.open("w") as f:
        json.dump(ledger, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Track the capacity-fill pulse")
    parser.add_argument("--write", action="store_true", help="Write updates to ledger and docs")
    args = parser.parse_args()

    if args.write:
        write_ledger()
    else:
        board = load_board()
        census_rows = capacity_census(board=board)
        print(format_capacity_census(census_rows))


if __name__ == "__main__":
    main()
