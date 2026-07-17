# Reacceptance Continuation Capsule

## Objective

Continue the shared-keeper recovery from live evidence until each frozen session, workflow, and PR
row has an evidence-backed terminal disposition. Claude, Codex, Gemini, OpenCode, and every other
canonical executor are co-equal peer keepers. An executor name records provenance and routing only;
it never grants authority over another keeper or its live session.

## Evidence index

- `scope.json` freezes the current historical denominator.
- `ledger.json` records the redacted row-by-row reconciliation state.
- `external-actions.md` prevents unsafe replay of already-observed outward actions.
- `privacy-containment.md` records the restricted-repository containment boundary.
- `predicates.md` defines row acceptance and campaign release.

The private prompt-corpus owner contains source lineage and sensitive evidence. Do not copy raw
prompts, personal records, private paths, full hashes, or credentials into this tracked capsule.

## Authorities and prohibitions

- Continue isolated, reversible repair and read-only verification in parallel with healthy peer
  sessions.
- Do not stop, retune, close, subordinate, or mutate another keeper's live session or permission
  settings.
- Do not edit `tasks.yaml` from this direct-session lane; TABVLARIVS remains the serialization
  boundary for board projection, not a superior agent.
- Do not merge merely because CI is green. Require exact-head CI, zero current unresolved review
  conversations, and a distinct peer-review receipt through either a distinct native login or the
  separately custodied SSH-signed execution-plus-review path.
- Do not apply branch protection until the gate source is present on the live default branch and a
  separately custodied dedicated GitHub App publishes the required context. The generic
  `github-actions` identity is not workflow-bound and must never satisfy this trust boundary.
- Do not replay mail, calendar, storage, media, host, or remote-backup effects. Preview paths must be
  zero-write; apply paths require an owner-native authorization receipt.
- Do not rewrite history, delete personal material, roll back live host state, or restore repository
  visibility without the applicable human and custody gates.

## Current fail-closed residuals

- All 105 frozen ledger rows remain `repair_required`; this capsule is a recovery receipt, not an
  acceptance claim. Current P1/P2 review debt has not reached zero.
- The replacement host-pressure implementation is preserved in draft Limen PR #1162. Its exact
  head is locally scoped-green, but GitHub did not start the remote jobs because of the existing
  billing/spend owner gate; the review gate correctly rejects the draft and missing peer receipt.
- Branch protection has not been applied. A dedicated review-gate GitHub App must first be
  provisioned and publish an observable live App mapping; generic Actions fails closed. Separately
  custodied keeper signer principals must also be provisioned by Domus for the shared-login path.
- `limen.execution_trajectory.v1` remains shadow-only: production spend is still unreported for
  current local attempts, and no owner-native value authority can award verified credit. Board
  events cannot steer or manufacture value while those receipts are absent.
- UMA PR #174 preserves the receipt-bound mail implementation, but UMA default remains the old
  invocation-is-authorization entrypoint. Limen now forces preview and refuses apply against that
  deployed interface; no mail lane is reaccepted until the UMA owner lands and verifies its exact
  default invocation.
- Relationship review is fail-closed without an immutable owner handoff, but no owner-native signed
  hydrator/coverage receipt is deployed. HORREVM, Fable, and other effectors require their own
  signed/armed predicates before their rows can leave `repair_required`.

## First live probes

Run from the reacceptance worktree before any mutation:

```bash
git fetch --prune
git status --short --branch
python3 scripts/reacceptance-ledger.py --check docs/reviews/claude-reacceptance-2026-07-16/ledger.json
python3 scripts/pr-review-gate.py 1147 --repo organvm/limen --json
scripts/verify-scoped.sh
```

Then query the current remote heads, review threads, required checks, open repair PRs, live provider
catalogs, prompt-corpus custody, mounted substrates, host pressure, and owner-published peer-session
receipts. Never discover or resume another peer's private runtime. The snapshot in a prior handoff
is evidence, never current authority.

## Completion predicates

1. Every row in the frozen ledger has `accepted`, `repair_required`, `reverted`, or `superseded`
   backed by its owner receipt; campaign completion permits no residual `repair_required` row.
2. Every scoped repair predicate passes on the deployed invocation path.
3. Current P1/P2 review debt is zero, and `limen.pr_review_gate.v1` accepts every replacement exact
   head after a distinct peer review. The shared-login path remains blocked until Domus provisions
   separately custodied keeper principals and the base repository receives their allowed-signers
   material; the current single operator signer is not distinct-peer proof.
4. All formerly open cohort PRs are closed or reaccepted; all merged cohort PRs have terminal
   dispositions.
5. The execution-trajectory/session-value gate passes and no stale in-flight custody remains.
6. Privacy containment has an explicit terminal owner receipt; repository visibility and destructive
   history action remain human-gated.
7. The final ledger refresh is idempotent and this capsule records the resulting fixed point.

## Ownership and session-switch rules

Each repository owns its own code and external-effect adapters. Limen owns integration gates and the
redacted campaign ledger. Private owners retain sensitive evidence. The executing keeper is credited
for its attempt, while acceptance remains a distinct peer action.

At a context, value, provider, host-pressure, or human-gate boundary, preserve every useful branch,
push a durable PR or owner receipt, update this capsule with exact blockers and next commands, and
start a successor capsule. Never manufacture green by changing evidence or thresholds.

## Copy/paste resume command

From the Limen repository root:

```bash
bash scripts/start-worktree-session.sh --shell --workstream claude-reacceptance \
  --prompt-file docs/reviews/claude-reacceptance-2026-07-16/continuation.md \
  limen claude-reacceptance-successor
```

If the existing `work/claude-reacceptance-20260716` worktree is still active, continue it directly
instead of creating a competing writer; the command above is for a deliberate successor boundary.
