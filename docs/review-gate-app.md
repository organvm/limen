# Dedicated review-gate App contract

`limen.pr_review_gate.v1` is an exact-head acceptance receipt, not a status label. The authoritative
producer is a separately installed GitHub App. Generic GitHub Actions publishes only
`limen.pr_review_gate.diagnostic.v1`; it can neither satisfy branch protection nor authorize a
merge consumer.

## Acceptance inputs

The evaluator reads two complete normalized snapshots. Each snapshot cursor-paginates current-head
checks, review threads, issue comments, native reviews, and changed files. A changed head or changed
normalized evidence between snapshots rejects. Acceptance requires:

- at least one successful non-gate project check and no pending, failed, or unknown project check;
- no unresolved current review thread;
- one active native `APPROVED` review on the exact head from a repository collaborator, member, or
  owner distinct from the GitHub principal on the head commit; and
- complete comment, review, thread, check, and file evidence.

The report names the head-commit executor and whether it came from the commit's GitHub committer or
author. GitHub's native `require_last_push_approval` rule remains the authority for who performed the
network push. A caller-supplied allowed-signers file is not an authenticated custody source and is
rejected as review authority.

## CheckRun publication

The App evaluates without requiring its own prior result, so it cannot circularly block. It filters
lookalike `limen.pr_review_gate.v1` markers by App identity before parsing or counting them. The App
then publishes one bounded `limen.pr_review_gate.check_receipt.v1` envelope:

- the complete target and adjudication fields;
- the normalized evidence digest;
- a digest of the receipt body; and
- an `external_id` binding that receipt digest.

Publication first proves that the active installation credentials match both the configured App
slug and the provisioned `LIMEN_REVIEW_GATE_APP_ID`. It updates
the same current-head CheckRun when one exists, re-reads its version before mutation, and reads the
written CheckRun back afterward. App identity, target head, conclusion, receipt body, receipt
digest, and `external_id` must all agree. Merge consumers use `--require-published-result` and
require the current successful App receipt whose evidence digest still matches live normalized
evidence.

The repository workflow is intentionally diagnostic-only. App creation, account billing/plan
changes, private-repository protection support, installation on all seven repositories, and
reviewer credentials remain external owner gates.

## Sacrificial protection proof

Before installing protection estate-wide, use one minimal bootstrap PR and record the exact head.

1. Green project CI plus an unresolved current thread must remain rejected and unmergeable.
2. Resolve the thread and obtain one native exact-head approval from a principal distinct from the
   head-commit executor. The App receipt and native protection must pass.
3. Push a subsequent commit. The prior approval and App receipt must no longer satisfy the new head.
4. Re-review the new exact head and confirm protection readback: strict checks, App-bound context,
   one native approval, last-push approval, stale dismissal, resolved conversations, and admin
   enforcement.

Run `scripts/setup-rulesets.py --apply --review-app-slug <slug>` only after that proof exists. The
script defaults to the frozen seven-repository cohort and fails closed for any repository without a
live accepted App receipt or supported protection surface.
