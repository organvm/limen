# organs/ — the VLTIMA institutional pillars

Each subdirectory is one **organ**: a civilizational pillar (legal, financial, education, …) rebuilt as
an AI-run institution, so one person carries the institutional weight the ultra-rich take for granted —
"the prosthesis for human weakness." The conductor drives them from [`../organ-ladder.json`](../organ-ladder.json)
via `scripts/generate-organ-backlog.py`; see [`../docs/MONSTER-MAP.md`](../docs/MONSTER-MAP.md) for the
whole body at a glance.

Every organ shares the domain-neutral **5-primitive kernel** — `Member · Mandate · Standing · Standard ·
Governance` — and is built as a **fractal**: a MACRO deployment (a platform anyone can hold) and a MICRO
deployment (Anthony's own instance). Generic + nameless underneath, his instance on top; never hardcoded
to one person.

The 5-primitives are the institutional projection of the broader
[`vltima/`](vltima/) kernel: `Object · Subject · Agent · Actor · System · Event · Record ·
Covenant`, plus the value layer `Exchange · Entitlement · Obligation`. The executable predicate is:

```bash
python3 scripts/validate-vltima-kernel.py
```

The machine-readable substrate lives at [`vltima/kernel.yaml`](vltima/kernel.yaml); the validator
derives the organ projection terms from that registry and rejects drift between the registry,
the universal kernel document, and each organ's `KERNEL.md`.

Standard files per organ: `KERNEL.md` (the primitive map + macro/micro), `CHARTER.md` (the org-chart of
AI roles + workflows + what real institution it rivals), then the organ's working artifacts.

| organ | pillar | home |
|---|---|---|
| [legal/](legal/) | Legal Organism — a litigation firm at the Cochran standard | the flagship |
| [vltima/](vltima/) | Universal substrate — objects, subjects, agents, records, covenants, institutions, value | meta-kernel |
| financial/ | Financial Office — a billionaire's family office | seeded |
| education/ | Education Organism — an academy + the alt-ed thesis | seeded (edu-organism is 60–80%) |
| media/ | Carrier-Wave Media — a cross-platform empire | seeded |
| governance/ | Aerarium / Cvrsvs Honorvm — governance-as-code | seeded |
| [consulting/](consulting/) | Sovereign Systems — agency-as-a-service | seeded |
| [artist/](artist/) | A-MAVS-OLEVM — a living museum/studio (Pantheon standard) | maturing — KERNEL + CHARTER + micro deck live |
| social/ | Koinonia — civic + relationship support | seeded |
| health/ | Health / Body — concierge recovery + ADA access | seeded |
| [contributions/](contributions/) | SPECVLVM — the contributions mirror (an OSPO: outward to learn inward) | maturing — autopoietic: MIRROR + LIFECYCLE + ESTATE + the scout pool, all on the beat |
