# Social Organism - CHARTER (Koinonia, the civic relationship desk)

> **Boundary:** this is social-institution infrastructure that augments human care,
> memory, judgment, and consent. It does not manipulate relationships, send messages
> autonomously, surveil people, replace therapy, or appoint itself as a community
> authority. Every outreach, invitation, apology, introduction, boundary, and rule
> stays with the human or community that owns the relationship. See [KERNEL.md](KERNEL.md)
> for the full guardrails.

## What it rivals - the civic/community institution standard

Koinonia rivals the operating floor of a serious civic institution: the church office,
community center, alumni association, mutual-aid desk, neighborhood organizer, social
secretary, and trusted relationship counsel working together. Those institutions do not
make a person more caring. They make care continuous: names are remembered, visits are
scheduled, conflicts are held in a process, newcomers are welcomed, obligations are not
lost, and no single tired mind has to carry the whole social field alone.

The "relationship gurus" function is not seduction, pressure, or private-life control.
It is a disciplined support desk that helps the human see a relationship clearly, choose
an honorable posture, draft words for review, preserve boundaries, and keep promises.
It gives one person the institutional weight of a community body without pretending the
machine is the friend, pastor, elder, therapist, organizer, or partner.

The civic standard, distilled: **every person is remembered before they disappear, every
promise is tracked before it is broken, every conflict is staged before it becomes
damage, every boundary is preserved before any cadence or growth goal.** This organ makes
that the default operating state for one person's network and, later, for any community.

## Institutional weight - how idle fleet capacity becomes a civic bench

VLTIMA's fleet produces idle AI workunits that can be converted into ongoing social
operations. Koinonia maps that spare capacity to the work a real civic/community
institution performs between human touchpoints:

| Fleet idle capacity (supply) | -> | Social organ demand |
|---|---|---|
| Cheap reads and writes | -> | Relationship posture briefs, people registers, promise ledgers |
| Background beats | -> | Weekly care cadence, reply queue scans, overdue-contact surfacing |
| Drafting runs | -> | Staged notes, invitations, apologies, gratitude messages, rule drafts |
| Structured-data workflows | -> | Contact records, tie state, reciprocity norms, boundary registers |
| Cross-model verification | -> | Consent, privacy, manipulation, and boundary sentinel checks |

The binding constraint is not model capacity. It is **legitimate relational context**:
who the person is, what the relationship is, what was consented to, what is owed, what is
off-limits, and what Anthony or another human actually wants to do. One active personal
network can consume 20-50 workunits/month in steady state. A community deployment can
consume more, but the first proof is local Markdown/YAML records and staged drafts.

## The org-chart (AI roles, human-supervised)

| Role | Institution equivalent | Does | Human check |
|---|---|---|---|
| **Relationship Holder** *(the human)* | Friend, family member, organizer, host, community elder | owns the real relationship, decides contact, sends messages, sets boundaries, makes commitments | - (this is the human) |
| **People Registrar** | Membership clerk / alumni office | maintains the people register: identities, contexts, consent notes, relationship category, and access limits | human confirms identity and privacy scope |
| **Relationship Steward** | Social secretary / pastoral-care coordinator | turns context into a relationship-posture brief: tie, standing, cadence, owed care, open risks | human approves the posture before action |
| **Correspondence Clerk** | Executive assistant / community correspondence desk | triages inbound/outbound message needs, drafts reply options, stages unsent notes | human edits and sends or discards every message |
| **Care Cadence Clerk** | Community care calendar | tracks birthdays, check-ins, gratitude, visits, follow-ups, and dormant ties needing attention | human chooses whether care is wanted or appropriate |
| **Obligations Clerk** | Promise ledger / mutual-aid coordinator | records promises, introductions, favors, borrowed items, debts of gratitude, and follow-up dates | human validates that an obligation is real |
| **Relationship Counsel** | Trusted advisor / "relationship guru" desk | produces options for repair, gratitude, distance, apology, boundary-setting, or reconnection | human supplies judgment; counsel never pressures or decides |
| **Community Rulekeeper** | Bylaws clerk / moderator support | drafts community norms, meeting protocols, conflict procedures, and decision records | community or human ratifies every rule |
| **Privacy & Consent Sentinel** | Confidentiality officer | gates every output for privacy, consent, manipulation risk, no-contact boundaries, and external-send prohibitions | human is final authority; sentinel blocks unsafe drafts |

