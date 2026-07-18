# Peer-conductor mesh implementation receipt

This receipt owns the bounded implementation completed in
`work/peer-conductor-mesh-20260718`. It does not claim that the production broker was deployed or
that the whole-PR campaign reviewed, repaired, merged, or closed any pull request.

## Delivered substrate

- versioned session, packet, lease, and receipt contracts with generated JSON Schemas;
- a bounded-DAG coordination kernel with idempotency, authority attenuation, leases, fencing,
  adoption, cooperative stop, harvesting, and restart recovery;
- matching CLI and MCP conduct surfaces plus compatibility submission for legacy task operations;
- an authenticated Worker/Durable Object cutover scaffold with GitHub SHA compare-and-swap
  projection;
- agent-neutral lane discovery, fanout, workstream launch, session-source adapters, ianva config
  generation, and native context injection;
- an organization-level Copilot custom-agent profile source, preserved in
  <https://github.com/organvm/.github/pull/21>;
- a fully paginated, exact-head `organvm` PR census and deterministic campaign graph builder.

## Deliberately unclaimed

The Worker is not safe to deploy yet. Its shared bearer authenticates endpoint access but does not
bind a request to a server-derived principal, registered session, root authority, or caller role.
Reservation responses also expose the executor capability to the submitting conductor. Principal
binding and executor-only, loss-recoverable capability delivery are merge gates.

The five-by-five live Codex/Claude/Copilot/Agy/OpenCode matrix has not run. The checked-in matrix is
test evidence, not a live provider receipt. No campaign leaf is “reviewed,” “ready,” or “done” from
the census alone. Exact-head readiness remains owned by
<https://github.com/organvm/limen/pull/1171>.

Copilot billing reports no assigned organization seats. This work did not buy or assign a seat,
install a credential, deploy the Worker, merge or close a PR, spend paid overage, or mutate
`tasks.yaml`.

## Verification

The final exact-head command results and implementation PR URL are appended after the direct-writer,
scoped, whole-repo, Worker, census-repeat, and remote-CI gates complete. Until then this is a draft
receipt and the continuation capsule is the owner for all residual work.
