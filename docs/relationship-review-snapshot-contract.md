# Relationship Review Snapshot Contract

`relationship-review-delta` is a zero-write consumer. Limen does not own the relationship source,
does not read a live Messages database, and does not hydrate or publish private relationship state.
The private relationship owner produces and preserves the source bundle; the heartbeat only consumes
an exact hydrated copy after checking this contract.

## Owner side

The owner creates one coherent bundle containing:

- an immutable, checkpointed SQLite snapshot with no `-wal`, `-shm`, or `-journal` companions;
- a `relationship.review_adapter.v1` JSON artifact whose private `people` rows contain `slug`,
  non-empty `handles`, and the `last_review` cursor as observed at snapshot production;
- a `relationship.review_snapshot.v1` receipt binding both artifacts by relative path, byte count,
  and SHA-256 digest; and
- durable, non-`file:` `snapshot_uri` and `receipt_uri` values containing the receipt's
  content-derived `sha256:<digest>` immutable reference.

The owner sets timezone-aware `produced_at` and `expires_at` timestamps and preserves the exact bundle
and receipt at those content-addressed private custody URIs. A local checkout is never a custody URI.
The ordering must be production, remote custody verification, then hydration; all three timestamps are
subject to the consumer freshness ceiling.

The snapshot ID is deterministic. Canonicalize this object as UTF-8 JSON with sorted keys and separators
`,` and `:` (no spaces), hash those bytes with SHA-256, and prefix the lowercase hex digest with `sha256:`:

```json
{
  "adapter": {"bytes": 123, "sha256": "<adapter digest>"},
  "messages": {"bytes": 456, "sha256": "<SQLite digest>"}
}
```

The owner receipt shape is:

```json
{
  "schema": "relationship.review_snapshot.v1",
  "snapshot_id": "sha256:<content-derived digest>",
  "produced_at": "<timezone-aware timestamp>",
  "expires_at": "<timezone-aware timestamp>",
  "custody": {
    "immutable_ref": "sha256:<content-derived digest>",
    "snapshot_uri": "https://private-owner.invalid/snapshots/sha256:<content-derived digest>",
    "receipt_uri": "https://private-owner.invalid/receipts/sha256:<content-derived digest>.json"
  },
  "artifacts": {
    "adapter": {"path": "review-adapter.json", "bytes": 123, "sha256": "<adapter digest>"},
    "messages": {"path": "messages.snapshot.sqlite", "bytes": 456, "sha256": "<SQLite digest>"}
  }
}
```

## Hydration handoff

An owner-native hydrator copies the already-produced bundle into a private directory, verifies the
durable source, then atomically publishes one `limen.relationship_review_handoff.v1` JSON file last.
The handoff binds:

- the relative snapshot-receipt path and its SHA-256 digest;
- the same content-derived snapshot ID;
- the exact durable snapshot and receipt URIs; and
- `custody_verification: verified`, a timezone-aware `custody_verified_at`, and a later
  timezone-aware `hydrated_at` timestamp. The hydrator records these only after fetching and
  digest-checking the remote owner receipt and snapshot.

Every handoff, receipt, adapter, and database artifact must be a single-link regular file owned by the
effective user with no group or world permissions. Paths are relative to the handoff directory; absolute
paths, traversal, and symlinks fail closed. Hydration implementation and authorization belong to the
private owner, not to Limen.

The heartbeat receives the handoff path through `LIMEN_RELATIONSHIP_REVIEW_HANDOFF`. There is no
checkout, registry, adapter, or raw database fallback. `LIMEN_RELATIONSHIP_REVIEW_MAX_SNAPSHOT_AGE_SECONDS`
sets a second consumer-side freshness ceiling (eight days by default); an owner expiry cannot weaken it.

## Consumer guarantees

Before querying, the detector verifies both receipt layers, remote content-addressed custody, freshness,
file privacy, artifact sizes, and artifact digests. It opens SQLite with `mode=ro&immutable=1`, enables
`PRAGMA query_only`, refuses mutable SQLite companions, and rechecks file identities before publishing a
count. It has no notify, hydrate, copy, checkpoint, or storage-effector path.

Missing, stale, changed, unbound, or local-only custody returns a PII-clean `available: false` result with
`review_due: null`. That is explicit coverage debt, never evidence that nobody is due for review.

## Minimal private example shape

The values below are schematic and deliberately contain no real owner paths or relationship data.

```json
{
  "schema": "limen.relationship_review_handoff.v1",
  "snapshot_id": "sha256:<content-derived digest>",
  "custody_verification": "verified",
  "custody_verified_at": "<timezone-aware timestamp>",
  "hydrated_at": "<timezone-aware timestamp>",
  "source_snapshot_uri": "https://private-owner.invalid/snapshots/sha256:<content-derived digest>",
  "source_receipt_uri": "https://private-owner.invalid/receipts/sha256:<content-derived digest>.json",
  "snapshot_receipt": {
    "path": "snapshot-receipt.json",
    "sha256": "<digest of the exact owner receipt bytes>"
  }
}
```
