# Overnight Watch

- Status: `alert`
- Updated: `2026-07-09T11:24:17+00:00`
- Log age: `44` seconds
- Launchd: `None`
- Stale tick samples: `3`
- Active workers: `0`
- Heartbeat child processes: `0`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `false`.
- Gate action: `switch_to_direct_product_work` (exit `10`).
- Dispatch allowed: `false`.
- Next command: `python3 scripts/product-ledger.py --refresh --redacted-summary`.

## Gate Checks

- Handoff refresh: `0`; check: `0`.
- Value gate: `10`; action: `switch_to_direct_product_work`.
- Dispatch control: session value gate requested a lane switch before generic dispatch.

## WATCH_ALERT
- `heartbeat-launchd-not-running`: state=None error=Bad request.
Could not find service "com.limen.heartbeat" in domain for user gui: 501
- `heartbeat-async-env-mismatch`: LIMEN_DISPATCH_ASYNC=None expected=1
- `heartbeat-lanes-env-mismatch`: LIMEN_DISPATCH_LANES=None expected=auto
