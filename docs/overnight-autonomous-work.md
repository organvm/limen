# Overnight Autonomous Work

Generated: `2026-06-29T03:02:48Z`

## Goal

Harden this Limen trench for bounded overnight autonomous work by making the goal, launch prompt,
budget envelope, gates, and stop criteria explicit and verified from current receipts.

Current `/goal`:

> Harden the existing overnight autonomous-work preparation for the Limen main trench by making the
> goal, launch prompt, budget envelope, gates, and stop criteria explicit and verified from current
> receipts.

## Decision

Use a direct Codex-style autonomous work session, not live Limen dispatch.

Reason: `scripts/autonomy-governor.py explain` reports dispatch mode enabled, but the live heartbeat
substrate is still blocked. `docs/dispatch-health.md` reports `live-root-not-at-origin-main` and
`live-root-dirty`; `docs/live-root-gate.md` requires an operator gate before branch switches, resets,
task-board writes, launchd reloads, or async enablement.

## Budget Envelope

- Wall clock: stop after 8 hours or 4 completed tranches, whichever comes first.
- Tranche size: one-to-two-hour direct-session tranches.
- Live dispatch spend: 0. Do not run `limen dispatch --live`, `dispatch-async.py` without
  `--dry-run`, `dispatch-parallel.py`, or any command that reserves queue budget.
- Task board: 0 mutations. Do not edit `tasks.yaml` unless a new explicit operator packet opens
  that scope.
- Network/GitHub mutation: 0 writes. Read-only GitHub/status probes are allowed only through the
  existing verification scripts.
- Progress gate: stop after one tranche that cannot produce a preservation receipt, an explicit
  blocker receipt, or a refreshed `docs/conductor-tranche.md`.
- Failure gate: stop on the first unexpected owner dirty path, failed `diff --check`, failed
  `bash scripts/verify-whole.sh`, or live-root gate drift that would require operator action.

## Selected Packet

Use `docs/conductor-tranche.md` as the source of truth.

Packet: `tranche-owner-state-dirty-knowledge-corpus`

Purpose: Preserve `owner-state-dirty-knowledge-corpus` as scoped owner state for
`~/Workspace/knowledge-corpus` without rewriting corpus content or broadening into creative placement
work.

Allowed owner files:

- `~/Workspace/knowledge-corpus/00-THE-ONE.md`
- `~/Workspace/knowledge-corpus/reduced/narrative-as-computation.md`
- `~/Workspace/knowledge-corpus/reduced/substrate-backup-tier.md`

Allowed Limen receipt files:

- `docs/session-corpus-ledger.md`
- `docs/session-lifecycle-blockers.md`
- `docs/session-attack-paths.md`
- `docs/conductor-tranche.md`
- `.limen-private/session-corpus/inventory/session-corpus-ledger.json`
- `.limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json`
- `.limen-private/session-corpus/lifecycle/session-attack-paths.json`
- `.limen-private/session-corpus/lifecycle/conductor-tranche.json`

## Stop Conditions

Stop before:

- live dispatch, `tasks.yaml` mutation, launchd reload, branch switch, reset, or stash drop;
- plaintext secrets, credential hydration, GitHub App install, repo transfer, or rename;
- content rewriting, synthesis, deletion/revert of owner changes, or broad corpus convergence;
- owner repo push/PR unless a new explicit operator packet opens that scope;
- edits outside the allowed owner files and allowed Limen receipt files.

## Preflight

Run these first and stop on any unexpected owner scope:

```bash
git status --short --branch
git -C ~/Workspace/knowledge-corpus status --branch --short
git -C ~/Workspace/knowledge-corpus diff --name-status
git -C ~/Workspace/knowledge-corpus diff --check
python3 scripts/autonomy-governor.py explain
python3 scripts/dispatch-health.py --write --probe-async
python3 scripts/live-root-gate.py --write
```

Expected owner dirty set:

```text
M 00-THE-ONE.md
M reduced/narrative-as-computation.md
M reduced/substrate-backup-tier.md
```

Expected live-dispatch posture: dispatch governor may be enabled, but dispatch health remains blocked
until the live root gate is cleared by the operator.

## Work Loop

Work in one-to-two-hour tranches.

1. Inspect only the three allowed `knowledge-corpus` diffs.
2. Preserve the current owner state as either an owner-repo commit or a patch receipt.
3. Do not rewrite or improve the prose as part of preservation.
4. Refresh Limen receipts after preservation:

```bash
python3 scripts/session-corpus-ledger.py --write --all --materialize
python3 scripts/prompt-lifecycle-ledger.py --write --all
python3 scripts/session-blockers-ledger.py --write
python3 scripts/session-lifecycle-pressure.py --write
python3 scripts/session-attack-paths.py --write
python3 scripts/conductor-tranche.py --write
```

5. Verify:

```bash
git -C ~/Workspace/knowledge-corpus status --branch --short
git -C ~/Workspace/knowledge-corpus diff --name-status
git -C ~/Workspace/knowledge-corpus diff --check
bash scripts/verify-whole.sh
```

## Report Contract

The overnight session should report:

- the preservation method used: owner commit, patch receipt, or explicit blocker;
- exact changed paths;
- verification commands and results;
- whether `owner-state-dirty-knowledge-corpus` cleared from `docs/session-lifecycle-blockers.md`;
- the next `docs/conductor-tranche.md` packet after refresh.

If the selected packet cannot be completed, record the blocker in the report and stop. Do not fall
through into queue dispatch, credential work, live root repair, or creative corpus synthesis.

## Launch Prompt

Use this prompt to start the overnight session:

```text
Continue from docs/overnight-autonomous-work.md in /Users/4jp/Workspace/limen-main-trench-20260628.

Objective: execute the selected packet, tranche-owner-state-dirty-knowledge-corpus, as a bounded
direct Codex session. Preserve the three dirty files in ~/Workspace/knowledge-corpus as owner state.
Do not rewrite corpus content, delete/revert owner changes, push, open a PR, mutate tasks.yaml,
launch live dispatch, change launchd, repair credentials, or touch files outside the allowed scope.

First run the Preflight section. Stop if the owner dirty set differs from the expected three files,
if dispatch/live-root gates require operator action, or if diff hygiene fails. Work in one-to-two-hour
tranches with zero live-dispatch spend. After preservation, refresh the listed Limen receipts, run
the Verify section, and report the preservation method, changed paths, verification results, whether
owner-state-dirty-knowledge-corpus cleared, and the next conductor tranche.
```

## Morning Check

Run these after the overnight session completes:

```bash
git status --short --branch
git -C ~/Workspace/knowledge-corpus status --branch --short
sed -n '1,180p' docs/session-lifecycle-blockers.md
sed -n '1,180p' docs/conductor-tranche.md
bash scripts/verify-whole.sh
```
