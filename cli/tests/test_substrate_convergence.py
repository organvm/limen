"""Contract tests for the literal Workspace convergence court."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess

import pytest
import yaml

from limen.substrate_convergence import ManifestError, audit


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _seed_repo(path: Path, remote: Path) -> None:
    remote.mkdir(parents=True)
    _git(remote, "init", "--bare", "-q")
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-qm", "seed")
    _git(path, "branch", "-M", "main")
    _git(path, "remote", "add", "origin", str(remote))
    _git(path, "push", "-u", "origin", "main")


def _base_rows(remote: Path) -> list[dict[str, object]]:
    return [
        {"path": "library", "kind": "structural", "owner_ref": "portvs", "residency": "structural"},
        {
            "path": "library/engine",
            "kind": "structural",
            "owner_ref": "portvs",
            "residency": "structural",
        },
        {
            "path": "library/engine/organvm",
            "kind": "structural",
            "owner_ref": "portvs",
            "residency": "structural",
        },
        {
            "path": "library/engine/organvm/limen",
            "kind": "repository",
            "owner_ref": "organvm/limen",
            "residency": "laptop",
            "remote": str(remote),
            "custody_ref": "refs/remotes/origin/main",
        },
        {"path": "domains", "kind": "structural", "owner_ref": "portvs", "residency": "structural"},
        {
            "path": "domains/governance",
            "kind": "structural",
            "owner_ref": "limen",
            "residency": "structural",
        },
        {"path": "private", "kind": "structural", "owner_ref": "portvs", "residency": "structural"},
        {
            "path": "private/life",
            "kind": "private",
            "owner_ref": "private-inventory/life",
            "residency": "private",
            "sealed_inventory_ref": "manifest://inventory.json",
            "restoration_receipt_ref": "manifest://receipts.json#life",
            "custody_label": "life",
        },
        {"path": "runtime", "kind": "structural", "owner_ref": "limen", "residency": "structural"},
        {
            "path": "runtime/worktrees",
            "kind": "ephemeral",
            "owner_ref": "limen/reaper",
            "residency": "ephemeral",
            "expires_after": 86400,
            "reaper": "limen worktree reap",
        },
    ]


def _fixture(
    tmp_path: Path,
    *,
    rows: list[dict[str, object]] | None = None,
    compatibility_links: list[dict[str, str]] | None = None,
    valid_custody: bool = True,
) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "Workspace"
    remote = tmp_path / "remote.git"
    manifest_dir = tmp_path / "portvs" / "governance"
    manifest_dir.mkdir(parents=True)
    selected_rows = rows or _base_rows(remote)
    seeded_remotes: set[str] = set()
    for row in selected_rows:
        path = workspace / str(row["path"])
        if row["kind"] == "repository":
            remote_key = str(row["remote"])
            if remote_key not in seeded_remotes:
                _seed_repo(path, remote)
                seeded_remotes.add(remote_key)
            else:
                path.mkdir(parents=True, exist_ok=True)
        elif row["kind"] == "index":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "inventory.json").write_text('{"sealed": true}\n', encoding="utf-8")
    (manifest_dir / "receipts.json").write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "label": "life",
                        "restoration_passed": valid_custody,
                        "copy_count": 2 if valid_custody else 1,
                        "independent_physical_devices": valid_custody,
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    data = {
        "schema": "portvs.workspace_manifest.v1",
        "workspace_root": str(workspace),
        "limits": {
            "max_scan_entries": 10_000,
            "max_violations": 0,
            "max_unmeasured": 0,
            "max_compatibility_links": 0,
        },
        "rows": selected_rows,
        "migration": {"compatibility_links": compatibility_links or []},
    }
    manifest = manifest_dir / "workspace-manifest.yaml"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return manifest, workspace, remote


def _codes(report: dict[str, object]) -> set[str]:
    return {str(item["code"]) for item in report["violations"]}  # type: ignore[index]


def test_exact_literal_tree_passes(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    report = audit(manifest, workspace_root=workspace, active_cwds=[], now=datetime(2026, 7, 30, tzinfo=UTC))
    assert report["ok"] is True, report
    assert report["counts"]["violations"] == 0


def test_empty_declared_container_persists_and_missing_container_fails(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    governance = workspace / "domains" / "governance"
    assert list(governance.iterdir()) == []
    governance.rmdir()
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert "declared_entry_missing" in _codes(report)


def test_undeclared_root_is_rejected_without_wildcard_bypass(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    (workspace / ".DS_Store").write_text("noise", encoding="utf-8")
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert "undeclared_entry" in _codes(report)
    assert any(item["path"] == ".DS_Store" for item in report["violations"])


def test_manifest_rejects_traversal(tmp_path: Path) -> None:
    manifest, workspace, remote = _fixture(tmp_path)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["rows"].append(
        {
            "path": "domains/../escape",
            "kind": "structural",
            "owner_ref": "portvs",
            "residency": "structural",
        }
    )
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ManifestError, match="not a normalized relative path"):
        audit(manifest, workspace_root=workspace, active_cwds=[])
    assert remote.exists()


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    governance = workspace / "domains" / "governance"
    governance.rmdir()
    governance.symlink_to(outside, target_is_directory=True)
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert "symlink_escape" in _codes(report)


def test_repository_in_wrong_container_fails(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    expected = workspace / "library" / "engine" / "organvm" / "limen"
    wrong = workspace / "domains" / "limen"
    expected.rename(wrong)
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert "declared_entry_missing" in _codes(report)
    assert "undeclared_entry" in _codes(report)


def test_duplicate_checkout_remote_is_rejected_by_manifest(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    rows = _base_rows(remote)
    rows.extend(
        [
            {
                "path": "library/storefront",
                "kind": "structural",
                "owner_ref": "portvs",
                "residency": "structural",
            },
            {
                "path": "library/storefront/duplicate",
                "kind": "repository",
                "owner_ref": "organvm/limen",
                "residency": "laptop",
                "remote": str(remote),
                "custody_ref": "refs/remotes/origin/main",
            },
        ]
    )
    manifest, workspace, _ = _fixture(tmp_path, rows=rows)
    with pytest.raises(ManifestError, match="one canonical physical home"):
        audit(manifest, workspace_root=workspace, active_cwds=[])


def test_nested_unregistered_repository_fails(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    nested = workspace / "library" / "engine" / "organvm" / "limen" / ".worktrees" / "competing"
    nested.mkdir(parents=True)
    _git(nested, "init", "-q")
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert "undeclared_nested_repository" in _codes(report)


def test_dirty_and_unpushed_repository_cannot_converge(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    repo = workspace / "library" / "engine" / "organvm" / "limen"
    (repo / "dirty.txt").write_text("local only\n", encoding="utf-8")
    _git(repo, "add", "dirty.txt")
    _git(repo, "commit", "-qm", "not pushed")
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert {"repository_unpreserved"} <= _codes(report)


def test_private_root_requires_dual_copy_restoration_receipt(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path, valid_custody=False)
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert "private_restoration_unverified" in _codes(report)


def test_private_reference_resolves_through_declared_legacy_repo_during_migration(
    tmp_path: Path,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    repo_row = next(row for row in data["rows"] if row["kind"] == "repository")
    repo_row["legacy_paths"] = ["limen"]
    custody = workspace / repo_row["path"] / "custody.json"
    custody.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "label": "life",
                        "restoration_passed": True,
                        "copy_count": 2,
                        "independent_physical_devices": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    private_row = next(row for row in data["rows"] if row["kind"] == "private")
    private_row["sealed_inventory_ref"] = f"workspace://{repo_row['path']}/custody.json"
    private_row["restoration_receipt_ref"] = f"workspace://{repo_row['path']}/custody.json#life"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (workspace / repo_row["path"]).rename(workspace / "limen")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    custody_row = next(row for row in report["private_custody"] if row["path"] == "private/life")
    assert custody_row["inventory_available"] is True
    assert custody_row["restoration_verified"] is True


def test_active_compatibility_path_blocks_removal(tmp_path: Path) -> None:
    link = {
        "path": "limen",
        "target": "library/engine/organvm/limen",
        "owner_ref": "organvm/limen",
        "expires_at": "2026-08-15T00:00:00Z",
    }
    manifest, workspace, _ = _fixture(tmp_path, compatibility_links=[link])
    (workspace / "limen").symlink_to(workspace / "library" / "engine" / "organvm" / "limen")
    report = audit(
        manifest,
        workspace_root=workspace,
        active_cwds=[workspace / "limen" / "scripts"],
        now=datetime(2026, 7, 30, tzinfo=UTC),
    )
    assert {"compatibility_link_unresolved", "active_legacy_path"} <= _codes(report)


def test_same_manifest_and_root_are_independent_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    first = audit(manifest, workspace_root=workspace, active_cwds=[])
    elsewhere = tmp_path / "some" / "worktree"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)
    second = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert second == first
