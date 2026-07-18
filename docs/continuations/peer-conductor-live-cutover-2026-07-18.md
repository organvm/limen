# Peer-conductor live-cutover continuation

Continue the symmetric peer-conductor mesh from its isolated implementation branch and durable PR.
Do not restart the design or treat the census as completed review work.

Read these modules in order:

1. `docs/continuations/peer-conductor-live-cutover-2026-07-18/objective.md`
2. `docs/continuations/peer-conductor-live-cutover-2026-07-18/constraints.md`
3. `docs/continuations/peer-conductor-live-cutover-2026-07-18/decision.md`
4. `docs/continuations/peer-conductor-live-cutover-2026-07-18/receipts.md`
5. `docs/continuations/peer-conductor-live-cutover-2026-07-18/workstream.json`
   — the validated finite-runway, authorization, and conductor receipt.

Missing, stale, contradictory, or unreadable modules make the capsule invalid. Start a fresh
isolated continuation from the remotely preserved implementation branch:

```bash
limen workstream --autonomous --agent auto \
  --from origin/work/peer-conductor-mesh-20260718 \
  --prompt-file docs/continuations/peer-conductor-live-cutover-2026-07-18.md \
  limen peer-conductor-live-cutover
```

The bootstrap command deliberately omits `--conduct`: the production broker must not accept a new
session until principal-bound authentication and executor-only lease delivery pass. This direct
human continuation may repair that gate in isolation, then must register before launching any
child, task transition, external effect, or separate capacity.
