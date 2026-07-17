# Governance Receipt Cadence Owner

The Limen `receipt` owner is the final bounded owner in the governance-memory cadence. It consumes
direct outputs from custody, normalization, reconciliation, distillation, validation, and Atlas
rendering. It does not search the workspace, infer source families, ratify a candidate testament, or
manufacture stage/cadence receipts.

Its only governed output is `governance-snapshot-bundle-pre-proof.v1`. The document carries the full
normalized-event, source-envelope, and assertion-evidence sets plus compact, schema-shaped references
for the remaining final-bundle fields. Stage receipts, cadence receipts, post-proof observation,
final readiness, timestamps, and the final bundle digest remain reserved for the Limen orchestrator.

## Owner and predicate commands

Configure the `receipt` stage owner command with every direct input:

```bash
python3 scripts/governance-receipt-owner.py \
  --source-census "$SOURCE_CENSUS" \
  --normalized-events "$NORMALIZED_EVENTS" \
  --source-envelopes "$SOURCE_ENVELOPES" \
  --assertion-evidence "$ASSERTION_EVIDENCE" \
  --lineage-graph "$LINEAGE_GRAPH" \
  --governance-testament "$GOVERNANCE_TESTAMENT" \
  --coverage "$COVERAGE_RECEIPT" \
  --ideal-form-register "$IDEAL_FORM_REGISTER" \
  --node-self-image-set "$NODE_SELF_IMAGE_SET" \
  --iceberg-atlas "$ICEBERG_ATLAS" \
  --normalization-parity-receipt "$NORMALIZATION_PARITY_RECEIPT" \
  --governance-atlas-receipt "$GOVERNANCE_ATLAS_RECEIPT" \
  --render-projection "$RENDER_PROJECTION" \
  --snapshot-digest "$LIMEN_GOV_SNAPSHOT_DIGEST" \
  --cadence-id "$LIMEN_GOV_CADENCE_ID" \
  --output "$LIMEN_GOV_RUN_ROOT/artifacts/governance-snapshot-bundle-pre-proof.v1.json"
```

The independently revision-pinned predicate uses the same arguments:

```bash
python3 scripts/governance-receipt-predicate.py \
  ...the same direct inputs, snapshot digest, cadence ID, and output...
```

Pin the owner and predicate revisions independently to the exact clean Limen Git
head in cadence configuration. The predicate imports only the pure contract
derivations in `scripts/governance_receipt_contract.py`; it never imports the
mutating owner and never writes output or metrics.

Limen injects `LIMEN_GOV_STAGE`, `LIMEN_GOV_STAGE_ATTEMPT`, `LIMEN_GOV_TRAVERSAL`,
`LIMEN_GOV_PROOF_MODE`, `LIMEN_GOV_STAGE_METRICS_OUT`, `LIMEN_GOV_STAGE_RECEIPTS`,
`LIMEN_GOV_PREDECESSOR_RECEIPT_DIGEST`, `LIMEN_GOV_PRIOR_STAGE_RECEIPT`,
`LIMEN_GOV_MAX_ITEMS`, `LIMEN_GOV_SNAPSHOT_ID`, `LIMEN_GOV_SNAPSHOT_AT`, and
`LIMEN_GOV_RUN_ROOT`. Missing or contradictory runtime bindings fail closed.

## Truth and boundedness

Every snapshot-bearing input must bind the exact runtime snapshot ID, digest, and timestamp where
the contract carries them. Embedded census, coverage, ideal, self-image, parity, Atlas, Atlas
receipt, and render-projection digests are recomputed with RFC 8785. The receipt owner also verifies
the complete census-to-promotion crosswalk, event-to-source-envelope resolution, coverage
classification counts, exactly one self-image per registered node, two populated timelines, six
populated zoom levels, and the Atlas receipt's bindings to its inputs.

`LIMEN_GOV_MAX_ITEMS` bounds the full direct denominator: census raw units, events, source
envelopes, assertions, lineage nodes and edges, ideal forms, self-images, promotions, timeline lanes,
and zoom levels. It does not merely count the one output file.

Readiness is re-derived and unioned from every owner:

- coverage and normalization parity;
- assertion verification and distinct citation evidence;
- candidate or ratified testament state and constitutional authority;
- ideal forms and exact-one self-images;
- Atlas coverage, citations, timelines, and zooms;
- the Atlas receipt and render predecessor projection.

A candidate testament always contributes a missing ratification requirement and can never produce
global `ready`. A blocked, quarantined, incomplete, stale, disputed, or owner-routed input remains
typed debt. `closed_with_owner_routed_debt` is preserved as owner evidence but never aliases
`ready`.

## Fixed-point proof

Traversal one writes the canonical pre-proof document and one metrics child with RFC 8785
input/output digests. Metrics contain only the stable child ID and digests—never local paths, source
bodies, or source-family literals.

Proof traversal recomputes the entire result in memory, requires the governed output bytes to be
exact, and binds the prior completed child receipt. It reports `skipped_completed`, zero emitted
events, and the RFC 8785 prior-child digest. It does not write the governed output. Any changed
direct input, predecessor digest, prior receipt, or output byte fails without repairing the
evidence.
