#!/usr/bin/env python3
"""Run the Limen aggregate court for PORTVS's literal Workspace manifest."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.substrate_convergence import (  # noqa: E402
    ManifestError,
    audit,
    load_active_cwds,
    render_text,
)
from limen.worktree_layout import canonical_workspace_root  # noqa: E402


def default_manifest() -> Path:
    if value := os.environ.get("PORTVS_WORKSPACE_MANIFEST"):
        return Path(value).expanduser()
    if value := os.environ.get("PORTVS_ROOT"):
        return Path(value).expanduser() / "governance" / "workspace-manifest.yaml"
    workspace_root = Path(os.environ.get("WORKSPACE_ROOT", str(Path.home() / "Workspace"))).expanduser()
    return workspace_root / "library" / "engine" / "organvm" / "portvs" / "governance" / "workspace-manifest.yaml"


def canonical_live_workspace_root() -> Path:
    configured = os.environ.get("WORKSPACE_ROOT", str(Path.home() / "Workspace"))
    return canonical_workspace_root(configured)


def prepare_receipt_report(report: dict[str, object]) -> dict[str, object]:
    """Redact only the canonical live root while preserving its audited identity."""

    result = dict(report)
    audited_root = Path(str(report["workspace_root"]))
    identity = report.get("workspace_root_identity")
    expected_hash = hashlib.sha256(str(audited_root).encode("utf-8")).hexdigest()
    if not isinstance(identity, dict) or identity.get("lexical_sha256") != expected_hash:
        raise ManifestError("workspace root identity does not match the audited root")
    canonical_root = canonical_live_workspace_root()
    is_canonical_live = audited_root == canonical_root
    result["workspace_root_is_canonical_live"] = is_canonical_live
    if is_canonical_live:
        result["workspace_root"] = "$WORKSPACE_ROOT"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--workspace-root", type=Path, default=None)
    parser.add_argument("--active-cwds", type=Path, help="JSON fixture; default discovers live process CWDs")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--receipt", type=Path, help="write the bounded JSON report to this path")
    args = parser.parse_args()

    try:
        active_cwds = load_active_cwds(args.active_cwds) if args.active_cwds else None
        report = audit(
            args.manifest or default_manifest(),
            workspace_root=args.workspace_root,
            active_cwds=active_cwds,
            now=datetime.now(UTC),
        )
    except ManifestError as exc:
        payload = {
            "schema": "limen.substrate_convergence_report.v1",
            "ok": False,
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"substrate-convergence: FAIL\n  {exc}")
        return 1

    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt_report = prepare_receipt_report(report)
        rendered = json.dumps(receipt_report, indent=2, sort_keys=True) + "\n"
        if not args.receipt.exists() or args.receipt.read_text(encoding="utf-8") != rendered:
            args.receipt.write_text(rendered, encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
