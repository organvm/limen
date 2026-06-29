# 50-State UCC Public-Records Intelligence Platform - Proof Page

Public-safe August pipeline page for `organvm/public-record-data-scrapper`.

## Offer

Fresh, enriched, scored UCC lead intelligence for MCA funders, ISOs, brokers, and alternative-finance teams that need better data than recycled commodity lists.

## What Is Proven

- 50-state UCC collection surface.
- 60+ collection agents.
- 3399 passing tests.
- Terraform AWS shape for RDS, Redis, and S3.
- Dashboard, REST API, and CLI delivery surfaces.
- Enrichment model spanning public records plus key-gated premium sources.
- Financing-likelihood score from `0` to `100` and a buyer-readable health grade.

## What Is Public

The public repo proves the form: collectors, tests, infra shape, scoring structure, and delivery surfaces. A buyer can inspect the build.

## What Is Paid

The paid service is the operation: fresh pulls, tuned scoring, buyer-specific filters, delivery cadence, CRM/dialer handoff, and exclusivity rules. The source can be public while the fed instance remains the product.

## Sample Output

Use `docs/positioning/public-record-data-scrapper-sample-output.json` as the public-safe sample. It uses fictional/redacted companies only; it does not expose real debtors, contacts, phone numbers, emails, premium data, or live prospect records.

## Case Study

Use `docs/positioning/public-record-data-scrapper-case-study.md` as the buyer narrative: commodity UCC list to scored current feed.

## Contact Path

Primary CTA: `Deploy this for your shop`.

Contact routing is defined in `docs/positioning/public-record-data-scrapper-contact-path.md`. The current public contact switch remains controlled by `positioning-seeds.json` -> `frontdoor.contact`; until a dedicated inbound alias is set there, public CTAs stay non-addressed text.

## Buyer Qualification

A qualified inbound has all of:

- Buyer type: MCA funder, ISO, broker, or alternative-finance operator.
- Stated geography or state coverage need.
- Lead use case: feed, white-label deploy, custom scoring, or data-org retainer.
- Delivery path: CSV, API, dashboard, CRM, dialer, or managed handoff.
- Budget/timeline signal strong enough to justify a call.

## Scoreboard Contract

Every public push of this page should be tracked in `state/aug1/pipeline-scoreboard.json` as visits, qualified inbound, replies, calls, paid trials, and cash.

