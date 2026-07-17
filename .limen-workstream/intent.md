# Continuation Capsule: Truth-First Governance Recovery

## Objective

Complete and verify the existing seven-owner governance-memory stack without creating another
repository or authority layer. One frozen snapshot must traverse
`discover → snapshot → parse → classify → reconcile → distill → validate → render → receipt`,
then traverse again with zero emitted events, zero changed bytes, and no replayed completed child.

## Authority and prohibitions

- CORPVS owns constitutional ratification; Engine compiles; Ontologia owns reviewed lineage and
  node self-images; session-meta owns custody; CCE owns provider-neutral normalization; Limen owns
  orchestration, strict readiness, and the aggregate receipt.
- Raw bodies, private paths, and full custody hashes remain under the private Archive4T root.
  Public projections contain redacted identities and typed receipts only.
- Preserve operator intent separately from assistant or transport echoes. The July formulation
  controls; March ancestry remains immutable.
- Do not touch dirty live roots or `tasks.yaml`. Work only in the named isolated worktrees.
- Do not mutate billing, credentials, browser state, or personal data. Do not merge or undraft any
  PR while exact-head runner proof is unavailable.
- Do not retire legacy CCE importers in this lane.

## Final execution

First verify that every owner worktree is clean and exactly matches the head in `evidence.md` (with
the post-capsule Limen head derived live). Verify that `final-truth-first.v1.yaml` binds those exact
heads and that no other cadence process is active. Then run:

```bash
python3 scripts/governance-memory-cadence.py \
  --snapshot-id "$LIMEN_GOV_SNAPSHOT_ID" \
  --snapshot-at "$LIMEN_GOV_SNAPSHOT_AT" \
  --config "$LIMEN_GOV_CONFIG" \
  --run-root "$LIMEN_GOV_RUN_ROOT/$LIMEN_GOV_SNAPSHOT_ID" \
  --write
```

Repeat that exact command once after it succeeds to seal the separate post-proof observation.
Finally run it once with `--strict --write`. Strict mode is expected to fail while the owner-routed
source and ideal-form debt recorded in `evidence.md` remains; a nonzero strict exit is correct
fail-closed behavior, not permission to rewrite readiness.

## Finish line

- Nine ordered typed stage receipts and one aggregate cadence receipt bind the exact snapshot and
  owner revisions.
- Traversal two reports `new_event_count=0`, `changed_byte_count=0`,
  `replayed_completed_children=0`, and an output digest identical to traversal one.
- The separate observation seals the final snapshot bundle and post-proof receipt without changing
  bytes.
- Every repository passes its scoped local predicate. Remote checks are recorded as executed green
  or as the exact runner-allocation billing blocker; neither state is misrepresented.
- All seven PR bodies state current truth and remain draft. Merge remains a later authorized action
  in dependency order.
- If any gate remains, this capsule and its launch command are the durable resume surface.
