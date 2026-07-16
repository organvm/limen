# Governance Memory Readiness

> Limen is the bounded scheduler and redacted read model. Constitutional, custody, lineage, and compiler owners remain authoritative for their own receipts.

- Status: `degraded`
- Snapshot: `not-coherent`
- Receipt: `sha256:438e483bcd31f327a32df5f71e143c9879b6deba12b353677347d8bbb41e22e9`
- Exact classification: `False` (0 / None)
- Operationally ready: `False`
- Visible residuals: `8`

## Owner Inputs

| Input | Contract | State | Snapshot |
|---|---|---|---|
| `source_census` | `source-census.v1` | `missing-configuration` | `—` |
| `source_envelopes` | `source-envelope.v1` | `missing-configuration` | `—` |
| `lineage_graph` | `lineage-graph.v1` | `missing-configuration` | `—` |
| `governance_testament` | `governance-testament.v1` | `missing-configuration` | `—` |
| `assertion_evidence` | `assertion-evidence.v1` | `missing-configuration` | `—` |
| `coverage_receipt` | `coverage-receipt.v1` | `missing-configuration` | `—` |
| `iceberg_atlas` | `iceberg-atlas.v1` | `missing-configuration` | `—` |
| `self_images` | `node-self-image.v1` | `missing-configuration` | `—` |

## Iceberg Atlas Projection

- Operator-intent events: `0`
- Artifact events: `0`
- Ideal forms: `0`
- Node self-images: `0`

## Bounded Cadence

`discover → snapshot → parse → classify → reconcile → distill → validate → render → receipt`

## Owner Blockers

- `owner-receipt:assertion_evidence:missing-configuration` — owner `parameter-contract:LIMEN_GOV_ASSERTION_EVIDENCE`; predicate `assertion-evidence.v1 input state is missing-configuration`; next: `LIMEN_GOV_ASSERTION_EVIDENCE="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:coverage_receipt:missing-configuration` — owner `parameter-contract:LIMEN_GOV_COVERAGE_RECEIPT`; predicate `coverage-receipt.v1 input state is missing-configuration`; next: `LIMEN_GOV_COVERAGE_RECEIPT="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:governance_testament:missing-configuration` — owner `parameter-contract:LIMEN_GOV_TESTAMENT`; predicate `governance-testament.v1 input state is missing-configuration`; next: `LIMEN_GOV_TESTAMENT="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:iceberg_atlas:missing-configuration` — owner `parameter-contract:LIMEN_GOV_ICEBERG_ATLAS`; predicate `iceberg-atlas.v1 input state is missing-configuration`; next: `LIMEN_GOV_ICEBERG_ATLAS="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:lineage_graph:missing-configuration` — owner `parameter-contract:LIMEN_GOV_LINEAGE_GRAPH`; predicate `lineage-graph.v1 input state is missing-configuration`; next: `LIMEN_GOV_LINEAGE_GRAPH="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:self_images:missing-configuration` — owner `parameter-contract:LIMEN_GOV_SELF_IMAGES`; predicate `node-self-image.v1 input state is missing-configuration`; next: `LIMEN_GOV_SELF_IMAGES="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:source_census:missing-configuration` — owner `parameter-contract:LIMEN_GOV_SOURCE_CENSUS`; predicate `source-census.v1 input state is missing-configuration`; next: `LIMEN_GOV_SOURCE_CENSUS="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
- `owner-receipt:source_envelopes:missing-configuration` — owner `parameter-contract:LIMEN_GOV_SOURCE_ENVELOPES`; predicate `source-envelope.v1 input state is missing-configuration`; next: `LIMEN_GOV_SOURCE_ENVELOPES="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.

## Validation Debt

- `cadence-stage-missing:classify`
- `cadence-stage-missing:discover`
- `cadence-stage-missing:distill`
- `cadence-stage-missing:parse`
- `cadence-stage-missing:receipt`
- `cadence-stage-missing:reconcile`
- `cadence-stage-missing:render`
- `cadence-stage-missing:snapshot`
- `cadence-stage-missing:validate`

## Fixed-point Predicate

Run twice with the same configured owner receipts. The public JSON, private JSON, Markdown, input fingerprint, and receipt ID must remain byte-identical; `--write` reports no changed files on the second run.
