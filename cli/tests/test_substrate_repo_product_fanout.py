from __future__ import annotations

import importlib.util
import json
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def _load_script(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_repo(path: Path, *, remote: str | None = None, package_name: str | None = None) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "README.md").write_text(f"# {package_name or path.name}\n", encoding="utf-8")
    if package_name:
        (path / "package.json").write_text(
            json.dumps({"name": package_name, "scripts": {"test": "node --test", "build": "echo build"}}),
            encoding="utf-8",
        )
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)
    if remote:
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True)


def test_repo_surface_ledger_discovers_nested_repos_and_redacts_duplicate_remotes(tmp_path: Path) -> None:
    mod = _load_script(ROOT / "scripts" / "repo-surface-ledger.py", "repo_surface_ledger")
    workspace = tmp_path / "workspace"
    canonical = workspace / "same-app"
    nested = canonical / "vendor" / "nested-tool"
    duplicate = workspace / "duplicate-same-app"
    _git_repo(canonical, remote="git@github.com:organvm/same-app.git", package_name="same-app")
    _git_repo(nested, remote="https://github.com/organvm/nested-tool.git", package_name="nested-tool")
    _git_repo(duplicate, remote="https://github.com/organvm/same-app.git", package_name="same-app")

    snapshot = mod.build_snapshot([workspace])

    labels = {repo["path_label"] for repo in snapshot["repos"]}
    assert any(label.endswith("same-app") for label in labels)
    assert any(label.endswith("nested-tool") for label in labels)
    assert any(group["repo_count"] == 2 for group in snapshot["duplicate_remotes"])
    public = json.dumps(mod.public_snapshot(snapshot), sort_keys=True)
    assert "git@github.com" not in public
    assert "https://github.com" not in public
    assert "same-app.git" not in public


def test_salvage_map_clusters_duplicate_remote_and_product_surfaces(tmp_path: Path) -> None:
    repo_mod = _load_script(ROOT / "scripts" / "repo-surface-ledger.py", "repo_surface_ledger")
    salvage_mod = _load_script(ROOT / "scripts" / "salvage-yard-map.py", "salvage_yard_map")
    workspace = tmp_path / "workspace"
    first = workspace / "product-a"
    second = workspace / "product-a-copy"
    _git_repo(first, remote="git@github.com:organvm/product-a.git", package_name="shared-product")
    _git_repo(second, remote="https://github.com/organvm/product-a.git", package_name="shared-product")
    (second / "README.md").write_text("# shared-product\n\ndirty copy\n", encoding="utf-8")

    repo_snapshot = repo_mod.build_snapshot([workspace])
    salvage = salvage_mod.build_salvage_map(repo_snapshot, {"plan_source_proof": {"source_plan_hashes": ["abc123"]}})

    duplicate_clusters = [cluster for cluster in salvage["clusters"] if cluster["repo_count"] == 2]
    assert len(duplicate_clusters) == 1
    cluster = duplicate_clusters[0]
    assert cluster["disposition"] == "consolidate"
    assert cluster["children"][0]["disposition"] == "consolidate"
    assert set(salvage["source_plan_hashes"]) == {"abc123"}
    public = json.dumps(salvage_mod.public_salvage_map(salvage), sort_keys=True)
    assert "git@github.com" not in public
    assert "RAW_PRIVATE_PLAN_BODY" not in public


def test_product_ledger_keeps_global_selection_active_when_one_candidate_is_blocked() -> None:
    mod = _load_script(ROOT / "scripts" / "product-ledger.py", "product_ledger")

    ledger = mod.build_product_ledger(
        [
            {
                "id": "blocked-local",
                "repo": "organvm/blocked",
                "disposition": "blocked_local",
                "value_score": 100,
                "blocker": "missing local drive",
            },
            {
                "id": "open-build",
                "repo": "organvm/open",
                "disposition": "build",
                "value_score": 50,
            },
        ]
    )

    assert ledger["global_status"] == "active"
    assert [item["id"] for item in ledger["next_selections"]] == ["open-build"]
    assert [item["id"] for item in ledger["blocked_items"]] == ["blocked-local"]


def test_current_session_fanout_repo_salvage_executor_packet_propagates_source_hashes(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _load_script(ROOT / "scripts" / "current-session-fanout.py", "current_session_fanout")
    session = tmp_path / "session.jsonl"
    plan_text = (
        "# Repo Salvage Consolidation Plan\n\n"
        "## Summary\n"
        "- Salvage 400 repos into consolidated same app owner records.\n"
        "- Keep blocked_local work item-scoped while global product selection continues.\n"
    )
    session.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-30T00:00:00Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "A previous agent produced the plan below to accomplish the user's task.\n\n"
                                f"{plan_text}"
                            )
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mod,
        "lane_rows",
        lambda: [
            {
                "agent": "github_actions",
                "kind": "github-actions",
                "status": "active",
                "reachable": True,
                "remaining": 1,
                "detail": "test",
            }
        ],
    )

    snapshot = mod.build_snapshot(
        Namespace(
            session=str(session),
            min_codex_planners=1,
            executor_lanes="github_actions",
            include_contrib=False,
            allow_reset_spend=False,
        )
    )

    assert "repo-salvage-consolidation" in snapshot["themes"]
    expected_hashes = [event["hash"] for event in snapshot["unique_plan_sources"]]
    executor = snapshot["executor_packets"][0]
    assert executor["id"] == "EXEC-github_actions-1c17c8a3"
    assert executor["source_plan_hashes"] == expected_hashes
    assert any("repo-surface-ledger.py" in item for item in executor["verification_predicates"])
    planner = next(packet for packet in snapshot["planner_packets"] if packet["theme"] == "repo-salvage-consolidation")
    assert any("salvage-yard-map.py" in item for item in planner["owner_packet"]["criteria"])
