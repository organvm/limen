# Chain-of-Custody Register

**DRAFT - COUNSEL REVIEW ONLY - NOT LEGAL ADVICE**

This register tracks how records enter the legal-organ evidence room. It currently contains only repo-held institutional source records. No primary employer, medical, agency, court, or privileged attorney-client documents have been copied into this packet.

## Current Custody Entries

| Custody ID | Date | Actor | Action | Records | Boundary |
|---|---|---|---|---|---|
| CUST-2026-07-04-001 | 2026-07-04 | Codex in isolated worktree | Read existing legal-organ source records and derived the first matter packet | LEG-SRC-001 through LEG-SRC-004 | Internal repo sources only; no external send |
| CUST-2026-07-04-002 | 2026-07-04 | Codex in isolated worktree | Read health-organ handoff source records and linked them as context | LEG-SRC-005 through LEG-SRC-006 | Context source only; no medical records ingested |
| CUST-2026-07-04-003 | 2026-07-04 | Codex in isolated worktree | Created review artifacts for counsel/client review | `posture.md`, `elements-map.md`, `deadlines.md`, `ethics-log.md`, `drafts/micah-review-cover-note.md` | Draft work product; not sent, filed, served, or relied on |

## Primary Evidence Intake Protocol

Primary matter records require an explicit human gate before entry. When Micah or Anthony authorizes a record for indexing, the evidence clerk records:

| Field | Required entry |
|---|---|
| Evidence ID | Stable ID such as `ADA-REQ-001`, never a vague filename |
| Source holder | Who supplied the record: client, counsel, employer record copy, provider record copy, agency/court source |
| Original location | Where the original remains, without exposing credentials or private storage URLs |
| Date received | UTC date/time the legal organ received the copy |
| Hash | SHA-256 or other counsel-approved integrity hash when a file is stored |
| Privilege status | Counsel/client supplied classification before sharing or use |
| Scope note | What the record is being indexed to organize, not a legal conclusion |
| Review status | `unreviewed`, `client-confirmed`, `counsel-verified`, `excluded`, or `privileged-do-not-use` |

## Current Integrity Notes

- The current six evidence rows are institutional source records, not primary case evidence.
- Every current source path exists in this repository and is reviewable by counsel.
- No chain entry authorizes disclosure outside the attorney/client review channel.
- Any future stored primary record should receive a hash before summaries or excerpts are generated.

## Forbidden Custody Moves

- Do not copy privileged records into a public issue, PR body, task board, chat transcript, or non-privileged deck.
- Do not summarize medical, employment, or correspondence records into outbound text without counsel/client approval.
- Do not convert an indexed record into legal advice, a demand, a filing, service, negotiation, or settlement posture.
- Do not treat a repo-held derivative summary as the original record.
