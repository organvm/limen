import importlib.util
import sys
import types
from pathlib import Path

import yaml


def _ensure_mcp_runtime():
    try:
        import mcp.server.fastmcp  # noqa: F401
        return
    except Exception:
        pass

    mcp_mod = types.ModuleType("mcp")
    server_mod = types.ModuleType("mcp.server")
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")

    class FastMCP:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self):
            return lambda fn: fn

        def run(self):
            pass

    fastmcp_mod.FastMCP = FastMCP
    server_mod.fastmcp = fastmcp_mod
    mcp_mod.server = server_mod
    sys.modules.setdefault("mcp", mcp_mod)
    sys.modules.setdefault("mcp.server", server_mod)
    sys.modules.setdefault("mcp.server.fastmcp", fastmcp_mod)


def _load_server():
    _ensure_mcp_runtime()
    path = Path(__file__).resolve().parents[2] / "mcp" / "src" / "limen_mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("limen_mcp_server_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_agent_claim_preserves_board_extensions_and_reserves_budget(tmp_path, monkeypatch):
    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "test",
                    "agents": {"opencode": {"status": "idle"}},
                    "budget": {
                        "daily": 100,
                        "unit": "runs",
                        "track": {
                            "date": "2026-07-02",
                            "spent": 4,
                            "per_agent": {"opencode": 2},
                            "per_agent_reset": {"opencode": "2026-07-02T00:00:00+00:00"},
                        },
                    },
                },
                "tasks": [
                    {
                        "id": "TASK-1",
                        "title": "Claim me",
                        "target_agent": "any",
                        "priority": "high",
                        "budget_cost": 3,
                        "status": "open",
                        "created": "2026-07-02",
                        "claude_tier": "sonnet",
                        "depends_on": ["TASK-0"],
                        "custom_extension": {"keep": True},
                    }
                ],
            },
            sort_keys=False,
        )
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks))

    assert server.agent_claim("TASK-1", "opencode") == "opencode claimed task TASK-1 (status=dispatched)"

    data = yaml.safe_load(tasks.read_text())
    assert data["portal"]["agents"]["opencode"]["status"] == "idle"
    assert data["portal"]["budget"]["track"]["spent"] == 7
    assert data["portal"]["budget"]["track"]["per_agent"]["opencode"] == 5
    assert data["portal"]["budget"]["track"]["per_agent_reset"]["opencode"] == "2026-07-02T00:00:00+00:00"
    task = data["tasks"][0]
    assert task["status"] == "dispatched"
    assert task["target_agent"] == "opencode"
    assert task["claude_tier"] == "sonnet"
    assert task["depends_on"] == ["TASK-0"]
    assert task["custom_extension"] == {"keep": True}
    assert task["dispatch_log"][-1]["status"] == "dispatched"


def test_add_task_uses_tabularius_ticket(tmp_path, monkeypatch):
    from limen.tabularius import pending_count

    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "LIMEN-001",
                        "title": "Existing",
                        "target_agent": "codex",
                        "status": "open",
                        "created": "2026-07-02",
                    },
                    *[
                        {
                            "id": f"FILL-{i}",
                            "title": "filler",
                            "target_agent": "codex",
                            "status": "open",
                            "created": "2026-07-02",
                        }
                        for i in range(5)
                    ],
                ],
            },
            sort_keys=False,
        )
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks))

    assert server.add_task("New task", "x/y", agent="codex", priority="high") == "Created task LIMEN-002"

    data = yaml.safe_load(tasks.read_text())
    created = {task["id"]: task for task in data["tasks"]}["LIMEN-002"]
    assert created["title"] == "New task"
    assert created["priority"] == "high"
    assert pending_count(tasks) == 0


def test_update_task_status_uses_tabularius_ticket(tmp_path, monkeypatch):
    from limen.tabularius import pending_count

    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "TASK-1",
                        "title": "Update me",
                        "target_agent": "codex",
                        "budget_cost": 2,
                        "status": "in_progress",
                        "created": "2026-07-02",
                    },
                    *[
                        {
                            "id": f"FILL-{i}",
                            "title": "filler",
                            "target_agent": "codex",
                            "status": "open",
                            "created": "2026-07-02",
                        }
                        for i in range(5)
                    ],
                ],
            },
            sort_keys=False,
        )
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks))

    assert server.update_task_status("TASK-1", "failed", context="needs retry") == (
        "Updated TASK-1 to failed. New budget cost: 4"
    )

    task = {task["id"]: task for task in yaml.safe_load(tasks.read_text())["tasks"]}["TASK-1"]
    assert task["status"] == "failed"
    assert task["budget_cost"] == 4
    assert task["context"] == "needs retry"
    assert task["dispatch_log"][-1]["session_id"] == "mcp-update-task-status"
    assert pending_count(tasks) == 0
