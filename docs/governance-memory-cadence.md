# Governance Memory Cadence

Limen owns the bounded orchestration contract for governance memory. It does not own provider
discovery, raw custody, normalization, reviewed lineage, constitutional ratification, self-images,
ideal forms, or Atlas compilation. Each of those owners supplies a runtime command, finite execution
profile, predicate, and durable receipt target.

The ordered stages are exact:

`discover → snapshot → parse → classify → reconcile → distill → validate → render → receipt`

## Operator command

```bash
python3 scripts/governance-memory-cadence.py \
  --snapshot-id "$LIMEN_GOV_SNAPSHOT_ID" \
  --snapshot-at "$LIMEN_GOV_SNAPSHOT_AT" \
  --config "$LIMEN_GOV_CONFIG" \
  --run-root "$LIMEN_GOV_RUN_ROOT/$LIMEN_GOV_SNAPSHOT_ID" \
  --strict --write
```

The first invocation performs two complete owner traversals of the same frozen snapshot. The first
executes incomplete children. Its cadence receipt is always `exact_all: false`, `ready: false`, and
`status: incomplete`; a stage chain cannot call its first pass ready. The second invokes every owner
command in proof mode, independently reruns its separately revision-pinned predicate, and requires
every durable child to return `skipped_completed` with its exact prior child-receipt digest. A proof
owner or predicate gets one attempt: any nonzero exit, invalid metrics, revision change, or governed
output mutation invalidates the cadence immediately. A later retry cannot restore bytes and erase
the failed attempt.

Every stage profile must set `max_attempts: 1`; there is no blind internal retry. The private
attempt ledger permits at most two execution-mode full attempts for one snapshot/config digest.
After the first failed full attempt, the second is refused until
`repairs/<stage>.governance-stage-repair-receipt.v1.json` binds the exact snapshot, config, prior
failure digest, failed stage, owner revision, and independently revision-pinned predicate. A third
full attempt is always denied. A successful fixed point followed by the separate proof-only
observation below does not consume another full-attempt slot.

The run-two receipt is written only after that unchanged traversal proves:

- zero new events;
- zero changed governed-output bytes;
- zero replayed completed children;
- byte-identical output digests;
- one exact nine-stage predecessor chain.

Run-two readiness is not a cadence default. Every stage declares one governed output as its
`readiness_evidence`; the orchestrator validates and unions those owners' `exact_all`, blockers,
quarantines, missing requirements, citation debt, and incomplete predicates. Run two is ready only
when the fixed point is proven and every owner declares exact coverage with no debt. Otherwise the
typed run-two receipt remains blocked.

Strict mode intentionally returns nonzero after that first invocation because the separate
post-proof observation does not exist yet. Repeating the exact command invokes every owner once more
in proof mode; it must execute no completed child and write no stage, cadence, or collection
receipt. The second invocation must leave every governed owner output, full stage receipt, cadence
receipt, and receipt collection byte-identical. Only then is `post-proof-idempotence.v1.json`
persisted.

The receipt-stage owner does not fabricate a final bundle containing receipts that do not exist yet.
It emits one governed `governance-snapshot-bundle-pre-proof.v1` payload with the non-cadence bundle
fields and its owner readiness. After the exact post-proof invocation, Limen derives stage references
from the nine full receipts, derives cadence references from runs one and two, adds the post-proof
observation, validates the completed `governance-snapshot-bundle.v1` against the configured public
schema, and seals its RFC 8785 digest. The final bundle is an orchestrator control-plane artifact,
not a receipt-stage governed output, so no digest depends on itself.

A changed input, output, owner revision, command, predicate, environment, execution profile, or
predecessor digest invalidates the aggregate proof before resuming from the first incomplete owner.
An active or invalidated marker makes strict readiness fail, including after an external process
kills the orchestrator. Invalidation removes stale post-proof and final-bundle claims.

Without `--write`, the command validates configuration and limits without executing owners. Strict
mode fails closed unless both the run-two fixed point and the separate unchanged post-proof
invocation are proven.

## Runtime configuration

`LIMEN_GOV_CONFIG` is JSON or YAML with `contract_name: governance-cadence-config.v1`. Its root must
contain a stable `cadence_id`, an `owner_reference`, the frozen `snapshot_digest`, a runtime
`schema_catalog`, an `execution_policy`, and exactly the nine stage keys. Provider names and model
catalogs are runtime data; adding or renaming a source changes owner configuration rather than
Limen code.

`execution_policy` is digest-bound and fail-closed:

- `max_full_attempts` must equal `2`.
- `aggregate_output_budget_bytes` must cover the declared four command/predicate log reservations
  plus governed artifacts for all nine stages. The parent also measures every regular file under
  the run root after each command and receipt write, so undeclared intermediates consume the same
  ceiling.
- `scratch_authority.root` must contain `--run-root`. Its receipt must be an exact
  `domus-non-backed-scratch-receipt.v1` record owned by `repo:organvm/domus-genoma`, binding the
  resolved root, live mount point and device, and verified backup exclusion. Symlinked roots fail.
  The Domus observation must be current, timezone-aware, unexpired, and valid for no more than 24
  hours; an old receipt cannot survive a later Backblaze selection change indefinitely.
- `final_receipt_promotion.root` is a distinct durable Archive4T destination with a public-safe
  owner reference. It must already exist; the cadence never manufactures a missing mount.

