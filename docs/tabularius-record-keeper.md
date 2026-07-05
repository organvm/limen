# TABVLARIVS — the one record-keeper over the board

> *The Roman* tabularius *kept the* tabulae publicae *— the single authoritative civic ledger. This
> organ keeps `tasks.yaml`: the one process allowed to edit the holy board, so the ~32 uncoordinated
> writers stop tearing it.* Sibling of MONETA (intakes cash), quaestor (finds money), CVSTOS (keeps
> the host), VVLTVS (keeps the face). **TABVLARIVS keeps the books.**

## The disease

`tasks.yaml` is the single SSOT board. Today **~32 code paths** across 5 tiers (CLI core, ~20
scripts, 7 FastAPI endpoints, 4 Cloudflare-Worker endpoints, 3 MCP handlers) each mutate it by
*read-whole-board → mutate-in-memory → rewrite-whole-board*. A `queue_lock` mutex exists but only
~13 of them honor it; the MCP server bypasses even the atomic write.

Two failure modes follow, and they are distinct:

- **Torn bytes** — a non-atomic writer (MCP's raw `open(w)+yaml.dump`) can leave a truncated/partial
  file. `io.atomic_write_text` (temp + `os.replace`) already prevents this *for writers that use it*.
- **Lost updates (clobber)** — two writers that both `load→mutate→save`, even under a save-only lock,
  race: the second's whole-board rewrite overwrites the first's just-committed change (last-writer-
  wins). Locking the `save` alone does **not** fix this — only serializing the whole
  read-modify-write does. Once collapsed 1449 tasks → 1 (the 2026-06-26 halt).

This is the "it's been messing up things a lot" the record-keeper dissolves.

## The cure: the single-writer principle

Workers stop mutating shared state. They **append one immutable ticket per unit of work** to a
lock-free inbox and hand it off. Exactly **one** keeper — TABVLARIVS — drains the inbox, folds the
tickets onto the board in order, validates, and seals. Because it is the *only* process doing
read-modify-write, there is no interleave to tear and no update to lose.

This is not new infrastructure. It is **Step 2+3 of `board-is-event-log-projection`** (memory;
PR #543): `materialize.fold` is the already-proven pure reducer (`board = fold(events)`); TABVLARIVS
gives it a live stream to consume. A ticket **is** a `materialize` Event with provenance, and the
archived ticket files are the append-only event log the board projects from.

```
   worker ──submit_ticket()──▶  logs/tickets/inbox/<id>.json   (atomic exclusive create; no lock, no board read)
                                          │
                     TABVLARIVS (each beat, sole queue-lock holder)
                                          │  drain → fold onto healed board → validate → collapse-guarded seal
                                          ▼
   logs/tickets/archive/  ◀── applied     tasks.yaml (the committed projection)
   logs/tickets/rejected/ ◀── quarantined (+ <id>.reason.txt)
```

### Components (shipped)

| Piece | Where | Role |
|-------|-------|------|
| Engine | `cli/src/limen/tabularius.py` | `Ticket`, `submit_ticket()`, `submit_task_upsert()`, `drain_once()`, the fold/validate/seal + quarantine |
| Producer API | `cli/src/limen/tabularius.py` → `submit_task_upsert()` | the one-line conversion target: a writer swaps `save_limen_file` for this call per NEW task (validates up front, then hands the keeper an upsert ticket; supports optional stale-read guards for id allocators) |
| Status API | `cli/src/limen/tabularius.py` → `submit_task_status()` | the one-line conversion target for existing-task lifecycle transitions: status + dispatch_log + optional field patch as one keeper-owned ticket |
| Beat organ | `scripts/tabularius-organ.py` | thin per-beat wrapper (like `heal-board.py`); `--check`/`--dry-run`; writes the liveness stamp |
| Beat wiring | `scripts/heartbeat-loop.sh` | runs after `heal-board` (fold onto a *healthy* board), before the body's own mutation |
| Proprioception | `scripts/organ-health.py` | a TABVLARIVS rung, green when `logs/tabularius-organ-state.json` is fresh |
| Keeper gate | `institutio/governance/parameters.yaml` → `LIMEN_TABVLARIVS` | master kill-switch for the keeper (default ON) |
| Cutover gate | `institutio/governance/parameters.yaml` → `LIMEN_TICKETS_PRODUCE` | flips converted writers from direct-write to producer (default **OFF** — a merge changes nothing live; the flip is the deliberate, revertible cutover) |
| Tests | `cli/tests/test_tabularius.py` | 13 tests: end-to-end submit→drain, ordering, quarantine, lock-deferral, collapse-guard, **and the producer≡direct-write identity invariant** |

### Safety invariants (each inherited from a shipped precedent)

- **A worker never touches `tasks.yaml`** — `submit_ticket` is an exclusive atomic create (`os.link`).
  No read, no lock, no collapse risk. Preserves the one writer the fleet must never starve
  (`ingest-backlog.py`, which deliberately skipped the lock — tickets are exactly its mechanism).
- **One bad ticket never rejects the batch** — each ticket is applied + validated individually; a bad
  one is quarantined and the rest still land (the `_sanitize_dispatch_logs` tolerate-and-salvage law).
- **The seal is collapse-guarded** — the board is written through `save_limen_file`, so a batch that
  would shrink it is rejected whole and the good board is left intact.
- **Never dead-stop the beat** — if the queue lock is held (a legacy writer mid-migration), the keeper
  defers to the next beat rather than blocking (exactly `heal-board`'s stance).
- **Idempotent no-op while dark** — an empty inbox touches nothing (no lock, no board I/O), which is
  what makes it safe to run every beat before any producer exists.

## Migration path

`tasks.yaml` is a deploy-trigger path, so every step is additive and reversible until a final flip.

- **Step 1 — SHIPPED (this PR).** The keeper exists and runs every beat. No writer behavior changes,
  so with no producers yet it is a proven no-op. The office is manned; no clerks hand it tickets yet.
- **Step 2 — convert writers to producers, one tier at a time (reversible per tier).**
  Each conversion is behind `LIMEN_TICKETS_PRODUCE` (default OFF), so it merges as a no-op and the
  cutover is a deliberate flip. The parity is *proven*, not assumed: `test_producer_path_matches_
  legacy_direct_write` shows a converted writer produces a board identical to the legacy direct write
  (same tasks, same fields, same order) save for the keeper's added `updated` provenance stamp — so
  every remaining conversion is a mechanical edit against a known-safe template, not surgery.
  1. **Scripts first** (lowest blast radius). **Reference pair converted** (`mine-backlog`,
     `ingest-backlog` — the latter a natural fit, it wanted lock-free): each now calls
     `submit_task_upsert` per new task when `LIMEN_TICKETS_PRODUCE=1`, keeping its read-only dedup so
     it only ever emits brand-new ids. The rest (`generate-backlog`, `generate-revenue-backlog`,
     `generate-organ-backlog`, `generate-positioning`, `discover-value`, `ingest-coverage`) are the
     same one-line swap against the proven template.
  2. **CLI harvest/dispatch result-apply** → emit a ticket instead of mutating the blob.
  3. **MCP server** — replace the raw `yaml.dump` + git-push with a ticket append (removes the worst
     offender: no lock, no atomic write, no collapse-guard, and its own drifted duplicate models).
  4. **FastAPI + Worker endpoints** — enqueue a ticket and return; the keeper projects. This is the
     **website-sensitive** tier — requires green CI + a `web/app` build, and the decision below.
- **Step 3 — flip the source of truth.** Once every writer produces tickets and `materialize --verify`
  proves N consecutive beats of byte-identity, declare the archived event log the truth and
  `tasks.yaml` the derived cache. `heal-board`'s restore-from-HEAD stays as the outer safety net.

## The one genuine human decision (surfaces at Step 2.4, not before)

Routing the **live Cloudflare Worker / FastAPI** through the keeper makes their writes *eventually
consistent* — an API `POST` that used to write synchronously would return before the next beat folds
its ticket. **Decision:** is a bounded async delay acceptable for the live API contract, or must the
API keep a synchronous write path that *also* emits a ticket for reconciliation?
**Recommended default:** synchronous-write-plus-ticket for the live API tier (no contract change),
pure-ticket for the internal fleet. This is the only step gated by the website guardrail; everything
above it is autonomous.

## Recorded remaining work (this doc is the owner)

- [x] Step 2.1 (pattern proven) — `submit_task_upsert` producer API + `LIMEN_TICKETS_PRODUCE` gate +
      the producer≡direct-write identity test; reference pair `mine-backlog` + `ingest-backlog` converted.
- [x] Step 2.1 (creation tier converted + **CUTOVER LIVE**) — the whole task-CREATION tier now
      produces tickets: `generate-backlog`, `generate-revenue-backlog`, `generate-organ-backlog`,
      `discover-value` converted (behind the same gate). `scripts/auto-scale.py` submits guarded
      upsert tickets and drains synchronously through TABVLARIVS, preserving the CI `tasks.yaml` commit
      contract while preventing stale sequential-id clobber. `scripts/self-heal.py` submits guarded
      upsert tickets for stable `HEAL-*` repair tasks and drains synchronously in ticket mode.
      `scripts/converge-organ.py` does the same for bounded `CONV-*` gap tasks, and
      `scripts/corpus-converge.py` does the same for bounded `CORP-*` corpus-gap tasks.
      `scripts/current-session-fanout.py` does the same for deterministic current-session seed
      tasks. `scripts/insight-route.py` submits guarded `TASK-<insight-id>` upsert tickets and drains
      them synchronously in ticket mode. Reading the code corrected the remainder list:
      `generate-positioning` and `ingest-coverage` **never write `tasks.yaml`** (obligations / read-only) —
      not writers, so not converted. **`scripts/heartbeat-loop.sh` sets `LIMEN_TICKETS_PRODUCE=1`**, so the
      LIVE fleet routes task creation through the keeper (revertible via `~/.limen.env`). Smoke-proven:
      a real `generate-backlog` run submitted 5 tickets, left the board untouched, and the keeper folded
      them (2→7). The status-mutator tier is now Step 2.2-complete; the remaining conversion surfaces
      are MCP/API and the event-log SSOT flip.
- [x] Step 2.2 — the STATUS-mutator tier (`route`, `dispatch-async`, `heal-dispatch`, `rebalance`,
      `recover`, `quicken`) → emit an INTENT_STATUS ticket instead of a direct RMW (NOT an upsert — an
      upsert of a live id merge-clobbers; these change existing tasks). The
      `submit_task_status()` producer API is shipped and parity-tested, `scripts/recover.py --apply`
      submits and drains guarded status-repair tickets through TABVLARIVS, and the Jules harvest path submits
      completion/failure tickets instead of saving the board directly. `scripts/heal-dispatch.py --apply`
      submits and drains guarded lifecycle-repair tickets through TABVLARIVS. `scripts/rebalance.py` submits guarded
      target-agent tickets through TABVLARIVS and drains them on every `--apply`. `scripts/route.py`
      submits guarded target-agent and workstream tickets in ticket mode. `scripts/quicken.py`
      submits human-residue upsert/refresh tickets in ticket mode. `scripts/dispatch-async.py` submits guarded reserve/reap/harvest
      tickets in ticket mode and drains the keeper before launching workers or clearing markers.
      CLI dispatch result-apply submits result tickets in ticket mode. `scripts/claim-task.py`
      submits and drains a guarded claim ticket for live manual claims.
      `scripts/reclassify-needs-human.py --apply` submits and drains guarded reopen tickets instead
      of directly rewriting false human-gate records. `scripts/jules-land.py --apply` is
      TABVLARIVS-only: it submits and drains guarded completion tickets after a Jules session lands
      as a PR. `scripts/self-improve.py --apply` submits and drains guarded priority/status re-plan
      tickets through TABVLARIVS.
      `limen release-stale --apply` submits and drains guarded stale-claim release/restore tickets.
      Parallel dispatch result-commit submits and drains the same result tickets as serial dispatch.
      Serial dispatch budget-window resets submit and drain board-meta tickets in ticket mode.
      Parallel dispatch reservations submit guarded status tickets and drain them before agent runs.
      Jules harvest submits completion/failure tickets and drains them before returning.
      `generate-backlog --apply` submits upsert tickets and drains them before returning.
      `generate-revenue-backlog --apply` submits upsert tickets and drains them before returning.
      Legacy `scripts/append-tasks.py` submits and drains guarded upsert tickets instead of
      rewriting `tasks.yaml` directly.
      Post-transfer `scripts/rewrite-owners.py --apply` submits and drains guarded repo-owner
      rewrite tickets instead of rewriting `tasks.yaml` directly.
- [x] Step 2.3 — MCP server → ticket producer. `mcp/src/limen_mcp/server.py` now loads through
      the shared Limen loader and its mutating tools (`add_task`, `update_task_status`,
      `agent_claim`) submit TABVLARIVS upsert/status tickets, drain the keeper synchronously, and
      no longer run the old YAML rewrite + git stash/pull/push path.
- [x] Step 2.4 — live API/Worker tier. Local file-backed FastAPI mutation endpoints now submit
      and synchronously drain TABVLARIVS tickets before responding; GitHub-backed FastAPI mutations
      and Cloudflare Worker mutation routes reject until a remote TABVLARIVS ticket sink exists,
      while read and dry-run surfaces stay live.
- [x] Step 2 guardrail — `scripts/check-tabularius-writers.py` audits the codebase for direct
      task-board writers. It is wired into `scripts/verify-whole.sh` and blocks any new unapproved
      `tasks.yaml` writer; remaining reversible legacy fallbacks must stay explicitly allowlisted
      and carry `LIMEN_TICKETS_PRODUCE` plus TABVLARIVS producer proof. The whole-repo gate pins
      the legacy fallback ceiling at 15, so the count can be ratcheted down but not silently grow.
      `scripts/discover-value.py --apply` is now TABVLARIVS-only: it submits and drains upsert
      tickets instead of retaining a legacy direct append fallback. `scripts/rebalance.py --apply`
      is now TABVLARIVS-only: it submits and drains guarded target-agent status tickets instead of
      retaining a legacy direct rewrite fallback. `scripts/recover.py --apply` is now TABVLARIVS-only:
      it submits and drains guarded failed/orphan/done-repair status tickets instead of retaining a
      legacy direct repair fallback. `scripts/jules-land.py --apply` is now TABVLARIVS-only: it
      submits and drains guarded completion tickets instead of retaining a legacy direct done-marking
      fallback. `scripts/heal-dispatch.py --apply` is now TABVLARIVS-only: it submits and drains
      guarded lifecycle-repair tickets while holding the queue lock instead of retaining a legacy
      direct repair fallback. `scripts/self-improve.py --apply` is now TABVLARIVS-only: it submits
      and drains guarded priority/status re-plan tickets instead of retaining a legacy direct
      re-plan fallback. `scripts/auto-scale.py` is now TABVLARIVS-only: it submits and drains
      guarded task upsert tickets instead of retaining a legacy direct append fallback.
- [ ] Step 3 — flip SSOT to the event log; add an archive→`events.jsonl` compactor + a standing
      `fold(archive) == board` predicate.
      Seed landed: `limen tabularius-events --write --verify` writes
      `logs/tickets/events.jsonl` as a compacted projection seed plus
      `logs/tickets/events.jsonl.manifest.json` as the archive watermark. Verification now proves
      both `materialize.fold(events.jsonl) == tasks.yaml` for a fresh seed and
      `fold(seed + archived tickets after watermark) == tasks.yaml` after later keeper drains;
      `limen tabularius-events --sync-archive --verify` appends those post-watermark archive deltas
      into `events.jsonl` and advances the manifest; `scripts/verify-whole.sh` runs the same
      predicate against a temp event-log path to avoid repo drift.

See also: `board-is-event-log-projection` (memory), `cli/src/limen/materialize.py`,
`scripts/heal-board.py`, `io.py` (`queue_lock`, `save_limen_file`, the collapse-guard).
