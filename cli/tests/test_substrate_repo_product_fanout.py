from __future__ import annotations

import importlib.util
import json
import subprocess
from argparse import Namespace
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load(script_name: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "scripts" / script_name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(*args: str, cwd: Path) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stdout}\n{result.stderr}")


def test_substrate_ledger_uses_env_roots_without_stale_drive_blocker(tmp_path: Path, monkeypatch) -> None:
    active = tmp_path / "active-root"
    active.mkdir()
    missing = tmp_path / "missing-root"
    monkeypatch.setenv("LIMEN_STORAGE_ROOTS", f"{active}{','}{missing}")
    mod = _load("substrate-ledger.py", "substrate_ledger_under_test")

    snap = mod.build_snapshot(
        config_path=tmp_path / "missing-config.json",
        include_mounted=False,
        free_floor_gib=0,
        usage_ceiling_pct=100,
    )

    by_path = {Path(row["path"]).name: row for row in snap["roots"]}
    assert by_path["active-root"]["status"] == "active"
    assert by_path["missing-root"]["status"] == "missing"
    assert snap["status"] == "ready"
    assert "4444-iivii" not in json.dumps(snap)


def test_repo_surface_ledger_discovers_nested_repos_and_duplicate_remotes(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    repo_a = root / "app-a"
    repo_b = repo_a / "nested" / "app-b"
    repo_b.mkdir(parents=True)
    repo_a.mkdir(exist_ok=True)
    for repo in (repo_a, repo_b):
        _git("init", "-q", cwd=repo)
        _git("remote", "add", "origin", "git@example.invalid:owner/shared.git", cwd=repo)
        (repo / "package.json").write_text('{"scripts":{"test":"true"}}\n', encoding="utf-8")

    monkeypatch.setenv("LIMEN_REPO_ROOTS", str(root))
    mod = _load("repo-surface-ledger.py", "repo_surface_ledger_under_test")

    snap = mod.build_snapshot(max_depth=5)

    assert snap["repo_count"] == 2
    assert snap["duplicate_remotes"] == {"git@example.invalid:owner/shared.git": 2}
    assert all("package.json" in row["surfaces"] for row in snap["repos"])


def test_product_ledger_keeps_global_work_active_when_one_product_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "tasks.yaml"))
    private = tmp_path / ".limen-private" / "session-corpus" / "lifecycle"
    private.mkdir(parents=True)
    (tmp_path / "tasks.yaml").write_text(
        yaml.safe_dump(
            {
                "tasks": [
                    {
                        "id": "BLOCKED",
                        "title": "blocked local product",
                        "target_agent": "codex",
                        "status": "failed_blocked",
                        "created": "2026-06-30",
                    },
                    {
                        "id": "REV",
                        "title": "open revenue product",
                        "target_agent": "codex",
                        "status": "open",
                        "labels": ["revenue", "product"],
                        "repo": "owner/revenue",
                        "created": "2026-06-30",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "value-repos.json").write_text(json.dumps({"repos": ["owner/revenue"]}), encoding="utf-8")
    (tmp_path / "positioning-seeds.json").write_text(json.dumps({"repos": {"owner/revenue": {}}}), encoding="utf-8")
    (private / "prompt-lifecycle-index.json").write_text(
        json.dumps({"sessions": [{"session_key": "session-a", "source": "codex-sessions"}]}),
        encoding="utf-8",
    )

    mod = _load("product-ledger.py", "product_ledger_under_test")
    snap = mod.build_snapshot()

    assert snap["blocked_count"] == 1
    assert snap["global_status"] == "active"
    assert any(row["outward_path"] in {"revenue-path", "seo-proof"} for row in snap["next_unblocked"])
    assert all(not row["blocked"] for row in snap["next_unblocked"])


def test_current_session_fanout_creates_ten_codex_planners_and_executor_packets(tmp_path: Path, monkeypatch) -> None:
    session = tmp_path / "session.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:00:00Z",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"text": "Build 1000 alpha omega products from every prompt."}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:01:00Z",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"text": "Use 10 Codex planner worktrees plus contrib mirror and no reset spend."}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    mod = _load("current-session-fanout.py", "current_session_fanout_under_test")
    monkeypatch.setattr(mod, "lane_selection", lambda selector: ["codex", "opencode", "github_actions"])

    snap = mod.build_snapshot(
        Namespace(
            session=str(session),
            min_codex_planners=10,
            executor_lanes="auto",
            include_contrib=True,
            allow_reset_spend=False,
        )
    )

    assert snap["status"] == "ready"
    assert len(snap["planner_packets"]) == 10
    assert {packet["target_agent"] for packet in snap["planner_packets"]} == {"codex"}
    assert {packet["target_agent"] for packet in snap["executor_packets"]} == {"opencode", "github_actions"}
    assert snap["no_reset_spend"] is True
    assert all(packet["spend_guard"] == "no-reset-spend" for packet in snap["planner_packets"])
