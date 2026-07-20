"""Pure normalization, lineage, token, receipt, and outcome rules."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

UTC = dt.timezone.utc

AGENTS = ("codex", "claude", "agy", "opencode", "gemini", "copilot", "jules")
AGENT_FAMILY = frozenset(AGENTS)
OUTCOMES = (
    "verified_done",
    "verified_partial",
    "durably_homed_open",
    "blocked",
    "superseded",
    "not_done_or_unverified",
    "coverage_unknown",
)
EXECUTOR_ROLES = ("executor", "verifier", "integrator", "lander")
TOKEN_KEYS = {
    "codex": (
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "cached_input_tokens",
    ),
    "claude": (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ),
    "opencode": (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ),
    "copilot": (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    ),
}
PR_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[0-9]+)"
)
REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$"
)
LOCAL_REPOSITORY_PREFIXES = ("~/", "/", "file://")


def parse_ts(value: Any) -> dt.datetime | None:
    """Parse ISO, epoch-second, or epoch-millisecond timestamps as UTC."""

    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            return dt.datetime.fromtimestamp(number, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text or text.startswith("0001-"):
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_z(value: dt.datetime | None) -> str | None:
    """Render an aware timestamp in stable UTC form."""

    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclasses.dataclass(frozen=True)
class Window:
    """One half-open review window."""

    id: str
    label: str
    start: dt.datetime
    end: dt.datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("window timestamps must be timezone-aware")
        if self.end <= self.start:
            raise ValueError("window end must be after start")

    def contains(self, timestamp: dt.datetime | None) -> bool:
        return bool(timestamp is not None and self.start <= timestamp < self.end)

    def intersects(self, start: dt.datetime | None, end: dt.datetime | None) -> bool:
        if start is None and end is None:
            return False
        left = start or end
        right = end or start
        assert left is not None and right is not None
        if right < left:
            left, right = right, left
        if right == left:
            return self.contains(left)
        return left < self.end and right >= self.start

    def clip(
        self,
        start: dt.datetime | None,
        end: dt.datetime | None,
    ) -> tuple[dt.datetime, dt.datetime] | None:
        if not self.intersects(start, end):
            return None
        left = start or end
        right = end or start
        assert left is not None and right is not None
        if right < left:
            left, right = right, left
        left = max(left, self.start)
        right = min(right, self.end)
        return None if right < left else (left, right)


def union_seconds(intervals: Iterable[tuple[dt.datetime, dt.datetime]]) -> float:
    """Return concurrency-adjusted wall time for half-open intervals."""

    ordered = sorted((a, b) if a <= b else (b, a) for a, b in intervals)
    if not ordered:
        return 0.0
    total = 0.0
    cur_start, cur_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += max(0.0, (cur_end - cur_start).total_seconds())
            cur_start, cur_end = start, end
    return total + max(0.0, (cur_end - cur_start).total_seconds())


def int_value(value: Any) -> int:
    """Coerce a native numeric meter to a non-negative integer."""

    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def native_metric(value: Any) -> int | None:
    """Preserve a missing native metric as unknown instead of inventing zero."""

    return None if value is None else int_value(value)


def codex_usage(raw: Mapping[str, Any] | None) -> dict[str, int]:
    """Normalize one Codex native token payload without cross-provider mixing."""

    raw = raw or {}
    input_tokens = int_value(raw.get("input_tokens"))
    cached = int_value(raw.get("cached_input_tokens"))
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "uncached_input_tokens": max(0, input_tokens - cached),
        "output_tokens": int_value(raw.get("output_tokens")),
        "reasoning_output_tokens": int_value(raw.get("reasoning_output_tokens")),
    }


def cumulative_delta(
    current: Mapping[str, int],
    previous: Mapping[str, int] | None,
) -> dict[str, int]:
    """Turn a cumulative native meter into a non-negative event delta.

    A component that decreases has reset; its current value is the first
    post-reset delta rather than zero.
    """

    if previous is None:
        return {key: int_value(value) for key, value in current.items()}
    return {
        key: (
            int_value(current.get(key))
            if int_value(current.get(key)) < int_value(previous.get(key))
            else int_value(current.get(key)) - int_value(previous.get(key))
        )
        for key in current
    }


def extract_pr_urls(text: str) -> list[str]:
    """Extract unique normalized GitHub pull-request URLs."""

    seen: set[str] = set()
    result: list[str] = []
    for match in PR_URL_RE.finditer(text or ""):
        url = f"https://github.com/{match.group('owner')}/{match.group('repo')}/pull/{int(match.group('number'))}"
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def parse_pr_url(url: str) -> tuple[str, str, int] | None:
    """Return owner, repository, and number for an exact GitHub PR URL."""

    match = PR_URL_RE.fullmatch((url or "").strip().rstrip("/"))
    if not match:
        return None
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def canonical_repository(
    value: Any,
    *,
    aliases: Mapping[str, str] | None = None,
) -> str:
    """Return a public owner/repo or ``unknown``; never publish a local path."""

    raw = str(value or "").strip()
    if not raw or raw.startswith(LOCAL_REPOSITORY_PREFIXES):
        return "unknown"
    if raw.startswith(("git@github.com:", "ssh://git@github.com/", "https://github.com/")):
        raw = re.sub(r"^(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)", "", raw)
        raw = raw.removesuffix(".git").strip("/")
    aliases = aliases or {}
    canonical = aliases.get(raw.lower(), aliases.get(raw, raw))
    return canonical if REPOSITORY_RE.fullmatch(canonical) else "unknown"


def canonical_receipt_key(receipt: Mapping[str, Any]) -> str:
    """Deduplicate redirects and repeated references by terminal PR identity."""

    canonical_url = str(receipt.get("canonical_url") or receipt.get("url") or "")
    parsed = parse_pr_url(canonical_url)
    if parsed:
        owner, repo, number = parsed
        return f"github:{owner.lower()}/{repo.lower()}#{number}"
    return f"opaque:{canonical_url}"


def _event_key(event: Mapping[str, Any]) -> str:
    explicit = event.get("event_id")
    if explicit:
        return str(explicit)
    stable = {
        "timestamp": event.get("timestamp"),
        "tokens": event.get("tokens") or event.get("components") or {},
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def canonicalize_sessions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge file fragments into one native session and deduplicate token events."""

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        agent = str(row.get("agent") or "")
        native_id = str(row.get("native_id") or row.get("_native_id") or "")
        if agent and native_id:
            grouped[(agent, native_id)].append(row)
    canonical: list[dict[str, Any]] = []
    for (agent, native_id), fragments in sorted(grouped.items()):
        starts = [value for row in fragments if (value := parse_ts(row.get("start"))) is not None]
        ends = [value for row in fragments if (value := parse_ts(row.get("end"))) is not None]
        parents = {
            str(row.get("parent_id") or row.get("_parent_id") or "")
            for row in fragments
            if row.get("parent_id") or row.get("_parent_id")
        }
        token_events: dict[str, dict[str, Any]] = {}
        native_events: set[str] = set()
        prompt_session_refs: set[str] = set()
        source_atom_ids: set[str] = set()
        for fragment in fragments:
            native_events.update(str(value) for value in fragment.get("event_ids") or [] if value)
            prompt_session_refs.update(str(value) for value in fragment.get("_prompt_session_refs") or [] if value)
            source_atom_ids.update(str(value) for value in fragment.get("_source_atom_ids") or [] if value)
            for event in fragment.get("token_events") or fragment.get("_token_events") or []:
                if isinstance(event, tuple) and len(event) == 2:
                    timestamp, components = event
                    normalized = {
                        "timestamp": iso_z(parse_ts(timestamp)),
                        "components": dict(components),
                    }
                elif isinstance(event, Mapping):
                    normalized = dict(event)
                else:
                    continue
                token_events.setdefault(_event_key(normalized), normalized)
        canonical.append(
            {
                "agent": agent,
                "native_id": native_id,
                "parent_id": sorted(parents)[0] if parents else None,
                "role": "child" if parents else "root",
                "start": iso_z(min(starts)) if starts else None,
                "end": iso_z(max(ends)) if ends else None,
                "events": (
                    len(native_events)
                    if native_events
                    else max(
                        (int_value(row.get("events")) for row in fragments),
                        default=0,
                    )
                ),
                "time_basis": next(
                    (str(row.get("time_basis")) for row in fragments if row.get("time_basis")),
                    "unknown",
                ),
                "token_events": sorted(
                    token_events.values(),
                    key=lambda event: str(event.get("timestamp") or ""),
                ),
                "_prompt_session_refs": sorted(prompt_session_refs),
                "_source_atom_ids": sorted(source_atom_ids),
            }
        )
    return canonical


