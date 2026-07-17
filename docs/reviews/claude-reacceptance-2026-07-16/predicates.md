# Reacceptance Predicates

A row may be `accepted` only when all applicable facts are present and current:

1. The redacted source-ask reference resolves in the private prompt-corpus owner.
2. Actual execution spend is reconciled to one attempt and one executing keeper/session.
3. The exact commit or PR head is named; local-only output has a durable owner receipt.
4. Every outward side effect is inventoried without replay and has an owner-native receipt.
5. The scoped executable predicate passes on the deployed invocation path.
6. Current P1/P2 review debt is zero and `limen.pr_review_gate.v1` accepts the exact head after a
   distinct peer-keeper review through a native distinct login or verified SSH-signed
   execution-plus-review receipts from separately custodied principals.
7. The receipt is durable and remotely queryable.

`reverted` requires proof that the effect and code were safely reversed without deleting required
evidence. `superseded` requires a linked replacement whose own row is accepted. Otherwise the row
is `repair_required`.

The machine contract is fail-closed. Every terminal row carries a `predicate` with
`status: verified`, `result: passed`, the executed command, a timestamp, and the matching
`exact_head` when one exists. Its `receipt.adjudication` carries `status: verified`, the matching
terminal disposition, a durable URL or owner-bound SHA-256 digest, a timestamp, and the same exact
head. Accepted PRs additionally record an accepted review-gate result and a distinct reviewing
keeper. Reverted rows record `reversal_status: verified`. Superseded rows name a stable accepted
replacement row and its exact head when applicable.

The campaign release predicate is stricter than terminal classification: all rows must have
evidence-backed dispositions; current P1, P2, and unclassified unresolved debt must all be zero; and
every `completion_gates` entry must be `passed` with its own verified predicate and durable receipt.
The fixed gate set covers formerly open PR closure/reacceptance, session value, stale in-flight
custody, privacy containment, and the continuation fixed point. The validator derives
`summary.release_ready` from those facts and rejects either a manufactured `true` or a stale `false`.
