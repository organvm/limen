#!/usr/bin/env python3
"""Write a current storage-pressure ledger for the local substrate.

This is a receipt, not a deletion tool. It names the remaining large buckets and
the gate that owns each one after safe generated/cache/model reclaim has run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", "/Users/4jp")).expanduser()
ROOT = Path(os.environ.get("LIMEN_ROOT", HOME / "Workspace" / "limen")).expanduser()
DOC_PATH = ROOT / "docs" / "substrate-storage-pressure.md"
PRIVATE_PATH = ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "substrate-storage-pressure.json"
TARGET_FREE_GIB = float(os.environ.get("LIMEN_ALWAYS_WORKING_TARGET_FREE_GIB", "200"))
INVENTORY_MAX_AGE_SECONDS = int(os.environ.get("LIMEN_STORAGE_INVENTORY_MAX_AGE_SECONDS", "21600"))
BUCKET_SCAN_BUDGET_SECONDS = int(os.environ.get("LIMEN_STORAGE_BUCKET_SCAN_BUDGET_SECONDS", "30"))
BUCKET_SCAN_TIMEOUT_SECONDS = int(os.environ.get("LIMEN_STORAGE_BUCKET_SCAN_TIMEOUT_SECONDS", "8"))

RECLAIM_LOGS = {
    "generated-state": ROOT / "logs" / "reclaim-generated-state.jsonl",
    "tool-cache": ROOT / "logs" / "reclaim-tool-caches.jsonl",
    "ollama-models": ROOT / "logs" / "reclaim-ollama-models.jsonl",
}
OPENCODE_INTAKE_DOC = ROOT / "docs" / "opencode-db-corpus-intake.md"
OPENCODE_INTAKE_LOG = ROOT / "logs" / "opencode-db-corpus-intake.jsonl"

BUCKETS = (
    {
        "id": "opencode-db",
        "path": "~/.local/share/opencode/opencode.db",
        "class": "protected-agent-state",
        "owner": "aw-opencode-db-corpus-intake-0709",
        "gate": "extract/export into prompt-corpus intake before vendor retention decision; never delete outright",
    },
    {
        "id": "limen-private-session-corpus",
        "path": "~/Workspace/limen/.limen-private/session-corpus",
        "class": "protected-private-corpus",
        "owner": "docs/session-corpus-ledger.md",
        "gate": "two-copy/restore archive gate before move or purge",
    },
    {
        "id": "photos-library",
        "path": "~/Pictures/Photos Library.photoslibrary",
        "class": "personal-media",
        "owner": "media/photos custody",
        "gate": "personal-data human gate plus two-copy restore proof",
    },
    {
        "id": "messages",
        "path": "~/Library/Messages",
        "class": "personal-communications",
        "owner": "communications custody",
        "gate": "personal-data human gate plus two-copy restore proof",
    },
    {
        "id": "session-meta",
        "path": "~/Workspace/session-meta",
        "class": "repo-corpus-state",
        "owner": "organvm/session-meta",
        "gate": "repo/archive custody proof before local cache eviction",
    },
    {
        "id": "antigravity-scratch",
        "path": "~/.gemini/antigravity-cli/scratch",
        "class": "agy-scratch",
        "owner": "docs/antigravity-scratch-bridge.md",
        "gate": "antigravity scratch archive/redaction acceptance ledger before removal",
    },
    {
        "id": "limen-worktrees",
        "path": "~/Workspace/.limen-worktrees",
        "class": "worktree-cache",
        "owner": "docs/worktree-reclaim-acceptance.md",
        "gate": "clean+merged+idle or explicit acceptance; current worktree-debt gate reports zero reapable",
    },
    {
        "id": "gemini-agent-state",
        "path": "~/.gemini/antigravity-cli",
        "class": "protected-agent-state",
        "owner": "agy conductor",
        "gate": "preserve conversations/brain before eviction; scratch handled separately",
    },
    {
        "id": "limen-claude-worktrees",
        "path": "~/Workspace/limen/.claude/worktrees",
        "class": "regenerable-fleet-state",
        "owner": "organvm/domus-genoma#306",
        "gate": "live Domus exclusion coverage before growth is tolerated; worktree-debt owns deletion",
    },
    {
        "id": "limen-repo-worktrees",
        "path": "~/Workspace/limen/.worktrees",
        "class": "regenerable-fleet-state",
        "owner": "organvm/domus-genoma#306",
        "gate": "live Domus exclusion coverage before growth is tolerated; preserve dirty or unpushed roots before deletion",
    },
    {
        "id": "limen-codex-worktrees",
        "path": "~/Workspace/limen/.codex/worktrees",
        "class": "regenerable-fleet-state",
        "owner": "organvm/domus-genoma#306",
        "gate": "live Domus exclusion coverage before growth is tolerated; preserve dirty or unpushed roots before deletion",
    },
)


def stable(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser()
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        return str(resolved)


def expand(path: str) -> Path:
    return Path(path.replace("~", str(HOME), 1)).expanduser()


def du_kib(path: Path, timeout: int = 60) -> int | None:
    try:
        proc = subprocess.run(["du", "-sk", str(path)], text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return int(proc.stdout.split()[0])
    except (IndexError, ValueError):
        return None


def fmt_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def disk_free_gib(path: Path = HOME) -> float | None:
    try:
        stat = os.statvfs(path)
    except OSError:
        return None
    return round((stat.f_bavail * stat.f_frsize) / 1024**3, 1)


def parse_generated_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def age_seconds(generated_at: object, now: datetime) -> float | None:
    observed = parse_generated_at(generated_at)
    if observed is None:
        return None
    return max((now - observed).total_seconds(), 0.0)


def load_previous_snapshot(path: Path = PRIVATE_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def host_pressure_summary() -> dict[str, Any]:
    script = ROOT / "scripts" / "host-work-admission.py"
    if not script.exists():
        return {
            "present": False,
            "known": False,
            "allowed": False,
            "reasons": ["host-admission-missing"],
            "pressure": {},
        }
    try:
        proc = subprocess.run(
            ["python3", str(script), "status"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "present": True,
            "known": False,
            "allowed": False,
            "reasons": ["host-admission-unavailable"],
            "error": str(exc),
            "pressure": {},
        }
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return {
            "present": True,
            "known": False,
            "allowed": False,
            "reasons": ["host-admission-invalid-json"],
            "returncode": proc.returncode,
            "pressure": {},
        }
    pressure = data.get("pressure") if isinstance(data.get("pressure"), dict) else {}
    return {
        "present": True,
        "known": not bool(pressure.get("sensor_errors")),
        "allowed": data.get("allowed") is True,
        "reasons": data.get("reasons") if isinstance(data.get("reasons"), list) else [],
        "pressure": pressure,
    }


def backblaze_exclusion_coverage() -> dict[str, Any]:
    configured = os.environ.get("DOMUS_BACKBLAZE_EXCLUSIONS")
    executable = configured or shutil.which("domus-backblaze-exclusions")
    if not executable:
        return {
            "present": False,
            "known": False,
            "complete": False,
            "status": "unknown",
            "missing_exclusions": [],
            "unknown_internal_worktree_pools": [],
        }
    try:
        proc = subprocess.run(
            [executable, "--check", "--json"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "present": True,
            "known": False,
            "complete": False,
            "status": "unknown",
            "error": str(exc),
            "missing_exclusions": [],
            "unknown_internal_worktree_pools": [],
        }
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return {
            "present": True,
            "known": False,
            "complete": False,
            "status": "unknown",
            "returncode": proc.returncode,
            "error": (proc.stderr or "invalid JSON").strip()[:500],
            "missing_exclusions": [],
            "unknown_internal_worktree_pools": [],
        }
    plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
    missing = plan.get("missing_exclusions") if isinstance(plan.get("missing_exclusions"), list) else []
    unknown = (
        plan.get("unknown_internal_worktree_pools")
        if isinstance(plan.get("unknown_internal_worktree_pools"), list)
        else []
    )
    status = str(data.get("status") or "unknown")
    return {
        "present": True,
        "known": True,
        "complete": status == "ok" and not missing and not unknown,
        "status": status,
        "returncode": proc.returncode,
        "missing_exclusions": missing,
        "unknown_internal_worktree_pools": unknown,
        "required_exclusions": (
            plan.get("required_exclusions") if isinstance(plan.get("required_exclusions"), list) else []
        ),
        "protected_backup_roots": (
            plan.get("protected_backup_roots") if isinstance(plan.get("protected_backup_roots"), list) else []
        ),
    }


def select_inventory_mode(requested: str, host_pressure: dict[str, Any]) -> str:
    if requested == "auto":
        return "inventory" if host_pressure.get("allowed") else "cheap"
    if requested not in {"cheap", "inventory"}:
        raise ValueError(f"unsupported storage inventory mode: {requested}")
    return requested


def reclaim_summary(path: Path) -> dict[str, Any]:
    total = 0
    events = 0
    latest: dict[str, Any] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        latest = row
        if row.get("apply") is True:
            events += 1
            try:
                total += int(row.get("total_reclaimed_kib") or row.get("reclaimed_kib") or 0)
            except (TypeError, ValueError):
                pass
    return {
        "present": bool(latest),
        "apply_events": events,
        "latest_generated_at": latest.get("generated_at"),
        "cumulative_reclaimed_kib": total,
        "cumulative_reclaimed_size": fmt_bytes(total * 1024),
    }


def latest_opencode_intake() -> dict[str, Any]:
    latest: dict[str, Any] = {}
    try:
        lines = OPENCODE_INTAKE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            latest = row
    return {
        "present": bool(latest),
        "doc_present": OPENCODE_INTAKE_DOC.exists(),
        "status": latest.get("status"),
        "archive_status": latest.get("archive_status"),
        "generated_at": latest.get("generated_at"),
        "run_id": latest.get("run_id"),
        "private_manifest": latest.get("private_manifest"),
        "doc": stable(OPENCODE_INTAKE_DOC),
    }


def worktree_lifecycle_summary() -> dict[str, Any]:
    script = ROOT / "scripts" / "worktree-debt.py"
    if not script.exists():
        return {"present": False, "ok": False, "error": "scripts/worktree-debt.py missing"}
    try:
        proc = subprocess.run(
            ["python3", str(script), "--json"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"present": True, "ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {
            "present": True,
            "ok": False,
            "returncode": proc.returncode,
            "error": (proc.stderr or proc.stdout or "worktree-debt failed").strip()[:500],
        }
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return {"present": True, "ok": False, "returncode": proc.returncode, "error": "invalid JSON"}
    by_reason = data.get("by_reason") if isinstance(data.get("by_reason"), dict) else {}
    by_reapable_reason = data.get("by_reapable_reason") if isinstance(data.get("by_reapable_reason"), dict) else {}
    total = int(data.get("total") or 0)
    debt = int(data.get("debt") or 0)
    reapable = int(data.get("reapable") or 0)
    return {
        "present": True,
        "ok": True,
        "total": total,
        "debt": debt,
        "reapable": reapable,
        "debt_target": 0,
        "complete": debt == 0,  # exact-zero completion; no tolerated debt count
        "reapable_limit": data.get("reapable_limit"),
        "by_reason": by_reason,
        "by_reapable_reason": by_reapable_reason,
        "summary": f"{debt} debt roots / {total} scanned; {reapable} reapable roots",
    }


def build_snapshot(
    *,
    mode: str = "inventory",
    previous: dict[str, Any] | None = None,
    host_pressure: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if mode not in {"cheap", "inventory"}:
        raise ValueError(f"unsupported storage inventory mode: {mode}")
    previous = previous or {}
    now = now or datetime.now(timezone.utc)
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    previous_age = age_seconds(previous.get("generated_at"), now)
    previous_fresh = previous_age is not None and previous_age <= INVENTORY_MAX_AGE_SECONDS
    previous_inventory = previous.get("inventory") if isinstance(previous.get("inventory"), dict) else {}
    inherited_inventory_fresh = previous_inventory.get("fresh", True) is True
    previous_buckets = {
        str(row.get("id")): row for row in previous.get("buckets", []) if isinstance(row, dict) and row.get("id")
    }

    free = disk_free_gib()
    shortfall = round(max(TARGET_FREE_GIB - (free or 0), 0), 1) if free is not None else None
    inherited_trend = previous.get("free_space_trend") if isinstance(previous.get("free_space_trend"), dict) else {}
    previous_free = inherited_trend.get("previous_free_gib", previous.get("internal_free_gib"))
    inherited_window = inherited_trend.get("window_seconds")
    try:
        free_delta = round(float(free) - float(previous_free), 1) if free is not None else None
    except (TypeError, ValueError):
        free_delta = None
    try:
        trend_window = float(inherited_window or 0) + float(previous_age or 0)
    except (TypeError, ValueError):
        trend_window = previous_age
    if free_delta is None:
        free_direction = "unknown"
    elif free_delta > 0:
        free_direction = "rising"
    elif free_delta < 0:
        free_direction = "falling"
    else:
        free_direction = "flat"

    if mode == "cheap" and isinstance(previous.get("opencode_intake"), dict):
        opencode_intake = dict(previous["opencode_intake"])
        opencode_intake["source"] = "cached"
        opencode_intake["age_seconds"] = previous_age
        opencode_intake["fresh"] = previous_fresh
    else:
        opencode_intake = latest_opencode_intake()
        opencode_intake["source"] = "measured"
        opencode_intake["age_seconds"] = 0.0
        opencode_intake["fresh"] = True
    rows = []
    scan_started = time.monotonic()
    scan_count = 0
    unknown_count = 0
    cached_count = 0
    for bucket in BUCKETS:
        path = expand(str(bucket["path"]))
        previous_row = previous_buckets.get(str(bucket["id"]), {})
        size_kib: int | None
        size_source: str
        measured_at: object
        if mode == "cheap":
            raw_size = previous_row.get("size_kib")
            try:
                size_kib = int(raw_size) if raw_size is not None else None
            except (TypeError, ValueError):
                size_kib = None
            size_source = "cached" if size_kib is not None else "unknown"
            measured_at = previous.get("generated_at") if size_kib is not None else None
            cached_count += int(size_kib is not None)
        else:
            remaining = BUCKET_SCAN_BUDGET_SECONDS - (time.monotonic() - scan_started)
            if remaining <= 0:
                size_kib = None
            else:
                timeout = max(1, min(BUCKET_SCAN_TIMEOUT_SECONDS, int(remaining)))
                size_kib = du_kib(path, timeout=timeout)
                scan_count += 1
            size_source = "measured" if size_kib is not None else "unknown"
            measured_at = generated_at if size_kib is not None else None
        unknown_count += int(size_kib is None)
        gate = str(bucket["gate"])
        evidence: dict[str, Any] = {}
        if bucket["id"] == "opencode-db" and opencode_intake.get("archive_status") == "verified":
            gate = (
                "external archive and private intake verified; local retention decision remains; never delete outright"
            )
            evidence["opencode_intake"] = opencode_intake
        rows.append(
            {
                **bucket,
                "gate": gate,
                "evidence": evidence,
                "display_path": stable(path),
                "exists": path.exists(),
                "size_kib": size_kib,
                "size": fmt_bytes(size_kib * 1024 if size_kib is not None else None),
                "size_source": size_source,
                "measured_at": measured_at,
            }
        )
    rows.sort(key=lambda row: int(row["size_kib"] or -1), reverse=True)

    if mode == "cheap" and isinstance(previous.get("safe_reclaim"), dict):
        reclaim = dict(previous["safe_reclaim"])
    else:
        reclaim = {name: reclaim_summary(path) for name, path in RECLAIM_LOGS.items()}
    if mode == "inventory":
        worktree_lifecycle = worktree_lifecycle_summary()
        lifecycle_source = "measured"
        lifecycle_age = 0.0
    else:
        cached_lifecycle = previous.get("worktree_lifecycle")
        worktree_lifecycle = dict(cached_lifecycle) if isinstance(cached_lifecycle, dict) else {}
        lifecycle_source = "cached" if worktree_lifecycle else "unknown"
        try:
            lifecycle_age = (
                float(worktree_lifecycle.get("age_seconds") or 0) + float(previous_age or 0)
                if worktree_lifecycle
                else None
            )
        except (TypeError, ValueError):
            lifecycle_age = None
        if worktree_lifecycle:
            cached_ok = bool(cached_lifecycle.get("cached_ok", cached_lifecycle.get("ok")))
            worktree_lifecycle["ok"] = cached_ok and bool(
                lifecycle_age is not None and lifecycle_age <= INVENTORY_MAX_AGE_SECONDS
            )
            worktree_lifecycle["cached_ok"] = cached_ok
            worktree_lifecycle.setdefault("debt_target", 0)
            worktree_lifecycle["complete"] = int(worktree_lifecycle.get("debt") or 0) == 0
    worktree_lifecycle["source"] = lifecycle_source
    worktree_lifecycle["age_seconds"] = lifecycle_age
    worktree_lifecycle["fresh"] = lifecycle_age is not None and lifecycle_age <= INVENTORY_MAX_AGE_SECONDS

    host = host_pressure or host_pressure_summary()
    exclusions = backblaze_exclusion_coverage()
    inventory_fresh = mode == "inventory" or (previous_fresh and inherited_inventory_fresh)
    scope_issues: list[str] = []
    if free is None:
        scope_issues.append("internal-free-space-unknown")
    if not host.get("known"):
        scope_issues.append("host-pressure-unknown")
    if not exclusions.get("known"):
        scope_issues.append("backblaze-exclusion-coverage-unknown")
    if not worktree_lifecycle.get("fresh"):
        scope_issues.append("worktree-inventory-stale-or-unknown")
    if unknown_count:
        scope_issues.append("bucket-size-inventory-incomplete")
    if not inventory_fresh:
        scope_issues.append("storage-inventory-stale")
    if not previous and mode == "cheap":
        scope_issues.append("no-prior-storage-inventory")

    known_components = (
        free is not None,
        bool(host.get("known")),
        bool(exclusions.get("known")),
        bool(worktree_lifecycle),
        any(row.get("size_kib") is not None for row in rows),
    )
    if not scope_issues:
        scope_status = "complete"
    elif any(known_components):
        scope_status = "partial"
    else:
        scope_status = "unknown"

    debt = worktree_lifecycle.get("debt")
    reapable = worktree_lifecycle.get("reapable")
    lifecycle_red = (
        not worktree_lifecycle.get("ok")
        or debt is None
        or reapable is None
        or int(debt or 0) != 0
        or int(reapable or 0) != 0
    )
    pressure_red = not host.get("allowed")
    exclusion_red = not exclusions.get("complete")
    if scope_status != "complete":
        status = scope_status
    elif shortfall is None:
        status = "unknown"
    elif shortfall > 0 or lifecycle_red or pressure_red or exclusion_red:
        status = "needs-owner-gates"
    else:
        status = "clear"

    return {
        "schema": "limen.substrate_storage_pressure.v2",
        "generated_at": generated_at,
        "status": status,
        "scope_status": scope_status,
        "scope_issues": scope_issues,
        "inventory": {
            "mode": mode,
            "fresh": inventory_fresh,
            "max_age_seconds": INVENTORY_MAX_AGE_SECONDS,
            "previous_generated_at": previous.get("generated_at"),
            "previous_age_seconds": previous_age,
            "bucket_scan_budget_seconds": BUCKET_SCAN_BUDGET_SECONDS,
            "bucket_scan_timeout_seconds": BUCKET_SCAN_TIMEOUT_SECONDS,
            "bucket_count": len(rows),
            "measured_bucket_count": scan_count,
            "cached_bucket_count": cached_count,
            "unknown_bucket_count": unknown_count,
            "truncated": unknown_count > 0,
        },
        "target_free_gib": TARGET_FREE_GIB,
        "internal_free_gib": free,
        "shortfall_gib": shortfall,
        "free_space_trend": {
            "previous_free_gib": previous_free,
            "delta_gib": free_delta,
            "direction": free_direction,
            "window_seconds": trend_window,
        },
        "host_admission": host,
        "backblaze_pressure": host.get("pressure") if isinstance(host.get("pressure"), dict) else {},
        "backblaze_exclusion_coverage": exclusions,
        "safe_reclaim": reclaim,
        "opencode_intake": opencode_intake,
        "worktree_lifecycle": worktree_lifecycle,
        "buckets": rows,
    }


def render(snapshot: dict[str, Any]) -> str:
    inventory = snapshot.get("inventory") if isinstance(snapshot.get("inventory"), dict) else {}
    trend = snapshot.get("free_space_trend") if isinstance(snapshot.get("free_space_trend"), dict) else {}
    pressure = snapshot.get("backblaze_pressure") if isinstance(snapshot.get("backblaze_pressure"), dict) else {}
    exclusions = (
        snapshot.get("backblaze_exclusion_coverage")
        if isinstance(snapshot.get("backblaze_exclusion_coverage"), dict)
        else {}
    )
    lines = [
        "# Substrate Storage Pressure",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        f"Scope status: `{snapshot.get('scope_status', 'unknown')}`",
        (
            f"Inventory: `{inventory.get('mode', 'legacy')}`; "
            f"fresh: `{inventory.get('fresh', False)}`; "
            f"unknown buckets: `{inventory.get('unknown_bucket_count', 'unknown')}`"
        ),
        f"Internal free: `{snapshot['internal_free_gib']} GiB`",
        f"Target free: `{snapshot['target_free_gib']} GiB`",
        f"Shortfall: `{snapshot['shortfall_gib']} GiB`",
        (
            f"Free-space trend: `{trend.get('direction', 'unknown')}` "
            f"(`{trend.get('delta_gib', 'unknown')} GiB` over "
            f"`{trend.get('window_seconds', 'unknown')}s`)"
        ),
        "",
        "## Host and Backup Admission",
        "",
        (
            f"- Backblaze CPU: `{pressure.get('backblaze_cpu_percent', 'unknown')}%`; "
            f"RSS: `{pressure.get('backblaze_rss_bytes', 'unknown')}` bytes."
        ),
        (
            f"- Swap fraction: `{pressure.get('swap_fraction', 'unknown')}`; "
            f"host admission allowed: `{(snapshot.get('host_admission') or {}).get('allowed', False)}`."
        ),
        (
            f"- Exclusion coverage: `{exclusions.get('status', 'unknown')}`; "
            f"complete: `{exclusions.get('complete', False)}`; "
            f"missing: `{len(exclusions.get('missing_exclusions') or [])}`; "
            f"unknown pools: `{len(exclusions.get('unknown_internal_worktree_pools') or [])}`."
        ),
        "",
        "## Safe Reclaim Already Run",
        "",
    ]
    for name, row in snapshot["safe_reclaim"].items():
        lines.append(
            f"- `{name}`: `{row['cumulative_reclaimed_size']}` over `{row['apply_events']}` apply event(s); "
            f"latest `{row['latest_generated_at']}`."
        )
    lifecycle = snapshot.get("worktree_lifecycle") or {}
    lines += [
        "",
        "## Scratch / Worktree Lifecycle",
        "",
    ]
    if lifecycle.get("ok") or lifecycle.get("source") == "cached":
        label = "Summary" if lifecycle.get("ok") else "Cached stale summary"
        lines.append(f"- {label}: `{lifecycle.get('summary', 'unknown')}`.")
        if lifecycle.get("source") == "cached":
            lines.append(
                f"- Inventory age: `{lifecycle.get('age_seconds', 'unknown')}s`; "
                f"fresh: `{lifecycle.get('fresh', False)}`."
            )
        lines.append(
            f"- Debt target: `{lifecycle.get('debt_target', 0)}`; complete: `{lifecycle.get('complete')}`; "
            f"reapable cap: `{lifecycle.get('reapable_limit')}`."
        )
        by_reason = lifecycle.get("by_reason") if isinstance(lifecycle.get("by_reason"), dict) else {}
        if by_reason:
            lines += ["", "| Reason | Roots |", "|---|---:|"]
            for reason, count in sorted(by_reason.items(), key=lambda item: (-int(item[1]), str(item[0]))):
                lines.append(f"| `{reason}` | `{count}` |")
    else:
        lines.append(f"- Worktree lifecycle unavailable: `{lifecycle.get('error', 'unknown')}`.")
    lines += [
        "",
        "## Remaining Large Buckets",
        "",
        "| Bucket | Size | Class | Owner | Gate |",
        "|---|---:|---|---|---|",
    ]
    for row in snapshot["buckets"]:
        lines.append(
            f"| `{row['display_path']}` | `{row['size']}` | `{row['class']}` | `{row['owner']}` | {row['gate']} |"
        )
    opencode_intake = snapshot.get("opencode_intake") if isinstance(snapshot.get("opencode_intake"), dict) else {}
    if opencode_intake.get("present"):
        lines += [
            "",
            "## OpenCode DB Intake",
            "",
            f"- Status: `{opencode_intake.get('status')}`.",
            f"- Archive status: `{opencode_intake.get('archive_status')}`.",
            f"- Receipt: `{opencode_intake.get('doc')}`.",
            f"- Private manifest: `{(opencode_intake.get('private_manifest') or {}).get('path', 'none')}`.",
        ]
    lines += [
        "",
        "## Contract",
        "",
        "- A stale, partial, or unknown inventory can never report `clear`.",
        "- Under red host admission, auto mode reads cheap sensors and cached bounded inventories; it does not run broad bucket or worktree scans.",
        "- Bucket inventory is bounded by an aggregate scan budget and a per-bucket timeout; unknown sizes remain explicit.",
        "- Do not delete personal communications, photos, private corpus, or agent session databases as cache.",
        "- Worktree and Agy scratch removal stay behind their acceptance ledgers.",
        "- More disk reduction now requires owner gates, archive/restore proof, or explicit product decision to lower the hot-cache target.",
    ]
    return "\n".join(lines) + "\n"


def write(snapshot: dict[str, Any], *, private_path: Path = PRIVATE_PATH) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(render(snapshot), encoding="utf-8")
    private_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Write substrate storage pressure receipts.")
    parser.add_argument("--write", action="store_true", help="write docs and private JSON")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument(
        "--mode",
        choices=("auto", "cheap", "inventory"),
        default="auto",
        help="auto uses inventory only when machine-wide host admission is green",
    )
    parser.add_argument(
        "--previous-receipt",
        type=Path,
        default=PRIVATE_PATH,
        help="prior private receipt used for trend and cheap cached inventory",
    )
    parser.add_argument(
        "--private-output",
        type=Path,
        default=PRIVATE_PATH,
        help="private JSON receipt target (use the canonical corpus from isolated worktrees)",
    )
    args = parser.parse_args()
    previous = load_previous_snapshot(args.previous_receipt)
    host = host_pressure_summary()
    mode = select_inventory_mode(args.mode, host)
    snapshot = build_snapshot(mode=mode, previous=previous, host_pressure=host)
    if args.write:
        write(snapshot, private_path=args.private_output)
    if args.json or not args.write:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(
            f"substrate-storage-pressure: {snapshot['status']} free={snapshot['internal_free_gib']}GiB "
            f"shortfall={snapshot['shortfall_gib']}GiB"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
