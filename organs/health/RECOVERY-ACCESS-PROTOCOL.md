# Health Organism - Recovery/Access Protocol

> **First vertical slice:** this is the first concrete artifact produced by the health organ.
> It turns the chartered institution into a review-only protocol for one real case: an unnamed
> post-injury recovery and disability-access matter anchored by a 4th-story fall (~2024) and
> linked to the ADA accommodation track in `organs/legal/`.

> **Boundary:** informational health-operations infrastructure only. This is not medical advice,
> diagnosis, treatment, prescription, physical-therapy instruction, legal advice, or an outbound
> communication. Licensed clinicians own clinical judgment. Counsel owns legal judgment. The
> patient owns every decision and every send/sign/book action.

## Status

- **Artifact status:** review-only working protocol.
- **Outbound status:** no email, letter, form, calendar booking, appointment request, employer
  message, provider message, legal filing, or signature is sent from this artifact.
- **Identity status:** unnamed and repo-safe. No protected health information is stored here.
- **Private record location:** real health facts belong outside git in the private health chart
  described by `docs/health-office/CHARTER.md`.
- **Legal link:** the accommodation record produced here feeds `organs/legal/`; the legal organ
  decides legal posture with counsel and never receives medical advice from this organ.

## What this proves

The health organ is no longer only a constitution (`KERNEL.md`) and charter (`CHARTER.md`). It can
produce an end-to-end recovery/access operations artifact for one live-style case without crossing
medical, privacy, or legal boundaries.

The proof is narrow and concrete:

1. It names the case scope without exposing the patient's name or private medical details.
2. It converts the six charter workflows into a daily/weekly/event cadence.
3. It produces the fields the patient can fill from clinician instructions and lived state.
4. It produces an ADA accommodation record shape that the legal organ can consume.
5. It stamps every downstream draft as review-only and unsent.

## Case scope

| Field | Repo-safe value |
|---|---|
| Case id | `health-post-injury-access-001` |
| Principal | unnamed patient / principal |
| Anchor event | 4th-story fall (~2024) |
| Recovery frame | post-injury recovery coordination and disability access |
| Legal tie | ADA accommodation matter tracked by `organs/legal/` |
| Health authority | licensed clinicians and the patient's care team |
| Legal authority | counsel and the patient |
| Repo boundary | no private symptoms, diagnoses, medications, provider names, dates of care, or correspondence text |

## Artifact primitive map

| Primitive | Protocol field | What is recorded |
|---|---|---|
| Member | body / capability profile | functional capacity observations, limits, fatigue burden, access needs, patient corrections |
| Mandate | clinician-supplied protocol | instructions the patient has already received from licensed clinicians; no new treatment instructions |
| Standing | recovery/access posture | current state summary, open care loops, appointment posture, accommodation posture |
| Standard | safety and evidence rules | clinician primacy, privacy firewall, review-only drafts, source-tagged records |
| Governance | care plan + legal handoff | cadence, human gates, legal-organ handoff, no-send/no-book/no-file controls |

## Workflow runbook

### 1. Intake -> posture

**Trigger:** first run, new clinician instruction, new appointment, material recovery change, or
new accommodation event.

**Inputs accepted:**

- Patient-provided functional observations.
- Clinician-provided restrictions, protocols, discharge notes, appointment instructions, or
  referral instructions.
- Existing accommodation correspondence or decision records supplied by the patient.

**Output:** the repo-safe posture brief below, plus any private details written only to the private
health chart.

### 2. State -> record

**Trigger:** daily beat or patient-reported change.

**Inputs accepted:** patient-observed state markers, phrased as observations rather than clinical
interpretations.

**Output:** append-only state log entry in the private chart. The repo stores only this field
contract.

### 3. Protocol -> adherence

**Trigger:** clinician-supplied protocol exists or changes.

**Inputs accepted:** instructions already given by licensed clinicians, plus patient-supplied
completion notes.

**Output:** adherence log that records completed, skipped, rescheduled, deferred, or clinician-
modified actions. The organ never recommends a deviation.

### 4. Appointments -> calendar

**Trigger:** appointment scheduled, rescheduled, completed, missed, or follow-up window known.

**Inputs accepted:** appointment facts supplied by the patient or care team.

**Output:** private appointment calendar and visit-prep sheet. The organ never books, cancels, or
reschedules appointments.

### 5. Accommodation -> documentation

**Trigger:** functional limitation identified, accommodation considered, accommodation requested,
response received, status changed, or correspondence added.

**Inputs accepted:** patient-described limitation, clinician documentation if supplied, and
correspondence records.

**Output:** accommodation record with limitation, requested support, status, evidence source, and
legal-organ handoff flag. This is operational documentation, not legal advice.

### 6. Safety sentinel

**Trigger:** every output before the patient, clinician, counsel, or legal organ sees it.

**Checks:**

- No diagnosis.
- No treatment instruction.
- No medication instruction.
- No contradiction of a licensed directive.
- No legal advice.
- No outbound action.
- No private health information in repo-tracked files.

## Cadence

| Cadence | Workflow | Output | Human gate |
|---|---|---|---|
| Daily | State -> record | private state log entry | patient confirms or corrects |
| Weekly | Intake -> posture | posture brief refresh | patient reviews; clinician validates clinical facts as needed |
| On clinician instruction | Protocol -> adherence | protocol/adherence row | clinician instruction is source of authority |
| On appointment event | Appointments -> calendar | visit prep and follow-up checklist | patient books/confirms |
| On access event | Accommodation -> documentation | accommodation event row | patient and counsel decide legal use |
| Every output | Safety sentinel | certification stamp | human reviewer remains final authority |

## Repo-safe posture brief

