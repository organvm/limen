# Seven-Agent Whole-Estate Session Review

This directory contains the reproducible, redacted source for the frozen
2026-07-19 whole-estate review of Codex, Claude, Agy, OpenCode, Gemini,
Copilot, and Jules.

## Delivery status

The existing owner-only Sites version 1 is a private historical receipt. Its
analytical conclusions are provisional and must not be cited. The corrected
version 2 will replace it only after exact prompt authority, exhaustive owner
links, byte-identical shadow runs, default-branch custody, and owner-only
access verification all pass. Until then, the current `snapshot.json`,
`artifact.json`, and `validation.json` are likewise superseded provisional
outputs rather than decision evidence.

The two half-open windows overlap and are never added:

- completed calendar week: `2026-07-06T04:00:00Z` through
  `2026-07-13T04:00:00Z`;
- latest seven days: `2026-07-12T15:11:00Z` through the frozen snapshot at
  `2026-07-19T15:11:00Z`.

## Reproduction

From the repository root:

```bash
python3 -m unittest -v \
  docs/reviews/seven-agent-whole-estate-2026-07-19/test_model.py
PYTHONPATH=cli/src python3 -m limen.estate_review \
  --snapshot-at 2026-07-19T15:11:00Z --write
PYTHONPATH=cli/src python3 -m limen.estate_review \
  --snapshot-at 2026-07-19T15:11:00Z --check
```

The equivalent installed CLI is `limen estate-review`. Collection reads the
native provider stores and only the digest-bound prompt chunks intersecting the
frozen windows, without mutating them. Collection also requires the authority
seal to be digest-valid, authority-ready, and bound to that exact manifest. It
rejects the legacy monolithic prompt projection by default;
`--legacy-full-prompt-projection` exists only for an
explicit compatibility run and is not an accepted corrected-report path.
Board rows are evidence only when they carry exact `source_atom_ids`; they are
never reconstructed into asks. Reconciliation dynamically enumerates GitVS
owners, resolves repository transfers, and classifies timestamped exact-head
GitHub receipts at the frozen snapshot. A second `--check` build is
side-effect-free and must be byte-identical.

The dated `collect.py`, `reconcile.py`, `build_report.py`, and `model.py` files
are compatibility entrypoints. Product code lives in
`cli/src/limen/estate_review`; this directory remains the frozen output owner.

## Files

- `model.py` — pure time, token, receipt, and outcome rules.
- `test_model.py` — boundary, token-delta, concurrency, lineage, redirect,
  receipt, late-write, and deduplication tests.
- `collect.py` — compatibility entrypoint for canonical native-store collection.
- `reconcile.py` — live estate census and exact remote receipt reconciliation.
- `build_report.py` — compatibility entrypoint for the canonical report build.
- `snapshot.json` — public-safe frozen analytical snapshot.
- `artifact.json` — canonical self-contained report manifest and bounded data.
- `validation.json` — reconciliation, test, validator, and hosting receipts.
- `../../estate-session-review-seal.json` — partial-source readiness,
  coverage, owner-reconciliation, freshness, and output hashes.

Raw prompts, secrets, machine-local paths, private receipt URLs, and full
commit hashes are excluded. Unknown duration and token meters remain unknown
rather than being rendered as zero.
