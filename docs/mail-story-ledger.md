# Mail Story Ledger

Redacted control-plane view over the local mail story corpus. Raw/private atoms stay in the ignored
`.limen-private/mail-story/` cartridge; this tracked report keeps only counts, domains, hashes,
cluster ids, and synthesized pain-point theses.

## Snapshot

- Generated: `2026-07-06T17:37:12Z`
- Source: Apple Mail Envelope Index, opened read-only.
- Processed scope: `flagged`
- Body/thread reads: `false`
- Mailbox mutations: `false`
- Private atom store: `.limen-private/mail-story/inventory/mail-story-atoms.jsonl`

## Corpus Counts

- Total indexed messages: `81564`
- Non-deleted messages: `81564`
- Flagged non-deleted messages: `126`
- First received: `2008-09-22 02:30:28`
- Last received: `2026-07-06 17:33:06`
- Atoms emitted in this run: `126`
- No silent drops: `true`

## Reconciliation

- Baseline source: `user_brief_2026-07-06`
- Reconciliation status: `drift`

| check | expected | actual | delta | status | note |
| --- | --- | --- | --- | --- | --- |
| Apple Mail total indexed messages | 81541 | 81564 | 23 | drift | - |
| Apple Mail flagged non-deleted | 108 | 126 | 18 | drift | - |
| Gmail All Mail flagged locally | 97 | 115 | 18 | drift | - |
| iCloud Inbox flagged locally | 11 | 11 | 0 | match | - |
| Gmail connector STARRED messages | 97 | 115 | 18 | drift | from read-only Gmail connector label count |
| Gmail connector STARRED threads | 96 | 113 | 17 | drift | from read-only Gmail connector label count |

## Gmail STARRED Reconciliation

- Source: `gmail_connector_list_labels_2026-07-06T17:00Z`
- Mode: `count_only`
- Gmail body reads: `false`
- Gmail label writes: `false`
- Local Gmail flagged messages: `115`
- Local Gmail flagged threads: `114`
- Connector STARRED messages: `115`
- Connector STARRED threads: `113`
- Message count delta local-minus-connector: `0`
- Thread count delta local-minus-connector: `1`
- Matched messages: `0`
- Local-only messages: `None`
- Gmail-only messages: `None`
- Coverage: Count-only connector reconciliation; identity matching requires --gmail-starred-export.

## Pain Point Clusters

| cluster | type | atoms | priority | next actions | recurring pattern | candidate products | market/UX thesis |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Billing continuity | billing | 30 | critical (360) | human_review:27, obligation:3 | Payment, renewal, card, invoice, and subscription notices arrive across vendors. | billing custody ledger, renewal exception router | The user wants one obligation queue, not a scavenger hunt across billing portals. |
| Identity and compliance gates | identity | 20 | critical (275) | human_review:15, obligation:5 | KYC, account review, and verification requests block access until evidence is assembled. | compliance dossier, verification request tracker | The durable product is a user-owned evidence vault with state, not a one-off upload helper. |
| Debt and default navigation | debt | 15 | critical (225) | human_review:12, obligation:3 | Loan, tax, repayment, and default notices create a fragmented case history. | debt case file, repayment option navigator | People need procedural clarity and proof, not another generic finance dashboard. |
| Relationship and personal administration | relationship | 16 | high (190) | product_research:16 | Human-origin messages and self-reminders carry relationship context beside vendor noise. | relationship memory ledger, owed-reply router | People will trust a tool that preserves context while refusing to send on its own. |
| Infrastructure and domain custody | infra | 9 | high (150) | human_review:7, obligation:2 | Cloud, domain, DNS, API, and developer platform notices become ownership risk. | operator custody ledger, domain and cloud notice router | Operators need a cockpit that converts vendor mail into resource state and risk. |
| Legal and government accountability | legal | 9 | high (150) | human_review:9 | Legal, government, benefits, and signature notices carry procedural obligations. | civic case ledger, legal notice timeline | The UX should feel like a case file with receipts, not a to-do list. |
| Uncategorized pressure | other | 12 | medium (135) | needs_thread_read:12 | Flagged mail without a confident class still carries enough pressure to preserve. | parked evidence queue, uncertainty triage ledger | The first useful UX is honest parking with the next smallest evidence step. |
| Security and fraud risk | security | 5 | medium (125) | human_review:5 | Security, fraud, login, and password alerts demand action but resemble phishing. | verify-first security queue, fraud alert receipt locker | The product should slow the click and speed the safe verification route. |
| Career routing | career | 5 | medium (80) | product_research:5 | Recruiter, opportunity, interview, and role messages mix signal with staffing noise. | career opportunity router, fit-and-next-step extractor | The value is fast triage with memory of prior fit, not another job board. |
| Health administration | health | 2 | medium (80) | human_review:2 | Appointment, lab, pharmacy, insurance, and portal notices require careful follow-up. | private care follow-up ledger, health notice router | The market wedge is privacy-safe coordination, not medical advice. |
| Platform and developer ecosystem intelligence | platform | 1 | low (40) | product_research:1 | AI, developer, release, newsletter, and platform notices become product intelligence. | platform intelligence digest, vendor signal graph | The product should convert noisy updates into decision support with provenance. |
| Life and creative logistics | creative_life | 2 | low (35) | product_research:2 | Tickets, events, creative commitments, and life receipts accumulate operational context. | life logistics ledger, creative commitment tracker | The UX should preserve lived context without making every event a productivity chore. |

