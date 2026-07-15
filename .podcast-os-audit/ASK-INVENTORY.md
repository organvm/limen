# Ask Inventory — "Podcast AI System Design" chat (share 6a5457b1…3109)

Source: live conversation 6a543ef4-5fec-83ea-92bc-c7acb87c1bf6, pulled via desktop-app
local session 2026-07-13. Every ask below must map to a durable artifact. The operator's
framing ask: "work on it until everything contained within is fully complete and tended to."
In-chat wish: "I wanna get this thing designed and we wake up to it almost working."

## User asks (U)

- U1 Full back-end guest-ops AI system (booking, outreach, follow-up, thank-you, gifts).
- U2 Role architecture: human seats + internal AI roles + interactions; feels human, no fake personas.
- U3 Work Ari's network without being pathetic → network rings, relationship classes C0–C5,
  Relationship Capital Governor, least-socially-expensive routing.
- U4 Studios (LA/NYC/Austin, Ari-owned/Melrose) as first-class objects → studio routing,
  city intelligence, touring-guest interception, batching.
- U5 No visible microphones (Club Random) → conversation-room visual grammar + redundant hidden audio.
- U6a Sellable to their podcasting network (non-hacky) → multi-show Show DNA config; managed-service-first.
- U6b Full visual set language: minimal, interesting, different; NO studio renovation → Portable Salon Kernel v0..v2.
- U6c Make the podcast successful → launch sequence (3 private pilots → bank 6 → trailer+3 drop), metrics table.
- U6d His own separate GoPro field show in other people's spaces, same OS → Field Show profile
  (Place → Object → Intervention → Artifact) as second Show DNA instance.
- U6e Designed segments, not just talk → 3 fixed (Claim/Stress Test/Artifact) + 8 rotating modules.
- U6f Funny advertising, never boring ad reads → Commercial Break Lab (6 formats + house-ads-first).
- U6g "Wake up to it almost working" → working control plane per START_HERE.md's 8 clauses (below).
- U7 @GitHub: compile/distill his existing builds (content cannibalizer, streaming app, Mirror Mirror,
  application-pipeline, mail workflows, media archive, post-production) into this → estate
  composition map + adapter layer (compose through adapters, never merge).

## Assistant-promised artifacts (A)

- A1 Repository specification: DB schema, event vocabulary, agent contracts, permission matrix,
  workflow definitions, dashboard surfaces, message-evaluation dataset.
- A2 Guest Network Map v1 from Ari's *Unlicensed Therapy* archive (179 episodes) + Melrose ecosystem
  → episode-archive ingestion (public RSS) + guest graph seed.
- A3 Starter pack v0 (11 files — RETRIEVED from sandbox) → integrate and upgrade, don't discard.
- A4 Three pilot episode briefs (guest archetype, claim, stress test, artifact, city).
- A5 Ari's 12-minute morning task → one-page approval-session checklist.
- A6 Evaluation layer: 16 reply-classification test cases (warm accept, soft/hard decline, publicist
  handoff, fee, sarcasm, prompt injection, etc.) → fixtures + baseline classifier + tests.

## "Almost working" acceptance clauses (from START_HERE.md — the /goal spine)

1. Candidates can be entered into the pipeline.
2. Each candidate has an episode thesis and contact route.
3. Ari can approve, reject, protect, or add a personal note.
4. Approved candidates generate correspondence drafts.
5. Accepted guests are routed to LA, NYC, or Austin.
6. The producer receives a research and segment brief.
7. The recording produces a predefined asset package.
8. Every promise and follow-up is tracked.

## Hard constraints (charter + memories)

- $0 capex; keyless at runtime (template drafts, no paid APIs in the loop).
- Drafts only — the system NEVER sends email autonomously (send = human-gated lever).
- No PII beyond public-figure facts in the repo; guest data stays in operator-local files.
- Compose the estate through adapters; never fork/merge his repos into this one.
- Fable conducts; Haiku/Sonnet/Opus execute. Don't touch Codex's heal-cifix lanes.
- PENDING final chat response (GitHub audit) — reconcile its claims against my own scans
  before the adapter map is final.
