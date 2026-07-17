# Disk-capacity apply authorization

`scripts/disk-capacity.py` is an observation-only sensor. It cannot remove a file,
truncate a log, or publish a receipt.

The separate `scripts/disk-capacity-reclaim.py` effector is also zero-write by
default. An apply requires:

1. an explicit `--apply`;
2. the exact previewed `limen.disk_capacity.apply_receipt.v1` document;
3. a detached OpenSSH signature under the same schema namespace; and
4. a signer accepted by the repository-pinned owner trust root at
   `docs/keys/disk-capacity-apply.allowed-signers`.

The signed receipt binds the real Limen root identity, exact target fingerprints,
plan hash, one attempt ID, and a lifetime of at most 15 minutes. The effector
rechecks the target and expiry at every mutation boundary, consumes the signed
receipt once, and publishes an effect-aware result.

Generate the zero-write plan and receipt template:

```bash
python3 scripts/disk-capacity-reclaim.py --check --attempt-id '<unique-attempt-id>'
```

One exact apply then names the owner receipt and detached signature:

```bash
python3 scripts/disk-capacity-reclaim.py --apply \
  --receipt '<receipt.json>' \
  --signature '<receipt.json.sig>'
```

The trust root is intentionally unprovisioned. Domus must publish a dedicated
owner public key through an accepted PR and keep its private key unavailable to
the executing session. Until then, production apply fails closed.
