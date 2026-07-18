# Whole-PR campaign receipts

These JSON files are complete, exact-head census receipts for the canonical `organvm` estate. Each
file records:

- the repository and open-PR pagination denominator;
- one `OWNER/REPO#NUMBER@HEAD` leaf per observed current head;
- a baseline disposition, owner surface, eligible action, and durable receipt target;
- a digest over the complete ordered leaf set.

They do not claim that a review, repair, or merge occurred. `review-candidate` means only that the
leaf is non-draft, non-empty, has a head, and belongs to a non-archived repository. Exact CI,
reviews, review threads, requested-changes state, and readiness remain separate exact-head evidence.

`2026-07-18-pass-1.json` is the first live baseline. `2026-07-18-pass-2.json` is the first repeated
complete pass. It is intentionally retained as negative fixed-point evidence: the open-PR
denominator moved from 1,143 to 1,145 heads, with 9 newly observed keys, 7 no-longer-observed keys,
and 6 moved heads. The comparison therefore returned `zero_growth: false`.

The closeout pass is run only after implementation verification, immediately before publication.
If the live estate still changes between complete passes, that delta remains owned evidence; it is
not rewritten into a false fixed point and it does not imply that campaign review or repair ran.
