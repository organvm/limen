# Unified remote-first fanout

`limen fanout` is the board-independent path for decomposing a direct request into bounded,
independently receiptable work. It compiles `FanoutManifestV1` leaves to the existing
`WorkPacketV1` protocol and registers the complete graph atomically with the authenticated conduct
keeper. It never reads or writes `tasks.yaml`.

## Operator interface

```text
limen fanout plan --manifest FILE
limen fanout start --manifest FILE --remote-first --local-max 1
limen fanout status ROOT_RUN --json
limen fanout harvest ROOT_RUN [--merge]
```

`plan` validates and canonicalizes without launching. It orders overlapping resource claims as
explicit dependencies and prints the same manifest hash used by every entry route. `start` discovers
healthy sessions from the keeper, prefers remote capacity, admits at most one local-heavy fallback,
atomically submits the graph, and immediately returns the root run ID. `status` and `harvest` resume
solely from keeper state; there is no local campaign database.

Production `start` requires `LIMEN_CONDUCT_URL` plus `LIMEN_CONDUCT_TOKEN`. The SQLite conduct
adapter is development/test-only and the public fanout command always rejects it.

## Manifest contract

Every leaf declares:

- stable `work_id` and `idempotency_key`;
- `owner_repository`, an exact Git base object ID, a topic branch, allowed paths, and resource
  claims;
- dependencies and provider-neutral required capabilities;
- intended effect, an executable predicate, and a durable receipt target;
- finite deadline, bounded retry policy, and spend ceiling;
- SHA-256 prompt and plan hashes, never raw prompt or plan text.

The schema rejects raw prompts, provider/model/tier selectors, missing predicates, expired deadlines,
unbounded retries, dependency cycles, unknown dependencies, and unresolved resource conflicts.
Automatic evaluation (two or more independently verifiable reversible leaves), conversational
triggers (`multitask`, `parallelize`, `fan out`, or `use cloud`), and the CLI all call the same
canonicalization and hashing pipeline.

Credentials, public sends, destructive effects, private-data movement, and unapproved spending are
outside this manifest's automatic authority. Fanout leaves are limited to read and repository-write
effects; external actions remain on their owner-specific gated paths.

## Dynamic routing and completion

Routing uses only live keeper session facts: health, accepting state, current load, concurrency,
transport, and advertised capabilities. No provider, model, tier, price, quota reset, or fallback
table is encoded. A write leaf is eligible only when a live executor advertises exact base, diff,
head, predicate, and pull-request receipt capabilities. Consequently:

- remote coding lanes become eligible when their live adapter proves the complete receipt contract;
- exact-head verification lanes can receive read/verification leaves but cannot receive
  implementation leaves without code receipts;
- paid or incompletely receipted lanes remain excluded without a name-based denylist;
- exhausted lanes disappear from live eligibility and routing recomputes from the remaining
  capacity; it never resets quota, creates an account, or authorizes overage.

Provider readiness and generated diffs are not completion. A code receipt must be keeper-authorized,
match the exact base, name a distinct exact head, include the provider run URL, prove the predicate,
prove a durable diff, prove a PR whose head is exact, and keep all changed paths within authority.
Harvest fails closed on any omission or moved base/head.

Landing adapters are discovered through the `limen.fanout_landing` Python entry-point group. The
built-in adapter accepts an already-created exact-head GitHub PR receipt. `--merge` calls the single
sanctioned `scripts/await-pr.sh --merge` path. Adapters that fetch a provider diff, hash it, apply it
in a dedicated linked worktree, verify, commit, push, and open a PR may opt in only after they emit
the same exact receipt set; direct shared-checkout landing is not an adapter surface.

## Minimal example

```yaml
schema_version: limen.fanout_manifest.v1
root_work_id: campaign-20260720
idempotency_key: campaign-20260720/v1
initiator: &identity
  schema_version: limen.agent_identity.v1
  agent: codex
  surface: cli
  session_id: session-20260720
conductor: *identity
predicate: limen fanout status campaign-20260720 --json
receipt_target: conduct:campaign-20260720
deadline: 2026-07-21T00:00:00Z
leaves:
  - schema_version: limen.fanout_leaf.v1
    work_id: leaf-docs
    idempotency_key: campaign-20260720/leaf-docs
    owner_repository: organvm/limen
    exact_base: 0000000000000000000000000000000000000000
    topic_branch: work/leaf-docs
    allowed_paths: [docs]
    resource_claims:
      - {key: "path/organvm/limen/0000000000000000000000000000000000000000/docs", mode: exclusive}
    dependencies: []
    required_capabilities: [code]
    intended_effect: update one bounded document
    effect: write
    predicate: python3 scripts/check-docs.py
    receipt_target: github:organvm/limen:pr
    deadline: 2026-07-21T00:00:00Z
    retry: {max_attempts: 2, transient_only: true}
    spend: {unit: runs, limit: 2, reserve: 0}
    prompt_hash: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    plan_hash: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
```
