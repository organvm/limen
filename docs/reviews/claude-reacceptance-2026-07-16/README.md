# Shared-Keeper Reacceptance Ledger

This directory is the redacted, durable index for the workstream that began at
`2026-07-12T15:37:35Z`. It covers exactly 29 top-level Claude sessions, 11 Claude workflows, and
the conservatively attributable 65-PR GitHub cohort. The provider name describes execution
provenance only; every canonical agent remains a co-equal keeper of the work and its receipts.

The ledger is intentionally fail-closed. A row remains `repair_required` until its source ask,
spend, exact output, side effects, current review findings, executable predicate, and durable
receipt are reconciled. Green CI alone is not acceptance. Raw prompts, private paths, personal
records, and full private hashes remain in the private prompt-corpus owner.

Files:

- `scope.json` freezes the historical denominator and attribution boundary.
- `ledger.json` is the generated redacted snapshot. It contains one row per session, workflow,
  and PR.
- `external-actions.md` inventories already-observed outward actions without repeating them.
- `privacy-containment.md` records the temporary repository restriction without reproducing the
  disclosed material.
- `incidents.md` records recovery-process boundary violations and their bounded remediation.
- `predicates.md` defines the release and per-row acceptance rules.
- `continuation.md` is the portable successor capsule: live probes, authority boundaries,
  predicates, ownership rules, and the copy/paste resume command.

Refresh is explicit and two-step:

```bash
python3 scripts/reacceptance-ledger.py --refresh > /tmp/reacceptance-ledger.json
python3 scripts/reacceptance-ledger.py --check /tmp/reacceptance-ledger.json
```

Refresh starts from the tracked ledger by default (or an explicit `--previous` path), joins rows by
their frozen stable IDs, and preserves adjudicated fields while replacing remote snapshot fields.
It refuses terminal or verified evidence when a PR head has changed, refuses a concurrent overwrite
when the destination changed after the prior read, and fails closed when either the review-thread or
nested-comment GraphQL connection is paginated. It never silently treats the first page as complete.

Writing the tracked snapshot requires `--refresh --write`; the default and `--check` paths perform no
writes. `release_ready` is derived rather than asserted. The containment boundary stays in force
until every row has valid terminal evidence, P1/P2/unclassified current debt is zero, every campaign
completion gate has a verified predicate and durable receipt, exact-head review acceptance passes,
and the session-value predicate passes.
