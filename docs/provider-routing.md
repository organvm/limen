# Dynamic provider routing

Limen routes from a task's current needs, not from a model-name table. Provider catalogs change;
their names, versions, availability, prices, and account reachability are runtime outputs.

## Contract

Each dispatch derives an extensible execution profile from live task evidence:

- reasoning depth and verification strength;
- minimum context and output room;
- tool and attachment requirements;
- cost and latency pressure;
- planning-only versus build permission; and
- optional generic numeric constraints such as `profile:min-context:131072`; and
- an opaque free-form hint from an existing `tier:*` label.

The profile is not a closed tier enum. A `tier:*` value is carried into the receipt and prompt but is
never interpreted by Limen, so `tier:economy`, `tier:plan`, and a future arbitrary value produce the
same routing profile for the same task evidence. Numeric `profile:<field>:<value>` labels are typed
from the execution-profile schema instead of a label-name table. Provider adapters filter their
current reachable catalog by hard capabilities, rank the survivors from metadata and current
pressure, and record the profile, catalog hash, selection source, and selected model when exposed.

OpenCode is selected from `opencode models --verbose` when that catalog exposes complete capability
metadata. An unavailable catalog leaves the invocation on provider Auto. A reachable catalog with no
candidate satisfying the execution profile fails blocked.

Claude, Codex, and Gemini default to provider Auto because their reachable discovery surfaces may
provide identifiers without enough capability/cost metadata to rank a default honestly. An explicit
`LIMEN_<PROVIDER>_MODEL` override is accepted only when its exact identifier is present in the live
provider catalog; a missing or unreachable catalog fails the override before a worktree or provider
side effect. The Claude fleet shim never injects a floor or trusts an environment pin on its own.

Warp/Oz normally receives the execution profile with the Action's `model` input blank. Warp Auto owns
the changing underlying catalog because Oz exposes model IDs but not enough capability/cost metadata
for Limen to rank them honestly. `LIMEN_WARP_MODEL_OVERRIDE` is an escape hatch only: dispatch first
proves the value exists in the current `oz model list --output-format json` result.

## Safety and planning

Credentials, secrets, personal data, irreversible deletion, paid overages, public-identity claims,
and `needs-human` work are rejected before a prompt reaches Warp/Oz. A planning-only profile uses the
explicit `mode:plan-only` task label and requires the existing current Fable acceptance/cap receipt;
without it, the request becomes maximally verified executable work. An accepted planning run returns
a build packet and may not build.

## Regression predicate

Provider-routing tests must use arbitrary/renamed fixture IDs and reorder/add/remove candidates. A
test that depends on a real model name is itself a regression. The implementation must prove:

1. catalog order and renames do not change capability semantics;
2. inaccessible models are never synthesized;
3. hard capability gaps block instead of silently downgrading;
4. explicit overrides are live-validated;
5. Warp defaults to provider Auto with no model ID; and
6. arbitrary `tier:*` text cannot change routing behavior; and
7. selection receipts contain no credential values.

Legacy production paths outside this dispatch integration are inventoried under owner issue #940;
they are not precedent for adding another named default.

## Execution trajectory

`limen.execution_trajectory.v1` freezes one execution attempt at launch: task classification,
executor, provider route, profile, repository, session, and start time. A later board edit cannot
reassign that attempt. Exact duplicate attempts count once; divergent rows for one attempt identity
are excluded.

The board is transport, not value authority. Success motion earns zero unless the predicate and
owner receipt both bind the exact commit and a fresh owner adapter independently verifies the
receipt. Credit belongs to `executing_keeper`, never to the provider route or the observer that
later reconciled the row.

Publication has no local-shadow default. `publish_bounded` requires an owner adapter with atomic
compare-and-set publication, rejects divergent existing attempts, and enforces finite record and
byte bounds before the owner write. The GitHub adapter publishes the whole batch through one
fast-forward commit/ref update; a lost compare-and-set can leave unreachable blobs but exposes no
partial trajectory paths.
