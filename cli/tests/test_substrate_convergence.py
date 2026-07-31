"""Contract tests for the literal Workspace convergence court."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import limen.substrate_convergence as convergence
from limen.substrate_convergence import ManifestError, audit, load_active_cwds


_INVENTORY_SHA256 = "1" * 64
_PLAN_SHA256 = "2" * 64
_CONTENT_SHA256 = "3" * 64


def _sealed_inventory(
    *,
    content_sha256: str = _CONTENT_SHA256,
) -> dict[str, object]:
    return {
        "label": "life",
        "sealed": True,
        "inventory_sha256": _INVENTORY_SHA256,
        "plan_sha256": _PLAN_SHA256,
        "content_sha256": content_sha256,
    }


def _restoration_receipt(
    inventory: dict[str, object],
    *,
    restoration_passed: bool = True,
) -> dict[str, object]:
    return {
        "label": str(inventory.get("label", "life")),
        "restoration_passed": restoration_passed,
        "copy_count": 2 if restoration_passed else 1,
        "independent_physical_devices": restoration_passed,
        "inventory_sha256": inventory["inventory_sha256"],
        "plan_sha256": inventory["plan_sha256"],
        "content_sha256": inventory["content_sha256"],
    }


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
            "expires_after": 604800,
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
                _seed_repo(path, Path(remote_key))
                seeded_remotes.add(remote_key)
            else:
                path.mkdir(parents=True, exist_ok=True)
        elif row["kind"] == "index":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
    sealed_inventory = _sealed_inventory()
    (manifest_dir / "inventory.json").write_text(
        json.dumps({"sealed_inventories": [sealed_inventory]}) + "\n",
        encoding="utf-8",
    )
    (manifest_dir / "receipts.json").write_text(
        json.dumps(
            {
                "receipts": [
                    _restoration_receipt(
                        sealed_inventory,
                        restoration_passed=valid_custody,
                    )
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


def test_canonical_runtime_worktree_is_measured_without_nested_repository_violation(
    tmp_path: Path,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    worktree = workspace / "runtime" / "worktrees" / "organvm--limen--fixture" / "bounded-fix"
    worktree.mkdir(parents=True)
    _git(worktree, "init", "-q")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "undeclared_nested_repository" not in _codes(report)
    runtime_receipt = next(row for row in report["ephemeral_roots"] if row["path"] == "runtime/worktrees")
    assert runtime_receipt["namespace_count"] == 1
    assert runtime_receipt["entry_count"] == 1
    assert report["ok"] is True, report


@pytest.mark.parametrize("symlink_level", ["namespace", "unit"])
def test_runtime_worktree_symlink_is_a_bounded_physical_containment_violation(
    tmp_path: Path,
    symlink_level: str,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    runtime_root = workspace / "runtime" / "worktrees"
    outside = tmp_path / "outside-runtime"
    outside.mkdir()
    (outside / "sentinel").write_text("do not follow\n", encoding="utf-8")
    namespace = runtime_root / "foreign-key"
    if symlink_level == "namespace":
        namespace.symlink_to(outside, target_is_directory=True)
        expected_path = "runtime/worktrees/foreign-key"
        expected_namespace_count = 0
    else:
        namespace.mkdir()
        (namespace / "foreign-unit").symlink_to(outside, target_is_directory=True)
        expected_path = "runtime/worktrees/foreign-key/foreign-unit"
        expected_namespace_count = 1

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    matching = [
        violation
        for violation in report["violations"]
        if violation["code"] == "ephemeral_nonphysical_entry" and violation["path"] == expected_path
    ]
    runtime_receipt = next(row for row in report["ephemeral_roots"] if row["path"] == "runtime/worktrees")
    assert report["ok"] is False
    assert len(matching) == 1
    assert runtime_receipt["namespace_count"] == expected_namespace_count
    assert runtime_receipt["entry_count"] == 1
    assert (outside / "sentinel").read_text(encoding="utf-8") == "do not follow\n"


@pytest.mark.parametrize("invalid_shape", ["empty-namespace", "namespace-file", "unit-file"])
def test_runtime_worktree_invalid_physical_shape_fails_closed(
    tmp_path: Path,
    invalid_shape: str,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    runtime_root = workspace / "runtime" / "worktrees"
    namespace = runtime_root / "arbitrary-key"
    if invalid_shape == "empty-namespace":
        namespace.mkdir()
        expected_code = "ephemeral_empty_namespace"
        expected_path = "runtime/worktrees/arbitrary-key"
        expected_namespace_count = 1
        expected_entry_count = 0
    elif invalid_shape == "namespace-file":
        namespace.write_text("not a namespace\n", encoding="utf-8")
        expected_code = "ephemeral_nonphysical_entry"
        expected_path = "runtime/worktrees/arbitrary-key"
        expected_namespace_count = 0
        expected_entry_count = 1
    else:
        namespace.mkdir()
        (namespace / "not-a-worktree").write_text("not a worktree\n", encoding="utf-8")
        expected_code = "ephemeral_nonphysical_entry"
        expected_path = "runtime/worktrees/arbitrary-key/not-a-worktree"
        expected_namespace_count = 1
        expected_entry_count = 1

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    matching = [
        violation
        for violation in report["violations"]
        if violation["code"] == expected_code and violation["path"] == expected_path
    ]
    runtime_receipt = next(row for row in report["ephemeral_roots"] if row["path"] == "runtime/worktrees")
    assert report["ok"] is False
    assert len(matching) == 1
    assert runtime_receipt["namespace_count"] == expected_namespace_count
    assert runtime_receipt["entry_count"] == expected_entry_count


def test_dirty_and_unpushed_repository_cannot_converge(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    repo = workspace / "library" / "engine" / "organvm" / "limen"
    (repo / "dirty.txt").write_text("local only\n", encoding="utf-8")
    _git(repo, "add", "dirty.txt")
    _git(repo, "commit", "-qm", "not pushed")
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert {"repository_unpreserved", "repository_unpreserved_branches"} <= _codes(report)


def test_deleted_live_remote_ref_revokes_local_custody(tmp_path: Path) -> None:
    manifest, workspace, remote = _fixture(tmp_path)
    _git(remote, "update-ref", "-d", "refs/heads/main")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert {
        "repository_custody_missing",
        "repository_unpreserved",
        "repository_unpreserved_branches",
    } <= _codes(report)


def test_unreachable_live_remote_is_unmeasured_not_cached_green(tmp_path: Path) -> None:
    manifest, workspace, remote = _fixture(tmp_path)
    remote.rename(tmp_path / "remote-offline.git")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "repository_unmeasured" in _codes(report)
    assert report["counts"]["unmeasured"] == 1


def test_unpushed_non_current_branch_blocks_convergence(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    repo = workspace / "library" / "engine" / "organvm" / "limen"
    _git(repo, "switch", "-qc", "local-only")
    (repo / "branch-only.txt").write_text("unique branch state\n", encoding="utf-8")
    _git(repo, "add", "branch-only.txt")
    _git(repo, "commit", "-qm", "local branch state")
    _git(repo, "switch", "-q", "main")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "repository_unpreserved_branches" in _codes(report)
    assert "repository_unpreserved" not in _codes(report)


def test_uncustodied_stash_blocks_convergence(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    repo = workspace / "library" / "engine" / "organvm" / "limen"
    (repo / "README.md").write_text("stashed fixture\n", encoding="utf-8")
    _git(repo, "stash", "push", "-qm", "private stash")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "repository_uncustodied_stashes" in _codes(report)


def test_stash_inspection_error_is_unmeasured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    real_run_git = convergence._run_git

    def failing_stash_probe(
        repo: Path,
        *args: str,
        timeout: float = convergence.GIT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        if args == ("rev-parse", "--verify", "--quiet", "refs/stash"):
            return subprocess.CompletedProcess(["git"], 128, "", "fatal: cannot inspect refs/stash")
        return real_run_git(repo, *args, timeout=timeout)

    monkeypatch.setattr(convergence, "_run_git", failing_stash_probe)

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "repository_unmeasured" in _codes(report)
    assert any("cannot inspect refs/stash" in row["message"] for row in report["violations"])


@pytest.mark.parametrize(
    ("ignored_path", "expected_code"),
    [
        (".env", "repository_uncustodied_ignored"),
        ("node_modules/cache/index.bin", None),
    ],
)
def test_ignored_repository_entries_require_loss_free_evidence(
    tmp_path: Path,
    ignored_path: str,
    expected_code: str | None,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    repo = workspace / "library" / "engine" / "organvm" / "limen"
    top = ignored_path.split("/", 1)[0]
    (repo / ".gitignore").write_text(f"/{top}/\n" if "/" in ignored_path else f"/{top}\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-qm", "declare ignored fixture")
    _git(repo, "push", "origin", "main")
    ignored = repo / ignored_path
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text("local ignored payload\n", encoding="utf-8")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    if expected_code is None:
        assert "repository_uncustodied_ignored" not in _codes(report)
        assert report["ok"] is True, report
    else:
        assert expected_code in _codes(report)


def test_private_root_requires_dual_copy_restoration_receipt(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path, valid_custody=False)
    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert "private_restoration_unverified" in _codes(report)


@pytest.mark.parametrize(
    "inventory",
    [
        {"sealed_inventories": [{"label": "other", "sealed": True}]},
        {"sealed_inventories": [{"label": "life", "sealed": False}]},
        {"sealed": True},
    ],
)
def test_private_inventory_requires_matching_sealed_evidence(
    tmp_path: Path,
    inventory: dict[str, object],
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    inventory_path = manifest.parent / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])
    custody = report["private_custody"][0]

    assert "private_inventory_unverified" in _codes(report)
    assert custody["inventory_available"] is True
    assert custody["sealed_inventory_verified"] is False
    assert custody["custody_verified"] is False


def test_malformed_private_inventory_fails_closed(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    (manifest.parent / "inventory.json").write_text("{not-json", encoding="utf-8")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "unmeasured_state" in _codes(report)
    assert report["counts"]["unmeasured"] >= 1
    assert report["private_custody"][0]["custody_verified"] is False


@pytest.mark.parametrize("suffix", ["json", "jsonl"])
def test_shared_private_custody_source_is_opened_once_across_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    life = _sealed_inventory()
    finance = {**_sealed_inventory(), "label": "finance"}
    shared = manifest.parent / f"shared.{suffix}"
    if suffix == "json":
        shared.write_text(
            json.dumps(
                {
                    "sealed_inventories": [life, finance],
                    "receipts": [_restoration_receipt(life), _restoration_receipt(finance)],
                }
            ),
            encoding="utf-8",
        )
    else:
        shared.write_text(
            "\n".join(
                json.dumps(row) for row in (life, finance, _restoration_receipt(life), _restoration_receipt(finance))
            )
            + "\n",
            encoding="utf-8",
        )
    life_row = next(row for row in data["rows"] if row["kind"] == "private")
    life_row["sealed_inventory_ref"] = f"manifest://shared.{suffix}#life"
    life_row["restoration_receipt_ref"] = f"manifest://shared.{suffix}#life"
    data["rows"].append(
        {
            "path": "private/finance",
            "kind": "private",
            "owner_ref": "private-inventory/finance",
            "residency": "private",
            "sealed_inventory_ref": f"manifest://shared.{suffix}#finance",
            "restoration_receipt_ref": f"manifest://shared.{suffix}#finance",
            "custody_label": "finance",
        }
    )
    (workspace / "private" / "finance").mkdir()
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(convergence, "CUSTODY_LEDGER_MAX_ROWS", 4)
    real_open = Path.open
    real_read_text = Path.read_text
    open_count = 0

    def counting_open(path: Path, *args: object, **kwargs: object):
        nonlocal open_count
        if path.resolve(strict=False) == shared.resolve(strict=False):
            open_count += 1
        return real_open(path, *args, **kwargs)

    def guarded_read_text(path: Path, *args: object, **kwargs: object):
        if path.resolve(strict=False) == shared.resolve(strict=False):
            raise AssertionError("custody source must use the bounded binary reader")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert report["ok"] is True, report
    assert open_count == 1
    assert len(report["private_custody"]) == 2
    assert all(row["custody_verified"] is True for row in report["private_custody"])


def test_private_custody_aggregate_byte_exhaustion_is_unmeasured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    finance = {**_sealed_inventory(), "label": "finance"}
    data["rows"].append(
        {
            "path": "private/finance",
            "kind": "private",
            "owner_ref": "private-inventory/finance",
            "residency": "private",
            "sealed_inventory_ref": "manifest://finance-inventory.json",
            "restoration_receipt_ref": "manifest://finance-receipts.json#finance",
            "custody_label": "finance",
        }
    )
    (workspace / "private" / "finance").mkdir()
    finance_inventory = manifest.parent / "finance-inventory.json"
    finance_receipts = manifest.parent / "finance-receipts.json"
    finance_inventory.write_text(
        json.dumps({"sealed_inventories": [finance]}),
        encoding="utf-8",
    )
    finance_receipts.write_text(
        json.dumps({"receipts": [_restoration_receipt(finance)]}) + (" " * 1024),
        encoding="utf-8",
    )
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    complete_prefix_bytes = sum(
        path.stat().st_size
        for path in (
            manifest.parent / "inventory.json",
            manifest.parent / "receipts.json",
            finance_inventory,
        )
    )
    monkeypatch.setattr(convergence, "CUSTODY_LEDGER_MAX_BYTES", complete_prefix_bytes + 1)

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "unmeasured_state" in _codes(report)
    assert report["counts"]["unmeasured"] >= 1
    assert report["private_custody"][0]["sealed_inventory_verified"] is True
    assert report["private_custody"][0]["restoration_verified"] is True
    assert [row["custody_verified"] for row in report["private_custody"]] == [False, False]
    assert not any(row["code"] == "private_restoration_unverified" for row in report["violations"])


def test_private_custody_aggregate_row_exhaustion_counts_irrelevant_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    receipt_path = manifest.parent / "receipts.json"
    valid = _restoration_receipt(_sealed_inventory())
    receipt_path.write_text(
        json.dumps({"receipts": [valid, "irrelevant-but-counted"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(convergence, "CUSTODY_LEDGER_MAX_ROWS", 2)

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "unmeasured_state" in _codes(report)
    assert report["counts"]["unmeasured"] >= 1
    assert report["private_custody"][0]["custody_verified"] is False
    assert any("row ceiling exceeded" in row["message"] for row in report["violations"])


def test_private_custody_shared_deadline_stops_later_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    receipt_path = (manifest.parent / "receipts.json").resolve()
    clock = [0.0]
    receipt_opens = 0
    real_read_rows = convergence.CustodyLedgerReader.read_rows
    real_open = Path.open
    calls = 0

    def advance_after_first_selection(
        reader: convergence.CustodyLedgerReader,
        path: Path,
        *,
        collection_keys: tuple[str, ...] = ("receipts",),
    ) -> convergence.CustodyLedgerRows:
        nonlocal calls
        result = real_read_rows(reader, path, collection_keys=collection_keys)
        calls += 1
        if calls == 1:
            clock[0] = convergence.CUSTODY_LEDGER_DEADLINE_SECONDS + 1
        return result

    def counting_open(path: Path, *args: object, **kwargs: object):
        nonlocal receipt_opens
        if path.resolve(strict=False) == receipt_path:
            receipt_opens += 1
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(convergence, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(convergence.CustodyLedgerReader, "read_rows", advance_after_first_selection)
    monkeypatch.setattr(Path, "open", counting_open)

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "unmeasured_state" in _codes(report)
    assert report["counts"]["unmeasured"] >= 1
    assert report["private_custody"][0]["custody_verified"] is False
    assert receipt_opens == 0
    assert any("deadline exhausted" in row["message"] for row in report["violations"])


@pytest.mark.parametrize("failure", ["invalid-utf8", "permission"])
def test_private_custody_inspection_failure_is_unmeasured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    inventory = (manifest.parent / "inventory.json").resolve()
    if failure == "invalid-utf8":
        inventory.write_bytes(b"\xff\xfe")
    else:
        real_open = Path.open

        def denied_open(path: Path, *args: object, **kwargs: object):
            if path.resolve(strict=False) == inventory:
                raise PermissionError("fixture denial")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", denied_open)

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "unmeasured_state" in _codes(report)
    assert report["counts"]["unmeasured"] >= 1
    assert report["private_custody"][0]["custody_verified"] is False


def test_private_reference_resolves_through_declared_legacy_repo_during_migration(
    tmp_path: Path,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    repo_row = next(row for row in data["rows"] if row["kind"] == "repository")
    repo_row["legacy_paths"] = ["limen"]
    sealed_inventory = _sealed_inventory()
    custody = workspace / repo_row["path"] / "custody.json"
    custody.write_text(
        json.dumps(
            {
                "sealed_inventories": [sealed_inventory],
                "receipts": [_restoration_receipt(sealed_inventory)],
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


def test_private_receipt_selects_current_identity_and_reseal_invalidates_stale_receipts(
    tmp_path: Path,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    receipt_path = manifest.parent / "receipts.json"
    receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))
    stale_inventory = _sealed_inventory(content_sha256="4" * 64)
    receipt_data["receipts"].insert(0, _restoration_receipt(stale_inventory))
    receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")

    current_report = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert current_report["ok"] is True, current_report
    current_custody = current_report["private_custody"][0]
    assert current_custody["restoration_identity_verified"] is True

    resealed_inventory = _sealed_inventory(content_sha256="5" * 64)
    inventory_path = manifest.parent / "inventory.json"
    inventory_path.write_text(
        json.dumps({"sealed_inventories": [_sealed_inventory(), resealed_inventory]}),
        encoding="utf-8",
    )
    stale_report = audit(manifest, workspace_root=workspace, active_cwds=[])
    stale_custody = stale_report["private_custody"][0]

    assert "private_restoration_unverified" in _codes(stale_report)
    assert stale_custody["sealed_inventory_verified"] is True
    assert stale_custody["restoration_identity_verified"] is False
    assert stale_custody["custody_verified"] is False


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


def test_absent_compatibility_link_does_not_expire(tmp_path: Path) -> None:
    link = {
        "path": "limen",
        "target": "library/engine/organvm/limen",
        "owner_ref": "organvm/limen",
        "expires_at": "2026-07-01T00:00:00Z",
    }
    manifest, workspace, _ = _fixture(tmp_path, compatibility_links=[link])

    report = audit(
        manifest,
        workspace_root=workspace,
        active_cwds=[],
        now=datetime(2026, 7, 30, tzinfo=UTC),
    )

    assert "compatibility_link_expired" not in _codes(report)
    assert report["ok"] is True, report


def test_manifest_rejects_multi_link_compatibility_cycle(tmp_path: Path) -> None:
    links = [
        {"path": "a", "target": "b", "owner_ref": "a", "expires_at": "2026-08-15T00:00:00Z"},
        {"path": "b", "target": "a", "owner_ref": "b", "expires_at": "2026-08-15T00:00:00Z"},
    ]
    manifest, workspace, _ = _fixture(tmp_path, compatibility_links=links)

    with pytest.raises(ManifestError, match="compatibility link graph contains a cycle"):
        audit(manifest, workspace_root=workspace, active_cwds=[])


def test_filesystem_compatibility_symlink_loop_fails_bounded(tmp_path: Path) -> None:
    links = [
        {
            "path": "a",
            "target": "library/engine/organvm/limen",
            "owner_ref": "a",
            "expires_at": "2026-08-15T00:00:00Z",
        },
        {
            "path": "b",
            "target": "library/engine/organvm/limen",
            "owner_ref": "b",
            "expires_at": "2026-08-15T00:00:00Z",
        },
    ]
    manifest, workspace, _ = _fixture(tmp_path, compatibility_links=links)
    (workspace / "a").symlink_to("b")
    (workspace / "b").symlink_to("a")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert "unmeasured_state" in _codes(report)
    assert all(row["present"] is True for row in report["compatibility_links"])


def test_canonical_cwd_is_ambiguous_not_legacy_for_symlink_doorway(tmp_path: Path) -> None:
    link = {
        "path": "limen",
        "target": "library/engine/organvm/limen",
        "owner_ref": "organvm/limen",
        "expires_at": "2026-08-15T00:00:00Z",
    }
    manifest, workspace, _ = _fixture(tmp_path, compatibility_links=[link])
    canonical = workspace / "library" / "engine" / "organvm" / "limen"
    (workspace / "limen").symlink_to(canonical)

    report = audit(
        manifest,
        workspace_root=workspace,
        active_cwds=[canonical / "scripts"],
        now=datetime(2026, 7, 30, tzinfo=UTC),
    )

    assert "compatibility_link_unresolved" in _codes(report)
    assert "active_legacy_path" not in _codes(report)
    assert "unmeasured_state" in _codes(report)
    link_report = report["compatibility_links"][0]
    assert link_report["active_cwd_count"] == 0
    assert link_report["ambiguous_cwd_count"] == 1


def test_physical_legacy_directory_cwd_remains_measurable(tmp_path: Path) -> None:
    link = {
        "path": "limen",
        "target": "library/engine/organvm/limen",
        "owner_ref": "organvm/limen",
        "expires_at": "2026-08-15T00:00:00Z",
    }
    manifest, workspace, _ = _fixture(tmp_path, compatibility_links=[link])
    legacy = workspace / "limen"
    legacy.mkdir()

    report = audit(
        manifest,
        workspace_root=workspace,
        active_cwds=[legacy / "scripts"],
        now=datetime(2026, 7, 30, tzinfo=UTC),
    )

    assert "active_legacy_path" in _codes(report)
    assert "unmeasured_state" not in _codes(report)
    link_report = report["compatibility_links"][0]
    assert link_report["active_cwd_count"] == 1
    assert link_report["ambiguous_cwd_count"] == 0


def test_workspace_root_symlink_is_rejected_before_resolution(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    alias = tmp_path / "Workspace-alias"
    alias.symlink_to(workspace, target_is_directory=True)

    report = audit(manifest, workspace_root=alias, active_cwds=[])

    assert "workspace_symlink" in _codes(report)


@pytest.mark.parametrize(
    "missing",
    [
        "max_scan_entries",
        "max_violations",
        "max_unmeasured",
        "max_compatibility_links",
    ],
)
def test_every_limit_field_is_required(tmp_path: Path, missing: str) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    del data["limits"][missing]
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ManifestError, match="limits missing required field"):
        audit(manifest, workspace_root=workspace, active_cwds=[])


def test_recursive_repositories_share_one_scan_budget(tmp_path: Path) -> None:
    primary_remote = tmp_path / "remote.git"
    secondary_remote = tmp_path / "secondary.git"
    rows = _base_rows(primary_remote)
    rows.extend(
        [
            {
                "path": "library/storefront",
                "kind": "structural",
                "owner_ref": "portvs",
                "residency": "structural",
            },
            {
                "path": "library/storefront/second",
                "kind": "repository",
                "owner_ref": "organvm/second",
                "residency": "laptop",
                "remote": str(secondary_remote),
                "custody_ref": "refs/remotes/origin/main",
            },
        ]
    )
    manifest, workspace, _ = _fixture(tmp_path, rows=rows)
    for relative in (
        Path("library/engine/organvm/limen"),
        Path("library/storefront/second"),
    ):
        repo = workspace / relative
        for index in range(8):
            (repo / f"fixture-{index}.txt").write_text(f"{index}\n", encoding="utf-8")
        _git(repo, "add", *[f"fixture-{index}.txt" for index in range(8)])
        _git(repo, "commit", "-qm", "expand scan fixture")
        _git(repo, "push", "origin", "main")
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["limits"]["max_scan_entries"] = 28
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert report["scan_truncated"] is True
    assert "unmeasured_state" in _codes(report)


def test_repository_fetches_share_one_wall_clock_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_remote = tmp_path / "remote.git"
    secondary_remote = tmp_path / "secondary.git"
    rows = _base_rows(primary_remote)
    rows.extend(
        [
            {
                "path": "library/storefront",
                "kind": "structural",
                "owner_ref": "portvs",
                "residency": "structural",
            },
            {
                "path": "library/storefront/second",
                "kind": "repository",
                "owner_ref": "organvm/second",
                "residency": "laptop",
                "remote": str(secondary_remote),
                "custody_ref": "refs/remotes/origin/main",
            },
        ]
    )
    manifest, workspace, _ = _fixture(tmp_path, rows=rows)
    clock = [0.0]
    fetches: list[float] = []
    real_run_git = convergence._run_git

    def bounded_run_git(
        repo: Path,
        *args: str,
        timeout: float = convergence.GIT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "fetch":
            fetches.append(timeout)
            result = real_run_git(repo, *args, timeout=timeout)
            clock[0] = convergence.REPOSITORY_FETCH_BUDGET_SECONDS + 1
            return result
        return real_run_git(repo, *args, timeout=timeout)

    monkeypatch.setattr(convergence, "_monotonic", lambda: clock[0])
    monkeypatch.setattr(convergence, "_run_git", bounded_run_git)

    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    assert len(fetches) == 1
    assert fetches[0] <= convergence.GIT_TIMEOUT_SECONDS
    assert any("aggregate repository fetch deadline exhausted" in row["message"] for row in report["violations"])


def test_expired_ephemeral_units_require_reaper_action(tmp_path: Path) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    unit = workspace / "runtime" / "worktrees" / "fixture-repository" / "expired"
    unit.mkdir(parents=True)
    old = datetime(2026, 7, 1, tzinfo=UTC).timestamp()
    os.utime(unit, (old, old))

    report = audit(
        manifest,
        workspace_root=workspace,
        active_cwds=[],
        now=datetime(2026, 7, 30, tzinfo=UTC),
    )

    assert "ephemeral_entries_expired" in _codes(report)
    assert report["ephemeral_roots"][0]["expired_entry_count"] == 1
    assert report["ephemeral_roots"][0]["reaper"] == "limen worktree reap"


def test_relative_active_cwd_fixture_is_rejected(tmp_path: Path) -> None:
    fixture = tmp_path / "active-cwds.json"
    fixture.write_text('["relative/worktree"]\n', encoding="utf-8")

    with pytest.raises(ManifestError, match="must be absolute"):
        load_active_cwds(fixture)


@pytest.mark.parametrize("failure", ["missing", "nonzero"])
def test_failed_lsof_becomes_bounded_unmeasured_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    real_run = subprocess.run

    def fake_run(command: list[str], *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command and command[0] == "lsof":
            if failure == "missing":
                raise FileNotFoundError("fixture has no lsof")
            return subprocess.CompletedProcess(command, 2, "", "fixture lsof failure")
        return real_run(command, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(convergence.subprocess, "run", fake_run)
    report = audit(manifest, workspace_root=workspace, active_cwds=None)

    assert "unmeasured_state" in _codes(report)
    assert report["counts"]["unmeasured"] == 1
    assert any("active CWD discovery failed closed" in row["message"] for row in report["violations"])


def test_default_manifest_uses_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "substrate-convergence.py"
    spec = importlib.util.spec_from_file_location("substrate_convergence_script", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.delenv("PORTVS_WORKSPACE_MANIFEST", raising=False)
    monkeypatch.delenv("PORTVS_ROOT", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "custom-workspace"))

    assert module.default_manifest() == (
        tmp_path
        / "custom-workspace"
        / "library"
        / "engine"
        / "organvm"
        / "portvs"
        / "governance"
        / "workspace-manifest.yaml"
    )


def test_receipt_retains_fixture_root_and_binds_canonical_redaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "substrate-convergence.py"
    spec = importlib.util.spec_from_file_location("substrate_convergence_receipt_script", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    manifest, workspace, _ = _fixture(tmp_path)
    report = audit(manifest, workspace_root=workspace, active_cwds=[])

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "different-live-root"))
    fixture_receipt = module.prepare_receipt_report(report)
    assert fixture_receipt["workspace_root"] == str(workspace)
    assert fixture_receipt["workspace_root_is_canonical_live"] is False

    monkeypatch.setenv("WORKSPACE_ROOT", str(workspace))
    live_receipt = module.prepare_receipt_report(report)
    assert live_receipt["workspace_root"] == "$WORKSPACE_ROOT"
    assert live_receipt["workspace_root_is_canonical_live"] is True

    tampered = dict(report)
    tampered["workspace_root"] = str(tmp_path / "forged-root")
    with pytest.raises(ManifestError, match="identity does not match"):
        module.prepare_receipt_report(tampered)


def test_tilde_workspace_root_expands_before_abspath_and_redacts_from_arbitrary_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "substrate-convergence.py"
    spec = importlib.util.spec_from_file_location("substrate_convergence_tilde_script", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    manifest, workspace, _ = _fixture(tmp_path)
    elsewhere = tmp_path / "arbitrary" / "cwd"
    elsewhere.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WORKSPACE_ROOT", "~/Workspace")
    monkeypatch.chdir(elsewhere)

    assert module.canonical_live_workspace_root() == workspace
    receipt = module.prepare_receipt_report(audit(manifest, workspace_root=workspace, active_cwds=[]))
    assert receipt["workspace_root"] == "$WORKSPACE_ROOT"
    assert receipt["workspace_root_is_canonical_live"] is True


def test_same_manifest_and_root_are_independent_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, workspace, _ = _fixture(tmp_path)
    first = audit(manifest, workspace_root=workspace, active_cwds=[])
    elsewhere = tmp_path / "some" / "worktree"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)
    second = audit(manifest, workspace_root=workspace, active_cwds=[])
    assert second == first
