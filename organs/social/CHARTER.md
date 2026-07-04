# Social Organism - CHARTER (Koinonia)
## The civic relationship office

> **Boundary:** this organ builds social-institution infrastructure. It does not manipulate
> relationships, send messages autonomously, surveil people, practice therapy, mediate disputes
> as an authority, or replace consent. Every outreach, invitation, apology, boundary statement,
> introduction, and community rule stays with the human who owns the relationship. See
> [KERNEL.md](KERNEL.md) for the full guardrails.

## What it rivals

A civic/community institution plus a retained relationship-support team: the social secretary,
community operator, alumni office, mutual-aid clerk, correspondence desk, and trusted relationship
advisor that wealthy or institutionally protected people have behind them.

The point is not to automate friendship or pretend to be a "relationship guru." The point is to
give one person enough institutional weight to hold a community's worth of ties without depending
on exhausted memory, scattered chats, or mood-driven follow-through.

Koinonia makes relationship stewardship institutional:

- Every person/tie has a record, not a vague feeling.
- Every obligation has a standing, cadence, and human gate.
- Every draft is staged for review, never sent.
- Every boundary outranks every reminder.
- Every community rule is written, reviewable, and owned by the people involved.

## Current implementation surface

This charter is intentionally concrete. The social organ currently has these buildable surfaces:

| Surface | Path | Status | What it proves |
|---|---|---|---|
| Organ assertion | [`seed.yaml`](seed.yaml) | scaffold | declares social inputs, outputs, and consumers |
| Engagement records | [`engagements/*.yaml`](engagements/) | scaffold | one machine-readable relationship posture per tie |
| First engagement | [`engagements/derek.yaml`](engagements/derek.yaml) | live scaffold | proves a multi-dimensional collaborator/client/creative-partner tie |
| Validator | [`validate-social.py`](validate-social.py) | implemented | enforces the first six social rules across the engagement fleet |
| Brief generator | [`scripts/relationship-brief.py`](scripts/relationship-brief.py) | implemented | turns one engagement YAML into a reviewable Relationship-Posture Brief |
| Macro face | [`MACRO-FACE.md`](MACRO-FACE.md) | specified | describes the portable community/relationship platform |
| Micro face | [`MICRO-FACE.md`](MICRO-FACE.md) | specified | describes Anthony's live social instance and next proof targets |

Not implemented yet: live inbox ingestion, calendar sync, contact syncing, automatic reminders,
social-media scheduling, autonomous draft routing, or a dashboard. Those are future build targets
and must remain human-gated if they are added.

## The org-chart (AI roles, human-supervised)

The organ is a virtual civic office. Each role can be run by an AI lane, a script, or a manual
review pass, but authority stays with the human.

| Role | Does | Current surface | Human check |
|---|---|---|---|
| **Principal Steward** *(the human)* | owns the relationships, decides whether to contact, repair, distance, disclose, invite, introduce, or archive | all external action | This is the human |
| **Social Chancellor** | keeps the whole organ coherent: chooses the next relationship slice, assigns role work, and checks that outputs stay inside the guardrails | this charter, KERNEL, MACRO/MICRO faces | Human confirms priorities and any scope expansion |
| **Memory Registrar** | maintains the people/tie record: Member, Mandate, Standing, Standard, Governance, evidence, and update timestamp | `engagements/*.yaml` | Human confirms accuracy and revokes stale or sensitive data |
| **Relationship Analyst** | converts messy context into posture: active, warm, dormant, strained, broken, or protected; names what changed and why | engagement YAML + generated brief | Human confirms the standing; posture is not a value judgment |
| **Cadence Clerk** | tracks expected reply windows, check-ins, gratitude, care patterns, owed replies, anniversaries, and dormant ties | `standard.*` fields; future triage report | Human approves cadence changes and can cancel reminders |
| **Correspondence Steward** | drafts replies, invitations, apologies, introductions, gratitude notes, and care actions from the posture record | staged text only; no current auto-send integration | Human reviews, edits, sends, or discards |
| **Boundary Sentinel** | blocks work that violates no-contact, no-sharing, no-introduction, privacy, or manual-mode rules | `governance.*`, `validate-social.py` | Human sets boundaries; sentinel enforces them structurally |
| **Community Clerk** | records group norms, membership expectations, shared decisions, conflict history, and rule changes for communities | future community engagement YAML; chartered workflow | Community/human ratifies; organ does not appoint itself authority |
| **Archive Clerk** | closes or transitions ties with a record of what changed, what is owed, and what must not be reopened casually | future closeout record | Human approves retention, deletion, and future contact posture |
| **Receipt Clerk** | produces proof that the social office is operating: validation result, generated brief, changed paths, and next reviewable output | validator + brief generator | Human receives evidence before any external act |

