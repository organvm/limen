from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "warp-notification-provenance.py"
    spec = importlib.util.spec_from_file_location("warp_notification_provenance_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_prefs(path: Path, *, claude_enabled: bool) -> None:
    path.write_text(
        json.dumps(
            {
                "AvailableHarnesses": [
                    {"harness": "claude", "display_name": "Claude Code", "enabled": claude_enabled},
                    {"harness": "codex", "display_name": "Codex", "enabled": True},
                    {"harness": "oz", "display_name": "Warp/Oz", "enabled": True},
                ],
                "Notifications": {"is_agent_task_completed_enabled": True},
            }
        )
    )


def test_warns_when_enabled_harness_is_not_expected(tmp_path: Path) -> None:
    module = load_module()
    prefs = tmp_path / "warp.json"
    _write_prefs(prefs, claude_enabled=True)

    args = module.parse_args(
        [
            "--prefs-json",
            str(prefs),
            "--expect-enabled",
            "codex",
            "--expect-enabled",
            "oz",
            "--strict",
        ]
    )
    report = module.build_report(args)

    assert report["status"] == "warn"
    assert report["warp_preferences"]["unexpected_enabled_harnesses"] == ["claude"]
    assert any("unexpected harnesses: claude" in warning for warning in report["warnings"])


def test_disabled_unexpected_harness_passes_strict_policy(tmp_path: Path) -> None:
    module = load_module()
    prefs = tmp_path / "warp.json"
    _write_prefs(prefs, claude_enabled=False)

    exit_code = module.main(
        [
            "--prefs-json",
            str(prefs),
            "--expect-enabled",
            "codex",
            "--expect-enabled",
            "oz",
            "--strict",
            "--json",
        ]
    )

    assert exit_code == 0


def test_parses_warp_plist_json_string_values(tmp_path: Path) -> None:
    module = load_module()
    prefs = tmp_path / "warp.json"
    prefs.write_text(
        json.dumps(
            {
                "AvailableHarnesses": json.dumps(
                    [
                        {"harness": "oz", "display_name": "Warp", "enabled": True},
                        {"harness": "claude", "display_name": "Claude Code", "enabled": False},
                        {"harness": "codex", "display_name": "Codex", "enabled": True},
                    ]
                ),
                "Notifications": json.dumps({"is_agent_task_completed_enabled": True}),
            }
        )
    )

    args = module.parse_args(
        [
            "--prefs-json",
            str(prefs),
            "--expect-enabled",
            "codex",
            "--expect-enabled",
            "oz",
            "--strict",
        ]
    )
    report = module.build_report(args)

    assert report["status"] == "ok"
    assert report["warp_preferences"]["enabled_harnesses"] == ["codex", "oz"]
    assert report["warp_preferences"]["task_completed_notifications_enabled"] is True


def test_native_host_scan_redacts_command_path(tmp_path: Path) -> None:
    module = load_module()
    host_dir = tmp_path / "NativeMessagingHosts"
    host_dir.mkdir()
    (host_dir / "com.anthropic.claude_code.json").write_text(
        json.dumps(
            {
                "name": "com.anthropic.claude_code",
                "description": "Claude Code bridge",
                "path": "/private/secret/home/claude-native-host",
            }
        )
    )

    hosts = module.scan_native_hosts([host_dir])

    assert hosts == [
        {
            "name": "com.anthropic.claude_code",
            "manifest": str(host_dir / "com.anthropic.claude_code.json"),
            "provider_kind": "claude",
            "readable": True,
            "has_command_path": True,
        }
    ]
    assert "/private/secret/home" not in json.dumps(hosts)
