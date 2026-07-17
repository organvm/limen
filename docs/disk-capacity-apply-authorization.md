# Disk-capacity apply authorization

`scripts/disk-capacity.py` is an observation-only sensor. It cannot remove a file,
truncate a log, or publish a receipt.

The separate `scripts/disk-capacity-reclaim.py` effector is also zero-write by
default. An apply requires:

1. execution from the Domus-installed, owner-custodied effector at
   `/Library/Application Support/org.organvm.domus/limen/authority/bin/disk-capacity-reclaim`
   (the checkout copy is preview-only);
2. an explicit `--apply`;
3. the exact previewed `limen.disk_capacity.apply_receipt.v1` document;
4. a detached OpenSSH signature under the same schema namespace;
5. a signer accepted by the fixed Domus-owned trust root at
   `/Library/Application Support/org.organvm.domus/limen/authority/trust/disk-capacity-apply.allowed-signers`;
   and
6. atomic consumption by the Domus execution identity in its owner-only
   `authority/consumed/disk-capacity` registry.

The signed receipt binds the root-owned configuration hash, visible canonical
root path/device/inode binding, exact target fingerprints, plan hash, one attempt
ID, and a lifetime of at most 15 minutes. The attempt-hash owner marker is created
with `O_EXCL`, so a differently signed receipt cannot replay the same attempt. The effector
rechecks the target and expiry at every mutation boundary, consumes the signed
receipt once, and publishes its effect-aware result only below
`authority/results/disk-capacity`.

Generate the zero-write plan and receipt template:

```bash
python3 scripts/disk-capacity-reclaim.py --check --attempt-id '<unique-attempt-id>'
```

One exact apply then names the owner receipt and detached signature:

```bash
'/Library/Application Support/org.organvm.domus/limen/authority/bin/disk-capacity-reclaim' --apply \
  --receipt '<receipt.json>' \
  --signature '<receipt.json.sig>'
```

Domus must also install `config/disk-capacity.json` for the observation threshold,
`config/disk-capacity-reclaim.json` for the canonical root and log cap, the private
result/quarantine directories, and the trust/consumption surfaces. Those deployed
paths are currently absent, so the live checkout truth is fail-closed. A repository
checkout is never an authority source.

## Domus provision contract

All ancestors from `/` through each leaf are root-owned, non-symlinked, and not
group/world writable. Files are single-link regular files. Result, quarantine,
and consumed directories are mode `0700`.

`authority/config/disk-capacity.json`:

```json
{"schema":"limen.disk_capacity.owner_config.v1","threshold_percent":80}
```

`authority/config/disk-capacity-reclaim.json`:

```json
{"schema":"limen.disk_capacity.reclaim_owner_config.v1","root_path":"/absolute/canonical/limen","log_cap_mb":50}
```

Domus also installs `bin/disk-capacity-reclaim`,
`trust/disk-capacity-apply.allowed-signers`,
`consumed/disk-capacity/`, `results/disk-capacity/`, and
`results/disk-capacity/.quarantine/`. The checkout does not create any of them.
