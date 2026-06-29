# 50-State UCC Public-Records Intelligence Platform - Proof Page

Public-safe August pipeline page for `organvm/public-record-data-scrapper`.

## Offer

Fresh, enriched, scored UCC lead intelligence for MCA funders, ISOs, brokers, and alternative-finance teams that need better data than recycled commodity lists.

## First Screen

Headline: `Fresh UCC filings, enriched and scored before your competitors call them.`

Subhead: `A 50-state public-records intelligence engine for MCA and alternative-finance teams: current filings, public and buyer-approved enrichment, financing-likelihood scoring, and delivery through CSV, REST API, dashboard, or CRM handoff.`

Primary CTA: `Request a sample feed for my states`

Secondary CTA: `See the scoring method`

## What Is Proven

- 50-state UCC collection surface.
- 60+ collection agents.
- 3399 passing tests.
- Terraform AWS shape for RDS, Redis, and S3.
- Dashboard, REST API, and CLI delivery surfaces.
- Enrichment model spanning public records plus key-gated premium sources.
- Financing-likelihood score from `0` to `100` and a buyer-readable health grade.

## Buyer Promise

The repo proves the platform shape; the service proves the operating feed. A buyer should leave this page knowing exactly what gets delivered:

| Need | Public proof | Paid operation |
|---|---|---|
| Fresh filings | Collector and normalization code | Scheduled state pulls and freshness checks |
| Prioritized queues | Scoring model and sample schema | Buyer-tuned thresholds, state filters, and exclusions |
| Handoff | API/dashboard/CLI surfaces | CSV, REST API, dashboard, CRM/dialer delivery |
| Confidence | Tests, Terraform, and observable pipeline shape | Current run logs, quality checks, and exclusivity rules |

## What Is Public

The public repo proves the form: collectors, tests, infra shape, scoring structure, and delivery surfaces. A buyer can inspect the build.

## What Is Paid

The paid service is the operation: fresh pulls, tuned scoring, buyer-specific filters, delivery cadence, CRM/dialer handoff, and exclusivity rules. The source can be public while the fed instance remains the product.

## Sample Output

Use `docs/positioning/public-record-data-scrapper-sample-output.json` as the public-safe sample. It uses fictional/redacted companies only; it does not expose real debtors, contacts, phone numbers, emails, premium data, or live prospect records.

The sample should appear on the proof page as a compact table plus an expandable JSON block. Show these columns first: state, filing age, industry hint, financing likelihood, health grade, confidence, recommended action, delivery formats.

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

Use source tag `public-record-data-scrapper-proof` for proof-page traffic and source tag `public-record-data-scrapper-sample` for sample-output requests. Do not add synthetic events; only count real visits, real qualified inbound, real replies, real calls, and real paid trials.
