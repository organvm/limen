"""Bounded native-store and prompt-authority source adapters."""

from __future__ import annotations

import collections
import glob
import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

import yaml

from limen.jules_remote import classify_jules_remote_status
from limen.prompt_sources import source_adapter_contract

from .config import ReviewConfig
from .model import (
    AGENT_FAMILY,
    TOKEN_KEYS,
    canonical_repository,
    canonicalize_sessions,
    claude_identity,
    codex_usage,
    cumulative_delta,
    int_value,
    iso_z,
    parse_ts,
)


def _jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def _ro_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _token_event(
    timestamp: Any,
    components: dict[str, int],
    *,
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": iso_z(parse_ts(timestamp)),
        "components": components,
        **({"event_id": event_id} if event_id else {}),
    }


def _native_event_id(row: dict[str, Any], timestamp: Any) -> str:
    """Return a stable, path-independent hash for fragment deduplication."""

    explicit = row.get("id") or row.get("uuid") or row.get("message_id")
    if explicit:
        return str(explicit)
    stable = {
        "timestamp": iso_z(parse_ts(timestamp)),
        "type": row.get("type"),
        "payload": row.get("payload"),
        "message": row.get("message"),
    }
    return hashlib.sha256(
        json.dumps(
            stable,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        ).encode()
    ).hexdigest()


def _path_repository(path_value: Any) -> str:
    """Resolve a local checkout to its GitHub remote without publishing the path."""

    raw = str(path_value or "").strip()
    direct = canonical_repository(raw)
    if direct != "unknown":
        return direct
    if not raw.startswith(("~/", "/")):
        return "unknown"
    path = Path(raw).expanduser()
    if not path.exists():
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return canonical_repository(result.stdout) if result.returncode == 0 else "unknown"


