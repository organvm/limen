# Public Record Data Scraper - Contact Path

This is the public-safe inbound route for the August pipeline artifact.

## Current Switch

`positioning-seeds.json` -> `frontdoor.contact` is currently empty. That means public CTAs render as text and no email address is published.

To turn capture live, set `frontdoor.contact` to a dedicated inbound alias. Do not use a personal inbox address; this surface is meant to be indexed.

## CTA Subjects

When the contact alias is configured, route scraper CTAs with these subject tags:

- `[public-record-data-scrapper · deploy] - inbound`
- `[public-record-data-scrapper · feed] - inbound`
- `[public-record-data-scrapper · white-label] - inbound`
- `[public-record-data-scrapper · custom] - inbound`

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