The point of the chart: each role is a repeatable workflow the conductor can run. The
human remains the center of gravity. Koinonia increases prepared social surface area; it
does not take over relationships.

## Current build surface

This charter's first implementation surface is deliberately small and local. The organ
is buildable when each relationship or community can be represented as reviewable files:

```text
organs/social/
  KERNEL.md                       # invariant model + guardrails
  CHARTER.md                      # this civic relationship operating charter
  people/<person-id>.yaml         # private person/contact record (future)
  relationships/<tie-id>/
    posture.md                    # living relationship-posture brief
    correspondence.md             # staged reply queue and draft notes
    cadence.md                    # check-ins, care events, anniversaries, follow-ups
    obligations.md                # promises, favors, introductions, unresolved items
    boundaries.md                 # consent, no-contact, privacy, access limits
    repair-plan.md                # staged options for repair or distance, never sent
  communities/<community-id>/
    rulebook.md                   # norms, roles, decision rules
    member-register.md            # consent-scoped roster, not a public dump
    conflict-log.md               # process record, not gossip
    events.md                     # gatherings, invitations, follow-ups
```

Only `KERNEL.md` and this `CHARTER.md` exist now. The folder structure above is the next
build target, not a claim that private contacts or community records have already been
ingested.

## The workflows it runs

Each workflow maps to the 5-primitive kernel (Member, Mandate, Standing, Standard,
Governance) and produces a specific artifact. Workflows run on a cadence: on intake, on
event, weekly for posture, and before every staged message.

### 1. Intake -> relationship posture (Member + Mandate + Standing)

- **Trigger:** a person, group, or community becomes relevant; a relationship changes;
  the human asks "where do we stand?"
- **Process:** capture who the person or group is, what the tie is, why it matters, the
  current standing, recent history, open obligations, active boundaries, and what kind of
  care is appropriate.
- **Runs:** on intake, on material change, and weekly for active ties.
- **Output:** relationship-posture brief: one page naming Member, Mandate, Standing,
  Standard, and Governance.
- **Human gate:** the human confirms the posture and may delete, narrow, or redact it.

### 2. People -> register (Member + Governance)

- **Trigger:** a new contact is added, identity details change, or privacy scope changes.
- **Process:** maintain a minimal person record: name or alias, relationship context,
  contact channels if the human supplied them, consent/access notes, and what must not be
  stored or shared.
- **Runs:** on update and during privacy review.
- **Output:** consent-scoped people register.
- **Human gate:** the human confirms the record and may require aliases or omission.

### 3. Correspondence -> staged replies (Mandate + Governance)

- **Trigger:** a message needs a reply, the human wants to reach out, or a drafted note
  needs review.
- **Process:** summarize the context, identify the relational posture, draft one or more
  possible replies, label tone/risk, and run the Privacy & Consent Sentinel.
- **Runs:** on demand; optionally in a weekly unsent-reply review.
- **Output:** staged, unsent correspondence options with context notes.
- **Human gate:** nothing is sent automatically. The human edits, sends, delays, or discards.

### 4. Care cadence -> attention list (Standing + Standard)

- **Trigger:** weekly social beat, dated occasion, promised follow-up, or long silence on
  a relationship the human has marked as active.
- **Process:** compare each active tie's standing against its declared reciprocity norm:
  expected cadence, overdue care, upcoming events, and boundaries that override cadence.
- **Runs:** weekly minimum for active relationships.
- **Output:** care attention list: who may need attention, why, and what action is staged.
- **Human gate:** the human decides whether contact is wanted, respectful, and possible.

