# Governance Memory Readiness

> Limen is the bounded scheduler and redacted read model. Constitutional, custody, lineage, and compiler owners remain authoritative for their own receipts.

- Status: `blocked`
- Snapshot: `not-coherent`
- Receipt: `sha256:d90c5beb43abc7a0a6b7006eb80181d897fbf507a10dadf20a87b5b1fe4cc4b0`
- Exact classification: `False` (0 / None)
- Operationally ready: `False`
- Visible residuals: `15`

## Owner Inputs

| Input | Contract | State | Snapshot |
|---|---|---|---|
| `schema_catalog` | `public-governance-memory-schema-catalog` | `missing-configuration` | `—` |
| `source_census` | `source-census.v1` | `missing-configuration` | `—` |
| `snapshot_bundle` | `governance-snapshot-bundle.v1` | `missing-configuration` | `—` |
| `source_envelopes` | `source-envelope.v1` | `missing-configuration` | `—` |
| `normalized_events` | `normalized-event.v1` | `missing-configuration` | `—` |
| `normalization_parity` | `normalization-parity-receipt.v1` | `missing-configuration` | `—` |
| `lineage_graph` | `lineage-graph.v1` | `missing-configuration` | `—` |
| `governance_testament` | `governance-testament.v1` | `missing-configuration` | `—` |
| `assertion_evidence` | `assertion-evidence.v1` | `missing-configuration` | `—` |
| `coverage_receipt` | `coverage-receipt.v1` | `missing-configuration` | `—` |
| `ideal_forms` | `ideal-form-register.v1` | `missing-configuration` | `—` |
| `iceberg_atlas` | `iceberg-atlas.v1` | `missing-configuration` | `—` |
| `self_images` | `node-self-image-set.v1` | `missing-configuration` | `—` |
| `cadence_receipt` | `governance-cadence-receipt.v1` | `missing-configuration` | `—` |
| `atlas_receipt` | `governance-atlas-receipt.v1` | `missing-configuration` | `—` |

## Iceberg Atlas Projection

- Operator-intent events: `0`
- Artifact events: `0`
- Ideal forms: `0`
- Node self-images: `0`

## Bounded Cadence

`discover → snapshot → parse → classify → reconcile → distill → validate → render → receipt`

## Owner Blockers

- `owner-receipt:assertion_evidence:missing-configuration` — owner `parameter-contract:LIMEN_GOV_ASSERTION_EVIDENCE`; predicate `assertion-evidence.v1 input state is missing-configuration`; next: `LIMEN_GOV_ASSERTION_EVIDENCE="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:atlas_receipt:missing-configuration` — owner `parameter-contract:LIMEN_GOV_ATLAS_RECEIPT`; predicate `governance-atlas-receipt.v1 input state is missing-configuration`; next: `LIMEN_GOV_ATLAS_RECEIPT="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:cadence_receipt:missing-configuration` — owner `parameter-contract:LIMEN_GOV_CADENCE_RECEIPT`; predicate `governance-cadence-receipt.v1 input state is missing-configuration`; next: `LIMEN_GOV_CADENCE_RECEIPT="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:coverage_receipt:missing-configuration` — owner `parameter-contract:LIMEN_GOV_COVERAGE_RECEIPT`; predicate `coverage-receipt.v1 input state is missing-configuration`; next: `LIMEN_GOV_COVERAGE_RECEIPT="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:governance_testament:missing-configuration` — owner `parameter-contract:LIMEN_GOV_TESTAMENT`; predicate `governance-testament.v1 input state is missing-configuration`; next: `LIMEN_GOV_TESTAMENT="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:iceberg_atlas:missing-configuration` — owner `parameter-contract:LIMEN_GOV_ICEBERG_ATLAS`; predicate `iceberg-atlas.v1 input state is missing-configuration`; next: `LIMEN_GOV_ICEBERG_ATLAS="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:ideal_forms:missing-configuration` — owner `parameter-contract:LIMEN_GOV_IDEAL_FORMS`; predicate `ideal-form-register.v1 input state is missing-configuration`; next: `LIMEN_GOV_IDEAL_FORMS="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:lineage_graph:missing-configuration` — owner `parameter-contract:LIMEN_GOV_LINEAGE_GRAPH`; predicate `lineage-graph.v1 input state is missing-configuration`; next: `LIMEN_GOV_LINEAGE_GRAPH="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:normalization_parity:missing-configuration` — owner `parameter-contract:LIMEN_GOV_NORMALIZATION_PARITY`; predicate `normalization-parity-receipt.v1 input state is missing-configuration`; next: `LIMEN_GOV_NORMALIZATION_PARITY="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:normalized_events:missing-configuration` — owner `parameter-contract:LIMEN_GOV_NORMALIZED_EVENTS`; predicate `normalized-event.v1 input state is missing-configuration`; next: `LIMEN_GOV_NORMALIZED_EVENTS="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:schema_catalog:missing-configuration` — owner `parameter-contract:LIMEN_GOV_SCHEMA_ROOT`; predicate `public governance-memory schemas are available`; next: `LIMEN_GOV_SCHEMA_ROOT="$SCHEMA_DEFINITIONS_ROOT" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:self_images:missing-configuration` — owner `parameter-contract:LIMEN_GOV_SELF_IMAGES`; predicate `node-self-image-set.v1 input state is missing-configuration`; next: `LIMEN_GOV_SELF_IMAGES="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:snapshot_bundle:missing-configuration` — owner `parameter-contract:LIMEN_GOV_SNAPSHOT_BUNDLE`; predicate `governance-snapshot-bundle.v1 input state is missing-configuration`; next: `LIMEN_GOV_SNAPSHOT_BUNDLE="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:source_census:missing-configuration` — owner `parameter-contract:LIMEN_GOV_SOURCE_CENSUS`; predicate `source-census.v1 input state is missing-configuration`; next: `LIMEN_GOV_SOURCE_CENSUS="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:source_envelopes:missing-configuration` — owner `parameter-contract:LIMEN_GOV_SOURCE_ENVELOPES`; predicate `source-envelope.v1 input state is missing-configuration`; next: `LIMEN_GOV_SOURCE_ENVELOPES="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.

## Validation Debt

- `assertions-empty`
- `atlas-missing`
- `atlas-receipt-readiness-missing`
- `cadence-fixed-point-not-proven`
- `cadence-readiness-missing`
- `cadence-run-one-invalid`
- `cadence-stage-count-mismatch`
- `cadence-stage-missing:classify`
- `cadence-stage-missing:discover`
- `cadence-stage-missing:distill`
- `cadence-stage-missing:parse`
- `cadence-stage-missing:receipt`
- `cadence-stage-missing:reconcile`
- `cadence-stage-missing:render`
- `cadence-stage-missing:snapshot`
- `cadence-stage-missing:validate`
- `cadence-two-run-proof-missing`
- `ideal-form-coverage-mismatch`
- `ideal-forms-empty`
- `ideal-forms-readiness-missing`
- `lineage-edges-empty`
- `lineage-lane-empty:artifact`
- `lineage-lane-empty:operator_intent`
- `lineage-nodes-empty`
- `normalization-parity-readiness-missing`
- `normalized-events-empty`
- `self-images-counts-mismatch`
- `self-images-empty`
- `self-images-readiness-missing`
- `self-images-registered-nodes-empty`
- `snapshot-bundle-missing`
- `source-census-empty`
- `source-envelopes-empty`
- `testament-missing`

## Fixed-point Predicate

Run twice with the same configured owner receipts. The public JSON, private JSON, Markdown, input fingerprint, and receipt ID must remain byte-identical; `--write` reports no changed files on the second run.
