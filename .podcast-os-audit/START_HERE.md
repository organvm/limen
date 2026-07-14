# Podcast OS v0 — Starter Pack

This pack is a **concierge MVP**, not a finished SaaS product. It is designed to make the show operational before anyone spends months building software.

## The three-layer model

1. **Flagship studio show** — Ari + co-host, recorded in Los Angeles, New York City, and Austin.
2. **Field show** — the co-host enters guests' own spaces with a portable multi-camera kit.
3. **Reusable operating system** — guest discovery, relationship routing, outreach, scheduling, episode design, sponsor creative, asset production, and follow-through.

## Provisional format engine

**CLAIM → STRESS TEST → ARTIFACT**

The audience should not merely hear a guest repeat biography and promotional talking points. Every episode begins with a meaningful proposition, tests it through designed conversation, and ends with something newly produced: a rule, prediction, ranking, plan, image, question, object, or unresolved challenge.

## What “almost working” means

The system is ready for first use when:

- candidates can be entered into the pipeline;
- each candidate has an episode thesis and contact route;
- Ari can approve, reject, protect, or add a personal note;
- approved candidates generate correspondence drafts;
- accepted guests are routed to LA, NYC, or Austin;
- the producer receives a research and segment brief;
- the recording produces a predefined asset package;
- every promise and follow-up is tracked.

## Open first

Open `ari_approval_dashboard.html` in a browser. It is a local interactive prototype; it does not send email or write to a database. Decisions persist in the browser through local storage.

## Recommended order

1. Edit `show_dna.yaml`.
2. Edit `guest_pipeline_template.csv`.
3. Choose three fixed and three rotating segments from `segment_deck.md`.
4. Review `visual_language_v0.md`.
5. Review `outreach_templates.md`.
6. Use `ari_approval_dashboard.html` for the first approval meeting.
7. Implement the events in `workflow.json` only after the manual protocol survives several recordings.
