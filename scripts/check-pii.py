#!/usr/bin/env python3
"""PII gate — prevent leaking person-adjacent organ paths.

This gate prevents committing references to paths like `_health-private`, `_life-private`,
`_financial-private`, and `_legal-private` in unapproved files. It defends the
boundary between the public open-source institutional substrate and the private
personal instances.
"""

import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))

FORBIDDEN_PATHS = {
    "_health-private",
    "_life-private",
    "_financial-private",
    "_legal-private",
}

# Where the gate itself is allowed to mention them.
# The core organ scripts use these paths to find the private instances.
ALLOWED_FILES = {
    "scripts/check-pii.py",
    "scripts/life-organ.py",
    "scripts/health-organ.py",
    "scripts/no-tasks-on-me.sh",
    "scripts/aug1-view.py",
    "institutio/governance/parameters.yaml",
    "docs/life-office/CHARTER.md",
    "docs/health-office/CHARTER.md",
    "cli/tests/test_life_organ.py",
    "his-hand-levers.json",
    "docs/AUG1-10K-GATE.md",
}

def scan_file(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    
    violations = []
    for line_no, line in enumerate(content.splitlines(), 1):
        for forbidden in FORBIDDEN_PATHS:
            if forbidden in line:
                violations.append(f"{path.relative_to(ROOT)}:{line_no}: contains {forbidden}")
                
    return violations

def main() -> int:
    all_violations = []
    for filepath in ROOT.rglob("*"):
        if not filepath.is_file():
            continue
            
        rel_path = filepath.relative_to(ROOT)
        
        # Skip git, cache, build artifacts
        if any(part.startswith(".") for part in rel_path.parts) and rel_path.parts[0] != ".github":
            continue
        if "node_modules" in rel_path.parts or "__pycache__" in rel_path.parts:
            continue
            
        if rel_path.as_posix() in ALLOWED_FILES:
            continue
            
        all_violations.extend(scan_file(filepath))
        
    if all_violations:
        print("PII GATE FAILED. The following files leak person-adjacent paths:")
        for v in all_violations:
            print(f"  {v}")
        return 1
        
    print("check-pii: OK — no person-adjacent paths leaked.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