`schema_catalog.root` is the runtime path to the available public catalog.
`schema_catalog.contracts` maps contract names to schema files below that root and must include
`governance-stage-receipt.v1` and `governance-snapshot-bundle.v1`. Limen checks the schemas
themselves, records only their digests in the public config projection, validates an existing or new
full stage receipt before accepting it, and validates the final bundle before writing it. An
unavailable, invalid, or mismatched catalog fails closed; there is no embedded fallback path.

Every stage requires:

| Field | Contract |
|---|---|
| `owner_reference` | Stable owner of the stage and its residual work |
| `owner_revision` | Exact clean Git HEAD or executed owner-file digest; live mismatch fails before execution |
| `predicate` | Nonempty `predicate_id`, independent executable argv `command`, separate exact `revision`, public-safe `receipt_command`, and `expected_result` |
| `receipt_target` | Durable owner-native result reference |
| `cwd` and `command` | Existing owner worktree and a nonempty argv array; shell strings are rejected |
| `env` | Optional non-secret string map; owners receive a bounded deterministic base environment |
| `inputs[]` | Nonempty artifacts typed as exact `predecessor_output` or snapshot-bound `snapshot_anchor` |
| `outputs[]` | Nonempty artifact references confined below `--run-root` |
| `readiness_evidence` | Exactly one declared output whose standard readiness object is owner evidence |
| `execution_profile` | Positive finite `max_items`, `timeout_seconds`, `max_log_bytes`, and `max_artifact_bytes`; `max_attempts` must be exactly `1` |

`discover` inputs are snapshot anchors and must repeat the exact configured snapshot ID and digest.
Each later stage must consume every declared predecessor output exactly once, matching artifact ID,
reference, path, and contract. Additional inputs are allowed only as separately typed
`snapshot_anchor` entries bound to that same frozen snapshot. One overlapping artifact is not a
dataflow contract.

The `receipt` stage must expose exactly one output with contract
`governance-snapshot-bundle-pre-proof.v1`, and that same output is its readiness evidence. Its
`bundle_payload` contains exactly the owner-supplied bundle fields; cadence/stage receipts,
post-proof evidence, readiness, timestamps, digest algorithm, and bundle digest are reserved for
the orchestrator seal.

The orchestrator injects `LIMEN_GOV_STAGE`, `LIMEN_GOV_STAGE_ATTEMPT`, `LIMEN_GOV_TRAVERSAL`,
`LIMEN_GOV_PROOF_MODE`, `LIMEN_GOV_STAGE_METRICS_OUT`, `LIMEN_GOV_STAGE_RECEIPTS`,
`LIMEN_GOV_PREDECESSOR_RECEIPT_DIGEST`, `LIMEN_GOV_PRIOR_STAGE_RECEIPT`, and
`LIMEN_GOV_MAX_ITEMS`. Owners write one bounded metrics object covering every child exactly once
with a resume token, disjoint completed and pending IDs, typed child receipts, immutable
input/output digests, and a nonnegative emitted-event count. The orchestrator independently runs
the predicate and emits the typed stage receipt; owner commands do not write that receipt.
Pending, failed, blocked, duplicate, unreceipted, aggregate-over-limit, or replayed proof children
prevent stage completion.

## Receipts and readiness

The private run root contains capped logs, owner metrics, nine
`governance-stage-receipt.v1` files, the deterministic
`governance-stage-receipts.v1.json` collection exposed through
`LIMEN_GOV_STAGE_RECEIPTS`, run-one and run-two
`governance-cadence-receipt.v1` files, and the ordered
`governance-cadence-receipts.v1.json` collection. The full stage collection is a control-plane
receipt excluded from governed-output byte counts. Each fixed-point record binds
`previous_output_digest` (`null` for run one and the exact run-one output digest for run two).
Public receipts contain references and digests, never configured local paths or source bodies.

Intermediates stay on the verified non-backed scratch root. Only after the separate post-proof
observation and final-bundle schema validation does the cadence atomically copy and hash-verify this
fixed allowlist to Archive4T:

- `governance-stage-receipts.v1.json`;
- `governance-cadence-receipts.v1.json`;
- `post-proof-idempotence.v1.json`;
- `governance-snapshot-bundle.v1.json`.

Logs, metrics, per-stage artifacts, attempt ledgers, and repair receipts are never promoted.
Promotion failure leaves the validated scratch receipts intact and nonterminal; it does not erase
or rewrite the proof. Existing historical Archive4T runs remain evidence and are not moved or
deleted by this contract.

`scripts/governance-memory-readiness.py --strict --write` validates these receipts against the
installed public schema catalog and the exact frozen snapshot bundle. It does not search arbitrary
documents for stage-like objects. Global `ready` remains false unless every owner contract is
nonempty and valid, the custody-to-event promotion crosswalk is complete, assertions and
ratification evidence pass, all registered nodes have one fresh self-image, both timelines and all
six Atlas zooms are populated, citation debt is zero, and run two plus the post-proof idempotence
probe are proven.

When all four cadence environment inputs are configured, `scripts/vltima-absorb-cadence.py` inserts
this cadence immediately before strict governance-memory readiness. The heartbeat remains fail-open
as a scheduler, but its tracked readiness receipt remains honestly degraded on any failed owner
predicate.