## Cluster Details

### Billing continuity

- Universal pain point: People are expected to monitor scattered payment warnings across vendors and inboxes.
- Software thesis: A custody layer should turn billing and renewal mail into one verified account-continuity queue.
- Affected domains: money, work, infrastructure
- Existing tools involved: vendor billing portals, card networks, email flags
- Failure modes: late notice, card decline, account suspension, renewal surprise
- Example atom ids: ms_10f65dcfd04dbc02, ms_eadd6db50fcd7ada, ms_096a620e69eb0c6a, ms_f96102bc8d5827c6, ms_323b1574cd1800e5

### Identity and compliance gates

- Universal pain point: Compliance workflows arrive as email fragments instead of an explainable case file.
- Software thesis: A compliance dossier should collect requests, evidence, deadline state, and safe verification routes.
- Affected domains: money, identity, platform access
- Existing tools involved: KYC portals, payment processors, identity forms, email
- Failure modes: opaque review, duplicate evidence asks, blocked payout
- Example atom ids: ms_3d0b1cc56f1635d1, ms_30a423d2709f7cef, ms_4de18c13ea42f621, ms_47d51f2ec918fea6, ms_d6ed474b9ad865fd

### Debt and default navigation

- Universal pain point: Debt systems expose consequences faster than they expose trustworthy next steps.
- Software thesis: A debt-navigation copilot should map notices into verified options, deadlines, and escalation paths.
- Affected domains: money, legal, career
- Existing tools involved: loan servicers, tax vendors, government portals, email
- Failure modes: unclear deadline, threat without path, servicer fragmentation
- Example atom ids: ms_3e1b91889c64c108, ms_303bee73be6cfd72, ms_05505f5ceb6fc343, ms_78e89257ad39a232, ms_77f55659afb067df

### Relationship and personal administration

- Universal pain point: Personal administration is structurally mixed with automated vendor mail.
- Software thesis: A relationship memory layer should separate human context from institutional noise.
- Affected domains: relationships, time, personal admin
- Existing tools involved: Gmail, Apple Mail, contacts, calendar
- Failure modes: human context buried, owed reply lost, automated mail overwhelms relationship mail
- Example atom ids: ms_b83d24b016b863ff, ms_c06e519a707dc6f9, ms_141eb6ac38012815, ms_eb67e86a16e3d9e4, ms_5cb2d015650c9a1d

### Infrastructure and domain custody

- Universal pain point: Solo operators hold production custody through vendor emails instead of a coherent control plane.
- Software thesis: An operator custody ledger should unify infra notices, owners, renewals, and blast-radius state.
- Affected domains: infrastructure, money, product
- Existing tools involved: cloud consoles, domain registrars, developer platforms, email
- Failure modes: resource expiry, API break, ownership drift, unread blast-radius notice
- Example atom ids: ms_0b9f31ad696a5e33, ms_c85c8b0d40ba109b, ms_ad73fd8cf0f3fa09, ms_9352aee02f536f7d, ms_24d59b8bfea6a146

### Legal and government accountability

- Universal pain point: Institutional email makes citizens assemble their own procedural memory.
- Software thesis: A civic/legal organizer should translate notices into timelines, obligations, and evidence packets.
- Affected domains: legal, government, money
- Existing tools involved: court portals, government portals, signature tools, email
- Failure modes: missed procedural step, lost evidence, opaque institution state
- Example atom ids: ms_2d1e5e25ba96c2e4, ms_03da6e47b4e3090d, ms_fe73e76fabf3b95a, ms_0ecf443c607f0285, ms_77219269a7851ce6

### Uncategorized pressure

- Universal pain point: People flag uncertainty because inbox tools do not support partial understanding.
- Software thesis: A story-mining workflow should park ambiguous mail with evidence and a next read action.
- Affected domains: unknown
- Existing tools involved: email flags, manual memory
- Failure modes: ambiguous pressure, silent drop, premature deletion
- Example atom ids: ms_802a1a611465ca1f, ms_8910e2bf16fe3837, ms_5077565aabf72080, ms_e3502ab4c83d12a9, ms_3a8b80206c34a401

### Security and fraud risk

