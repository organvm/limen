# setup-rulesets.py — dry-run merge-gate contract

**Updated:** 2026-07-18 · **Status:** DRY-RUN ONLY — no repository setting has been changed.

## Limen's concurrency rail

`organvm/limen` has one targeted native merge-queue ruleset. It serializes only the final
integration step; concurrent agents keep working and proving their own exact PR heads without
repeatedly merging a moving `main`.

The ruleset targets `~DEFAULT_BRANCH` and contains exactly one rule, `merge_queue`:

| Setting | Value |
|---|---:|
| merge method | `SQUASH` |
| grouping strategy | `HEADGREEN` |
| required-check timeout | 60 minutes |
| concurrent queue builds | 4 |
| maximum PRs merged per group | 1 |
| minimum PRs per group | 1 |
| minimum-size wait | 0 minutes |

`HEADGREEN` plus a one-PR merge group proves the head synthetic integration commit. A maximum of
four groups may build concurrently, but GitHub merges them one at a time. This keeps the integration
window serialized without turning the whole agent fleet into one serial lane.

The ruleset deliberately does **not** add `pull_request`, `update`, required-workflow, or other
direct-push restrictions. Classic default-branch protection remains the owner of the required check:

- context: `pr-gate`
- `strict:false`
- `enforce_admins:false`
- no human-review requirement

That preserves the existing Tabularius admin data-only writer. The queue governs PR merges; it does
not replace Tabularius's single-writer contract or prohibit its authorized direct projection push.

## Queue CI contract

`.github/workflows/pr-gate.yml` is the only required workflow triggered by
`merge_group: checks_requested`.

- On `pull_request`, `scripts/verify.py --changed` requires a resolvable base and retains
  `--skip-ci-covered pr-gate.yml:pr-gate`. The PR's full CI children remain independently owned
  exact-head receipts.
- On `merge_group`, `scripts/verify.py --changed --integration` compares the checked-out synthetic
  group commit with `github.event.merge_group.base_sha`. Integration mode fails closed if that base
  cannot resolve, runs every implicated scoped gate, does not use `--skip-ci-covered`, and does not
  restart the whole PR matrix merely because `main` advanced.

GitHub documents `merge_group` as a separate event whose `GITHUB_SHA` is the synthetic group commit;
required checks must explicitly subscribe to it or the queue cannot receive their result.

## What setup-rulesets.py changes

The script is dry-run by default. For every selected repository it reports the planned classic
protection and repository settings. `--apply` is the only mutation switch.

For `organvm/limen`, apply performs these idempotent operations:

1. Enable auto-merge and preserve source branches (`delete_branch_on_merge=false`).
2. Write classic protection once with required context `pr-gate`, `strict:false`,
   `enforce_admins:false`, no required review, and no actor restriction.
3. Create `limen-default-merge-queue`, or update the ruleset with the same name, with the exact
   queue body above.

The source branches remain after merge so removal stays with receipt-backed reaping. The queue ruleset
does not add a blanket pull-request or direct-push prohibition.

Other repositories retain the existing detected-check behavior and do not receive a merge-queue
ruleset.

## Commands

Read-only targeted preview:

```bash
cd ~/Workspace/limen
python3 scripts/setup-rulesets.py --repo organvm/limen
```

Explicit targeted apply, only after the workflow change is merged and the operator authorizes the
repository-setting mutation:

```bash
cd ~/Workspace/limen
python3 scripts/setup-rulesets.py --apply --repo organvm/limen
```

Re-running the apply updates the named ruleset rather than creating a duplicate. The script makes no
remote mutation without the exact `--apply` token.

## Reversibility

- Queue ruleset:
  `gh api -X DELETE /repos/organvm/limen/rulesets/<ruleset-id>`
- Classic branch protection:
  `gh api -X DELETE /repos/organvm/limen/branches/main/protection`
- Auto-merge:
  `gh api -X PATCH /repos/organvm/limen -F allow_auto_merge=false`

No apply was run while producing this document.
