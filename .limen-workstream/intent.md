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
- Raw bodies, private paths, and full custody hashes retain their existing Archive4T custody.
  New cadence intermediates run only below the Domus-attested non-backed Scratch root; only the
  four verified final receipts promote to Archive4T. Public projections contain redacted
  identities and typed receipts only.
- Preserve operator intent separately from assistant or transport echoes. The July formulation
  controls; March ancestry remains immutable.
- Do not touch dirty live roots or `tasks.yaml`. Work only in the named isolated worktrees.
- Do not mutate billing, credentials, browser state, or personal data. GitHub is operational;
  preserve zero-step hosted-runner results as verifier debt without treating them as a campaign
  gate. Merge authority remains with the declared repository owner.
- Do not retire legacy CCE importers in this lane.

## Final execution

First verify that every owner worktree is clean and exactly matches the head in `evidence.md` (with
the post-capsule Limen head derived live). Preserve `final-truth-first.v1.yaml` and all existing
Archive4T runs as historical evidence; create a superseding config whose stage attempts are one,
whose aggregate byte ceiling is declared, and whose Scratch and final-promotion authorities bind
live receipts. Verify no other cadence process is active. Then run:

```bash
python3 scripts/governance-memory-cadence.py \
  --snapshot-id "$LIMEN_GOV_SNAPSHOT_ID" \
  --snapshot-at "$LIMEN_GOV_SNAPSHOT_AT" \
  --config "$LIMEN_GOV_CONFIG" \
  --run-root "$LIMEN_GOV_RUN_ROOT/$LIMEN_GOV_SNAPSHOT_ID" \
  --write
```

If this full attempt fails, do not repeat it until the exact failed-stage repair receipt exists.
After a successful full attempt, repeat the exact command once with `--strict --write` to seal the
separate post-proof observation and promote the four final receipts. Strict mode remains nonzero
while owner-routed source or ideal-form debt in `evidence.md` remains; that is correct fail-closed
readiness, not another full-attempt failure and not permission to rewrite the evidence.

## Finish line

- Nine ordered typed stage receipts and one aggregate cadence receipt bind the exact snapshot and
  owner revisions.
- Traversal two reports `new_event_count=0`, `changed_byte_count=0`,
  `replayed_completed_children=0`, and an output digest identical to traversal one.
- The separate observation seals the final snapshot bundle and post-proof receipt without changing
  bytes.
- Scratch output remains under the declared aggregate ceiling; Archive4T contains byte-identical
  copies of only the four allowlisted final receipts.
- Every repository passes its scoped local predicate. A zero-step hosted-runner result is recorded
  narrowly as unexecuted verifier evidence, never as a GitHub or campaign block.
- All seven PR bodies state current truth, owner, predicate, and dependency-derived merge condition.
- If any gate remains, this capsule and its launch command are the durable resume surface.