### 5. Obligations -> promise ledger (Standard + Standing)

- **Trigger:** the human promises something, receives a promise, owes a follow-up, or
  resolves an obligation.
- **Process:** record the obligation, source, due date or cadence, status, and whether it
  is a real commitment, soft intention, or emotional debt of gratitude.
- **Runs:** on event, with weekly overdue scan.
- **Output:** promise and obligation ledger.
- **Human gate:** the human validates that the ledger is fair and not overclaiming.

### 6. Introductions -> bridge packet (Mandate + Governance)

- **Trigger:** the human considers connecting two people or communities.
- **Process:** draft a bridge packet that states mutual relevance, consent needed from each
  side, risks, boundaries, and a staged introduction note.
- **Runs:** on demand.
- **Output:** introduction packet and unsent intro draft.
- **Human gate:** both consent and the final send remain human-owned.

### 7. Repair / boundary -> counsel memo (Standing + Governance)

- **Trigger:** strain, conflict, avoidance, grief, apology, a no-contact boundary, or a
  relationship that needs distance rather than more effort.
- **Process:** produce a counsel memo with facts, harms, uncertainty, repair options,
  boundary options, and recommended next human checks. It may draft an apology or boundary
  statement for review, but it does not judge the other person or optimize persuasion.
- **Runs:** on demand; never automated from sentiment alone.
- **Output:** repair or boundary counsel memo plus staged language, if requested.
- **Human gate:** the human decides whether to act; no message is sent by the organ.

### 8. Community -> rulebook and conflict process (Standard + Governance)

- **Trigger:** a group needs norms, event rules, decision procedures, or conflict handling.
- **Process:** draft a lightweight rulebook: roles, acceptable use, moderation pathway,
  privacy expectations, escalation path, and how decisions are recorded.
- **Runs:** on community formation, event planning, and rule review.
- **Output:** community rulebook, member register, event plan, or conflict-process record.
- **Human gate:** the community or authorized human ratifies every rule and decision.

### 9. Digest -> social standing brief (Standing)

- **Trigger:** weekly beat or before a high-social-density event.
- **Process:** summarize active relationships, overdue obligations, upcoming gatherings,
  reply queue, boundary alerts, repair candidates, and high-care opportunities.
- **Runs:** weekly or on demand.
- **Output:** social standing brief.
- **Human gate:** the brief is advisory; it does not create obligations by itself.

### Workflow orchestration diagram

```text
                  +----------------+
                  | Intake ->      |
                  | Posture        |
                  | (Member +      |
                  |  Mandate)      |
                  +-------+--------+
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
   +-------------+  +--------------+  +-------------+
   | People ->   |  | Care cadence |  | Obligations |
   | Register    |  | -> Attention |  | -> Ledger   |
   | (Member)    |  | (Standing)   |  | (Standard)  |
   +------+------+  +------+-------+  +------+------+
          |                |                |
          +----------------+----------------+
                           |
                           v
                  +----------------+
                  | Correspondence |
                  | / Introduction|
                  | drafts         |
                  +-------+--------+
                          |
                          v
                  +----------------+
                  | Repair /       |
                  | Boundary memo  |
                  +-------+--------+
                          |
                          v
                  +----------------+
                  | Privacy &      |
                  | Consent        |
                  | Sentinel       |
                  +-------+--------+
                          |
                          v
                  +----------------+
                  | Human or       |
                  | Community      |
                  | decides        |
                  +----------------+
```

Everything flows through the sentinel before external action. The organ can prepare,
remember, draft, and route; the human or community decides.

## Inputs / outputs

### Inputs (what the human or community supplies)

| Input | Format | Source | Maps to kernel |
|---|---|---|---|
| Person or group context | Narrative, contact record, alias, role | Human-supplied | Member |
| Relationship type and purpose | Friend, family, collaborator, neighbor, student, client, community member | Human-supplied | Mandate |
| Recent history | Notes, events, messages the human chooses to include | Human-supplied | Standing |
| Reciprocity norm | Expected cadence, mutual obligations, care standard | Human-supplied or community-ratified | Standard |
| Boundaries and consent | No-contact, privacy scope, access rules, exclusions | Human or community | Governance |
| Messages or drafts | Text the human provides for review | Human-supplied | Mandate + Governance |
| Community norms | Rules, roles, event context, decision process | Community or authorized human | Standard + Governance |

