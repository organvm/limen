#!/usr/bin/env python3
"""Audit Warp agent notification provenance without reading notification text.

This is a local, read-only predicate for the Warp/Codex/Claude handoff confusion:
Warp can show task-completion notifications for enabled harnesses even when the
current Limen worker is a different provider. The script reports the enabled
Warp harnesses, task-completion notification toggle, and relevant native
messaging host presence. It deliberately does not read macOS usernoted history
because that database can contain raw notification bodies.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()

DEFAULT_PREF_PLISTS = [
    HOME / "Library" / "Preferences" / "dev.warp.Warp-Stable.plist",
    HOME / "Library" / "Preferences" / "dev.warp.Warp.plist",
    HOME / "Library" / "Preferences" / "dev.warp.Warp-Preview.plist",
]

DEFAULT_NATIVE_HOST_DIRS = [
    HOME / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts",
    HOME / "Library" / "Application Support" / "Google" / "Chrome Beta" / "NativeMessagingHosts",
    HOME / "Library" / "Application Support" / "Google" / "Chrome Canary" / "NativeMessagingHosts",
    HOME / "Library" / "Application Support" / "Chromium" / "NativeMessagingHosts",
    HOME / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts",
    HOME / "Library" / "Application Support" / "Microsoft Edge" / "NativeMessagingHosts",
    HOME / "Library" / "Application Support" / "Mozilla" / "NativeMessagingHosts",
    Path("/Library/Google/Chrome/NativeMessagingHosts"),
    Path("/Library/Application Support/Google/Chrome/NativeMessagingHosts"),
    Path("/Library/Application Support/Mozilla/NativeMessagingHosts"),
]

PROVIDER_HINTS = {
    "claude": ("claude", "anthropic"),
    "codex": ("codex", "openai", "chatgpt"),
    "warp": ("warp", "oz"),
}


def _rel(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        if value.lower() in {"1", "true", "yes", "enabled", "on"}:
            return True
        if value.lower() in {"0", "false", "no", "disabled", "off"}:
            return False
    return None


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "unknown"


def _provider_kind(*parts: Any) -> str:
    text = " ".join(str(part or "").lower() for part in parts)
    for kind, hints in PROVIDER_HINTS.items():
        if any(hint in text for hint in hints):
            return kind
    return "other"


def _parse_harness_string(value: str) -> dict[str, Any] | None:
    matches = dict(re.findall(r"([A-Za-z_]+)=([^,\s;]+)", value))
    if not matches:
        return None
    return {
        "harness": matches.get("harness") or matches.get("id") or matches.get("name"),
        "display_name": matches.get("display_name") or matches.get("displayName"),
        "enabled": _boolish(matches.get("enabled")),
    }


def _json_string(value: str) -> Any:
    stripped = value.strip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


def _as_harness_record(value: Any, *, key: str | None = None) -> dict[str, Any] | None:
    if isinstance(value, str):
        parsed = _json_string(value)
        if isinstance(parsed, dict):
            return _as_harness_record(parsed, key=key)
        return _parse_harness_string(value.strip())
    if not isinstance(value, dict):
        return None

    has_record_shape = any(
        field in value
        for field in ("harness", "id", "name", "display_name", "displayName", "enabled")
    )
    if not has_record_shape:
        return None

    raw_id = value.get("harness") or value.get("id") or value.get("name") or key
    display = value.get("display_name") or value.get("displayName") or value.get("title") or raw_id
    enabled = _boolish(value.get("enabled"))
    if enabled is None:
        enabled = _boolish(value.get("is_enabled"))
    if enabled is None:
        enabled = False
    harness_id = _slug(raw_id or display)
    return {
        "id": harness_id,
        "display_name": str(display or harness_id),
        "enabled": bool(enabled),
        "provider_kind": _provider_kind(harness_id, display),
    }


def _collect_harnesses(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, str):
        parsed = _json_string(value)
        if isinstance(parsed, (dict, list)):
            value = parsed
    if isinstance(value, list):
        for item in value:
            rec = _as_harness_record(item)
            if rec:
                records.append(rec)
    elif isinstance(value, dict):
        direct = _as_harness_record(value)
        if direct:
            records.append(direct)
        else:
            for key, item in value.items():
                rec = _as_harness_record(item, key=str(key))
                if rec:
                    records.append(rec)
    elif isinstance(value, str):
        direct = _as_harness_record(value)
        if direct:
            records.append(direct)

    unique: dict[str, dict[str, Any]] = {}
    for rec in records:
        unique[rec["id"]] = rec
    return sorted(unique.values(), key=lambda row: row["id"])


def _find_deep(value: Any, needle: str) -> Any:
    if isinstance(value, str):
        parsed = _json_string(value)
        if parsed is not None:
            return _find_deep(parsed, needle)
    if isinstance(value, dict):
        if needle in value:
            return value[needle]
        for child in value.values():
            found = _find_deep(child, needle)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_deep(child, needle)
            if found is not None:
                return found
    return None


def load_preferences(*, json_path: Path | None, plist_paths: list[Path]) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if json_path:
        try:
            return json.loads(json_path.read_text()), _rel(json_path), None
        except (OSError, ValueError) as exc:
            return None, _rel(json_path), str(exc)

    for path in plist_paths:
        if not path.is_file():
            continue
        try:
            with path.open("rb") as fh:
                return plistlib.load(fh), _rel(path), None
        except (OSError, plistlib.InvalidFileException, ValueError) as exc:
            return None, _rel(path), str(exc)
    return None, None, "no Warp preference plist found"


def scan_native_hosts(dirs: list[Path]) -> list[dict[str, Any]]:
    hosts: list[dict[str, Any]] = []
    for directory in dirs:
        if not directory.is_dir():
            continue
        for manifest in sorted(directory.glob("*.json")):
            try:
                data = json.loads(manifest.read_text())
            except (OSError, ValueError):
                hosts.append(
                    {
                        "name": manifest.stem,
                        "manifest": _rel(manifest),
                        "provider_kind": _provider_kind(manifest.stem),
                        "readable": False,
                    }
                )
                continue
            name = str(data.get("name") or manifest.stem)
            description = str(data.get("description") or "")
            command = Path(str(data.get("path") or "")).name
            hosts.append(
                {
                    "name": name,
                    "manifest": _rel(manifest),
                    "provider_kind": _provider_kind(name, description, command),
                    "readable": True,
                    "has_command_path": bool(data.get("path")),
                }
            )
    return sorted(hosts, key=lambda row: (row["provider_kind"], row["name"], row["manifest"]))


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    prefs, source, pref_error = load_preferences(
        json_path=args.prefs_json,
        plist_paths=args.plist or DEFAULT_PREF_PLISTS,
    )
    harnesses = _collect_harnesses((prefs or {}).get("AvailableHarnesses"))
    enabled = sorted(row["id"] for row in harnesses if row["enabled"])
    expected = sorted({_slug(item) for item in args.expect_enabled})
    missing = sorted(set(expected) - set(enabled))
    unexpected = sorted(set(enabled) - set(expected)) if expected else []
    notification_toggle = _boolish(_find_deep(prefs or {}, "is_agent_task_completed_enabled"))

    warnings: list[str] = []
    if pref_error:
        warnings.append(f"Warp preferences unavailable: {pref_error}")
    if notification_toggle and unexpected:
        warnings.append(
            "Warp task-completed notifications are enabled for unexpected harnesses: "
            + ", ".join(unexpected)
        )
    if missing:
        warnings.append("Expected harnesses are not enabled in Warp prefs: " + ", ".join(missing))

    native_hosts = scan_native_hosts(args.native_host_dir or DEFAULT_NATIVE_HOST_DIRS)
    report = {
        "status": "warn" if warnings else "ok",
        "warp_preferences": {
            "source": source,
            "available": prefs is not None,
            "error": pref_error,
            "task_completed_notifications_enabled": notification_toggle,
            "harnesses": harnesses,
            "enabled_harnesses": enabled,
            "expected_enabled_harnesses": expected,
            "unexpected_enabled_harnesses": unexpected,
            "expected_missing_harnesses": missing,
        },
        "native_messaging_hosts": native_hosts,
        "notification_history": {
            "status": "not_read",
            "reason": "macOS usernoted records can contain raw notification text",
        },
        "warnings": warnings,
    }
    return report


def print_human(report: dict[str, Any]) -> None:
    prefs = report["warp_preferences"]
    print("== Warp notification provenance ==")
    print(f"status: {report['status']}")
    print(f"prefs: {prefs.get('source') or 'not found'}")
    print(f"task-completed notifications: {prefs.get('task_completed_notifications_enabled')}")
    print("enabled harnesses: " + (", ".join(prefs.get("enabled_harnesses") or []) or "none"))
    disabled = [h["id"] for h in prefs.get("harnesses", []) if not h.get("enabled")]
    print("disabled harnesses: " + (", ".join(disabled) or "none"))
    if prefs.get("expected_enabled_harnesses"):
        print("expected enabled: " + ", ".join(prefs["expected_enabled_harnesses"]))
    print()
    print("native messaging hosts:")
    hosts = report.get("native_messaging_hosts") or []
    if not hosts:
        print("  none found")
    for host in hosts:
        suffix = " command-path-present" if host.get("has_command_path") else ""
        print(f"  - {host['provider_kind']}: {host['name']} ({host['manifest']}){suffix}")
    print()
    print("notification history: not read (private notification text risk)")
    if report.get("warnings"):
        print()
        print("warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefs-json", type=Path, help="JSON fixture/export of Warp preferences")
    parser.add_argument(
        "--plist",
        type=Path,
        action="append",
        help="Warp plist path to inspect; repeatable. Defaults to stable Warp plist names.",
    )
    parser.add_argument(
        "--native-host-dir",
        type=Path,
        action="append",
        help="NativeMessagingHosts directory to inspect; repeatable.",
    )
    parser.add_argument(
        "--expect-enabled",
        action="append",
        default=[],
        help="Harness id expected to be enabled, e.g. codex or oz. Repeatable.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a human report")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when warnings are present")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = build_report(args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 1 if args.strict and report["warnings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
