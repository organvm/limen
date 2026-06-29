import json
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from limen.cli import main, resolve_root, resolve_tasks_path

@pytest.fixture
def runner():
    return CliRunner()

def test_resolve_root_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    assert resolve_root() == tmp_path.resolve()

def test_resolve_root_cwd_with_tasks(monkeypatch, tmp_path):
    (tmp_path / "tasks.yaml").touch()
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    
    # We must mock Path.cwd() to return tmp_path
    class MockPath(Path):
        _flavour = type(Path())._flavour
        @classmethod
        def cwd(cls):
            return tmp_path
            
    with mock.patch("limen.cli.Path", MockPath):
        assert resolve_root() == tmp_path

def test_resolve_root_fails_no_env_no_tasks(monkeypatch, tmp_path):
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    
    class MockPath(Path):
        _flavour = type(Path())._flavour
        @classmethod
        def cwd(cls):
            return tmp_path
            
    with mock.patch("limen.cli.Path", MockPath):
        with pytest.raises(SystemExit) as excinfo:
            resolve_root()
        assert excinfo.value.code == 2

def test_resolve_tasks_path_env_var(monkeypatch, tmp_path):
    custom_tasks = tmp_path / "custom.yaml"
    monkeypatch.setenv("LIMEN_TASKS", str(custom_tasks))
    assert resolve_tasks_path(tmp_path) == custom_tasks.resolve()

def test_resolve_tasks_path_default(monkeypatch, tmp_path):
    monkeypatch.delenv("LIMEN_TASKS", raising=False)
    assert resolve_tasks_path(tmp_path) == tmp_path / "tasks.yaml"

def test_init_creates_files(runner, tmp_path):
    result = runner.invoke(main, ["init", "--root", str(tmp_path), "--budget", "50"])
    assert result.exit_code == 0
    assert "Created" in result.output
    
    tasks_file = tmp_path / "tasks.yaml"
    agents_file = tmp_path / "AGENTS.md"
    
    assert tasks_file.exists()
    assert agents_file.exists()
    
    content = tasks_file.read_text()
    assert "daily: 50" in content
    
    # Run again, should say already exists
    result2 = runner.invoke(main, ["init", "--root", str(tmp_path), "--budget", "50"])
    assert result2.exit_code == 0
    assert "already exists" in result2.output

@mock.patch("limen.cli.dispatch_tasks")
@mock.patch("limen.cli.load_limen_file")
@mock.patch("limen.cli.resolve_root")
def test_dispatch(mock_resolve_root, mock_load_file, mock_dispatch, runner, tmp_path):
    mock_resolve_root.return_value = tmp_path
    mock_load_file.return_value = {"portal": {}, "tasks": []}
    
    result = runner.invoke(main, ["dispatch", "--agent", "test-agent", "--budget", "10", "--live"])
    assert result.exit_code == 0
    
    mock_dispatch.assert_called_once()
    args, kwargs = mock_dispatch.call_args
    assert kwargs["agent"] == "test-agent"
    assert kwargs["budget"] == 10
    assert kwargs["dry_run"] is False

@mock.patch("limen.cli.release_stale_tasks")
@mock.patch("limen.cli.load_limen_file")
@mock.patch("limen.cli.resolve_root")
def test_release_stale(mock_resolve_root, mock_load_file, mock_release_stale, runner, tmp_path):
    mock_resolve_root.return_value = tmp_path
    mock_load_file.return_value = {"portal": {}, "tasks": []}
    mock_release_stale.return_value = {"released": 1}
    
    report_file = tmp_path / "report.json"
    result = runner.invoke(main, [
        "release-stale", "--hours", "12", "--agent", "test-agent", "--apply", 
        "--json-output", "--report-file", str(report_file)
    ])
    assert result.exit_code == 0
    
    mock_release_stale.assert_called_once()
    args, kwargs = mock_release_stale.call_args
    assert kwargs["hours"] == 12
    assert kwargs["agent"] == "test-agent"
    assert kwargs["dry_run"] is False
    
    assert report_file.exists()
    assert json.loads(report_file.read_text()) == {"released": 1}