**Case:** `health-post-injury-access-001`

**Known repo-safe facts:**

- The case is post-injury.
- The anchor event is a 4th-story fall (~2024).
- The recovery/access record ties to an ADA accommodation matter.
- The patient remains unnamed in tracked artifacts.
- Clinical details, correspondence text, provider names, and appointment dates are intentionally
  excluded from this repo.

**Current operating posture:**

- Build the private recovery/access record from patient-supplied and clinician-supplied facts.
- Track functional capacity as observation, not diagnosis.
- Keep every accommodation entry structured enough for the legal organ to ingest.
- Keep medical and legal authority separated.
- Keep all outbound communications staged as drafts only.

**Open human atoms surfaced once:**

- Patient supplies or confirms any active clinician restrictions/protocols before the protocol
  tracker can record adherence.
- Patient supplies appointment facts before the appointment calendar can produce visit prep.
- Patient and counsel decide whether any accommodation record is used in the ADA matter.

## Private chart field contract

These fields define the shape of private data. They do not belong in git.

```json
{
  "case_id": "health-post-injury-access-001",
  "identity": {
    "display": "unnamed principal",
    "repo_safe": true
  },
  "anchor_event": {
    "type": "post-injury event",
    "repo_safe_summary": "4th-story fall (~2024)"
  },
  "clinician_directives": [
    {
      "source": "licensed clinician",
      "date": "private",
      "directive_summary": "private",
      "status": "active | superseded | unclear",
      "patient_confirmed": false
    }
  ],
  "state_log": [],
  "protocol_adherence": [],
  "appointments": [],
  "accommodation_events": [],
  "safety_reviews": []
}
```

## Daily state record template

The patient records observations. The clinician interprets clinical meaning.

```text
Date:
Recorder:
Patient reviewed: yes/no

Functional observations:
- Mobility:
- Standing/sitting tolerance:
- Lifting/carrying tolerance:
- Stamina/fatigue:
- Pain interference:
- Sleep/rest impact:
- Cognitive load or concentration impact:
- Other access-relevant observation:

Change since last entry:
- improved / stable / worse / unclear

Care-team follow-up needed:
- none recorded / patient wants to ask clinician / already routed to clinician

Safety sentinel:
- no diagnosis made
- no treatment instruction made
- no medication instruction made
- no outbound action taken
```

## Weekly posture template

```text
Week of:
Patient reviewed: yes/no

1. Current recovery/access posture
- What changed this week:
- What stayed stable:
- What got harder:
- What needs clinician clarification:

2. Active clinician-supplied protocols
- Source:
- Date:
- What the patient is tracking:
- Any uncertainty to ask clinician:

3. Appointments and open loops
- Upcoming appointments:
- Follow-up items:
- Results or paperwork expected:

4. Accommodation posture
- Active limitations relevant to access:
- Accommodation requested or being considered:
- Status:
- Correspondence source:
- Legal-organ handoff needed: yes/no

5. Safety sentinel
- clinical boundary held: yes/no
- legal boundary held: yes/no
- private data kept off repo: yes/no
- outbound action taken: no
```

## Accommodation event record

This is the legal-organ bridge. It records facts and status; it does not advise on legal rights,
strategy, filings, or communications.

```text
Event id:
Date:
Source:
Patient reviewed: yes/no
Counsel review needed: yes/no

Functional limitation observed:

Impact on work/access/activity:

Accommodation or support discussed/requested:

Status:
- not yet requested / drafted / submitted by patient / under review / granted / denied /
  modified / appealed / closed

Evidence source:
- patient observation / clinician note / employer response / calendar record / other

Correspondence location:
- private record path or counsel-held source

Legal-organ handoff:
- none / add to ADA matter index / counsel review requested

Safety sentinel:
- no medical advice
- no legal advice
- no outbound action
- no private correspondence text in repo
```

## Draft-only message wrappers

Every message produced from this protocol must use one of these wrappers before it can leave the
health organ. The wrapper is part of the artifact because the no-send gate is load-bearing.

```text
DRAFT - NOT SENT
Audience:
Purpose:
Source facts used:
Human owner for send/sign:

Boundary:
This draft is for review only. It does not provide medical advice or legal advice. The patient,
licensed clinician, or counsel must review, edit, approve, and send/sign if appropriate.

Draft body:
```

```text
SAFETY REVIEW
clinical boundary held: yes/no
legal boundary held: yes/no
privacy boundary held: yes/no
contradicts known clinician directive: yes/no/unknown
outbound action taken by system: no
reviewer:
date:
```

## Legal-organ handoff packet

When counsel or the legal organ needs the accommodation record, the health organ hands over a
structured index, not medical conclusions.

```text
Handoff target: organs/legal/
Matter link: ADA accommodation matter
Packet type: accommodation documentation index
Patient reviewed: yes/no
Counsel reviewed: yes/no

Included:
- event ids
- dates
- source labels
- functional limitation summaries
- accommodation status
- correspondence locations

Excluded:
- diagnosis
- treatment opinion
- legal theory
- legal advice
- unsent drafts unless expressly selected by patient/counsel
```

## Acceptance checklist

- KERNEL guardrails are preserved.
- CHARTER workflows are instantiated in a concrete runbook.
- The first case is real enough to carry the post-injury/ADA access context.
- The record remains unnamed and repo-safe.
- Clinical and legal authority are separated.
- Outbound acts remain drafts only.
- The legal organ receives only structured factual accommodation records.
- The artifact can be validated without reading private medical data.

## Safety certification

Safety check passed for this repo-tracked artifact: clinical boundary held, legal boundary held,
privacy boundary held, no contradiction of licensed directives asserted, and no outbound action
taken.
