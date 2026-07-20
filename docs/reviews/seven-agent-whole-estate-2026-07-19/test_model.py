#!/usr/bin/env python3
"""Synthetic contract tests for the canonical seven-agent review model."""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from model import (  # type: ignore
    UTC,
    Window,
    canonical_receipt_key,
    canonical_repository,
    canonicalize_sessions,
    classify_receipt,
    cumulative_delta,
    event_executor_role,
    native_metric,
    semantic_receipt_link,
    session_role_counts,
    strongest_outcome,
    union_seconds,
)


def t(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class ReviewModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Window(
            "w",
            "Window",
            t("2026-07-06T04:00:00Z"),
            t("2026-07-13T04:00:00Z"),
        )
        self.snapshot = t("2026-07-19T15:11:00Z")

    def test_boundary_crossing_is_clipped_half_open(self) -> None:
        clipped = self.window.clip(
            t("2026-07-06T03:00:00Z"),
            t("2026-07-06T05:00:00Z"),
        )
        self.assertEqual(
            clipped,
            (t("2026-07-06T04:00:00Z"), t("2026-07-06T05:00:00Z")),
        )
        self.assertFalse(self.window.contains(t("2026-07-13T04:00:00Z")))

    def test_cumulative_token_meter_becomes_delta(self) -> None:
        self.assertEqual(
            cumulative_delta(
                {"input": 140, "output": 20},
                {"input": 100, "output": 12},
            ),
            {"input": 40, "output": 8},
        )

    def test_overlapping_intervals_use_union_wall_time(self) -> None:
        intervals = [
            (t("2026-07-06T04:00:00Z"), t("2026-07-06T06:00:00Z")),
            (t("2026-07-06T05:00:00Z"), t("2026-07-06T07:00:00Z")),
        ]
        self.assertEqual(union_seconds(intervals), 3 * 3600)

    def test_root_child_separation_uses_canonical_model(self) -> None:
        rows = [
            {"agent": "claude", "native_id": "root", "events": 1},
            {
                "agent": "claude",
                "native_id": "child",
                "parent_id": "root",
                "events": 1,
            },
        ]
        self.assertEqual(
            session_role_counts(rows),
            {"root": 1, "child": 1},
        )

    def test_duplicate_redirect_receipts_share_one_key(self) -> None:
        left = {
            "url": "https://github.com/a-organvm/demo/pull/7",
            "canonical_url": "https://github.com/organvm/demo/pull/7",
        }
        right = {"url": "https://github.com/organvm/demo/pull/7"}
        self.assertEqual(
            canonical_receipt_key(left),
            canonical_receipt_key(right),
        )

    def test_healer_transition_has_no_executor_credit(self) -> None:
        self.assertIsNone(
            event_executor_role({"agent": "heal-board", "status": "done"})
        )

    def test_timestamped_open_and_merged_prs_classify_differently(self) -> None:
        base = {
            "created_at": "2026-07-17T10:00:00Z",
            "base_ref": "main",
            "default_branch": "main",
            "checks": [
                {
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "completed_at": "2026-07-17T10:30:00Z",
                }
            ],
            "commits": [{"committed_at": "2026-07-17T10:05:00Z"}],
        }
        self.assertEqual(
            classify_receipt(base, snapshot_at=self.snapshot)[0],
            "durably_homed_open",
        )
        merged = {**base, "merged_at": "2026-07-17T11:00:00Z"}
        self.assertEqual(
            classify_receipt(merged, snapshot_at=self.snapshot)[0],
            "verified_done",
        )

    def test_missing_metrics_remain_unknown_not_zero(self) -> None:
        self.assertIsNone(native_metric(None))
        self.assertEqual(native_metric(0), 0)

    def test_session_fragments_and_token_events_deduplicate(self) -> None:
        event = {
            "event_id": "same",
            "timestamp": "2026-07-17T10:30:00Z",
            "components": {"input_tokens": 10},
        }
        rows = [
            {
                "agent": "codex",
                "native_id": "root",
                "start": "2026-07-17T10:00:00Z",
                "end": "2026-07-17T11:00:00Z",
                "events": 1,
                "token_events": [event],
            },
            {
                "agent": "codex",
                "native_id": "root",
                "start": "2026-07-17T10:30:00Z",
                "end": "2026-07-17T12:00:00Z",
                "events": 1,
                "token_events": [event],
            },
        ]
        canonical = canonicalize_sessions(rows)
        self.assertEqual(len(canonical), 1)
        self.assertEqual(len(canonical[0]["token_events"]), 1)

    def test_pr_839_is_assistance_for_unrelated_owner(self) -> None:
        linked, reason = semantic_receipt_link(
            {
                "source_atom_ids": ["pa-owner"],
                "canonical_repo": "organvm/owner-repo",
            },
            {
                "source_atom_ids": ["pa-control-plane"],
                "canonical_repo": "organvm/limen",
                "url": "https://github.com/organvm/limen/pull/839",
                "predicate_result": {"passed": True},
            },
        )
        self.assertFalse(linked)
        self.assertIn("assistance", reason)

    def test_local_repository_paths_never_publish(self) -> None:
        self.assertEqual(canonical_repository("~/Workspace/limen"), "unknown")
        self.assertEqual(canonical_repository("/Volumes/Archive/repo"), "unknown")

    def test_outcome_dedup_prefers_verified_terminal_receipt(self) -> None:
        self.assertEqual(
            strongest_outcome(
                ["coverage_unknown", "durably_homed_open", "verified_done"]
            ),
            "verified_done",
        )


if __name__ == "__main__":
    unittest.main()
