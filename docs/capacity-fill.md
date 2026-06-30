# Claude Capacity Fill

Generated: `2026-06-30T03:58:53+00:00`

## Lane State

- Status: `blocked`
- Dispatch health: `blocked`

## Capacity Snapshot

- Daily cap: `600`
- Claude daily consumed: `0`
- Remaining slot room (lane-local): `600`


## Claude Scope

- Total Claude-targeted tasks: `436`
- Status counts: `archived=173, done=246, needs_human=17`

## Open Queue (top 20)

- none

## Dispatch Blockers

- `live-root-not-at-origin-main`: live root branch main head d6757d3d21fc differs from origin/main 9f7af24dcb75.
- `live-root-dirty`: live root has 2 dirty entries.

## Next Step

- If status is `ready`, continue dispatch for the top open IDs.
- If status is `blocked`, run the human-gated lane checkup in `docs/lane-checkups/claude/20260629-03.md`.

## Commands

- Refresh this ledger: `python3 scripts/capacity-fill-ledger.py --write`
- Re-check dispatch-health freshness: `python3 scripts/dispatch-health.py --write --probe-async`