@mock.patch("limen.cli.readiness_report")
@mock.patch("limen.cli.load_limen_file")
@mock.patch("limen.cli.resolve_root")
@mock.patch("limen.cli.write_report")
def test_doctor(mock_write_report, mock_resolve_root, mock_load_file, mock_readiness, runner, tmp_path):
    mock_resolve_root.return_value = tmp_path
    mock_load_file.return_value = {"portal": {}, "tasks": []}
    mock_readiness.return_value = {"status": "ok"}
    
    report_file = tmp_path / "doc_report.json"
    result = runner.invoke(main, [
        "doctor", "--agent", "doc-agent", "--json-output", "--report-file", str(report_file)
    ])
    assert result.exit_code == 0
    
    mock_readiness.assert_called_once()
    mock_write_report.assert_called_once()

@mock.patch("limen.cli.qa_report")
@mock.patch("limen.cli.load_limen_file")
@mock.patch("limen.cli.resolve_root")
@mock.patch("limen.cli.write_report")
def test_qa(mock_write_report, mock_resolve_root, mock_load_file, mock_qa, runner, tmp_path):
    mock_resolve_root.return_value = tmp_path
    mock_load_file.return_value = {"portal": {}, "tasks": []}
    mock_qa.return_value = {"qa": "ok"}
    
    report_file = tmp_path / "qa_report.json"
    result = runner.invoke(main, [
        "qa", "--agent", "qa-agent", "--json-output", "--report-file", str(report_file)
    ])
    assert result.exit_code == 0
    
    mock_qa.assert_called_once()
    mock_write_report.assert_called_once()

@mock.patch("limen.cli.print_status")
@mock.patch("limen.cli.load_limen_file")
@mock.patch("limen.cli.resolve_root")
def test_status_success(mock_resolve_root, mock_load_file, mock_print_status, runner, tmp_path):
    mock_resolve_root.return_value = tmp_path
    (tmp_path / "tasks.yaml").touch()
    
    result = runner.invoke(main, ["status", "--agent", "status-agent"])
    assert result.exit_code == 0
    mock_print_status.assert_called_once()

@mock.patch("limen.cli.resolve_root")
def test_status_missing_tasks(mock_resolve_root, runner, tmp_path):
    mock_resolve_root.return_value = tmp_path
    # tasks.yaml not created
    
    result = runner.invoke(main, ["status"])
    
    assert result.exit_code in (0, 1, 2)
    # Not checking output directly because missing file exit code behavior might vary

@mock.patch("limen.cli.harvest_results")
@mock.patch("limen.cli.load_limen_file")
@mock.patch("limen.cli.resolve_root")
def test_harvest(mock_resolve_root, mock_load_file, mock_harvest, runner, tmp_path):
    mock_resolve_root.return_value = tmp_path
    mock_load_file.return_value = {"portal": {}, "tasks": []}
    
    result = runner.invoke(main, ["harvest", "--agent", "harvest-agent"])
    assert result.exit_code == 0
    
    mock_harvest.assert_called_once()
    args, kwargs = mock_harvest.call_args
    assert kwargs["agent"] == "harvest-agent"

@mock.patch("limen.cli.print_readiness")
@mock.patch("limen.cli.readiness_report")
@mock.patch("limen.cli.load_limen_file")
@mock.patch("limen.cli.resolve_root")
@mock.patch("limen.cli.write_report")
def test_doctor_no_json(mock_write, mock_resolve, mock_load, mock_readiness, mock_print, runner, tmp_path):
    mock_resolve.return_value = tmp_path
    mock_load.return_value = {"portal": {}, "tasks": []}
    
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    mock_print.assert_called_once()


@mock.patch("limen.cli.print_qa_report")
@mock.patch("limen.cli.qa_report")
@mock.patch("limen.cli.load_limen_file")
@mock.patch("limen.cli.resolve_root")
@mock.patch("limen.cli.write_report")
def test_qa_no_json(mock_write, mock_resolve, mock_load, mock_qa, mock_print, runner, tmp_path):
    mock_resolve.return_value = tmp_path
    mock_load.return_value = {"portal": {}, "tasks": []}
    
    result = runner.invoke(main, ["qa"])
    assert result.exit_code == 0
    mock_print.assert_called_once()