def claude_identity(row: Mapping[str, Any], fallback: str) -> tuple[str, str | None]:
    """Use Claude child agentId as the child identity and sessionId as parent."""

    root = str(row.get("sessionId") or fallback)
    child = str(row.get("agentId") or "").strip()
    if child:
        return child, root
    return root, None


def event_executor_role(event: Mapping[str, Any]) -> str | None:
    """Classify terminal credit without conflating verification or landing."""

    explicit = str(event.get("executor_role") or "").lower()
    if explicit in EXECUTOR_ROLES:
        return explicit
    agent = str(event.get("agent") or "").lower()
    status = str(event.get("status") or "").lower()
    if agent not in AGENT_FAMILY:
        return None
    if event.get("landing_event") or "land" in status:
        return "lander"
    if event.get("verification_context_digest") or status == "pr_open":
        return "verifier"
    if event.get("merge_group") or event.get("integration"):
        return "integrator"
    return "executor"


def session_role_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count canonical root and child sessions from model behavior."""

    counts = {"root": 0, "child": 0}
    for row in canonicalize_sessions(rows):
        counts[row["role"]] += 1
    return counts


def historical_checks_state(
    checks: Iterable[Mapping[str, Any]],
    *,
    snapshot_at: dt.datetime,
) -> tuple[bool, bool]:
    """Return (passed_by_snapshot, historically_complete).

    A missing completion timestamp cannot prove the frozen head and therefore
    yields ``historically_complete=False``.
    """

    rows = list(checks)
    if not rows:
        return False, False
    accepted = {"SUCCESS", "NEUTRAL", "SKIPPED", "EXPECTED"}
    complete = True
    passed = True
    for row in rows:
        completed = parse_ts(row.get("completed_at") or row.get("completedAt") or row.get("context_at"))
        conclusion = str(row.get("conclusion") or row.get("state") or "").upper()
        status = str(row.get("status") or "").upper()
        if completed is None:
            complete = False
            passed = False
            continue
        if completed > snapshot_at:
            passed = False
            continue
        if status and status not in {"COMPLETED", "SUCCESS"}:
            passed = False
        if conclusion not in accepted:
            passed = False
    return passed, complete


def classify_receipt(
    receipt: Mapping[str, Any],
    *,
    snapshot_at: dt.datetime,
    predicate_signal: bool = False,
) -> tuple[str, str]:
    """Classify one PR conservatively as it existed at the frozen snapshot."""

    created = parse_ts(receipt.get("created_at"))
    if created is None or created >= snapshot_at:
        return "coverage_unknown", "receipt did not exist before the frozen snapshot"
    commits = [row for row in (receipt.get("commits") or []) if parse_ts(row.get("committed_at")) is not None]
    if any((parse_ts(row.get("committed_at")) or snapshot_at) >= snapshot_at for row in commits):
        return "coverage_unknown", "exact head changed after the frozen snapshot"
    merged_at = parse_ts(receipt.get("merged_at"))
    closed_at = parse_ts(receipt.get("closed_at"))
    on_default = bool(
        receipt.get("base_ref")
        and receipt.get("default_branch")
        and receipt.get("base_ref") == receipt.get("default_branch")
    )
    checks_passed, historical_complete = historical_checks_state(
        receipt.get("checks") or [],
        snapshot_at=snapshot_at,
    )
    if receipt.get("historical_check_contexts_complete") is False:
        checks_passed = False
        historical_complete = False
    if merged_at and merged_at < snapshot_at and on_default:
        if checks_passed or predicate_signal:
            return "verified_done", "merged to default with a timestamped exact-head predicate"
        if not historical_complete:
            return "verified_partial", "merged to default; historical check timing is incomplete"
        return "verified_partial", "merged to default, but the exact-head predicate did not pass by snapshot"
    if closed_at and closed_at < snapshot_at:
        return "not_done_or_unverified", "closed without a default-reachable merge"
    return "durably_homed_open", "open PR at the frozen snapshot"


def semantic_receipt_link(
    ask: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[bool, str]:
    """Require exact atom lineage or an owner-specific predicate for completion."""

    ask_atoms = {str(value) for value in ask.get("source_atom_ids") or [] if value}
    receipt_atoms = {str(value) for value in receipt.get("source_atom_ids") or [] if value}
    if ask_atoms and ask_atoms & receipt_atoms:
        return True, "exact source atom lineage"
    ask_repo = canonical_repository(ask.get("canonical_repo") or ask.get("repo"))
    receipt_repo = canonical_repository(receipt.get("canonical_repo") or receipt.get("repo"))
    predicate = receipt.get("predicate_result")
    predicate_ok = isinstance(predicate, Mapping) and predicate.get("passed") is True
    if ask_repo != "unknown" and ask_repo == receipt_repo and predicate_ok:
        return True, "owner-specific predicate"
    return False, "receipt is assistance without exact atom or owner-specific predicate"


def outcome_rank(outcome: str) -> int:
    """Return the conservative ordering used only among semantically linked receipts."""

    return {
        "verified_done": 7,
        "verified_partial": 6,
        "durably_homed_open": 5,
        "blocked": 4,
        "superseded": 3,
        "not_done_or_unverified": 2,
        "coverage_unknown": 1,
    }.get(outcome, 0)


def strongest_outcome(outcomes: Iterable[str]) -> str:
    """Return the strongest recognized outcome, or explicit unknown."""

    values = [value for value in outcomes if value in OUTCOMES]
    return max(values, key=outcome_rank) if values else "coverage_unknown"
