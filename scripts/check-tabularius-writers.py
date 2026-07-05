#!/usr/bin/env python3
"""Audit direct task-board writers against the TABVLARIVS migration allowlist.

The ideal form is one board writer: TABVLARIVS. During the reversible cutover,
some legacy fallback paths still contain direct writes, but they must be named,
gated, and visible. This check fails any new unreviewed tasks.yaml writer.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = ("cli/src", "scripts", "mcp/src", "web/api", "web/worker/src")
SKIP_PARTS = {"__pycache__", ".pytest_cache", "node_modules", ".next"}
WRITE_PATTERNS = (
    re.compile(r"\bsave_limen_file\s*\("),
    re.compile(r"\batomic_write_text\s*\(\s*(?:TASKS_FILE|TASKS_YAML|TASKS|tasks_path|BOARD)\b"),
)

# Direct writes that are not live board mutation bypasses.
STRUCTURAL_ALLOWLIST = {
    "cli/src/limen/io.py": "canonical atomic writer primitive",
    "cli/src/limen/tabularius.py": "TABVLARIVS keeper seal",
    "cli/src/limen/cli.py": "explicit channel export writes a user-named output board, not the live board",
    "scripts/heal-board.py": "emergency collapse repair from committed-good snapshot",
}

# Legacy fallback paths that are still present during the reversible cutover. Each must carry the
# ticket-mode gate and TABVLARIVS producer path in the same file.
LEGACY_GATED_ALLOWLIST = {
    "cli/src/limen/dispatch.py",
    "cli/src/limen/harvest.py",
    "scripts/dispatch-async.py",
    "scripts/ingest-backlog.py",
    "scripts/insight-route.py",
    "scripts/mine-backlog.py",
    "scripts/quicken.py",
    "scripts/route.py",
}

PRODUCER_TOKENS = (
    "submit_task_upsert",
    "submit_task_status",
    "submit_board_meta",
    "submit_ticket",
)


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel_dir in SCAN_DIRS:
        base = root / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".js"}:
                continue
            if SKIP_PARTS & set(path.relative_to(root).parts):
                continue
            files.append(path)
    return sorted(files)


def _writer_lines(text: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("#", "//")):
            continue
        if any(pattern.search(line) for pattern in WRITE_PATTERNS):
            hits.append((lineno, stripped))
    return hits


def _is_gated_legacy(text: str) -> bool:
    return "LIMEN_TICKETS_PRODUCE" in text and any(token in text for token in PRODUCER_TOKENS)


def audit(root: Path, *, max_legacy_writers: int | None = None) -> list[str]:
    errors: list[str] = []
    observed: set[str] = set()
    observed_legacy: set[str] = set()
    for path in _iter_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = _writer_lines(text)
        if not hits:
            continue
        rel = path.relative_to(root).as_posix()
        observed.add(rel)
        if rel in STRUCTURAL_ALLOWLIST:
            continue
        if rel in LEGACY_GATED_ALLOWLIST:
            observed_legacy.add(rel)
            if not _is_gated_legacy(text):
                errors.append(f"{rel}: allowlisted legacy writer is missing ticket-mode gate/producer proof")
            continue
        rendered = "; ".join(f"L{lineno}: {line}" for lineno, line in hits[:3])
        errors.append(f"{rel}: unapproved direct board writer ({rendered})")

    stale = sorted((STRUCTURAL_ALLOWLIST.keys() | LEGACY_GATED_ALLOWLIST) - observed)
    for rel in stale:
        errors.append(f"{rel}: allowlist entry is stale; no direct writer was observed")
    if max_legacy_writers is not None and len(observed_legacy) > max_legacy_writers:
        errors.append(
            "legacy gated fallback writer ceiling exceeded: "
            f"{len(observed_legacy)} observed > {max_legacy_writers} allowed"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--max-legacy",
        type=int,
        default=None,
        help="Fail if more than this many legacy gated direct writers remain.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    if args.max_legacy is not None and args.max_legacy < 0:
        parser.error("--max-legacy must be non-negative")
    errors = audit(root, max_legacy_writers=args.max_legacy)
    if errors:
        print(f"tabularius-writers: blocked with {len(errors)} issue(s)", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(
            "tabularius-writers: direct board writers are limited to "
            f"{len(STRUCTURAL_ALLOWLIST)} structural path(s) and "
            f"{len(LEGACY_GATED_ALLOWLIST)} legacy gated fallback path(s)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