## Inputs

| Input | Source | Required shape | Constraint |
|---|---|---|---|
| Relationship context | Human notes, prior docs, direct relationship knowledge | enough to fill Member and Mandate | Do not infer private facts without evidence |
| Engagement declaration | `organs/social/engagements/<name>.yaml` | Member, Mandate, Standing, Standard, Governance, Artifacts | Must pass `validate-social.py` |
| Evidence items | Human-confirmed facts or durable internal artifacts | explicit, non-placeholder evidence list | No TODO/TBD placeholder evidence |
| Consent/boundary rules | Human, relationship, or community rules | `governance.consent`, `requires_human`, `never_autonomous`, `human_gates` | Boundaries outrank cadence and growth |
| Organ state | `seed.yaml`, `organ-ladder.json`, KERNEL/MACRO/MICRO faces | scaffold status, rank, maturity, next proof | Do not overclaim beyond implemented surfaces |
| Review target | The next thing a human can inspect | `artifacts.next_reviewable_output` | Every record must point to a reviewable output |

## Outputs

| Output | Produced by | Current status | Consumer |
|---|---|---|---|
| Relationship-Posture Record | Memory Registrar | implemented as YAML | human, validator, future triage |
| Validation result | `python organs/social/validate-social.py --fleet` | implemented | organ health, closeout evidence |
| Relationship-Posture Brief | `python organs/social/scripts/relationship-brief.py ...` | implemented | human review |
| Social triage list | Cadence Clerk + Relationship Analyst | chartered build target | human weekly review |
| Staged correspondence draft | Correspondence Steward | manual/AI-draft workflow, no send automation | human review only |
| Boundary conflict flag | Boundary Sentinel | partly implemented through required governance fields; deeper checks are build target | human decision |
| Community rulebook / group posture | Community Clerk | chartered build target | community/human ratification |
| Relationship closeout / transition record | Archive Clerk | chartered build target | future continuity and boundary preservation |

## The workflows it runs

### 1. Intake -> posture record

Messy social context becomes one relationship record in `engagements/*.yaml`.

Required output:

- `member`: who the person or group is, with context and privacy note
- `mandate`: what relationship is being held and why it matters
- `standing`: where the tie stands now
- `standard`: expected cadence, reciprocity norm, care pattern, owed replies, and boundaries
- `governance`: manual mode, human gates, consent, and never-autonomous acts
- `artifacts`: evidence and the next reviewable output

Current proof: [`engagements/derek.yaml`](engagements/derek.yaml).

### 2. Posture record -> validation

The Receipt Clerk runs:

```bash
python organs/social/validate-social.py --fleet
```

The validator enforces the first six social organ rules:

1. Valid posture in the relationship sequence (ACTIVE, WARM, DORMANT, STRAINED, BROKEN, PROTECTED).
2. Manual mode with explicit human gates.
3. Five-primitive completeness.
4. Real evidence, not placeholder text.
5. No overreach into manipulation, surveillance, or autonomous outreach claims.
6. A named next reviewable output.

### 3. Posture record -> reviewable brief

The Relationship Analyst and Receipt Clerk produce a human-readable brief:

```bash
python organs/social/scripts/relationship-brief.py organs/social/engagements/derek.yaml
```

This gives the human a concise institutional memo: who the tie is, why it matters, where it stands,
what standard governs it, what boundaries are active, and what the next reviewable output is.

### 4. Fleet -> social triage

Chartered build target: generate a weekly review list from all engagement records.

The triage list must sort by:

- care overdue
- reply overdue
- standing changed
- repair or boundary issue present
- protected tie requiring no contact/no sharing
- dormant tie that needs either care or release

Until a generator exists, this can be run manually from the same YAML fields. It must not create
outbound action; it only prepares a review queue.

### 5. Triage -> staged draft

The Correspondence Steward can draft a message, introduction, gratitude note, care action, apology,
or boundary statement using the posture record as context.

Required output:

- draft text
- the posture record it came from
- the human gate that applies
- the boundary check performed
- a clear statement that nothing has been sent

No current script sends messages. That absence is part of the safety contract.

### 6. Boundary -> enforcement

The Boundary Sentinel checks every proposed reminder, draft, cadence change, or community rule
against:

- `governance.manual_mode`
- `governance.human_gates`
- `governance.requires_human`
- `governance.never_autonomous`
- `standard.boundaries`

