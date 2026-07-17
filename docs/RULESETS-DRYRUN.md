# `setup-rulesets.py` fail-closed contract

The historical self-draining/CI-only recommendation is superseded. The current script never enables
GitHub auto-merge and never treats the generic `github-actions` App as an independent acceptance
principal; source branches remain after merge for receipt-backed reaping.

The default invocation is a read-only plan:

```bash
python3 scripts/setup-rulesets.py
```

`--apply` is an explicit, gated repository-settings mutation. Each target repository must already
have all of the following live evidence:

- a readable default branch;
- at least one project CI context from the current PR surface (or an explicit `--contexts` list);
- `.github/workflows/pr-review-gate.yml` on the live default branch;
- `LIMEN_REVIEW_GATE_APP_SLUG` naming a dedicated GitHub App; and
- a current `limen.pr_review_gate.v1` CheckRun whose live App slug maps uniquely to one App id.

`github-actions` is rejected as the configured slug. GitHub branch protection binds a required check
to an App id, not to a particular workflow file or event. Every workflow in a repository shares the
generic Actions App identity, so another base workflow could otherwise emit the same context. The
dedicated App must be provisioned and custodied outside Limen, configured to publish the review-gate
CheckRun, and named explicitly at apply time. Until that owner contract exists, setup fails closed and
makes no protection mutation.

For an eligible repository, apply uses this order:

1. `PATCH /repos/{repo}` with `allow_auto_merge=false` and
   `delete_branch_on_merge=false`.
2. Re-read the repository and require both values to be exactly false.
3. Only after that confirmation, `PUT` branch protection requiring strict current-head project CI
   plus the dedicated-App-bound `limen.pr_review_gate.v1`, stale review dismissal, zero native
   approval count, resolved conversations, and administrator enforcement.
4. Re-read both repository settings and branch protection. Verify the exact required context/App-id
   pairs, `strict=true`, admin enforcement, conversation resolution, the complete review policy,
   no push restrictions, auto-merge false, and branch deletion false.

A failed PATCH, failed or malformed read, live-state mismatch, failed protection PUT, or failed final
verification makes the command nonzero. Repositories are processed independently and all failures are
aggregated into the final nonzero result. A partial transaction remains fail closed: protection is
never installed before auto-merge and branch retention are confirmed, and a later failure never
re-enables auto-merge.

The review status itself accepts either a distinct native GitHub reviewer or the separately signed
exact-head execution/review receipt path. The signature trust material is separately Domus-owned;
branch-protection App custody and keeper receipt-signing custody are distinct controls.
The signed execution receipt belongs only to the same-login SSH fallback, where it separates the
executing and reviewing principals. A native approval from a distinct GitHub login uses the PR
author, exact reviewed commit, and latest decisive review directly; it does not manufacture a
second signature. Execution-trajectory value credit is a separate shadow authority and is never
inferred from either review path.

Apply only after the dedicated App owner has published its live mapping:

```bash
export LIMEN_REVIEW_GATE_APP_SLUG='<dedicated-app-slug>'
python3 scripts/setup-rulesets.py --apply --repo owner/repository
```

There is no automatic merge or branch-deletion follow-up. Merge effects remain owned by the signed,
exact-head merge authorization path, and branch deletion remains owned by receipt-backed lifecycle
reaping.
