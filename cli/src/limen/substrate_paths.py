"""Executable path-indirection contract for the literal Workspace substrate."""

from __future__ import annotations

from pathlib import Path
import re


_SCAN_ROOTS = (
    "install.sh",
    "scripts",
    "cli/src",
    "mcp/src",
    "container",
    "ianva",
    "organs",
    "apps",
    "institutio/governance/parameters.yaml",
    "pillars.yaml",
    "his-hand-levers.json",
)
_SKIP_PARTS = {
    ".git",
    ".worktrees",
    ".limen-private",
    "__pycache__",
    "docs",
    "logs",
    "tests",
    "public-portal",
}
_TEXT_SUFFIXES = {
    "",
    ".fish",
    ".html",
    ".json",
    ".plist",
    ".py",
    ".sh",
    ".toml",
    ".tsv",
    ".yaml",
    ".yml",
    ".zsh",
}

# Keep the disallowed spellings out of this source itself so the court can scan
# its own implementation without an exception.
_LEGACY_PATTERNS = (
    re.compile(r"(?:~|\$HOME|/Users/[^/]+)" + r"/Workspace/" + r"limen(?:/|\b)"),
    re.compile(r"(?:~|\$HOME|/Users/[^/]+)" + r"/Workspace/" + r"domus-genoma(?:/|\b)"),
    re.compile(r"(?:~|\$HOME|/Users/[^/]+)" + r"/Workspace/" + r"4444J99/portvs(?:/|\b)"),
    re.compile(r"Path\.home\(\)\s*/\s*['\"]Workspace['\"]\s*/\s*['\"]" + r"limen" + r"['\"]"),
    re.compile(r"Path\((?:HOME|home)\)\s*/\s*['\"]Workspace['\"]\s*/\s*['\"]" + r"limen" + r"['\"]"),
    re.compile(r"\{(?:HOME|home)\}" + r"/Workspace/" + r"limen(?:/|\b)"),
    re.compile(
        r"os\.path\.join\(\s*(?:HOME|home)\s*,\s*['\"]Workspace" + r"(?:/limen['\"]|['\"]\s*,\s*['\"]limen['\"])"
    ),
    re.compile(r"(?:HOME|home)\s*\+\s*['\"]" + r"/Workspace/limen" + r"(?:/|['\"])"),
)


def _candidate_files(root: Path) -> list[Path]:
    candidates: set[Path] = set()
    for raw in _SCAN_ROOTS:
        entry = root / raw
        if entry.is_file():
            candidates.add(entry)
            continue
        if not entry.is_dir():
            continue
        for path in entry.rglob("*"):
            relative = path.relative_to(root)
            if not path.is_file() or any(part in _SKIP_PARTS for part in relative.parts):
                continue
            if path.suffix.lower() in _TEXT_SUFFIXES:
                candidates.add(path)
    return sorted(candidates)


def find_legacy_references(root: Path) -> list[dict[str, object]]:
    """Return executable/config references that bypass the canonical root contract."""

    findings: list[dict[str, object]] = []
    for path in _candidate_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for pattern in _LEGACY_PATTERNS:
                match = pattern.search(line)
                if match:
                    findings.append(
                        {
                            "path": path.relative_to(root).as_posix(),
                            "line": line_number,
                            "reference": match.group(0),
                        }
                    )
                    break
    return findings
