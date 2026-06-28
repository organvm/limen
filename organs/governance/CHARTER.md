# Governance Organ — CHARTER (Aerarium / Cvrsvs Honorvm)

> **Boundary:** this organ makes governance rules machine-readable and executable. It does not
> adjudicate disputes, override human decision-makers, or act as a legal instrument. All
> constitutional acts (entity formation, policy ratification, personnel decisions) remain with
> the humans they belong to. The organ validates, tracks, and enforces the rules they have
> already agreed to.

## What it rivals

A constitutional state / a foundation's governance office — the apparatus that makes an
institution durable across time and personnel: clear succession rules, traceable authority,
auditable decisions, and constitutional articles that cannot be quietly rewritten. This organ
gives any project the same formal rigor, running continuously.

## The org-chart (AI roles, human-supervised)

| Role (Latin office) | Does | Human check |
|---|---|---|
| **Consul** — presiding chair | holds the canonical governance record; chairs review cycles | ratifies all constitutional changes |
| **Censor** — auditor | runs the promotion validator and DAG checker on every beat; surfaces violations | approves enforcement actions |
| **Quaestor** — treasurer | tracks the Aerarium: grants, allocations, entity financials | signs disbursements |
| **Aedile** — infrastructure steward | maintains the seed.yaml schema, promotion-ladder.yaml, and CI wiring | approves schema changes |
| **Tribune** — advocate | surfaces member/repo interests; blocks unconstitutional promotions | can veto promotion by voice |

These are workflow roles, not headcount. A single dispatched task can inhabit one or more roles.

## The workflows it runs

1. **Promotion review.** Given a `seed.yaml`, run `validate-promotion.py`: is the
   `metadata.promotion_status` a valid state? Are the required fields present? Report
   PASS / FAIL per-rule with the specific violation.
2. **Dependency audit.** Walk the estate's `seed.yaml` files and check that dependency
   edges form a valid DAG (no cycles, no back-edges that violate organizational boundaries).
3. **Seed contract compliance.** Validate the full `seed.yaml` structure against the schema
   for each required and optional field, every `produces` / `consumes` / `subscriptions` entry.
4. **Maturity reconciliation.** Cross-check `organ-ladder.json` maturity scores against
   `promotion_status` in the matching `seed.yaml` — catch divergence before it becomes
   technical debt.

## Inputs / outputs

- **Inputs:** `seed.yaml` files from any repo; `organ-ladder.json`; the `promotion-ladder.yaml`
  rule source.
- **Outputs:** PASS/FAIL validation reports with specific violations; a reconciliation diff
  when ladder scores and promotion states diverge; CI-exit-coded results (0 = clean, 1 = fail).

## First proof

`scripts/validate-promotion.py` run against `organvm/cvrsvs-honorvm/seed.yaml` — the external
repo that defined these concepts — and against any `seed.yaml` in the ORGANVM estate. One
command, readable output, machine-actionable exit code. That is the governance organ breathing.
