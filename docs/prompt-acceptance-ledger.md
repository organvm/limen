# Prompt Acceptance Ledger

Generated: `2026-06-29T22:00:45+00:00`

## Acceptance Frame

- `prompt_receipt`: What did we prompt, represented only by redacted ids/counts in tracked output.
- `evolved_intent`: What got addressed now; older repeats carry lineage weight, newer forms win.
- `owner_outcome`: What remains owner-recorded, closed, parked, or still needing a route.
- `august_runway_impact`: Whether this helps the Aug-1 operating checkpoint and late-August runway.
- `outward_reciprocity`: What was observed, absorbed, staged, gated, delivered, or not applicable.

Tracked output contains no raw prompt bodies, private session paths, full prompt hashes, or session ids.

## Coverage

- Acceptance packets: `87`.
- Prompt packets: `9` closed / `0` open / `9` total.
- Unpacketed review batches represented: `78`.
- Prompt events covered: `15069`.
- Unique prompt hash refs covered privately: `11427`.
- Acceptance status mix: `needs_private_review` 59, `closed` 24, `needs_reciprocity_gate` 2, `needs_owner_outcome` 2.
- Packet status mix: `owner-recorded` 8, `non-source-recorded` 1.

## August Runway

- Operational checkpoint: `2026-08-01`.
- Aug-1 gate: `false`; legs `0` / `5`.
- Hard runway premise: late-August unemployment runway.
- Runway note: Aug-1 remains the operational checkpoint; late-August unemployment remains the hard runway premise.

## Outward Reciprocity

- Status values: `absorbed`, `delivered`, `gated`, `not_applicable`, `observed`, `staged`.
- Receipt count: `1`.
- Status mix: `staged` 1.
- Identity-bearing outbound action stays human-gated; staged receipts are not sent automatically.

## Acceptance Queue

