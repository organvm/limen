"""Shared loss-free classification for ignored repository entries.

The literal-substrate court and the clone reaper must agree about which ignored
working-tree payloads are reproducible. Anything outside this positive
allowlist requires custody and therefore prevents checkout removal.
"""

from __future__ import annotations


REGENERABLE_DIRS = frozenset(
    "node_modules .venv venv .venv-demucs __pycache__ .pytest_cache .mypy_cache .ruff_cache "
    ".tox dist build .next .nuxt .svelte-kit .astro .turbo .parcel-cache .vercel .wrangler "
    ".gradle coverage .nyc_output .eggs .ipynb_checkpoints".split()
)
REGENERABLE_SUFFIXES = (".pyc", ".pyo")
REGENERABLE_FILES = frozenset({".DS_Store"})


def ignored_entries_from_porcelain(output: str) -> tuple[str, ...]:
    """Return raw relative paths from ``git status --porcelain=v1 -z --ignored``."""

    return tuple(
        record[3:].rstrip("/") for record in output.split("\0") if record.startswith("!! ") and record[3:].rstrip("/")
    )


def ignored_entry_is_regenerable(path: str) -> bool:
    """Whether one enumerated ignored entry is safe to recreate after cloning."""

    normalized = path.rstrip("/")
    if not normalized or normalized.startswith("/") or "\0" in normalized:
        return False
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    top = parts[0]
    base = parts[-1]
    if top in REGENERABLE_DIRS:
        return True
    return len(parts) == 1 and (base in REGENERABLE_FILES or base.endswith(REGENERABLE_SUFFIXES))