If a workflow conflicts with any boundary, the output is a blocked/staged note for the human, not an
attempt to route around the boundary.

### 7. Community -> governance

Chartered build target: extend the same five primitives from one-to-one ties to communities.

For a community, the primitives map as:

- Member: person, group, or role
- Mandate: reason for belonging or participating
- Standing: member/community posture
- Standard: norms, expectations, and reciprocity rules
- Governance: rule ownership, ratification, conflict path, privacy rules

The organ can draft rules and track decisions. It cannot declare binding authority over real people.

### 8. Transition -> archive

Chartered build target: close or transition a tie without memory loss or boundary drift.

The Archive Clerk records:

- what changed
- what care was given
- what remains owed
- what must not be reopened casually
- what data should be retained, hidden, or destroyed
- when the human should review the posture again, if ever

## How this gives one person institutional weight

The social organ gives one person the operating floor of a civic/community institution by turning
relational care into repeatable institutional functions:

| Institutional function | What a civic/community institution has | What Koinonia gives one person |
|---|---|---|
| Continuity | staff records, minutes, files, alumni databases | relationship-posture records that survive mood, fatigue, and context loss |
| Attention allocation | agenda setting, queues, committees | triage by standing, cadence, owed replies, care, repair, and boundaries |
| Counsel | senior advisors and relationship staff | role-separated AI review: analyst, clerk, sentinel, drafter, archivist |
| Correspondence desk | assistants who draft and route communication | staged drafts tied to human gates, never autonomous sends |
| Care cadence | birthday lists, check-in systems, membership rituals | explicit standards for reply windows, gratitude, care, and dormant ties |
| Boundary enforcement | bylaws, privacy rules, conflict protocols | no-contact/no-sharing/manual-mode rules checked before work proceeds |
| Governance memory | decision logs and rulebooks | community posture records and rule drafts that remain reviewable |
| Proof | board packets, memos, audit trails | validation output, generated briefs, evidence lists, changed paths |

That is the "relationship guru" replacement in concrete terms: not charismatic advice, but a
standing office that remembers, organizes, drafts, checks boundaries, preserves context, and hands
the human one clear decision at a time.

The leverage is structural:

1. The human spends attention on judgment, care, and courage, not administrative recall.
2. AI lanes can prepare parallel memos, drafts, and audits without receiving authority to act.
3. Every relationship gets the same minimum institutional dignity: record, posture, standard,
   governance, and reviewable next step.
4. Sensitive ties can be protected by rule instead of depending on willpower.
5. The next lane can resume from artifacts instead of re-interviewing the human.

## What this is not

- Not therapy, counseling, mediation, dating optimization, sales automation, or social-media growth.
- Not a surveillance system.
- Not an autonomous outreach agent.
- Not a substitute for apology, repair, friendship, family, community consent, or personal courage.
- Not a claim that the machine knows what another person wants.

The organ is infrastructure. The human and the community remain the moral actors.

## First proof

The first vertical slice is a **Relationship-Posture Brief** for one real tie:

- A Member record (person/contact: identity and context, private by default)
- A Mandate (the relationship: what tie is held and why it matters)
- A Standing (tie strength and urgency: active, warm, dormant, strained, broken, protected)
- A Standard (reciprocity norm: expected cadence, boundaries, owed replies, and care)
- A Governance note (who may act, what requires the human's hand, what must never be shared)

The first engagement (`engagements/derek.yaml`) proves the brief works for Derek: a collaborator,
client, and creative partner whose relationship spans professional and personal dimensions. The brief
captures the tie, its current standing, its care obligations, its privacy constraints, and its human
gates without claiming authority to act.

Checked by:

```bash
python organs/social/validate-social.py --fleet
python organs/social/scripts/relationship-brief.py organs/social/engagements/derek.yaml
```

## Maturity and next build targets

The organ is rank 8 on the organ ladder and remains **5% mature** (scaffold stage). The scaffold is
now explicit: charter, kernel, macro face, micro face, one real engagement, validator, and brief
generator.

The next build targets to reach the building stage:

1. Add 3-5 more engagement records across different tie types: family, peer collaborator, dormant
   friend, protected boundary, and community/group.
2. Add a generated social-triage report over `engagements/*.yaml`.
3. Add a boundary-conflict checker for staged drafts and cadence actions.
4. Add a closeout/transition record format for strained, broken, and protected ties.
5. Feed validation and brief receipts into `organ-health` without exposing private relationship data.

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`MACRO-FACE.md`](MACRO-FACE.md) (platform thesis), [`MICRO-FACE.md`](MICRO-FACE.md)
(Anthony's live instance).*