| Rank | Receipt | Status | Source | Prompt Coverage | Evolved Intent | Owner Outcome | August Impact | Reciprocity |
|---:|---|---|---|---|---|---|---|---|
| 1 | `packet-prompt-batch-critical-stalled-review-001-session_lifecycle` | `needs_reciprocity_gate` | prompt_packet / `session_lifecycle` | 14 sessions; 59 events; <=30d; lineage 114 | newer form wins; earlier repeats count as lineage evidence | `owner-recorded`; Owner outcome recorded in the private acceptance index. | Closes repeated session residue so August work is not re-prompted as fresh work. | `staged`; human gate |
| 2 | `packet-prompt-batch-high-stalled-review-001-session_lifecycle` | `needs_reciprocity_gate` | prompt_packet / `session_lifecycle` | 2 sessions; 9 events; <=30d; lineage 17 | newer form wins; earlier repeats count as lineage evidence | `owner-recorded`; Owner outcome recorded in the private acceptance index. | Closes repeated session residue so August work is not re-prompted as fresh work. | `staged`; human gate |
| 3 | `prompt-batch-high-remote-proof-001` | `needs_owner_outcome` | prompt_batch / `uncategorized` | 15 sessions; 143 events; <=1d; lineage 208 | newer form wins; earlier repeats count as lineage evidence | `needs-remote-proof`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 4 | `prompt-batch-critical-remote-proof-001` | `needs_owner_outcome` | prompt_batch / `uncategorized` | 5 sessions; 228 events; <=1d; lineage 326 | newer form wins; earlier repeats count as lineage evidence | `needs-remote-proof`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 5 | `prompt-batch-low-legacy-session-review-004` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 416 events; <=1d; lineage 806 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 6 | `prompt-batch-low-legacy-session-review-005` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 536 events; <=1d; lineage 1044 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 7 | `prompt-batch-low-legacy-session-review-006` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 464 events; <=1d; lineage 913 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 8 | `prompt-batch-critical-hash-review-001` | `needs_private_review` | prompt_batch / `uncategorized` | 2 sessions; 280 events; <=1d; lineage 409 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 9 | `prompt-batch-low-legacy-session-review-022` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 306 events; <=7d; lineage 586 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 10 | `prompt-batch-low-legacy-session-review-020` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 194 events; <=7d; lineage 350 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 11 | `prompt-batch-low-legacy-session-review-009` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 394 events; <=7d; lineage 761 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 12 | `prompt-batch-low-hash-review-001` | `needs_private_review` | prompt_batch / `uncategorized` | 2 sessions; 20 events; <=7d; lineage 32 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 13 | `prompt-batch-low-legacy-session-review-025` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 220 events; <=7d; lineage 407 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 14 | `prompt-batch-low-legacy-session-review-013` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 239 events; <=7d; lineage 428 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 15 | `prompt-batch-low-legacy-session-review-017` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 224 events; <=7d; lineage 394 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 16 | `prompt-batch-medium-historical-worktree-review-025` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 177 events; <=7d; lineage 319 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 17 | `prompt-batch-low-legacy-session-review-003` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 461 events; <=7d; lineage 902 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 18 | `prompt-batch-low-legacy-session-review-019` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 228 events; <=7d; lineage 422 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 19 | `prompt-batch-low-legacy-session-review-015` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 290 events; <=7d; lineage 551 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 20 | `prompt-batch-low-legacy-session-review-018` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 246 events; <=7d; lineage 449 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 21 | `prompt-batch-low-legacy-session-review-007` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 419 events; <=7d; lineage 811 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 22 | `prompt-batch-low-legacy-session-review-026` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 231 events; <=7d; lineage 433 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 23 | `prompt-batch-low-legacy-session-review-011` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 308 events; <=7d; lineage 577 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 24 | `prompt-batch-low-legacy-session-review-024` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 255 events; <=7d; lineage 486 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 25 | `prompt-batch-low-legacy-session-review-021` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 227 events; <=7d; lineage 426 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 26 | `prompt-batch-medium-historical-worktree-review-024` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 105 events; <=7d; lineage 186 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 27 | `prompt-batch-low-legacy-session-review-008` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 374 events; <=7d; lineage 742 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 28 | `prompt-batch-low-legacy-session-review-016` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 355 events; <=7d; lineage 695 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 29 | `prompt-batch-low-legacy-session-review-027` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 202 events; <=7d; lineage 411 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 30 | `prompt-batch-low-legacy-session-review-010` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 454 events; <=7d; lineage 903 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 31 | `prompt-batch-low-legacy-session-review-014` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 327 events; <=7d; lineage 649 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 32 | `prompt-batch-low-legacy-session-review-023` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 260 events; <=7d; lineage 493 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 33 | `prompt-batch-low-legacy-session-review-028` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 139 events; <=7d; lineage 281 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 34 | `prompt-batch-low-legacy-session-review-012` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 322 events; <=7d; lineage 603 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 35 | `prompt-batch-low-family-003` | `needs_private_review` | prompt_batch / `agent_coordination` | 22 sessions; 78 events; <=7d; lineage 147 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Prevents broad delegation churn from spending runway without owner receipts. | `not_applicable` |
| 36 | `prompt-batch-low-legacy-session-review-052` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 25 events; <=30d; lineage 75 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 37 | `prompt-batch-low-legacy-session-review-051` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 25 events; <=30d; lineage 75 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 38 | `prompt-batch-low-legacy-session-review-039` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 171 events; <=30d; lineage 337 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 39 | `prompt-batch-low-legacy-session-review-037` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 154 events; <=30d; lineage 307 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |
| 40 | `prompt-batch-low-legacy-session-review-035` | `needs_private_review` | prompt_batch / `uncategorized` | 25 sessions; 165 events; <=30d; lineage 315 | newer form wins; earlier repeats count as lineage evidence | `needs-private-review`; Owner outcome still pending in the private acceptance index. | Accepted only after it records an owner outcome that changes the August path. | `not_applicable` |

## Private Output

- Private acceptance index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-acceptance-ledger.json`.
- The private index keeps packet membership, full prompt hashes, session keys, and reciprocity links.

## Commands

- Refresh prerequisite packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh acceptance ledger: `python3 scripts/prompt-acceptance-ledger.py --write`
- Show a wider tracked slice: `python3 scripts/prompt-acceptance-ledger.py --write --limit 80`
