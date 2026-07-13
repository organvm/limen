#!/usr/bin/env python3
"""Fail before an unattended Claude run can strand itself on a permission prompt.

Claude evaluates permission rules in ``deny -> ask -> allow`` order.  A matching
``permissions.ask`` rule therefore still prompts in Auto *and* bypass mode, and a
PreToolUse ``allow`` decision does not override that rule.  This checker evaluates
the exact Bash command packet against the locally visible effective settings stack
before the packet is launched.

The checker is deliberately read-only.  It does not weaken settings or execute the
commands.  Generated-output deletion is accepted only when every target is inside a
caller-declared generated path.  Cleanup in bypass mode is rejected: removing a broad
``rm`` ask rule there would also remove the personal-data backstop.  Use Auto with its
built-in safety rules retained instead.

Examples::

    python3 scripts/claude-permission-preflight.py \
      --project-root "$PWD" --mode auto \
      --generated-path build \
      --command 'rm -rf build && python3 -m pytest -q'

    python3 scripts/claude-permission-preflight.py \
      --project-root "$PWD" --mode auto \
      --command 'git status --short' --json

Exit 0 means the visible settings and packet have no deterministic prompt/block
contradiction.  Exit 2 means the packet must not be launched unattended.  Exit 3 is
an invalid/unreadable configuration.  Remote/MDM policy and in-session mode changes
cannot be reconstructed from local files; pass exported settings with ``--settings``
and the actual session mode with ``--mode`` when either applies.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "limen.claude_permission_preflight.v1"
UNATTENDED_MODES = {"auto", "bypassPermissions"}


@dataclass(frozen=True)
class SettingsSource:
    scope: str
    path: Path
    data: dict[str, Any]


@dataclass(frozen=True)
class Rule:
    kind: str
    value: str
    source: str


class ConfigError(ValueError):
    """A settings source or command packet is not safe to interpret."""


def _load(path: Path, scope: str, *, required: bool) -> SettingsSource | None:
    if not path.is_file():
        if required:
            raise ConfigError(f"settings source does not exist: {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read settings source {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"settings source must contain a JSON object: {path}")
    return SettingsSource(scope=scope, path=path, data=value)


def _managed_paths() -> list[Path]:
    if sys.platform == "darwin":
        root = Path("/Library/Application Support/ClaudeCode")
    elif os.name == "nt":
        root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ClaudeCode"
    else:
        root = Path("/etc/claude-code")
    paths = [root / "managed-settings.json"]
    dropins = root / "managed-settings.d"
    if dropins.is_dir():
        paths.extend(sorted(p for p in dropins.glob("*.json") if not p.name.startswith(".")))
    return paths


def load_sources(args: argparse.Namespace, project_root: Path) -> list[SettingsSource]:
    """Load locally visible sources in low-to-high precedence order.

    Permission arrays merge across scopes; scalar mode settings use the last value.
    Explicit ``--settings`` files model CLI-supplied settings and sit below managed
    policy, matching Claude's documented precedence.
    """

    sources: list[SettingsSource] = []
    if not args.isolated_settings:
        config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")).expanduser()
        candidates = [
            (config_dir / "settings.json", "user"),
            (project_root / ".claude" / "settings.json", "project"),
            (project_root / ".claude" / "settings.local.json", "local"),
        ]
        for path, scope in candidates:
            source = _load(path, scope, required=False)
            if source:
                sources.append(source)

    for raw in args.settings:
        source = _load(Path(raw).expanduser().resolve(), "cli", required=True)
        assert source is not None
        sources.append(source)

    if not args.isolated_settings:
        for path in _managed_paths():
            source = _load(path, "managed", required=False)
            if source:
                sources.append(source)
    return sources


def _permission_sources(sources: list[SettingsSource]) -> list[SettingsSource]:
    managed_only = any(
        source.scope == "managed" and source.data.get("allowManagedPermissionRulesOnly") is True for source in sources
    )
    return [source for source in sources if source.scope == "managed"] if managed_only else sources


def collect_rules(sources: list[SettingsSource], args: argparse.Namespace) -> list[Rule]:
    rules: list[Rule] = []
    for source in _permission_sources(sources):
        permissions = source.data.get("permissions") or {}
        if not isinstance(permissions, dict):
            raise ConfigError(f"permissions must be an object in {source.path}")
        for kind in ("ask", "deny", "allow"):
            values = permissions.get(kind) or []
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ConfigError(f"permissions.{kind} must be an array of strings in {source.path}")
            rules.extend(Rule(kind, value, str(source.path)) for value in values)
    rules.extend(Rule("ask", value, "command-line") for value in args.ask_rule)
    rules.extend(Rule("deny", value, "command-line") for value in args.deny_rule)
    return rules


def effective_mode(sources: list[SettingsSource], override: str | None) -> str:
    mode = "default"
    for source in sources:
        permissions = source.data.get("permissions") or {}
        if isinstance(permissions, dict) and isinstance(permissions.get("defaultMode"), str):
            mode = permissions["defaultMode"]
    return override or mode


def split_clauses(command: str) -> list[str]:
    """Split shell control operators while respecting quotes.

    This is intentionally smaller than a shell parser.  Unbalanced quotes fail the
    preflight instead of being guessed.  The returned text preserves argument spacing
    closely enough for Claude permission-pattern matching.
    """

    clauses: list[str] = []
    buf: list[str] = []
    quote = ""
    escaped = False
    i = 0
    while i < len(command):
        char = command[i]
        if escaped:
            buf.append(char)
            escaped = False
            i += 1
            continue
        if char == "\\" and quote != "'":
            buf.append(char)
            escaped = True
            i += 1
            continue
        if quote:
            buf.append(char)
            if char == quote:
                quote = ""
            i += 1
            continue
        if char in {"'", '"'}:
            quote = char
            buf.append(char)
            i += 1
            continue
        separator_len = 0
        if command.startswith(("&&", "||", "|&"), i):
            separator_len = 2
        elif char in ";|&\n":
            separator_len = 1
        if separator_len:
            clause = "".join(buf).strip()
            if clause:
                clauses.append(clause)
            buf = []
            i += separator_len
            continue
        buf.append(char)
        i += 1
    if quote or escaped:
        raise ConfigError("command has unbalanced quoting or a trailing escape")
    clause = "".join(buf).strip()
    if clause:
        clauses.append(clause)
    return clauses


def _rule_spec(rule: str) -> str | None:
    if rule == "Bash":
        return "*"
    match = re.fullmatch(r"Bash\((.*)\)", rule, re.DOTALL)
    if not match:
        return None
    spec = match.group(1)
    if spec.endswith(":*"):
        spec = f"{spec[:-2]} *"
    return spec


def bash_rule_matches(rule: str, clause: str) -> bool:
    spec = _rule_spec(rule)
    if spec is None:
        return False
    clause = clause.strip()
    if spec in {"", "*"}:
        return True
    # Claude treats a trailing `` <wildcard>`` as a word boundary: the bare
    # command and the command followed by arguments both match.
    if spec.endswith(" *"):
        prefix = spec[:-2]
        return clause == prefix or fnmatch.fnmatchcase(clause, spec)
    return fnmatch.fnmatchcase(clause, spec)


def permission_clause_variants(clause: str) -> list[str]:
    """Return raw and built-in-wrapper-stripped permission-matching forms.

    Claude strips a fixed wrapper set before Bash rule matching.  We model the
    common deterministic forms and keep the raw clause too.  Unknown wrapper
    syntax stays raw rather than being guessed.
    """

    variants = [clause.strip()]
    tokens = _tokens(clause)
    if not tokens:
        return variants
    index = 0
    while index < len(tokens) and tokens[index] in {"timeout", "time", "nice", "nohup", "stdbuf"}:
        wrapper = tokens[index]
        index += 1
        if wrapper == "timeout":
            while index < len(tokens) and tokens[index].startswith("-"):
                # Options such as --signal=TERM are self-contained; -s/-k take
                # one following value.
                option = tokens[index]
                index += 1
                if option in {"-s", "--signal", "-k", "--kill-after"} and index < len(tokens):
                    index += 1
            if index < len(tokens):
                index += 1  # duration
        elif wrapper == "nice":
            if index < len(tokens) and tokens[index] == "-n":
                index += 2
            elif index < len(tokens) and re.fullmatch(r"-\d+", tokens[index]):
                index += 1
        elif wrapper in {"time", "stdbuf"}:
            while index < len(tokens) and tokens[index].startswith("-"):
                index += 1
        if index < len(tokens):
            variants.append(shlex.join(tokens[index:]))
        else:
            break
    return list(dict.fromkeys(variants))


def _tokens(clause: str) -> list[str]:
    try:
        return shlex.split(clause, posix=True)
    except ValueError as exc:
        raise ConfigError(f"cannot parse command clause {clause!r}: {exc}") from exc


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def generated_roots(project_root: Path, values: list[str]) -> list[Path]:
    roots: list[Path] = []
    for raw in values:
        if any(token in raw for token in ("$", "*", "?", "[", "]")):
            raise ConfigError(f"generated path must be literal, not expanded or globbed: {raw}")
        path = Path(raw).expanduser()
        path = (path if path.is_absolute() else project_root / path).resolve(strict=False)
        if path == project_root or not _path_within(path, project_root):
            raise ConfigError(f"generated path must be strictly inside the project root: {raw}")
        roots.append(path)
    return roots


def _cleanup_findings(commands: list[str], project_root: Path, roots: list[Path], mode: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for command_index, command in enumerate(commands, 1):
        cwd = project_root
        for clause in split_clauses(command):
            tokens = _tokens(clause)
            if not tokens:
                continue
            if tokens[0] == "cd":
                if len(tokens) != 2 or any(token in tokens[1] for token in ("$", "*", "?", "[", "]")):
                    findings.append(
                        {
                            "code": "unresolved_working_directory",
                            "command": command_index,
                            "clause": clause,
                            "message": "cleanup context cannot be resolved before launch",
                        }
                    )
                    continue
                target = Path(tokens[1]).expanduser()
                cwd = (target if target.is_absolute() else cwd / target).resolve(strict=False)
                continue

            if tokens[0] not in {"rm", "rmdir"}:
                # Refuse indirect cleanup forms rather than pretending to understand
                # wrappers, xargs, shell -c, or command substitution.
                if re.search(r"(^|\s)(rm|rmdir)(\s|$)", clause):
                    findings.append(
                        {
                            "code": "indirect_cleanup_unverifiable",
                            "command": command_index,
                            "clause": clause,
                            "message": "cleanup must be a direct rm/rmdir clause for path proof",
                        }
                    )
                continue

            if mode == "bypassPermissions":
                findings.append(
                    {
                        "code": "unsafe_bypass_cleanup",
                        "command": command_index,
                        "clause": clause,
                        "message": "generated cleanup must use Auto; bypass cannot retain a path-sensitive personal-data gate",
                    }
                )

            targets: list[str] = []
            after_dashdash = False
            for token in tokens[1:]:
                if token == "--" and not after_dashdash:
                    after_dashdash = True
                    continue
                if not after_dashdash and token.startswith("-"):
                    continue
                targets.append(token)
            if not targets:
                findings.append(
                    {
                        "code": "cleanup_has_no_target",
                        "command": command_index,
                        "clause": clause,
                        "message": "cleanup clause has no target",
                    }
                )
                continue
            for raw in targets:
                if any(token in raw for token in ("$", "*", "?", "[", "]", "`")):
                    findings.append(
                        {
                            "code": "dynamic_cleanup_target",
                            "command": command_index,
                            "clause": clause,
                            "message": f"cleanup target is dynamic and cannot be proven generated: {raw}",
                        }
                    )
                    continue
                target = Path(raw).expanduser()
                target = (target if target.is_absolute() else cwd / target).resolve(strict=False)
                if not roots or not any(target == root or _path_within(target, root) for root in roots):
                    findings.append(
                        {
                            "code": "cleanup_outside_declared_generated_path",
                            "command": command_index,
                            "clause": clause,
                            "message": f"cleanup target is not inside a --generated-path: {raw}",
                        }
                    )
    return findings


HARD_GATE_PATTERNS = (
    re.compile(r"(^|\s)shred(\s|$)"),
    re.compile(r"\bgit\s+push\b[^;&|]*(--force(?:-with-lease)?|-f\b|--delete\b|\s\+\S+|\s:\S+)"),
)


def assess(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).expanduser().resolve()
    if not project_root.is_dir():
        raise ConfigError(f"project root is not a directory: {project_root}")
    sources = load_sources(args, project_root)
    mode = effective_mode(sources, args.mode)
    rules = collect_rules(sources, args)
    roots = generated_roots(project_root, args.generated_path)
    findings: list[dict[str, Any]] = []

    if mode not in UNATTENDED_MODES:
        findings.append(
            {
                "code": "mode_will_prompt",
                "message": f"effective permission mode {mode!r} is not an unattended mode",
            }
        )
    if mode == "auto" and any(
        source.data.get("disableAutoMode") == "disable"
        or (source.data.get("permissions") or {}).get("disableAutoMode") == "disable"
        for source in sources
        if isinstance(source.data.get("permissions") or {}, dict)
    ):
        findings.append({"code": "auto_mode_disabled", "message": "a loaded settings source disables Auto mode"})
    if mode == "bypassPermissions" and any(
        source.data.get("disableBypassPermissionsMode") == "disable"
        or (source.data.get("permissions") or {}).get("disableBypassPermissionsMode") == "disable"
        for source in sources
        if isinstance(source.data.get("permissions") or {}, dict)
    ):
        findings.append(
            {"code": "bypass_mode_disabled", "message": "a loaded settings source disables bypassPermissions"}
        )

    auto_sources: list[tuple[SettingsSource, dict[str, Any]]] = []
    for source in sources:
        auto_mode = source.data.get("autoMode")
        if not isinstance(auto_mode, dict):
            continue
        if source.scope == "project":
            findings.append(
                {
                    "code": "shared_project_auto_mode_ignored",
                    "source": str(source.path),
                    "message": "Claude ignores autoMode in checked-in .claude/settings.json; move it to user/local/managed settings",
                }
            )
            continue
        auto_sources.append((source, auto_mode))

    if mode == "auto":
        auto_fields = {
            "environment": "auto_environment_defaults_replaced",
            "allow": "auto_allow_defaults_replaced",
            "soft_deny": "auto_safety_defaults_replaced",
            "hard_deny": "auto_hard_safety_defaults_replaced",
        }
        for field, code in auto_fields.items():
            configured: list[tuple[SettingsSource, list[str]]] = []
            for source, auto_mode in auto_sources:
                values = auto_mode.get(field)
                if values is None:
                    continue
                if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                    raise ConfigError(f"autoMode.{field} must be an array of strings in {source.path}")
                configured.append((source, values))
            if configured and not any("$defaults" in values for _, values in configured):
                findings.append(
                    {
                        "code": code,
                        "source": ", ".join(str(source.path) for source, _ in configured),
                        "message": f"combined autoMode.{field} omits $defaults, replacing Claude's built-in policy",
                    }
                )

    findings.extend(_cleanup_findings(args.command, project_root, roots, mode))

    for command_index, command in enumerate(args.command, 1):
        for clause in split_clauses(command):
            if any(pattern.search(clause) for pattern in HARD_GATE_PATTERNS):
                findings.append(
                    {
                        "code": "hard_gate_in_unattended_packet",
                        "command": command_index,
                        "clause": clause,
                        "message": "force-push/remote-delete/shred remains human-gated and cannot be in a routine packet",
                    }
                )
            variants = permission_clause_variants(clause)
            matching_deny = [
                rule
                for rule in rules
                if rule.kind == "deny" and any(bash_rule_matches(rule.value, value) for value in variants)
            ]
            matching_ask = [
                rule
                for rule in rules
                if rule.kind == "ask" and any(bash_rule_matches(rule.value, value) for value in variants)
            ]
            if matching_deny:
                for rule in matching_deny:
                    findings.append(
                        {
                            "code": "deny_blocks_packet",
                            "command": command_index,
                            "clause": clause,
                            "rule": rule.value,
                            "source": rule.source,
                            "message": "matching deny rule blocks this clause before unattended execution",
                        }
                    )
            elif matching_ask:
                for rule in matching_ask:
                    findings.append(
                        {
                            "code": "ask_overrides_unattended",
                            "command": command_index,
                            "clause": clause,
                            "rule": rule.value,
                            "source": rule.source,
                            "message": "matching ask rule prompts before Auto/bypass/allow hooks can approve the clause",
                        }
                    )

    # Stable, idempotent report ordering and no duplicate finding spam.
    unique: dict[str, dict[str, Any]] = {}
    for finding in findings:
        key = json.dumps(finding, sort_keys=True)
        unique[key] = finding
    findings = sorted(
        unique.values(),
        key=lambda item: (
            str(item.get("code", "")),
            int(item.get("command", 0)),
            str(item.get("source", "")),
            str(item.get("rule", "")),
        ),
    )
    return {
        "schema": SCHEMA,
        "ok": not findings,
        "mode": mode,
        "project_root": str(project_root),
        "settings_sources": [{"scope": source.scope, "path": str(source.path)} for source in sources],
        "commands_checked": len(args.command),
        "generated_paths": [str(root) for root in roots],
        "findings": findings,
        "coverage_note": (
            "local file settings plus explicit CLI fixtures; pass the actual --mode and exported managed settings "
            "when remote/MDM policy or an in-session override applies"
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=os.getcwd())
    parser.add_argument("--mode", choices=sorted(UNATTENDED_MODES | {"default", "acceptEdits", "dontAsk", "plan"}))
    parser.add_argument("--settings", action="append", default=[], metavar="PATH")
    parser.add_argument(
        "--isolated-settings",
        action="store_true",
        help="load only --settings files (for hermetic tests/exported effective settings)",
    )
    parser.add_argument("--ask-rule", action="append", default=[])
    parser.add_argument("--deny-rule", action="append", default=[])
    parser.add_argument("--generated-path", action="append", default=[], metavar="PATH")
    parser.add_argument("--command", action="append", required=True, metavar="BASH")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _render_human(report: dict[str, Any]) -> None:
    verdict = "PASS" if report["ok"] else "FAIL"
    print(
        f"claude-permission-preflight: {verdict} "
        f"({report['commands_checked']} command packet(s), mode={report['mode']})"
    )
    for finding in report["findings"]:
        context = []
        if finding.get("command"):
            context.append(f"command {finding['command']}")
        if finding.get("rule"):
            context.append(f"rule={finding['rule']}")
        if finding.get("source"):
            context.append(f"source={finding['source']}")
        suffix = f" ({'; '.join(context)})" if context else ""
        print(f"  - {finding['code']}: {finding['message']}{suffix}")
    if not report["ok"]:
        print(
            "  next: keep Auto safety defaults and real human gates; remove/reroute only the matching "
            "routine ask-rule or rewrite cleanup to a declared generated path, then rerun this exact packet"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = assess(args)
    except ConfigError as exc:
        if args.json:
            print(json.dumps({"schema": SCHEMA, "ok": False, "configuration_error": str(exc)}, sort_keys=True))
        else:
            print(f"claude-permission-preflight: configuration error: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _render_human(report)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
