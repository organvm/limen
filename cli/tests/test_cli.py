import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from limen.cli import main, resolve_root, resolve_tasks_path

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    monkeypatch.delenv("LIMEN_TASKS", raising=False)

def test_resolve_root_env(monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/limen")
    assert resolve_root() == Path("/tmp/limen").resolve()

def test_resolve_root_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tasks.yaml").touch()
    assert resolve_root() == tmp_path

def test_resolve_root_fail(monkeypatch, tmp_path):
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        resolve_root()
    assert e.value.code == 2

def test_resolve_tasks_path_env(monkeypatch):
    monkeypatch.setenv("LIMEN_TASKS", "/tmp/tasks.yaml")
    assert resolve_tasks_path(Path("/tmp")) == Path("/tmp/tasks.yaml").resolve()

def test_resolve_tasks_path_default(monkeypatch):
    monkeypatch.delenv("LIMEN_TASKS", raising=False)
    assert resolve_tasks_path(Path("/tmp")) == Path("/tmp/tasks.yaml")

def test_init_command_create(runner, tmp_path, mock_env):
    result = runner.invoke(main, ["init", "--root", str(tmp_path), "--budget", "50"])
    assert result.exit_code == 0
    assert "Created" in result.output
    assert (tmp_path / "tasks.yaml").exists()
    assert (tmp_path / "AGENTS.md").exists()
    content = (tmp_path / "tasks.yaml").read_text()
    assert "daily: 50" in content

def test_init_command_existing(runner, tmp_path, mock_env):
    (tmp_path / "tasks.yaml").touch()
    result = runner.invoke(main, ["init", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "already exists" in result.output

@patch("limen.cli.load_limen_file")
@patch("limen.cli.dispatch_tasks")
def test_dispatch_command(mock_dispatch, mock_load, runner, mock_env, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/limen")
    result = runner.invoke(main, ["dispatch", "--agent", "test", "--budget", "10", "--live", "--task", "t1", "--limit", "5"])
    assert result.exit_code == 0
    mock_load.assert_called_once()
    mock_dispatch.assert_called_once()

@patch("limen.cli.load_limen_file")
@patch("limen.cli.release_stale_tasks")
def test_release_stale_command(mock_release, mock_load, runner, mock_env, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/limen")
    mock_release.return_value = {"reopened": 1}
    report_file = tmp_path / "report.json"
    result = runner.invoke(main, ["release-stale", "--hours", "12", "--agent", "test", "--apply", "--json-output", "--report-file", str(report_file)])
    assert result.exit_code == 0
    assert "reopened" in result.output
    assert report_file.exists()

@patch("limen.cli.load_limen_file")
@patch("limen.cli.readiness_report")
@patch("limen.cli.print_readiness")
def test_doctor_command(mock_print, mock_report, mock_load, runner, mock_env, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/limen")
    mock_report.return_value = {"status": "ok"}
    report_file = tmp_path / "doc.json"
    result = runner.invoke(main, ["doctor", "--agent", "test", "--report-file", str(report_file)])
    assert result.exit_code == 0
    assert report_file.exists()
    mock_print.assert_called_once()

@patch("limen.cli.load_limen_file")
@patch("limen.cli.qa_report")
@patch("limen.cli.print_qa_report")
def test_qa_command(mock_print, mock_report, mock_load, runner, mock_env, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/limen")
    mock_report.return_value = {"qa": "passed"}
    report_file = tmp_path / "qa.json"
    result = runner.invoke(main, ["qa", "--agent", "test", "--report-file", str(report_file)])
    assert result.exit_code == 0
    assert report_file.exists()
    mock_print.assert_called_once()

@patch("limen.cli.load_limen_file")
@patch("limen.cli.print_status")
def test_status_command(mock_print, mock_load, runner, mock_env, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "tasks.yaml"))
    (tmp_path / "tasks.yaml").touch()
    result = runner.invoke(main, ["status", "--agent", "test", "--status", "open"])
    assert result.exit_code == 0
    mock_load.assert_called_once()
    mock_print.assert_called_once()

@patch("limen.cli.load_limen_file")
@patch("limen.cli.harvest_results")
def test_harvest_command(mock_harvest, mock_load, runner, mock_env, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/limen")
    result = runner.invoke(main, ["harvest", "--agent", "test"])
    assert result.exit_code == 0
    mock_load.assert_called_once()
    mock_harvest.assert_called_once()

@patch("limen.cli.load_limen_file")
@patch("limen.cli.readiness_report")
def test_doctor_command_json(mock_report, mock_load, runner, mock_env, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/limen")
    mock_report.return_value = {"status": "ok"}
    result = runner.invoke(main, ["doctor", "--json-output"])
    assert result.exit_code == 0
    assert '"status": "ok"' in result.output

@patch("limen.cli.load_limen_file")
@patch("limen.cli.qa_report")
def test_qa_command_json(mock_report, mock_load, runner, mock_env, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", "/tmp/limen")
    mock_report.return_value = {"qa": "passed"}
    result = runner.invoke(main, ["qa", "--json-output"])
    assert result.exit_code == 0
    assert '"qa": "passed"' in result.output

def test_status_command_no_file(runner, mock_env, monkeypatch):
    monkeypatch.setenv("LIMEN_TASKS", "/tmp/does_not_exist.yaml")
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 1
    assert "not found" in result.output

def test_main_block():
    with patch.object(sys, "argv", ["cli.py", "--help"]):
        import runpy
        try:
            runpy.run_path("cli/src/limen/cli.py", run_name="__main__")
        except SystemExit:
            pass

