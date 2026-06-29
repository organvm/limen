# Public Record Data Scraper - Contact Path

This is the public-safe inbound route for the August pipeline artifact.

## Current Switch

`positioning-seeds.json` -> `frontdoor.contact` is currently empty. That means public CTAs render as text and no email address is published.

To turn capture live, set `frontdoor.contact` to a dedicated inbound alias. Do not use a personal inbox address; this surface is meant to be indexed.

Until that switch is set, the proof page can still publish the CTA labels below as non-addressed text. Do not add a personal email, phone number, customer name, prospect list, or live buyer detail to this file.

## CTA Copy

- Primary: `Request a sample feed for my states`
- Feed path: `I want scored UCC leads for these states`
- White-label path: `I want this running under my brand`
- Custom path: `I need scoring tuned to my underwriting`
- Recruiter bridge: `I want the builder behind this system`

## CTA Subjects

When the contact alias is configured, route scraper CTAs with these subject tags:

- `[public-record-data-scrapper · deploy] - inbound`
- `[public-record-data-scrapper · feed] - inbound`
- `[public-record-data-scrapper · white-label] - inbound`
- `[public-record-data-scrapper · custom] - inbound`

## Intake Questions

Ask for these fields in the first human reply or future capture form:

- Buyer type: MCA funder, ISO, broker, lender, data buyer, or other.
- Target states or coverage geography.
- Desired cadence: daily, weekly, one-time audit, or custom.
- Desired delivery: CSV, REST API, dashboard, CRM, dialer, or managed handoff.
- Minimum row quality signal: freshness window, score threshold, industry filter, or exclusion rule.
- Decision timeline and pilot budget.

## Qualification Gate

Classify an inbound as `qualified_inbound` only when the message identifies at least three of:

- Buyer role or company type.
- Target states or coverage geography.
- Lead volume or delivery cadence.
- Desired output: feed, dashboard, API, CSV, CRM, dialer.
- Timeline or budget signal.
- Authority to buy or introduce the buyer.

## Reply Gate

Count `reply` only when a real human reply is sent or received. Drafts do not count.

## Call Gate

Count `call` only when a buyer call is scheduled or completed with a qualified prospect.

## Paid Trial Gate

Count `paid_trial` only when the buyer pays for a pilot, trial feed, audit, or scoped setup. If money clears, also append the payment to `state/aug1/revenue-received.json`.

## Scoreboard Mapping

Use `state/aug1/pipeline-scoreboard.json` for non-cash events:

- `visit`: real proof-page visit or sample-output request.
- `qualified_inbound`: message passes the qualification gate above.
- `reply`: a real human reply is sent or received.
- `call`: qualified buyer call is scheduled or completed.
- `paid_trial`: paid pilot, audit, trial feed, or scoped setup starts.

Use `state/aug1/revenue-received.json` only for cleared cash. Do not count projected contract value, unpaid trials, verbal interest, drafts, private customer data, or raw emails.
