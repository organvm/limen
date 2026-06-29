# Case Study - Commodity UCC Lists To Scored Current Feed

This is a public-safe representative case study for the August pipeline. It does not name a real customer and does not expose live lead data.

## Starting Point

An MCA or ISO team is buying generic UCC lists. The lists are stale, duplicated, thinly enriched, and already worked by competitors. Closers spend expensive time on bad records, and the team cannot tell which filings are worth same-day action.

The operating symptoms are simple:

- The same debtor appears in multiple vendor lists with no freshness signal.
- Filing date, secured-party type, entity match, and public enrichment are not normalized.
- Sales leaders cannot separate same-day opportunities from low-confidence rows.
- CRM import quality is inconsistent enough that closers distrust the queue.

## Intervention

The platform turns the lead source into an operated data feed:

- Collect filings across all 50 Secretary-of-State surfaces.
- Normalize records into a consistent debtor and filing shape.
- Enrich from public sources and buyer-approved premium sources.
- Score each record for financing likelihood.
- Deliver daily rows through dashboard, REST API, and CSV.
- Tune filters to the buyer's geography, risk appetite, and sales motion.

The public proof page should show the workflow without exposing private data:

1. Pull a public-safe fictional UCC row.
2. Normalize debtor, secured-party, filing-age, state, and industry-hint fields.
3. Add public-safe enrichment signals.
4. Apply the financing-likelihood score and health grade.
5. Route the row to a recommended buyer action.

## Buyer Outcome

The buyer stops treating UCC data as a commodity list and starts treating it as an operating feed:

- Fresh filings are visible before stale-list competitors work them.
- Closers get score-ranked queues instead of flat spreadsheets.
- The buyer can choose states, filters, delivery cadence, and exclusivity rules.
- Paid work starts as a feed and can deepen into white-label deploy or custom scoring.

The success measures are operational, not vanity metrics:

- Same-day reviewed filings.
- Qualified rows delivered per state.
- Duplicate or low-confidence rows filtered out before a closer sees them.
- Calls booked from score-ranked queues.
- Paid pilot or feed renewal from the buyer.

## Proof To Show Publicly

- Source, tests, collectors, infrastructure shape, and API/dashboard surfaces.
- Fictional sample output only.
- No real debtor contact data, no premium-source rows, no live customer data.

## Public-Safe Caveat

This case study is representative. It must not imply a named customer, current production pull, premium-source coverage, conversion rate, or guaranteed funded-deal outcome unless that evidence is separately approved for publication.

## Close

The repo proves the platform. The paid engagement runs the fresh, tuned, buyer-specific operation.
