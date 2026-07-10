# IDEAL-FORMS LEDGER — limen fleet

Claude's own ideal-form ideas for the organism, tracked as **named params** — the same
weight as one of Anthony's asks (doctrine: *track my ideas like asks*; *distillation, not
reduction*). Precedent: `sovereign-systems--elevate-align/docs/IDEAL-FORMS-LEDGER.md` tracked
the Maddie project only; the limen fleet had **no** such registry — the "portals each
attempting their own ideal" were tracked nowhere. This is that registry.

Each entry is liquid, not a checkbox (per the AVTOPOIESIS gate): it names the **ideal form**,
measures the **distance from ideal** at a moment in time, and carries a **status** and an
**owner**. The ledger includes *itself* (self-reference is required, not optional).

| Field | Meaning |
|-------|---------|
| **Ideal form** | the condition when this is fully alive |
| **Distance** | how far from it we are *right now*, with evidence |
| **Status** | OPEN · PARTIAL · BLOCKED(human) · SEEDED · CLOSED |
| **Owner** | who closes the remaining distance |

---

### IF-FIRST-DOLLAR — the revenue close
- **Ideal form:** an executable first-dollar predicate that is green only when a *real payment
  has cleared*; the Exporter faucet open.
- **Distance:** every revenue product is code-complete; **tx-hash = 0**. The Exporter
  (`a-i-chat--exporter/`) still carries a literal `TODO_KO_FI_SLUG` and a build-time placeholder
  store ID.
- **Status:** BLOCKED(human) — `L-REVENUE-ACCT` requires account creation/KYC Claude cannot do.
- **Owner:** Anthony (create Ko-fi + Lemon Squeezy, paste `LEMONSQUEEZY_STORE_ID`) → Claude (wire).

### IF-AMALGAMATION — the future tense closes
- **Ideal form:** the fleet amalgamates portals faster than it spawns them; a predicate measures
  open-PR + unmerged-branch debt and the merge daemon drives it *monotonically* down.
- **Distance:** 75 open PRs, 157 unmerged branches (2026-06-25); the daemon rebases stale-base
  PRs but `gen-*`/`FORCE-route` duplicates accrete faster than they merge. No debt-trend predicate.
- **Status:** PARTIAL — merge daemon live (`merge-policy.sh`); no monotonic-debt predicate yet.
- **Owner:** Claude (predicate) + merge daemon.

### IF-LIVE-TREE-COHERENCE — the live checkout never drifts
- **Ideal form:** the live daemon checkout is always `≡ origin/main`; capture/sync keeps it
  fast-forwarded; no ahead/behind divergence, no stranded local commits.
- **Distance:** live `main` is **ahead 6 / behind 24** with uncommitted daemon state
  (`tasks.yaml`, `state/`, `obligations-ledger.json`); 6 local commits novel by patch-id
  (one is `health-office` — needs a PHI scan before any push). Residue of the
  capture↔sync deadly-embrace.
- **Status:** OPEN.
- **Owner:** Claude + the sync organ.

### IF-SESSION-NON-CONTENTION — sessions don't sit in contended worktrees
- **Ideal form:** an interactive session's cwd is an isolated, non-recycled worktree; the fleet
  never rebases or `clean`s the tree a live session is working in.
- **Distance:** this session's cwd (`.claude/worktrees/stateful-dazzling-rainbow`) was checked
  out to a fleet PR branch (`fix/creds-hydrate-noninteractive-guard`, #276), rebased, and amended
  **by the daemon mid-session.**
- **Status:** OPEN.
- **Owner:** Claude (worktree allocation / harness convention).

### IF-SENSOR-REGISTRY — the beat sensors are declared data, all consumers derive
- **Ideal form:** the beat's continuous-runtime sensors live in one registry
  (`institutio/governance/sensors.yaml`, VIGILIA's third axis beside GATES + PARAMETERS); the beat loop
  and every consumer that reads a sensor gate **derive** from it; `check-sensors.py` holds it in parity.
  Adding a sensor is one registry entry, never a hand-wired shell block in three places.
- **Distance:** DONE for the beat. Phase 1 (#884) shipped the registry (now 20 sensors), `beat-sensors.py`
  (`--list`/`--run`), and `check-sensors.py` (pr-gate). Phase 2 landed the consumer flips: `metabolize.sh`
  **derives** its whole sensor loop from the registry — dark-first behind `LIMEN_BEAT_DERIVE` (#914,
  proven byte-equivalent by a 23-script test + an observed real-sensor run), then default-on with the 20
  hand-wired `── 0x ──` blocks deleted (#935, −227 lines). Two consumers that read sensor gates from the
  old shell location were repointed to the registry so they didn't go blind: `check-params.py`
  (`registry_referenced_tokens`, #935) and `armed-valve-audit.py` (`discover_registry_gates`, #938 —
  healing an ARMED 45→26 coverage regression). `check-sensors.py` D-parity now passes with **zero gate
  literals in the shell**, purely via derive-runner detection.
- **Deliberately NOT derived:** `omega.sh`. It is a *distinct* predicate (the autonomic fixed-point
  conjunction), not a beat-sensor consumer — it hardcodes 11 rungs, only 5 overlap the sensors, and it
  runs them with different flags (`--contract --offline`). It greps no shell gates, so the derive-flip
  didn't regress it. Forcing it to derive would couple two conceptually-separate predicates for a
  marginal DRY gain — out of scope by design, not an unfinished lane.
- **Status:** DONE (2026-07-10). The beat sensor estate is registry-owned; adding a sensor is one entry.
- **Follow-up (tracked, not blocking):** promote the three *domain-agnostic* predicates
  (`check-fork-safety.py`, `check-test-hygiene.py`, `check-main-green.py`) to the ecosystem layer
  (`organvm-engine/contextmd`, per `docs/agent-instruction-standard.md`) so the pattern becomes cross-repo
  law — dark-first, once proven in limen. The registry itself is limen-intrinsic and stays here.
- **Owner:** Claude + tabularius.

### IF-LEDGER-OF-IDEALS — this ledger (self)
- **Ideal form:** every Claude-originated ideal is a tracked named param here; the ledger is
  linked from memory and the autopoiesis heartbeat references it (closing the self-loop).
- **Distance:** created 2026-06-25; not yet wired into a verification/heartbeat lane.
- **Status:** SEEDED (this commit).
- **Owner:** Claude.
