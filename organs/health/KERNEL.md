# Health Organism — KERNEL

> **Boundary (load-bearing, repeated everywhere in this organ):** this is health-operations *infrastructure*
> that AUGMENTS a human principal's own agency. It does **not** diagnose, prescribe, change a dose,
> provide medical advice, or replace a clinician. Every clinical decision stays with the licensed
> provider of record. The organ coordinates, tracks, researches, and preps so the principal operates
> with a concierge medical team's leverage — without the team.

## Why this organ exists

The rich don't heal faster because their bodies are different — they heal faster because a *staff*
stands behind them: a care coordinator, a patient advocate, a records archivist, a medical librarian,
a scheduler who misses nothing. The under-resourced get a single overworked clinician and a folder of
paperwork. This organ gives one person the institutional weight of that staff — the **concierge
standard** — as a coordinated set of AI roles working under the principal's own direction.

## The 5-primitive kernel, mapped to the health domain

| Primitive | Health meaning | Concretely |
|---|---|---|
| **Member** | the body / patient | the person whose health this is; their physiology, capacity, conditions, and goals |
| **Mandate** | the protocol | the care plan, treatment regimen, recovery milestones, and therapeutic intent |
| **Standing** | health state | where the body is right now: vitals, symptoms, lab results, functional status, pain level |
| **Standard** | clinical guideline | the evidence-based rubric: standard of care, screening schedules, monitoring obligations, contraindications |
| **Governance** | care plan | who decides what: the principal's advance directives, consent boundaries, escalation triggers, the PII firewall |

This is the *same* kernel as the legal, financial, and education organs — only the skin changes. That is the
fractal: one structure, every pillar.

## Fractal deployment

- **MACRO** — a health/recovery + disability-access institution anyone can hold: a longitudinal health
  record keeper, a protocol tracker, a visit-prep engine, a surveillance/screening scheduler, a
  medication-and-monitoring coordinator, and an ADA-accommodation rights organizer. Institutional
  weight for the many.
- **MICRO** — the principal's own post-injury recovery and disability-access navigation, run with that
  weight: a unified view of his recovery state, a protocol tracker for his rehab and medication
  regimen, an accommodation-rights organizer that ties directly to the active legal ADA matter, and a
  daily briefing so that being well costs as little thought as possible. The instance is unnamed in the
  artifact layer; it is known only as the example the macro was built on.

## What the fleet builds next here (from organ-ladder.json)

1. `CHARTER.md` — the org-chart of AI roles + the workflows the office runs (see the existing draft at
   [`docs/health-office/CHARTER.md`](../../docs/health-office/CHARTER.md), which becomes the canonical charter).
2. The first vertical slice — a personal recovery/access protocol for the live post-injury recovery
   (4th-story fall ~2024), packaged as a framework that shows what an AI-run health office looks like.
3. Then: deepen toward a reusable health-institution substrate (macro), with the micro instance as the
   proving ground.

## Hard guardrails (every contributor + every dispatched task)

- No medical advice, no diagnosis, no prescription. Outputs are coordination, research, and prep for
  the principal to review with their licensed clinician.
- Protected health information lives **outside every git checkout** at `$LIMEN_HEALTH_DIR` (default
  `~/Workspace/_health-private/`), `chmod 700`, structurally uncommittable. The organ reads the Chart
  and never mutates it. No medical text reaches the repo, logs, or console.
- Nothing is sent to a provider by the system. The principal reviews, decides, and sends.
- Separation of powers: the principal decides, clinicians diagnose/prescribe, this office coordinates.
  No crossing.
- Cite real clinical authority only; never invent guidelines, studies, or standards of care.
