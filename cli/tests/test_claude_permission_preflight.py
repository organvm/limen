"""Hermetic contract tests for the unattended Claude permission preflight."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "claude-permission-preflight.py"


def write_settings(tmp_path: Path, value: dict, name: str = "settings.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def run_preflight(
    tmp_path: Path,
    settings: dict,
    command: str,
    *,
    mode: str = "auto",
    generated: tuple[str, ...] = (),
    extra_settings: tuple[Path, ...] = (),
) -> tuple[subprocess.CompletedProcess[str], dict]:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    settings_path = write_settings(tmp_path, settings)
    argv = [
        sys.executable,
        str(PREFLIGHT),
        "--isolated-settings",
        "--settings",
        str(settings_path),
        "--project-root",
        str(project),
        "--mode",
        mode,
        "--command",
        command,
        "--json",
    ]
    for path in extra_settings:
        argv.extend(("--settings", str(path)))
    for path in generated:
        argv.extend(("--generated-path", path))
    proc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True)
    return proc, json.loads(proc.stdout)


def finding_codes(report: dict) -> set[str]:
    return {finding["code"] for finding in report.get("findings", [])}


def safe_auto_settings(*ask: str) -> dict:
    return {
        "permissions": {"defaultMode": "auto", "ask": list(ask)},
        "autoMode": {
            "environment": ["$defaults"],
            "allow": ["$defaults", "Deleting declared generated output inside this project is allowed."],
            "soft_deny": ["$defaults"],
        },
    }


def test_safe_generated_cleanup_passes_with_unrelated_hard_gates(tmp_path: Path) -> None:
    settings = safe_auto_settings(
        "Bash(git push* --force*)",
        "Bash(git push* -f*)",
        "Bash(shred:*)",
    )
    command = f"cd {tmp_path / 'project'} && rm -rf out && python3 -m pytest -q"
    proc, report = run_preflight(tmp_path, settings, command, generated=("out",))
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert report["ok"] is True
    assert report["findings"] == []


def test_broad_rm_ask_overrides_auto_and_hook_allow(tmp_path: Path) -> None:
    settings = safe_auto_settings("Bash(rm:*)")
    settings["permissions"]["allow"] = ["Bash(rm -rf out)"]
    command = f"cd {tmp_path / 'project'} && rm -rf out && python3 -m pytest -q"
    proc, report = run_preflight(tmp_path, settings, command, generated=("out",))
    assert proc.returncode == 2
    assert finding_codes(report) == {"ask_overrides_unattended"}
    finding = report["findings"][0]
    assert finding["rule"] == "Bash(rm:*)"
    assert finding["clause"] == "rm -rf out"


def test_broad_rm_ask_matches_after_builtin_process_wrapper(tmp_path: Path) -> None:
    settings = safe_auto_settings("Bash(rm:*)")
    command = f"cd {tmp_path / 'project'} && nice -n 10 rm -rf out"
    proc, report = run_preflight(tmp_path, settings, command, generated=("out",))
    assert proc.returncode == 2
    codes = finding_codes(report)
    assert "ask_overrides_unattended" in codes
    assert "indirect_cleanup_unverifiable" in codes


def test_ask_from_higher_settings_scope_still_wins(tmp_path: Path) -> None:
    local = write_settings(tmp_path, {"permissions": {"ask": ["Bash(rm *)"]}}, "local.json")
    command = f"cd {tmp_path / 'project'} && rm -rf build"
    proc, report = run_preflight(
        tmp_path,
        safe_auto_settings(),
        command,
        generated=("build",),
        extra_settings=(local,),
    )
    assert proc.returncode == 2
    assert finding_codes(report) == {"ask_overrides_unattended"}
    assert report["findings"][0]["source"].endswith("local.json")


def test_matching_deny_is_reported_before_matching_ask(tmp_path: Path) -> None:
    settings = safe_auto_settings("Bash(rm:*)")
    settings["permissions"]["deny"] = ["Bash(rm -rf out)"]
    proc, report = run_preflight(tmp_path, settings, "rm -rf out", generated=("out",))
    assert proc.returncode == 2
    assert finding_codes(report) == {"deny_blocks_packet"}


def test_bypass_cleanup_is_rejected_even_without_an_ask_rule(tmp_path: Path) -> None:
    proc, report = run_preflight(
        tmp_path,
        {"permissions": {"defaultMode": "bypassPermissions"}},
        "rm -rf out",
        mode="bypassPermissions",
        generated=("out",),
    )
    assert proc.returncode == 2
    assert finding_codes(report) == {"unsafe_bypass_cleanup"}


def test_cleanup_must_stay_inside_declared_generated_path(tmp_path: Path) -> None:
    proc, report = run_preflight(
        tmp_path,
        safe_auto_settings(),
        "rm -rf ../private",
        generated=("out",),
    )
    assert proc.returncode == 2
    assert finding_codes(report) == {"cleanup_outside_declared_generated_path"}


def test_cleanup_without_declared_generated_path_fails(tmp_path: Path) -> None:
    proc, report = run_preflight(tmp_path, safe_auto_settings(), "rm -rf out")
    assert proc.returncode == 2
    assert finding_codes(report) == {"cleanup_outside_declared_generated_path"}


def test_force_push_and_shred_remain_human_gated(tmp_path: Path) -> None:
    proc, report = run_preflight(
        tmp_path,
        safe_auto_settings(),
        "git push --force-with-lease origin main && shred -u secret",
    )
    assert proc.returncode == 2
    assert finding_codes(report) == {"hard_gate_in_unattended_packet"}


def test_auto_soft_deny_must_retain_defaults(tmp_path: Path) -> None:
    settings = safe_auto_settings()
    settings["autoMode"]["soft_deny"] = ["Never touch production."]
    proc, report = run_preflight(tmp_path, settings, "python3 -m pytest -q")
    assert proc.returncode == 2
    assert finding_codes(report) == {"auto_safety_defaults_replaced"}


def test_non_unattended_mode_fails_before_launch(tmp_path: Path) -> None:
    proc, report = run_preflight(tmp_path, safe_auto_settings(), "python3 -m pytest -q", mode="default")
    assert proc.returncode == 2
    assert finding_codes(report) == {"mode_will_prompt"}


def test_shared_project_auto_mode_is_reported_as_ignored(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"autoMode": {"allow": ["Deleting generated output is allowed."]}}),
        encoding="utf-8",
    )
    user = write_settings(tmp_path, safe_auto_settings())
    proc = subprocess.run(
        [
            sys.executable,
            str(PREFLIGHT),
            "--settings",
            str(user),
            "--project-root",
            str(project),
            "--mode",
            "auto",
            "--command",
            "python3 -m pytest -q",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    report = json.loads(proc.stdout)
    assert proc.returncode == 2
    assert "shared_project_auto_mode_ignored" in finding_codes(report)


def test_invalid_settings_is_configuration_error(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(PREFLIGHT),
            "--isolated-settings",
            "--settings",
            str(broken),
            "--project-root",
            str(project),
            "--mode",
            "auto",
            "--command",
            "python3 -m pytest -q",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    report = json.loads(proc.stdout)
    assert proc.returncode == 3
    assert report["ok"] is False
    assert "configuration_error" in report
