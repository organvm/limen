from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import yaml

from limen.io import load_limen_file


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rewrite-owners.py"


def load_rewrite_owners() -> ModuleType:
    spec = importlib.util.spec_from_file_location("limen_rewrite_owners", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_board(path: Path, tasks: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "Universal Task Intake",
                    "budget": {
                        "daily": 100,
                        "unit": "runs",
                        "per_agent": {},
                        "track": {"date": "2026-06-22", "spent": 0, "per_agent": {}},
                    },
                },
                "tasks": tasks,
            },
            sort_keys=False,
        )
    )


def task(task_id: str, repo: str | None) -> dict:
    out = {
        "id": task_id,
        "title": task_id,
        "target_agent": "codex",
        "created": "2026-06-22",
        "dispatch_log": [],
    }
    if repo is not None:
        out["repo"] = repo
    return out


def test_map_repo_only_rewrites_owned_old_owners_and_bare_limen() -> None:
    m = load_rewrite_owners()

    assert m.map_repo("a-organvm/public-record-data-scrapper") == (
        "organvm/public-record-data-scrapper"
    )
    assert m.map_repo("  4444J99/limen  ") == "organvm/limen"
    assert m.map_repo("limen") == "organvm/limen"

    assert m.map_repo("organvm/limen") is None
    assert m.map_repo("langchain-ai/langgraph") is None
    assert m.map_repo("unknown-bare-repo") is None
    assert m.map_repo("") is None
    assert m.map_repo(None) is None


def test_plan_and_apply_tasks_rewrites_only_owned_repos(tmp_path: Path, monkeypatch) -> None:
    m = load_rewrite_owners()
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            task("OLD", "a-organvm/api"),
            task("BARE", "limen"),
            task("TARGET", "organvm/limen"),
            task("EXTERNAL", "langchain-ai/langgraph"),
            task("NONE", None),
        ],
    )
    before = tasks_path.read_text()
    monkeypatch.setattr(m, "TASKS_PATH", tasks_path)

    count, changes, limen_file = m.plan_tasks()

    assert count == 2
    assert changes == [
        ("OLD", "a-organvm/api", "organvm/api"),
        ("BARE", "limen", "organvm/limen"),
    ]
    assert tasks_path.read_text() == before, "planning must not mutate tasks.yaml"

    m.apply_tasks(limen_file)

    repos = {t.id: t.repo for t in load_limen_file(tasks_path).tasks}
    assert repos == {
        "OLD": "organvm/api",
        "BARE": "organvm/limen",
        "TARGET": "organvm/limen",
        "EXTERNAL": "langchain-ai/langgraph",
        "NONE": None,
    }


def test_plan_and_apply_deploy_rewrites_github_repo_literal(
    tmp_path: Path, monkeypatch
) -> None:
    m = load_rewrite_owners()
    deploy_yml = tmp_path / "deploy-api.yml"
    deploy_yml.write_text(
        "env:\n"
        "  LIMEN_GITHUB_REPO=4444J99/limen\n"
        "  OTHER_REPO=4444J99/not-limen\n"
    )
    monkeypatch.setattr(m, "DEPLOY_YML", deploy_yml)

    assert m.plan_deploy() == (
        True,
        "LIMEN_GITHUB_REPO=4444J99/limen",
        "LIMEN_GITHUB_REPO=organvm/limen",
    )

    assert m.apply_deploy() is True
    assert "LIMEN_GITHUB_REPO=organvm/limen" in deploy_yml.read_text()
    assert "OTHER_REPO=4444J99/not-limen" in deploy_yml.read_text()
    assert m.plan_deploy() == (False, None, None)


def test_plan_remotes_and_emit_commands_never_include_target_or_external(
    tmp_path: Path, monkeypatch
) -> None:
    m = load_rewrite_owners()
    workspace = tmp_path / "Workspace"
    old_checkout = workspace / "repo with space"
    target_checkout = workspace / "already-target"
    external_checkout = workspace / "external"
    for checkout in (old_checkout, target_checkout, external_checkout):
        (checkout / ".git").mkdir(parents=True)

    urls = {
        old_checkout: "git@github.com:a-organvm/demo.git",
        target_checkout: "https://github.com/organvm/limen.git",
        external_checkout: "https://github.com/langchain-ai/langgraph.git",
    }
    monkeypatch.setattr(m, "WORKSPACE", workspace)
    monkeypatch.setattr(m, "_git_remote_url", lambda checkout: urls[checkout])

    remotes = m.plan_remotes()

    assert remotes == [
        (
            old_checkout,
            "git@github.com:a-organvm/demo.git",
            "git@github.com:organvm/demo.git",
        )
    ]
    emitted = m.emit_remote_commands(remotes)
    assert "git -C '" in emitted
    assert "repo with space' remote set-url origin git@github.com:organvm/demo.git" in emitted
    assert "langchain-ai" not in emitted
