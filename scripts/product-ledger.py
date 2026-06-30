#!/usr/bin/env python3
"""Select the next unblocked repo/product work from the salvage map."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
SALVAGE_INDEX = PRIVATE_ROOT / "lifecycle" / "salvage-yard-map.json"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "product-ledger.json"
DOC_PATH = ROOT / "docs" / "product-ledger.md"

BLOCKED_STATES = {"blocked", "blocked_local", "blocked-human", "failed_blocked", "needs_human", "retire"}
SCORE_BY_DISPOSITION = {
    "build": 80,
    "publish-stage": 75,
    "verify": 60,
    "consolidate": 50,
    "private-sauce": 35,
    "blocked-human": 0,
    "retire": 0,
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        try:
            return str(path.resolve().relative_to(ROOT))
        except (OSError, ValueError):
            return str(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_script(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def salvage_snapshot() -> dict[str, Any]:
    existing = read_json(SALVAGE_INDEX)
    if existing:
        return existing
    module = load_script(ROOT / "scripts" / "salvage-yard-map.py", "salvage_yard_map")
    return module.build_salvage_map()


def candidates_from_salvage(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for cluster in snapshot.get("clusters") or []:
        disposition = str(cluster.get("disposition") or "verify")
        candidates.append(
            {
                "id": cluster.get("id"),
                "repo": cluster.get("canonical_repo"),
                "disposition": disposition,
                "value_score": SCORE_BY_DISPOSITION.get(disposition, 25),
                "source": "salvage-yard-map",
                "repo_count": cluster.get("repo_count", 1),
            }
        )
    return candidates


def is_blocked(candidate: dict[str, Any]) -> bool:
    state = str(candidate.get("state") or candidate.get("status") or candidate.get("disposition") or "")
    return bool(candidate.get("blocked")) or state in BLOCKED_STATES


def build_product_ledger(candidates: list[dict[str, Any]], *, max_next: int = 5) -> dict[str, Any]:
    blocked = [candidate for candidate in candidates if is_blocked(candidate)]
    open_items = [candidate for candidate in candidates if not is_blocked(candidate)]
    open_items.sort(
        key=lambda item: (
            -int(item.get("value_score") or 0),
            str(item.get("repo") or item.get("id") or ""),
        )
    )
    next_items = open_items[:max_next]
    if next_items:
        status = "active"
        reason = "blocked local work is item-scoped; unblocked candidates remain selectable"
    elif candidates:
        status = "blocked"
        reason = "all known candidates are blocked or retired"
    else:
        status = "empty"
        reason = "no candidates have been surfaced yet"
    return {
        "generated_at": now_iso(),
        "global_status": status,
        "reason": reason,
        "candidate_count": len(candidates),
        "blocked_count": len(blocked),
        "next_selections": next_items,
        "blocked_items": blocked,
    }


def render_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Product Ledger",
        "",
        f"Generated: `{ledger['generated_at']}`",
        f"Global status: `{ledger['global_status']}`",
        f"Candidates: `{ledger['candidate_count']}`",
        f"Blocked: `{ledger['blocked_count']}`",
        "",
        "## Next Selections",
        "",
        "| Candidate | Repo | Disposition | Score |",
        "|---|---|---|---:|",
    ]
    for item in ledger.get("next_selections") or []:
        lines.append(
            f"| `{item.get('id')}` | `{item.get('repo')}` | `{item.get('disposition')}` | "
            f"{int(item.get('value_score') or 0)} |"
        )
    if not ledger.get("next_selections"):
        lines.append("| none |  |  | 0 |")
    lines += [
        "",
        "## Blocked Items",
        "",
        "| Candidate | State | Blocker |",
        "|---|---|---|",
    ]
    for item in ledger.get("blocked_items") or []:
        state = item.get("state") or item.get("status") or item.get("disposition")
        lines.append(f"| `{item.get('id')}` | `{state}` | {item.get('blocker') or ''} |")
    if not ledger.get("blocked_items"):
        lines.append("| none |  |  |")
    lines += [
        "",
        "## Contract",
        "",
        "- A blocked repo, credential, transfer, or local checkout is item state, not a global stop.",
        "- Next selections exclude `blocked_local`, `needs_human`, `failed_blocked`, and `retire` items.",
        "- This ledger stages product choices only; it does not deploy, publish, rename, transfer, or send.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(ledger: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the repo/product selection ledger.")
    parser.add_argument("--write", action="store_true", help="write public docs and private index")
    parser.add_argument("--dry-run", action="store_true", help="print only; never write")
    parser.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    args = parser.parse_args()

    ledger = build_product_ledger(candidates_from_salvage(salvage_snapshot()))
    markdown = render_markdown(ledger)
    if args.write and not args.dry_run:
        write_outputs(ledger, markdown)
        print(f"product-ledger: wrote {DOC_PATH} and {PRIVATE_INDEX}")
        return 0
    if args.json:
        print(json.dumps(ledger, indent=2, sort_keys=True))
    else:
        print(markdown, end="")
        print("product-ledger: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
