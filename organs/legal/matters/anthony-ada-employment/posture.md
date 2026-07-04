# Case-posture brief - Anthony ADA employment matter

> Boundary: legal-operations posture for attorney review. This does not give
> legal advice and does not give legal advice implicitly through posture labels,
> risk labels, or next-step tracking. It does not practice law, assess merits,
> or decide strategy. Micah Longo, Esq. owns every legal judgment, deadline,
> filing, communication, and use of this material.

## Snapshot

| Field | Posture |
|---|---|
| Matter | Anthony ADA employment/accommodation matter |
| Counsel | Micah Longo, Esq. |
| Organ role | Back-office bench: posture, evidence index, custody discipline, deadlines posture, draft skeletons |
| Current status | `ATTORNEY_REVIEW_PACKET_STAGED` |
| Packet date | 2026-07-03 |
| Current evidence posture | Repository-level source artifacts indexed; private matter documents not ingested |
| External action | None. This packet is staged only. |

## What is known now

- The legal organ is the flagship Cochran-standard prototype.
- The micro instance is Anthony's active ADA employment/accommodation matter.
- The organ augments Micah's representation and does not replace counsel.
- The linked health organ records that accommodation documentation can feed the
  legal organ, while the health organ itself does not provide legal advice.
- No attorney-confirmed litigation deadlines, venue, case number, agency charge,
  or private evidence packet is present in this worktree.

## Open obligations

| Obligation | Owner | Status | Why it matters |
|---|---|---|---|
| Confirm matter scope and posture labels | Micah | Needed | Prevents the organ from encoding the wrong legal frame |
| Supply or identify source records through privileged channel | Anthony + Micah | Needed | Makes the evidence index litigation-grade |
| Confirm jurisdiction, forum, agency/court posture, and deadlines | Micah | Needed | Converts `deadlines.md` into an attorney-approved calendar |
| Approve a counsel-supplied elements map | Micah | Needed | Keeps the system from performing legal analysis |
| Decide whether Anthony may send the cover note/deck | Anthony | Staged | Outbound communication requires his hand |

## Risk register

| Risk | Current control | Human gate |
|---|---|---|
| Unauthorized practice of law | Every artifact states no legal advice/no filing/no sending; validator checks required boundary language | Micah reviews all outputs |
| Privilege leakage | Private records are not placed in this public repo; pending evidence rows require privileged-channel intake | Micah determines privilege handling |
| False precision | Unknown deadlines and facts are marked unconfirmed instead of guessed | Micah confirms dates and facts |
| Fabricated authority | No legal citations or element conclusions are asserted in this slice | Micah supplies/approves authorities |
| Stale posture | Packet has a dated status and required review cadence | Legal organ reruns after new facts |

## Next honest step

Show Micah the framework deck and this packet, then ask for the smallest
attorney-controlled correction set:

1. confirm/correct the matter label;
2. confirm the forum and any deadlines;
3. approve the evidence categories to ingest first;
4. decide whether an elements map should be built from counsel-supplied
   authorities.

Until those corrections arrive, this packet is a working institutional proof,
not a litigation record ready for use.
