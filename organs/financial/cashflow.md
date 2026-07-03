# Financial Office — Rolling Cash-Flow Projection

> Generated: 2026-07-03T08:14:31Z
> *Forward-looking estimate based on known revenue stages and obligations.
> Confidence increases as more balances are confirmed.*

## Assumptions

- No revenue is yet flowing (all products pre-revenue or deploy-ready)
- First revenue projected: ChatGPT Exporter (rank 1, deploy-ready)
- Current obligations are drawn from `obligations-ledger.json`
- All amounts are estimates until principal confirms

## Revenue Pipeline

| Rank | Product | Stage | Path to First Dollar |
|---|---|---|---|
| 1 | ChatGPT Exporter | deploy-ready | live page + Pro tier via Lemon Squeezy (already integrated) or Ko-fi donations now — individual rail, NOT the dead-LLC Stripe |
| 2 | Public Record Data Scraper | building | data-as-a-service / one-off scrape gigs once deployed |
| 3 | Universal Mail Automation | building | subscription on the automation tier once live |
| 4 | The Invisible Ledger | building | paid tier once live |
| 5 | Mirror Mirror | building | paid tier once live |
| 6 | Styx | building | paid tier once live |

## 12-Week Rolling Projection

| Week | Starting | Known Inflows | Known Outflows | Net | Cumulative | Note |
|---|---|---|---|---|---|---|
| W1 | 2026-07-03 | — | — | $+0.00 | $+0.00 | Pre-revenue — deploy Exporter to start pipeline |
| W2 | 2026-07-10 | — | — | $+0.00 | $+0.00 |  |
| W3 | 2026-07-17 | — | — | $+0.00 | $+0.00 |  |
| W4 | 2026-07-24 | — | — | $+0.00 | $+0.00 |  |
| W5 | 2026-07-31 | — | — | $+0.00 | $+0.00 |  |
| W6 | 2026-08-07 | — | — | $+0.00 | $+0.00 |  |
| W7 | 2026-08-14 | — | — | $+0.00 | $+0.00 |  |
| W8 | 2026-08-21 | — | — | $+0.00 | $+0.00 |  |
| W9 | 2026-08-28 | — | — | $+0.00 | $+0.00 |  |
| W10 | 2026-09-04 | — | — | $+0.00 | $+0.00 |  |
| W11 | 2026-09-11 | — | — | $+0.00 | $+0.00 |  |
| W12 | 2026-09-18 | — | — | $+0.00 | $+0.00 |  |

### Runway alert

- **Current runway:** Unknown (no balance data). Set balances in `entities.yaml` to enable runway calculation.
- **Threshold:** < 4 weeks of obligations = alert principal.

## Obligations (financial-material)

Sourced from `obligations-ledger.json` — 2 protocol-class obligations:

| Priority | Title | Owner | Next Step |
|---|---|---|---|
| 88 | Student loan — default risk — U.S. Department of Education | yours | Log in at nelnet.studentaid.gov: check default status, recertify the income-driven repayment plan, and set the lowest viable payment. |
| 78 | KYC / identity verification — Stripe | yours | Provide the exact info requested. Note: Stripe KYC is blocked on the dead LLC — prefer the individual monetization rail (Ko-fi/Lemon Squeezy). |
