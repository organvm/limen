# August Pipeline Scoreboard

This is the no-ambiguity scoreboard for the August inbound push.

## Source Of Truth

- Visits, qualified inbound, replies, calls, and paid trials: `state/aug1/pipeline-scoreboard.json`
- Cash: `state/aug1/revenue-received.json`
- Signed engagements: `state/aug1/engagements.json`
- Visible board: `scripts/aug1-view.py` renders the six pipeline metrics into `web/app/public/aug1.html`.

## Metric Definitions

| Metric | Counts When | Does Not Count |
|---|---|---|
| visits | A real public proof-page or inbound-surface visit is recorded. | Local previews, bot noise, accidental refreshes. |
| qualified inbound | A buyer message meets the qualification gate in `docs/positioning/public-record-data-scrapper-contact-path.md`. | Generic praise, spam, non-buyer chat, unqualified curiosity. |
| replies | A real human reply is sent or received. | Drafts, generated copy, unsent messages. |
| calls | A qualified buyer call is scheduled or completed. | Internal planning, unconfirmed availability, canceled non-buyer calls. |
| paid trials | A buyer pays for a trial, pilot, audit, feed, or scoped setup. | Free demos, verbal interest, unsigned intent. |
| cash | Cleared money in `state/aug1/revenue-received.json`. | Forecasts, invoices sent, verbal commitments, uncleared payments. |

## Current State

As created, all six metrics are `0`. That is intentional. The point is not to show momentum; the point is to make absence impossible to hide.

