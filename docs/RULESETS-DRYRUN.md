# `setup-rulesets.py` containment and protection contract

The historical automatic-merge/CI-only recommendation is superseded. The current script never enables
GitHub auto-merge and never treats generic `github-actions` as an independent acceptance principal.
Source branches remain after merge for receipt-backed reaping.

Containment and protected-rule installation are separate operations. Both preview by default.

## Immediate containment

The read-only preview covers the frozen seven-repository recovery cohort unless one or more explicit
`--repo owner/name` arguments narrow the scope:

```bash
python3 scripts/setup-rulesets.py --contain
python3 scripts/setup-rulesets.py --contain --repo organvm/limen
```

Preview paginates every open pull request and inspects both repository settings. It exits nonzero
when any active auto-merge request exists, either setting is not exactly false, or the evidence
cannot be read completely. A zero exit therefore means the selected repositories are already
contained; it is not a mutation receipt.

The explicit containment mutation is:

```bash
python3 scripts/setup-rulesets.py --contain apply
python3 scripts/setup-rulesets.py --contain apply --repo organvm/limen
```

For each selected repository, apply performs this order:

1. Patch `allow_auto_merge=false` and `delete_branch_on_merge=false`.
2. Read both settings back and require exact false values before cancelling anything.
3. Paginate every open pull request and cancel each current `autoMergeRequest`.
4. Re-read the settings and re-inventory all pages after each cancellation pass.
5. Require two consecutive complete empty inventories while the settings remain false.

The drain is bounded. A failed patch, unreadable or mismatched setting, pagination failure,
cancellation failure that remains live, settings drift, or failure to reach the stable-empty fixed
point makes that repository nonzero. Other selected repositories are still attempted. Malformed or
missing `--repo` values are argument errors; they never expand to the default cohort.

Disabling repository auto-merge before inventory closes the arming race. Existing requests are then
drained while new requests cannot lawfully be armed.

## Later protected-rule installation

Protection apply is separate and does not change repository merge settings:

```bash
python3 scripts/setup-rulesets.py
python3 scripts/setup-rulesets.py --apply \
  --review-app-slug '<dedicated-app-slug>' \
  --repo organvm/limen
```

Before protection is installed, the selected repository must already have:

- confirmed containment settings;
- current project CI contexts;
- a dedicated review-gate GitHub App named by `--review-app-slug`; and
- a recent complete, accepted `limen.pr_review_gate.v1` receipt published by that App.

This preflight is central-App evidence, not a per-repository workflow-file test. Generic
`github-actions`, same-named statuses, incomplete receipts, invalid receipt digests, and ambiguous
App IDs are rejected. For an eligible repository, protection requires strict current-head project
CI plus the App-bound gate, one native approval, approval by someone other than the last pusher,
stale-review dismissal, resolved conversations, and administrator enforcement. The script reads
repository settings and protection back and requires the full contract on every selected
repository. With no `--repo`, that means all seven recovery-cohort repositories.

Missing CI, App installation, private-repository plan support, or branch-protection permission can
block protected-rule installation, but none of those prerequisites block the independent
containment operation.

## Safety boundary

Neither preview mutates GitHub. Do not run either apply operation without the corresponding owner
authorization. This script performs no merges, branch deletion, history rewriting, or task-board
mutation.
