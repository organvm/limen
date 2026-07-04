# Financial Office — Obligation Action Plan

> Generated: 2026-07-04T17:23:32Z
> *Principal-safe operating queue. This stages work; it does not move money, file forms, or click external portals.*

## Operating Rule

1. Work top-down by band, then priority.
2. External portals, phone calls, payments, filings, and irreversible account changes stay principal-gated.
3. Each closed row needs a receipt: confirmation number, screenshot path, ledger entry, or explicit principal note.

## Queue

Sourced from `entities.yaml registry fallback` — 11 financial-material obligations.

| Band | Priority | Due Window | Obligation | Entity/Owner | Amount | Gate | Next Step | Receipt |
|---|---:|---|---|---|---|---|---|---|
| P0 | 95 | same-day verification | Security — credential change — U.S. Department of Education | anthony-personal | unknown | principal-hand | VERIFY you made this change. If NOT you: secure the account immediately (change password, revoke sessions/third-party access). | Record receipt in entities.yaml or obligations ledger under `ed-security-change`. |
| P0 | 90 | same-day verification | Fraud alert — verify first — Santander Bank | anthony-personal | unknown | principal-hand | VERIFY the sender is genuine (fraud notices are heavily spoofed — do NOT click links). If real, call the number on the back of the card. | Record receipt in entities.yaml or obligations ledger under `santander-fraud-alert`. |
| P0 | 90 | same-day verification | Fraud alert — verify first — Stripe | anthony-personal | unknown | principal-hand | VERIFY the sender is genuine (fraud notices are heavily spoofed — do NOT click links). If real, call the number on the back of the card. | Record receipt in entities.yaml or obligations ledger under `stripe-fraud-alert`. |
| P1 | 88 | this week | Student loan — default risk — Nelnet | anthony-personal | unknown | principal-hand | Log in at nelnet.studentaid.gov: check default status, recertify the income-driven repayment plan, and set the lowest viable payment. | Record receipt in entities.yaml or obligations ledger under `nelnet-student-loan-default`. |
| P1 | 88 | this week | Student loan — default risk — U.S. Department of Education | anthony-personal | unknown | principal-hand | Log in at nelnet.studentaid.gov: check default status, recertify the income-driven repayment plan, and set the lowest viable payment. | Record receipt in entities.yaml or obligations ledger under `student-loan-default`. |
| P1 | 82 | this week | Billing — payment failed — Anthropic | anthony-personal | unknown | principal-review | Root cause is the card-0186 hold — resolve THAT first, then update the payment method here. (Cascades to Anthropic / Google Cloud / GitHub.) | Record receipt in entities.yaml or obligations ledger under `anthropic-billing-failed`. |
| P1 | 82 | this week | Billing — payment failed — Google Cloud Platform | anthony-personal | unknown | principal-review | Root cause is the card-0186 hold — resolve THAT first, then update the payment method here. (Cascades to Anthropic / Google Cloud / GitHub.) | Record receipt in entities.yaml or obligations ledger under `gcp-billing-failed`. |
| P2 | 78 | next 30 days | KYC / identity verification — Stripe | sovereign-systems-llc | unknown | principal-review | Prefer individual monetization rail (Ko-fi/Lemon Squeezy/MONETA) — dead LLC blocks Stripe KYC | Record receipt in entities.yaml or obligations ledger under `stripe-kyc`. |
| P3 | 48 | watchlist | Domain renewal — Hostinger | anthony-personal | unknown | principal-hand | Decide which domains are worth keeping; renew those, let the rest lapse. | Record receipt in entities.yaml or obligations ledger under `hostinger-domain-renewal`. |
| P3 | 32 | watchlist | Infra alarm (self) — mail.anthropic.com | limen | unknown | daemon-monitor | Your own infra signal — the system self-heals. No action unless you want to raise the limit / preserve the resource. | Record receipt in entities.yaml or obligations ledger under `mail-anthropic-infra-alarm`. |
| P3 | 28 | watchlist | App update — ChatGPT | anthony-personal | unknown | principal-review | Update the app if still in use; otherwise ignore (low risk, often past deadline). | Record receipt in entities.yaml or obligations ledger under `chatgpt-app-update`. |

## Gate Notes

- **principal-hand:** Requires the principal in an external portal or phone channel.
- **principal-review:** Principal reviews and either records receipt or delegates.
- **daemon-monitor:** System watches; principal acts only if threshold changes.
