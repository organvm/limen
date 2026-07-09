# Overnight Watch

- Status: `blocked`
- Updated: `2026-07-09T12:37:39+00:00`
- Log age: `2` seconds
- Launchd: `active`
- Stale tick samples: `1`
- Active workers: `0`
- Heartbeat child processes: `1`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `false`.
- Gate action: `switch_to_packetization` (exit `10`).
- Dispatch allowed: `false`.
- Next command: `python3 scripts/prompt-batch-review-ledger.py --write`.

## Gate Checks

- Handoff refresh: `0`; check: `0`.
- Value gate: `10`; action: `switch_to_packetization`.
- Dispatch control: session value gate requested a lane switch before generic dispatch.
  - child `17948` `S` `00:03` `/bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh`