- Universal pain point: Security email mixes real incidents with phish-like UX and no trusted verification path.
- Software thesis: A verify-first security queue should route alerts through safe channels and preserve audit receipts.
- Affected domains: security, money, identity
- Existing tools involved: bank portals, password managers, account security pages, email
- Failure modes: spoofed link, alert fatigue, missed incident, unverified recovery path
- Example atom ids: ms_8ffc52b3d39c00a5, ms_7d0ad5ef3f6d49ba, ms_730b96f1d12249ee, ms_a08661a47ff94cf6, ms_b46449d889ba0e1e

### Career routing

- Universal pain point: Opportunity inboxes mix real leads, staffing noise, and identity fit with little ranking help.
- Software thesis: A career router should score fit, extract next steps, and preserve opportunity history.
- Affected domains: career, money, identity
- Existing tools involved: recruiting platforms, staffing firms, resume systems, email
- Failure modes: low-fit lead, missed good lead, context lost across threads
- Example atom ids: ms_0580ba43187ade3b, ms_607df58b161e86bc, ms_54421ebc11eeb714, ms_f563eaace80e6a95, ms_0bff73036f3459d4

### Health administration

- Universal pain point: Patients are expected to coordinate care logistics from fragmented notification systems.
- Software thesis: A health admin ledger should turn notices into private follow-up loops with strict privacy boundaries.
- Affected domains: health, time, money
- Existing tools involved: patient portals, pharmacies, insurers, email
- Failure modes: missed appointment, lost lab follow-up, coverage ambiguity, privacy leak
- Example atom ids: ms_873de26dec9b08eb, ms_94cfab9633cb7148

### Platform and developer ecosystem intelligence

- Universal pain point: Operators need a way to convert ecosystem noise into strategic intelligence.
- Software thesis: A platform-intelligence digest should cluster vendor signals into product and risk theses.
- Affected domains: product, career, infrastructure
- Existing tools involved: developer newsletters, platform changelogs, vendor dashboards, email
- Failure modes: signal lost in volume, missed deprecation, unconnected product clue
- Example atom ids: ms_d448948b53aa4d1a

### Life and creative logistics

- Universal pain point: Calendar-adjacent life mail is not treated as part of a personal operating system.
- Software thesis: A life-logistics layer should connect tickets, commitments, receipts, and story context.
- Affected domains: creative_life, time, relationships
- Existing tools involved: ticket platforms, calendar tools, receipts, email
- Failure modes: lost receipt, missed event context, unlinked calendar state
- Example atom ids: ms_010b0d1dcb04ed40, ms_122bedff2d25c370


## Top Sender Domains In Processed Scope

| domain | messages |
| --- | --- |
| gmail.com | 17 |
| google.com | 13 |
| email.apple.com | 8 |
| stripe.com | 6 |
| nelnet.studentaid.gov | 6 |
| taxrise.com | 6 |
| notify.cloudflare.com | 5 |
| studentaid.gov | 4 |
| mail.anthropic.com | 4 |
| account.chime.com | 4 |
| socket.dev | 3 |
| longofirm.com | 3 |
| buytickets.at | 2 |
| stage4solutions.com | 2 |
| insideapple.apple.com | 2 |
| ceiamerica.com | 2 |
| email.openai.com | 2 |
| info.hostinger.com | 2 |
| email.legalzoom.com | 2 |
| docusign.net | 2 |

## Flagged By Mailbox

| account | mailbox | scope | messages | threads |
| --- | --- | --- | --- | --- |
| gmail | all_mail | gmail/all-mail | 115 | 114 |
| icloud | inbox | icloud/inbox | 11 | 11 |

## Flagged By Year

| year | messages |
| --- | --- |
| 2026 | 115 |
| 2025 | 10 |
| 2024 | 1 |

## Privacy Boundary

- No message body text is read by this pass.
- Full sender addresses, sender display names, subjects, summaries, and Apple row ids stay in ignored private JSON.
- Private atoms expose a redacted subject plus hashes at top level; raw metadata is nested under `private_evidence`.
- The tracked report intentionally exposes only domains, counts, cluster names, atom ids, and synthesized theses.
- Gmail thread enrichment is a later gated action for atoms whose `next_action` requires it.

## Commands

- Preview the hot flagged pass: `python3 scripts/mail-story-ledger.py`
- Refresh the redacted report and ignored private atoms: `python3 scripts/mail-story-ledger.py --write`
- Reconcile live Gmail STARRED counts: `python3 scripts/mail-story-ledger.py --write --gmail-starred-messages <n> --gmail-starred-threads <n>`
- Reconcile a private Gmail metadata export: `python3 scripts/mail-story-ledger.py --write --gmail-starred-export .limen-private/mail-story/reconciliation/gmail-starred-export.json`
- Process all non-deleted indexed mail privately: `python3 scripts/mail-story-ledger.py --scope all --write`
