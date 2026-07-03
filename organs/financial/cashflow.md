# Financial Office — Rolling Cash-Flow Projection

> Generated: 2026-07-03T19:38:43Z
> *Forward-looking estimate based on known revenue stages and obligations.
> Confidence increases as more balances and obligation amounts are confirmed.*

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
| W1 | 2026-07-03 | — | — | $+0.00 | $+0.00 |  |
| W2 | 2026-07-10 | — | — | $+0.00 | $+0.00 |  |
| W3 | 2026-07-17 | — | — | $+0.00 | $+0.00 | post-deploy |
| W4 | 2026-07-24 | — | — | $+0.00 | $+0.00 | post-deploy |
| W5 | 2026-07-31 | — | — | $+0.00 | $+0.00 | post-deploy |
| W6 | 2026-08-07 | — | — | $+0.00 | $+0.00 | post-deploy |
| W7 | 2026-08-14 | — | — | $+0.00 | $+0.00 | post-deploy |
| W8 | 2026-08-21 | — | — | $+0.00 | $+0.00 | post-deploy |
| W9 | 2026-08-28 | — | — | $+0.00 | $+0.00 | post-deploy |
| W10 | 2026-09-04 | — | — | $+0.00 | $+0.00 | post-deploy |
| W11 | 2026-09-11 | — | — | $+0.00 | $+0.00 | post-deploy |
| W12 | 2026-09-18 | — | — | $+0.00 | $+0.00 | post-deploy |

### Runway

- **Current net position:** Unknown — set balances in `entities.yaml` to enable runway calculation.
- **Threshold:** < 4 weeks of obligations = alert principal.

## Obligations (financial-material)

Sourced from `obligations-ledger.json` — 12 protocol-class obligations:

| Priority | Title | Owner | Next Step |
|---|---|---|---|
| 95 | Security — credential change — U.S. Department of Education | yours | VERIFY you made this change. If NOT you: secure the account immediately (change password, revoke sessions/third-party access). |
| 95 | Security — credential change — nelnet.studentaid.gov | yours | VERIFY you made this change. If NOT you: secure the account immediately (change password, revoke sessions/third-party access). |
| 90 | Fraud alert — verify first — Stripe | yours | VERIFY the sender is genuine (fraud notices are heavily spoofed — do NOT click links). If real, call the number on the back of the card. |
| 90 | Fraud alert — verify first — Santander Bank | yours | VERIFY the sender is genuine (fraud notices are heavily spoofed — do NOT click links). If real, call the number on the back of the card. |
| 88 | Student loan — default risk — Nelnet | yours | Log in at nelnet.studentaid.gov: check default status, recertify the income-driven repayment plan, and set the lowest viable payment. |
| 88 | Student loan — default risk — U.S. Department of Education | yours | Log in at nelnet.studentaid.gov: check default status, recertify the income-driven repayment plan, and set the lowest viable payment. |
| 82 | Billing — payment failed — Anthropic | yours | Root cause is the card-0186 hold — resolve THAT first, then update the payment method here. (Cascades to Anthropic / Google Cloud / GitHub.) |
| 82 | Billing — payment failed — Google Cloud Platform | yours | Root cause is the card-0186 hold — resolve THAT first, then update the payment method here. (Cascades to Anthropic / Google Cloud / GitHub.) |
| 78 | KYC / identity verification — Stripe | yours | Provide the exact info requested. Note: Stripe KYC is blocked on the dead LLC — prefer the individual monetization rail (Ko-fi/Lemon Squeezy). |
| 48 | Domain renewal — Hostinger | yours | Decide which domains are worth keeping; renew those, let the rest lapse. |
| 32 | Infra alarm (self) — mail.anthropic.com | yours | Your own infra signal — the system self-heals. No action unless you want to raise the limit / preserve the resource. |
| 28 | App update — ChatGPT | yours | Update the app if still in use; otherwise ignore (low risk, often past deadline). |