class NativeCollectors:
    """Collect bounded native records without mutating provider stores."""

    def __init__(self, config: ReviewConfig, *, home: Path | None = None) -> None:
        self.config = config
        self.home = (home or Path.home()).expanduser()
        self.review_start = min(window.start for window in config.windows)

    def codex(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        fragments: list[dict[str, Any]] = []
        files = events = late = 0
        direct = collections.Counter()
        pattern = str(self.home / ".codex" / "sessions" / "**" / "*.jsonl")
        for name in glob.iglob(pattern, recursive=True):
            path = Path(name)
            rows = list(_jsonl(path))
            stamped = [(parse_ts(row.get("timestamp")), row) for row in rows]
            stamped = [(ts, row) for ts, row in stamped if ts]
            if (
                not stamped
                or max(ts for ts, _ in stamped) < self.review_start
                or min(ts for ts, _ in stamped) >= self.config.snapshot_at
            ):
                continue
            files += 1
            late += sum(ts >= self.config.snapshot_at for ts, _ in stamped)
            meta: dict[str, Any] = {}
            previous: dict[str, int] | None = None
            token_events: list[dict[str, Any]] = []
            event_ids = [
                _native_event_id(row, timestamp)
                for timestamp, row in stamped
                if self.review_start <= timestamp < self.config.snapshot_at
            ]
            for index, (timestamp, row) in enumerate(stamped):
                if row.get("type") == "session_meta":
                    meta = row.get("payload") or meta
                payload = row.get("payload") or {}
                if row.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                info = payload.get("info") or {}
                total = codex_usage(info.get("total_token_usage"))
                raw_delta = info.get("last_token_usage")
                delta = codex_usage(raw_delta) if isinstance(raw_delta, dict) else cumulative_delta(total, previous)
                # Seed the cumulative baseline from all pre-window native events.
                previous = total
                if timestamp < self.review_start or timestamp >= self.config.snapshot_at:
                    continue
                components = {key: delta[key] for key in TOKEN_KEYS["codex"]}
                token_events.append(
                    _token_event(
                        timestamp,
                        components,
                        event_id=_native_event_id(row, timestamp),
                    )
                )
                direct.update(components)
            before = [ts for ts, _ in stamped if ts < self.config.snapshot_at]
            sid = str(meta.get("id") or meta.get("session_id") or path.stem)
            parent = meta.get("parent_thread_id")
            if not parent and "sub_agent" in str(meta.get("thread_source") or ""):
                parent = "parent-unavailable"
            fragments.append(
                {
                    "agent": "codex",
                    "native_id": sid,
                    "parent_id": str(parent) if parent else None,
                    "start": iso_z(min(before)),
                    "end": iso_z(max(before)),
                    "events": sum(self.review_start <= ts < self.config.snapshot_at for ts, _ in stamped),
                    "event_ids": event_ids,
                    "time_basis": "native event span",
                    "token_events": token_events,
                }
            )
            events += fragments[-1]["events"]
        return fragments, {
            "files": files,
            "events": events,
            "late_writes_excluded": late,
            "direct_token_aggregation": dict(direct),
        }

    def claude(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        fragments: list[dict[str, Any]] = []
        files = events = late = 0
        direct = collections.Counter()
        pattern = str(self.home / ".claude" / "projects" / "**" / "*.jsonl")
        for name in glob.iglob(pattern, recursive=True):
            path = Path(name)
            stamped = [(parse_ts(row.get("timestamp")), row) for row in _jsonl(path)]
            stamped = [(ts, row) for ts, row in stamped if ts]
            before = [(ts, row) for ts, row in stamped if ts < self.config.snapshot_at]
            if not before or max(ts for ts, _ in before) < self.review_start:
                continue
            files += 1
            late += sum(ts >= self.config.snapshot_at for ts, _ in stamped)
            tokens: list[dict[str, Any]] = []
            native_id, parent_id = path.stem, None
            event_ids = [
                _native_event_id(row, timestamp) for timestamp, row in before if timestamp >= self.review_start
            ]
            for index, (timestamp, row) in enumerate(before):
                row_id, row_parent = claude_identity(row, path.stem)
                if row_parent:
                    native_id, parent_id = row_id, row_parent
                elif parent_id is None:
                    native_id = row_id
                if row.get("type") != "assistant" or timestamp < self.review_start:
                    continue
                message = row.get("message") or {}
                usage = message.get("usage") if isinstance(message, dict) else None
                if not isinstance(usage, dict):
                    continue
                components = {
                    "input_tokens": int_value(usage.get("input_tokens")),
                    "output_tokens": int_value(usage.get("output_tokens")),
                    "cache_creation_input_tokens": int_value(usage.get("cache_creation_input_tokens")),
                    "cache_read_input_tokens": int_value(usage.get("cache_read_input_tokens")),
                }
                tokens.append(
                    _token_event(
                        timestamp,
                        components,
                        event_id=_native_event_id(row, timestamp),
                    )
                )
                direct.update(components)
            fragments.append(
                {
                    "agent": "claude",
                    "native_id": native_id,
                    "parent_id": parent_id,
                    "start": iso_z(min(ts for ts, _ in before)),
                    "end": iso_z(max(ts for ts, _ in before)),
                    "events": sum(ts >= self.review_start for ts, _ in before),
                    "event_ids": event_ids,
                    "time_basis": "native event span",
                    "token_events": tokens,
                }
            )
            events += fragments[-1]["events"]
        return fragments, {
            "files": files,
            "events": events,
            "late_writes_excluded": late,
            "direct_token_aggregation": dict(direct),
        }

    def opencode(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        path = self.home / ".local" / "share" / "opencode" / "opencode.db"
        if not path.is_file():
            return [], {"available": False, "sessions": 0, "tokens": None}
        fragments: list[dict[str, Any]] = []
        direct = collections.Counter()
        messages = 0
        try:
            with closing(_ro_db(path)) as connection:
                sessions = connection.execute(
                    "SELECT id,parent_id,time_created,time_updated FROM session "
                    "WHERE time_updated>=? AND time_created<?",
                    (
                        int(self.review_start.timestamp() * 1000),
                        int(self.config.snapshot_at.timestamp() * 1000),
                    ),
                ).fetchall()
                for session in sessions:
                    token_events: list[dict[str, Any]] = []
                    stamped: list[Any] = []
                    for index, message in enumerate(
                        connection.execute(
                            "SELECT id,time_created,data FROM message WHERE session_id=? ORDER BY time_created,id",
                            (session["id"],),
                        )
                    ):
                        timestamp = parse_ts(message["time_created"])
                        if not timestamp or timestamp >= self.config.snapshot_at:
                            continue
                        stamped.append(timestamp)
                        if timestamp < self.review_start:
                            continue
                        try:
                            data = json.loads(message["data"])
                        except (TypeError, ValueError):
                            continue
                        native = data.get("tokens") if isinstance(data, dict) else None
                        if not isinstance(native, dict):
                            continue
                        cache = native.get("cache") or {}
                        components = {
                            "input_tokens": int_value(native.get("input")),
                            "output_tokens": int_value(native.get("output")),
                            "reasoning_tokens": int_value(native.get("reasoning")),
                            "cache_read_tokens": int_value(cache.get("read")),
                            "cache_write_tokens": int_value(cache.get("write")),
                        }
                        token_events.append(
                            _token_event(
                                timestamp,
                                components,
                                event_id=str(message["id"] or index),
                            )
                        )
                        direct.update(components)
                    fragments.append(
                        {
                            "agent": "opencode",
                            "native_id": str(session["id"]),
                            "parent_id": session["parent_id"] or None,
                            "start": iso_z(min(stamped) if stamped else parse_ts(session["time_created"])),
                            "end": iso_z(max(stamped) if stamped else parse_ts(session["time_updated"])),
                            "events": len(stamped),
                            "time_basis": "native message span",
                            "token_events": token_events,
                        }
                    )
                    messages += len(stamped)
        except (OSError, sqlite3.DatabaseError) as exc:
            return [], {
                "available": False,
                "sessions": 0,
                "tokens": None,
                "coverage": "coverage_unknown",
                "reason": f"opencode sqlite unavailable: {type(exc).__name__}",
            }
        return fragments, {
            "available": True,
            "sessions": len(fragments),
            "messages_in_sessions": messages,
            "direct_token_aggregation": dict(direct),
        }

    def agy(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        path = self.home / ".gemini" / "antigravity-cli" / "conversation_summaries.db"
        if not path.is_file():
            return [], {"available": False, "conversation_summaries": 0, "tokens": None}
        fragments: list[dict[str, Any]] = []
        try:
            with closing(_ro_db(path)) as connection:
                records = connection.execute(
                    "SELECT conversation_id,parent_conversation_id,last_modified_time,step_count "
                    "FROM conversation_summaries "
                    "WHERE last_modified_time>=? AND last_modified_time<?",
                    (iso_z(self.review_start), iso_z(self.config.snapshot_at)),
                ).fetchall()
                for row in records:
                    timestamp = parse_ts(row["last_modified_time"])
                    fragments.append(
                        {
                            "agent": "agy",
                            "native_id": str(row["conversation_id"]),
                            "parent_id": row["parent_conversation_id"] or None,
                            "start": iso_z(timestamp),
                            "end": iso_z(timestamp),
                            "events": int_value(row["step_count"]),
                            "time_basis": "native last-modified point; duration unknown",
                            "token_events": [],
                        }
                    )
        except (OSError, sqlite3.DatabaseError) as exc:
            return [], {
                "available": False,
                "conversation_summaries": 0,
                "tokens": None,
                "coverage": "coverage_unknown",
                "reason": f"agy sqlite unavailable: {type(exc).__name__}",
            }
        return fragments, {
            "available": True,
            "conversation_summaries": len(fragments),
            "tokens": None,
        }

    def gemini(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        fragments: list[dict[str, Any]] = []
        pattern = str(self.home / ".gemini" / "tmp" / "*" / "chats" / "*.jsonl")
        for name in glob.iglob(pattern):
            path = Path(name)
            if "agy" in str(path).lower() or "capfill" in str(path).lower():
                continue
            timestamps = [parse_ts(row.get("timestamp")) for row in _jsonl(path)]
            timestamps = [value for value in timestamps if value and value < self.config.snapshot_at]
            if not timestamps or max(timestamps) < self.review_start:
                continue
            fragments.append(
                {
                    "agent": "gemini",
                    "native_id": path.stem,
                    "parent_id": None,
                    "start": iso_z(min(timestamps)),
                    "end": iso_z(max(timestamps)),
                    "events": sum(value >= self.review_start for value in timestamps),
                    "time_basis": "native event span",
                    "token_events": [],
                }
            )
        return fragments, {
            "available": True,
            "files": len(fragments),
            "events": sum(row["events"] for row in fragments),
            "tokens": None,
        }

    def copilot(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        path = self.home / ".copilot" / "session-store.db"
        if not path.is_file():
            return [], {"available": False, "sessions": 0, "tokens": None}
        fragments: list[dict[str, Any]] = []
        direct = collections.Counter()
        usage_events = 0
        try:
            with closing(_ro_db(path)) as connection:
                sessions = connection.execute(
                    "SELECT id,created_at,updated_at FROM sessions WHERE updated_at>=? AND created_at<?",
                    (iso_z(self.review_start), iso_z(self.config.snapshot_at)),
                ).fetchall()
                for session in sessions:
                    token_events: list[dict[str, Any]] = []
                    event_times = []
                    usage_ms = 0
                    for index, row in enumerate(
                        connection.execute(
                            "SELECT created_at,input_tokens,output_tokens,cache_read_tokens,"
                            "cache_write_tokens,reasoning_tokens,duration_ms "
                            "FROM assistant_usage_events WHERE session_id=? AND created_at<?",
                            (session["id"], iso_z(self.config.snapshot_at)),
                        )
                    ):
                        timestamp = parse_ts(row["created_at"])
                        if not timestamp:
                            continue
                        event_times.append(timestamp)
                        if timestamp < self.review_start:
                            continue
                        components = {
                            "input_tokens": int_value(row["input_tokens"]),
                            "output_tokens": int_value(row["output_tokens"]),
                            "reasoning_tokens": int_value(row["reasoning_tokens"]),
                            "cache_read_tokens": int_value(row["cache_read_tokens"]),
                            "cache_write_tokens": int_value(row["cache_write_tokens"]),
                        }
                        token_events.append(
                            _token_event(
                                timestamp,
                                components,
                                event_id=f"{session['id']}:{index}",
                            )
                        )
                        direct.update(components)
                        usage_ms += int_value(row["duration_ms"])
                        usage_events += 1
                    fragments.append(
                        {
                            "agent": "copilot",
                            "native_id": str(session["id"]),
                            "parent_id": None,
                            "start": iso_z(min(event_times) if event_times else parse_ts(session["created_at"])),
                            "end": iso_z(max(event_times) if event_times else parse_ts(session["updated_at"])),
                            "events": len(event_times),
                            "time_basis": (
                                f"native request span; metered request duration {usage_ms / 3_600_000:.2f}h"
                                if usage_ms
                                else "session shell; duration unknown"
                            ),
                            "token_events": token_events,
                        }
                    )
        except (OSError, sqlite3.DatabaseError) as exc:
            return [], {
                "available": False,
                "sessions": 0,
                "tokens": None,
                "coverage": "coverage_unknown",
                "reason": f"copilot sqlite unavailable: {type(exc).__name__}",
            }
        return fragments, {
            "available": True,
            "sessions": len(fragments),
            "usage_events": usage_events,
            "direct_token_aggregation": dict(direct),
        }

    def jules(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Reuse the board's frozen remote lifecycle records as Jules proxies."""

        board_path = self.config.root / "tasks.yaml"
        if not board_path.is_file():
            return [], {"available": False, "sessions": 0, "tokens": None}
        board = yaml.safe_load(board_path.read_text(encoding="utf-8")) or {}
        groups: dict[str, list[Any]] = collections.defaultdict(list)
        remote_states = collections.Counter()
        for task in board.get("tasks") or []:
            for event in task.get("dispatch_log") or []:
                timestamp = parse_ts(event.get("timestamp"))
                if (
                    not timestamp
                    or not self.review_start <= timestamp < self.config.snapshot_at
                    or str(event.get("agent") or "").lower() != "jules"
                ):
                    continue
                session_id = str(event.get("provider_run_id") or event.get("session_id") or "")
                if session_id:
                    groups[session_id].append(timestamp)
                state = str(event.get("remote_state") or event.get("status") or "")
                remote_states[classify_jules_remote_status(state)] += 1
        fragments = [
            {
                "agent": "jules",
                "native_id": session_id,
                "parent_id": None,
                "start": iso_z(min(timestamps)),
                "end": iso_z(max(timestamps)),
                "events": len(timestamps),
                "time_basis": "board dispatch-to-terminal proxy",
                "token_events": [],
            }
            for session_id, timestamps in groups.items()
        ]
        return fragments, {
            "available": True,
            "sessions": len(fragments),
            "remote_states": dict(remote_states),
            "tokens": None,
        }

    def all(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Collect and canonicalize every configured native adapter."""

        fragments: list[dict[str, Any]] = []
        coverage: dict[str, Any] = {}
        for name in ("codex", "claude", "opencode", "agy", "gemini", "copilot", "jules"):
            rows, receipt = getattr(self, name)()
            fragments.extend(rows)
            coverage[name] = receipt
        sessions = canonicalize_sessions(fragments)
        for session in sessions:
            session["source_atom_ids"] = []
            session["coverage_flags"] = ["coverage_unknown"]
            session["outcome"] = "coverage_unknown"
            session["executor_role"] = "executor"
            session["canonical_repo"] = "unknown"
        coverage["prompt_source_adapter_contract"] = source_adapter_contract()
        return sessions, coverage


def _disposition(value: Any) -> str:
    return {
        "done": "verified_partial",
        "partial": "verified_partial",
        "blocked": "blocked",
        "superseded": "superseded",
        "not-done": "not_done_or_unverified",
        "not_done": "not_done_or_unverified",
        "unassessed": "coverage_unknown",
    }.get(str(value or "").lower(), "coverage_unknown")


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _exact_prompt_authority(
    public: dict[str, Any],
    marker: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Verify the tracked projection and private marker form one exact all/all seal."""

    errors: list[str] = []
    scope = public.get("source_scope") or {}
    if scope.get("scope") != "all" or scope.get("target_scope") != "all":
        errors.append("source_scope_not_all")
    if scope.get("all_baseline_complete") is not True:
        errors.append("all_baseline_incomplete")
    if int(scope.get("pending_files") or 0):
        errors.append("pending_source_files")
    if scope.get("source_errors"):
        errors.append("source_errors")
    if scope.get("adapter_gaps"):
        errors.append("adapter_gaps")
    if int(public.get("unresolved_atoms_truncated") or 0):
        errors.append("public_projection_truncated")
    validation = public.get("validation") or {}
    if validation.get("ok") is not True:
        errors.append("projection_validation_failed")
    declared_digest = str(public.get("projection_digest") or "")
    digest_input = {key: value for key, value in public.items() if key != "projection_digest"}
    if not declared_digest or _canonical_digest(digest_input) != declared_digest:
        errors.append("projection_digest_mismatch")
    if marker.get("public_projection_digest") != declared_digest:
        errors.append("private_marker_projection_mismatch")
    if marker.get("semantic_digest") != public.get("semantic_digest"):
        errors.append("private_marker_semantic_mismatch")
    if marker.get("source_cursor_digest") != public.get("source_cursor_digest"):
        errors.append("private_marker_cursor_mismatch")
    return not errors, errors


def _private_prompt_paths(config: ReviewConfig) -> tuple[Path, Path, Path]:
    configured = os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS")
    base = Path(configured).expanduser() if configured else config.root / ".limen-private" / "session-corpus"
    prompt_root = base / "prompt-atoms"
    return (
        prompt_root / "prompt-atom-ledger.json",
        prompt_root / "prompt-events.jsonl",
        prompt_root / "prompt-atom-outcomes.jsonl",
    )


def _source_agent(source: Any) -> str:
    value = str(source or "").lower()
    for prefix, agent in (
        ("codex", "codex"),
        ("claude", "claude"),
        ("agy", "agy"),
        ("opencode", "opencode"),
        ("gemini", "gemini"),
        ("copilot", "copilot"),
        ("jules", "jules"),
    ):
        if value.startswith(prefix):
            return agent
    return "unknown"


def _session_ref_hash(native_id: Any) -> str:
    return _canonical_digest(str(native_id or "unknown"))[:24]


def collect_prompt_atoms(
    config: ReviewConfig,
    sessions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Stream exact private prompt atoms; task rows are ownership evidence, never asks."""

    projection_path = config.root / "docs" / "prompt-atom-ledger.json"
    if not projection_path.is_file():
        return [], {
            "available": False,
            "authority": "prompt_atom_projection",
            "coverage": "coverage_unknown",
            "reason": "exact all/all prompt atom projection is absent",
        }
    marker_path, events_path, outcomes_path = _private_prompt_paths(config)
    required = (marker_path, events_path, outcomes_path)
    if any(not path.is_file() for path in required):
        return [], {
            "available": False,
            "authority": "prompt_atom_projection",
            "coverage": "coverage_unknown",
            "reason": "private prompt lineage is unavailable",
        }
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    exact, authority_errors = _exact_prompt_authority(projection, marker)
    if not exact:
        return [], {
            "available": True,
            "authority": "prompt_atom_projection",
            "coverage": "coverage_unknown",
            "source_scope": projection.get("source_scope") or {},
            "reason": "prompt authority is not exact all/all",
            "authority_errors": authority_errors,
        }
    review_start = min(window.start for window in config.windows)
    atoms_by_id: dict[str, dict[str, Any]] = {}
    atom_ids_by_occurrence: dict[str, set[str]] = collections.defaultdict(set)
    occurrence_count = 0
    for row in _jsonl(events_path):
        occurrence = row.get("occurrence") or {}
        if not isinstance(occurrence, dict):
            continue
        timestamp = parse_ts(occurrence.get("timestamp"))
        if timestamp is None or not review_start <= timestamp < config.snapshot_at:
            continue
        occurrence_id = str(occurrence.get("occurrence_id") or "")
        if not occurrence_id:
            continue
        occurrence_count += 1
        if row.get("revision_of"):
            for old_id in atom_ids_by_occurrence.pop(occurrence_id, set()):
                atoms_by_id.pop(old_id, None)
        current_ids: set[str] = set()
        for atom in row.get("atoms") or []:
            if not isinstance(atom, dict):
                continue
            atom_id = str(atom.get("atom_id") or "")
            if not atom_id:
                continue
            current_ids.add(atom_id)
            atoms_by_id[atom_id] = {
                "atom_id": atom_id,
                "kind": str(atom.get("kind") or "prompt atom"),
                "source": str(atom.get("source") or occurrence.get("source") or ""),
                "timestamp": iso_z(timestamp),
                "owner": atom.get("owner"),
                "owner_route": atom.get("owner_route"),
                "session_ref_hash": str(atom.get("session_ref_hash") or occurrence.get("session_ref_hash") or ""),
            }
        atom_ids_by_occurrence[occurrence_id] = current_ids
    outcomes: dict[str, dict[str, Any]] = {}
    for row in _jsonl(outcomes_path):
        atom_id = str(row.get("atom_id") or "")
        if atom_id in atoms_by_id:
            outcomes[atom_id] = row
    task_by_atom: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    board_path = config.root / "tasks.yaml"
    if board_path.is_file():
        board = yaml.safe_load(board_path.read_text(encoding="utf-8")) or {}
        for task in board.get("tasks") or []:
            for atom_id in task.get("source_atom_ids") or []:
                task_by_atom[str(atom_id)].append(task)
    asks: list[dict[str, Any]] = []
    for atom_id, atom in sorted(atoms_by_id.items()):
        timestamp = parse_ts(atom.get("timestamp"))
        linked_tasks = task_by_atom.get(atom_id, [])
        agents = {
            str(task.get("target_agent") or "").lower()
            for task in linked_tasks
            if str(task.get("target_agent") or "").lower() in AGENT_FAMILY
        }
        agent = sorted(agents)[0] if len(agents) == 1 else _source_agent(atom.get("source"))
        outcome = outcomes.get(atom_id) or {}
        asks.append(
            {
                "ask": atom_id,
                "source_atom_ids": [atom_id],
                "agent": agent,
                "subject": str(atom.get("kind") or "prompt atom"),
                "canonical_repo": (
                    _path_repository(linked_tasks[0].get("repo"))
                    if len(linked_tasks) == 1
                    else canonical_repository(atom.get("owner") or outcome.get("owner"))
                ),
                "executor_role": "executor",
                "outcome": _disposition(outcome.get("disposition")),
                "predicate_result": None,
                "predicate_checked_at": None,
                "receipt_head_sha": None,
                "receipt": None,
                "observed_at": iso_z(timestamp),
                "coverage_flags": ([] if timestamp is not None and agent != "unknown" else ["coverage_unknown"]),
            }
        )
    atom_by_session: dict[str, set[str]] = collections.defaultdict(set)
    for atom_id, atom in atoms_by_id.items():
        session_hash = str(atom.get("session_ref_hash") or "")
        if session_hash:
            atom_by_session[session_hash].add(atom_id)
    for session in sessions:
        atom_ids = sorted(atom_by_session.get(_session_ref_hash(session["native_id"]), set()))
        if atom_ids:
            session["source_atom_ids"] = atom_ids
            session["coverage_flags"] = []
    source_scope = projection.get("source_scope") or {}
    return asks, {
        "available": True,
        "authority": projection.get("authority") or "prompt_atom_projection",
        "projection_digest": projection.get("projection_digest"),
        "source_scope": source_scope,
        "coverage": projection.get("coverage") or {},
        "occurrences_in_window": occurrence_count,
        "atoms_loaded": len(atoms_by_id),
        "asks_in_window": len(asks),
        "private_lineage_digest": _canonical_digest(
            {
                "event_journal_size": events_path.stat().st_size,
                "outcome_journal_size": outcomes_path.stat().st_size,
                "public_projection_digest": projection.get("projection_digest"),
            }
        ),
    }
