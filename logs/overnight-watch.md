# Overnight Watch

- Status: `alert`
- Updated: `2026-07-21T07:47:41+00:00`
- Log age: `46` seconds
- Launchd: `active`
- Latest tick: `tick emitted: 2026-07-21T04:29:19+00:00 total=3015 open=741 spent=4/600`
- Latest async: `async: reaped 0 dead · harvested 0 · 0 still running · launched 0`
- Stale tick samples: `1`
- Active workers: `0`
- Heartbeat child processes: `2`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `true`.
- Gate action: `stop_no_durable_progress` (exit `20`).
- Dispatch allowed: `false`.
- Lane switch: `blocked`; owner packet: `none`; tickets: `0`.
- Lane blocker: `overnight-handoff-blocked`.
- Next command: `python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check`.

## Gate Checks

- Handoff refresh: `0`; check: `1`.
- Value gate: `20`; action: `stop_no_durable_progress`.
- Dispatch control: handoff relay is not fresh enough to transfer one owner packet.
- Selected owner: `organvm/limen`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0.0`).
- Below floor: `false`; suppressed: `no`.
  - child `35848` `S` `00:46` `timeout 300 python3 /Users/4jp/Workspace/limen/scripts/cvstos-organ.py`
  - child `35849` `S` `00:46` `tail -1`

## WATCH_ALERT
- `handoff-relay-stale`: handoff-relay --check: FAIL — provider headroom stale (214m > 90m)
- `overnight-lane-switch-blocked`: blocker=overnight-handoff-blocked owner=organvm/limen reason=handoff relay is not fresh enough to transfer one owner packet
