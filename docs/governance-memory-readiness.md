# Governance Memory Readiness

> Limen is the bounded scheduler and redacted read model. Constitutional, custody, lineage, and compiler owners remain authoritative for their own receipts.

- Status: `degraded`
- Snapshot: `snapshot-governance-organ-20260716-001`
- Receipt: `sha256:b7424bed20438fe867dad4c9541a5c79b49942042adae930f895473b7e808420`
- Exact classification: `True` (9 / 9)
- Operationally ready: `False`
- Visible residuals: `2`

## Owner Inputs

| Input | Contract | State | Snapshot |
|---|---|---|---|
| `source_census` | `source-census.v1` | `missing-configuration` | `—` |
| `source_envelopes` | `source-envelope.v1` | `missing-configuration` | `—` |
| `lineage_graph` | `lineage-graph.v1` | `available` | `snapshot-governance-organ-20260716-001` |
| `governance_testament` | `governance-testament.v1` | `available` | `—` |
| `assertion_evidence` | `assertion-evidence.v1` | `missing-configuration` | `—` |
| `coverage_receipt` | `coverage-receipt.v1` | `available` | `snapshot-governance-organ-20260716-001` |
| `iceberg_atlas` | `iceberg-atlas.v1` | `available` | `snapshot-governance-organ-20260716-001` |
| `self_images` | `node-self-image.v1` | `available` | `—` |

## Iceberg Atlas Projection

- Operator-intent events: `4`
- Artifact events: `7`
- Ideal forms: `3`
- Node self-images: `1`

## Bounded Cadence

`discover → snapshot → parse → classify → reconcile → distill → validate → render → receipt`

## Owner Blockers

- `owner-receipt:assertion_evidence:missing-configuration` — owner `parameter-contract:LIMEN_GOV_ASSERTION_EVIDENCE`; predicate `assertion-evidence.v1 input state is missing-configuration`; next: `LIMEN_GOV_ASSERTION_EVIDENCE="$OWNER_RECEIPT_PATH" python3 scripts/governance-memory-readiness.py --strict`.
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
