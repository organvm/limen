# Mail Story Ledger

Redacted control-plane view over the local mail story corpus. Raw/private atoms stay in the ignored
`.limen-private/mail-story/` cartridge; this tracked report keeps only counts, domains, hashes,
cluster ids, and synthesized pain-point theses.

## Snapshot

- Generated: `2026-07-07T14:02:24Z`
- Source: Apple Mail Envelope Index, opened read-only.
- Processed scope: `all`
- Batch offset: `2`
- Body/thread reads: `false`
- Mailbox mutations: `false`
- Private atom store: `.limen-private/mail-story/inventory/mail-story-atoms.jsonl`

## Corpus Counts

- Total indexed messages: `3`
- Non-deleted messages: `3`
- Flagged non-deleted messages: `0`
- First received: `2021-05-03 00:00:00`
- Last received: `2021-05-03 00:00:02`
- Atoms emitted in this run: `1`

## Pain Point Clusters

| cluster | type | atoms | priority | next actions | software thesis |
| --- | --- | --- | --- | --- | --- |
| Uncategorized pressure | other | 1 | 25 | read_thread:1 | A story-mining workflow should park ambiguous mail with evidence and a next read action. |

## Top Sender Domains In Processed Scope

| domain | messages |
| --- | --- |
| example.com | 1 |

## Flagged By Mailbox

| mailbox scope | messages |
| --- | --- |
| - | 0 |

## Flagged By Year

| year | messages |
| --- | --- |
| - | 0 |

## Privacy Boundary

- No message body text is read by this pass.
- Full sender addresses, sender display names, subjects, summaries, and Apple row ids stay in ignored private JSON.
- The tracked report intentionally exposes only domains, counts, cluster names, and synthesized theses.
- Gmail thread enrichment is a later gated action for atoms whose `next_action` requires it.

## Commands

- Preview the hot flagged pass: `python3 scripts/mail-story-ledger.py`
- Refresh the redacted report and ignored private atoms: `python3 scripts/mail-story-ledger.py --write`
- Process all non-deleted indexed mail privately: `python3 scripts/mail-story-ledger.py --scope all --write`
