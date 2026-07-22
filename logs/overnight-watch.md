# Overnight Watch

- Status: `alert`
- Updated: `2026-07-22T21:32:51+00:00`
- Log age: `164` seconds
- Launchd: `active`
- Latest tick: `tick emitted: 2026-07-22T21:30:06+00:00 total=3029 open=754 spent=4/600`
- Latest async: `async: reaped 0 dead · harvested 0 · 0 still running · launched 0`
- Stale tick samples: `0`
- Active workers: `0`
- Heartbeat child processes: `1`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `false`.
- Gate action: `stop_no_durable_progress` (exit `20`).
- Dispatch allowed: `false`.
- Lane switch: `blocked`; owner packet: `none`; tickets: `0`.
- Lane blocker: `overnight-owner-packets-gated`.
- Next command: `python3 scripts/always-working.py --write`.

## Gate Checks

- Handoff refresh: `0`; check: `0`.
- Value gate: `20`; action: `stop_no_durable_progress`.
- Dispatch control: all bounded owner packets are closed by current capability, lifecycle, owner gate(s).
- Selected owner: `organvm/limen`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0.0`).
- Below floor: `false`; suppressed: `no`.
  - child `90444` `S` `02:45` `sleep 1800`

## WATCH_ALERT
- `overnight-lane-switch-blocked`: blocker=overnight-owner-packets-gated owner=organvm/limen reason=all bounded owner packets are closed by current capability, lifecycle, owner gate(s)
