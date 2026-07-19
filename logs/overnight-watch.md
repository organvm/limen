# Overnight Watch

- Status: `alert`
- Updated: `2026-07-19T10:35:30+00:00`
- Log age: `48` seconds
- Launchd: `active`
- Latest tick: `tick emitted: 2026-07-19T10:23:11+00:00 total=2693 open=419 spent=13/600`
- Latest async: `async: reaped 0 dead · harvested 0 · 0 still running · launched 0`
- Stale tick samples: `1`
- Active workers: `0`
- Heartbeat child processes: `2`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `false`.
- Gate action: `switch_to_packetization` (exit `10`).
- Dispatch allowed: `false`.
- Lane switch: `blocked`; owner packet: `none`; tickets: `0`.
- Lane blocker: `overnight-owner-packets-gated`.
- Next command: `python3 scripts/always-working.py --write`.

## Gate Checks

- Handoff refresh: `0`; check: `0`.
- Value gate: `10`; action: `switch_to_packetization`.
- Dispatch control: all bounded owner packets are closed by current capability, owner gate(s).
- Selected owner: `organvm/limen`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0.0`).
- Below floor: `false`; suppressed: `no`.
  - child `59425` `S` `00:48` `bash /Users/4jp/Workspace/limen/scripts/capture.sh`
  - child `59426` `S` `00:48` `tail -3`

## WATCH_ALERT
- `overnight-lane-switch-blocked`: blocker=overnight-owner-packets-gated owner=organvm/limen reason=all bounded owner packets are closed by current capability, owner gate(s)