### Outputs (what the organ delivers)

| Output | Format | Cadence | Maps to kernel |
|---|---|---|---|
| Relationship-posture brief | Markdown | On intake, on event, weekly for active ties | Standing |
| People register | YAML/Markdown | On update and privacy review | Member + Governance |
| Reply queue | Markdown list with staged drafts | On demand / weekly | Mandate + Governance |
| Care attention list | Markdown brief | Weekly | Standing + Standard |
| Promise ledger | Markdown/YAML table | On event + weekly overdue scan | Standard |
| Introduction packet | Markdown memo + staged note | On demand | Mandate + Governance |
| Repair / boundary memo | Markdown counsel memo | On demand | Standing + Governance |
| Community rulebook | Markdown | On formation / rule review | Standard + Governance |
| Social standing brief | Markdown digest | Weekly or before events | Standing |
| Sentinel certification | Inline stamp or checklist | Every external-facing output | Governance |

All outputs are advisory and staged. None are sent, published, or enforced without human
or community approval.

## Exact mechanism - how one person gets the weight

Koinonia gives one person the weight of a civic/community institution through five
concrete mechanisms:

1. **Persistent relational memory.** People, promises, boundaries, cadence, and history
   live in structured records instead of in one exhausted private mind.
2. **Role separation.** Registrar, steward, correspondence, cadence, obligations, counsel,
   rulekeeping, and sentinel functions check one another the way a real institution has
   separate desks instead of one overloaded generalist.
3. **Cadence.** Weekly and event-driven beats keep relationships warm, promises visible,
   and conflicts staged even when the human is busy.
4. **Staged counsel.** The relationship-support desk produces options and draft language,
   but the human supplies judgment, consent, courage, restraint, and final words.
5. **Boundary-first governance.** No-contact, privacy, and community rules override every
   optimization target. The organ can help care persist; it cannot turn care into control.

The result is a private civic bench: an always-current social map, a correspondence desk,
a care calendar, a promise ledger, a repair desk, and a rulekeeper. The human still does
the irreducible human work. Koinonia makes sure that work is prepared, remembered, and
never lost between beats.

## First proof: Anthony's micro instance

The micro instance is Anthony's private network, correspondence, and relationship
support. It starts with one non-public relationship-posture brief and one weekly social
standing brief. No private names are required in the scaffold; aliases are acceptable
until the human chooses otherwise.

Rollout order:

1. **Posture brief template.** Define the first `relationships/<tie-id>/posture.md` shape
   using the five primitives and the guardrails in `KERNEL.md`.
2. **Reply queue.** Add `correspondence.md` for staged, unsent replies and notes.
3. **Care cadence.** Add `cadence.md` for check-ins, occasions, and overdue care.
4. **Obligations ledger.** Add `obligations.md` for promises, favors, introductions, and
   gratitude debts.
5. **Boundary register.** Add `boundaries.md` and make it a required sentinel input.
6. **Weekly social standing brief.** Generate one digest from the records, with no
   autonomous outreach.

This proves the macro platform because the same artifacts can be used by a neighborhood
group, class, mutual-aid circle, founder network, family system, or cultural community:
people register, relationship posture, care cadence, obligations, rulebook, and sentinel.

## Non-goals

- No autonomous outreach or auto-send.
- No scraping private social data without explicit human-supplied context.
- No relationship scoring as human worth.
- No persuasion optimization, seduction tooling, or funnel treatment of people.
- No therapy, diagnosis, legal advice, or spiritual authority claims.
- No community rule enforcement without community authorization.
- No public exposure of private relationship facts.

Koinonia is the civic bench behind care, not the actor replacing care.
