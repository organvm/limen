"""Frozen review configuration and timezone-derived windows."""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from .model import UTC, Window, parse_ts

DEFAULT_TIMEZONE = "America/New_York"


@dataclasses.dataclass(frozen=True)
class ReviewConfig:
    """Inputs and durable output locations for one review."""

    root: Path
    snapshot_at: dt.datetime
    output_dir: Path
    timezone: str = DEFAULT_TIMEZONE

    @classmethod
    def from_values(
        cls,
        *,
        root: Path,
        snapshot_at: str | dt.datetime,
        output_dir: Path,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> "ReviewConfig":
        parsed = parse_ts(snapshot_at)
        if parsed is None:
            raise ValueError("snapshot_at must be a valid ISO-8601 timestamp")
        return cls(
            root=root.resolve(),
            snapshot_at=parsed,
            output_dir=output_dir.resolve(),
            timezone=timezone,
        )

    @property
    def windows(self) -> tuple[Window, Window]:
        return derive_windows(self.snapshot_at, timezone=self.timezone)


def derive_windows(
    snapshot_at: dt.datetime,
    *,
    timezone: str = DEFAULT_TIMEZONE,
) -> tuple[Window, Window]:
    """Derive the prior completed Monday week and rolling seven-day view."""

    snapshot = snapshot_at.astimezone(UTC)
    local = snapshot.astimezone(ZoneInfo(timezone))
    current_week_start = (local - dt.timedelta(days=local.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    completed_start = current_week_start - dt.timedelta(days=7)
    return (
        Window(
            "completed_week",
            "Completed calendar week",
            completed_start.astimezone(UTC),
            current_week_start.astimezone(UTC),
        ),
        Window(
            "latest_7d",
            "Latest seven days",
            snapshot - dt.timedelta(days=7),
            snapshot,
        ),
    )
