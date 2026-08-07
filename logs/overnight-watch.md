# Overnight Watch

- Status: `alert`
- Updated: `2026-08-07T15:22:53+00:00`
- Log age: `104` seconds
- Launchd: `active`
- Latest tick: `tick emitted: 2026-08-07T15:15:13+00:00 total=3111 open=829 spent=8/600`
- Latest async: `None`
- Stale tick samples: `1`
- Active workers: `0`
- Heartbeat child processes: `1`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `true`.
- Gate action: `continue_direct_product_work` (exit `0`).
- Dispatch allowed: `false`.
- Lane switch: `not_requested`; owner packet: `none`; tickets: `0`.
- Lane blocker: `none`.
- Next command: `python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check`.

## Gate Checks

- Handoff refresh: `1`; check: `1`.
- Value gate: `0`; action: `continue_direct_product_work`.
- Dispatch control: handoff relay check failed; refresh handoff before launching workers.
- Selected owner: `none`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0`).
- Below floor: `false`; suppressed: `no`.
  - child `24403` `S` `03:24:04` `/bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh`

## WATCH_ALERT
- `handoff-relay-stale`: Command '['/Users/4jp/.local/share/limen/runtimes/06f96a8f41bcba81ee4b5989939f5114fb7ba8f4/venv/bin/python', '/Users/4jp/Workspace/limen/scripts/handoff-relay.py', '--check']' timed out after 20 seconds
