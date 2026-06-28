# Governance Organ — KERNEL (Aerarium / Cvrsvs Honorvm)

## Why this organ exists

Every institution that persists does so because it has governance: the rules that say who may
occupy which role, in what order, with what authority, and how that authority transfers. The rich
and powerful have this by default — boards, charters, bylaws, succession plans. Everyone else
improvises. This organ makes governance a *first-class artifact*: machine-readable, executable,
and portable, so any person or collective can hold the same constitutional weight as a foundation
or a state.

Named after the Roman *cursus honorum* — the sequential order of public offices in the Republic:
the quaestor before the aedile before the praetor before the consul. That sequence was not
ceremonial; it was the Republic's operating system. This organ rebuilds it as code.

## The 5-primitive kernel, mapped to the governance domain

| Primitive | Governance meaning | Concretely |
|---|---|---|
| **Member** | a participating entity subject to governance | a repository, organ, organization, or role in the system |
| **Mandate** | a governance rule, policy, or constitutional article | a promotion rule, a dependency constraint, an office-eligibility requirement |
| **Standing** | the current state of an entity in the lifecycle ladder | INCUBATOR / ALPHA / BETA / STABLE / ARCHIVED / FROZEN / DEPRECATED |
| **Standard** | the cvrsvs-honorvm promotion ladder | the ordered states, valid transitions, and invariants that constitute governance-as-code |
| **Governance** | the meta-process for how this organ itself evolves | separation of powers between the roles; the rule that the standard must itself pass the validator |

This is the same kernel as every other organ — only the skin changes. That is the fractal.

## Fractal deployment

- **MACRO** — a portable governance-as-code open standard any multi-repository ecosystem can adopt:
  declare a `seed.yaml`, have the promotion ladder validate your lifecycle state, run the dependency
  DAG validator in CI. Governance-as-code for OSS foundations, digital cooperatives, and any body
  that needs transparent succession rules.
- **MICRO** — ORGANVM's own dual-entity operation: the non-profit open project (Cind & Sol Foundation)
  and the commercial LLC operating arm, with promotion states governing repo lifecycle across 182+
  repos and the organ ladder governing institutional maturity.

## What the fleet builds next here (from organ-ladder.json)

1. `CHARTER.md` — the org-chart of governance roles + the workflows the organ runs.
2. `promotion-ladder.yaml` — the canonical state machine: the ONE rule, made declarative.
3. `scripts/validate-promotion.py` — the executable validator: runs against any `seed.yaml`.
4. Deepen: dependency DAG validation, seed contract schema, maturity reconciliation.
