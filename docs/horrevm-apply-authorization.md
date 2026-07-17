# HORREVM apply authorization

HORREVM previews and freshness checks are zero-write. Egress requires:

1. execution from the Domus-installed, owner-custodied effector at
   `/Library/Application Support/org.organvm.domus/limen/authority/bin/horrevm-custody`
   (the checkout copy is preview/status-only);
2. an explicit `--apply` invocation for `--push` or `--probe`;
3. the safety valve `LIMEN_HORREVM_APPLY=1`, rechecked at each mutation boundary;
4. an exact `limen.horrevm.apply_receipt.v1` JSON document and detached OpenSSH signature under
   the dedicated `limen.horrevm.apply_receipt.v1` namespace; and
5. the fixed Domus-owned trust root at
   `/Library/Application Support/org.organvm.domus/limen/authority/trust/horrevm-apply.allowed-signers`;
   and
6. attempt-hash `O_EXCL` consumption and a serialized state lock in the owner-only
   `authority/consumed/horrevm` registry.

The signed JSON binds the signer principal, action, attempt ID, issue and expiry times, canonical
source-manifest hash, every source content hash and root identity, owner-config and deployed-tool
hashes, rail identity, payload hash, immutable object-set root, and every remote object
that the attempt may touch. The command boundary permits only `copyto` and probe-only
`deletefile` against those enumerated objects. `sync`, move operations, broad deletion, an unsigned
`authorized: true` field, and a valve without a signed receipt all fail closed.

Generate a zero-write binding packet first:

```bash
python3 scripts/horrevm-custody.py --push --attempt-id '<unique-attempt-id>'
```

The Domus authority owner turns those bindings into canonical JSON, signs the exact bytes, and
publishes the public key principal through its allowed-signers owner. A detached signature can be
created with:

```bash
ssh-keygen -Y sign \
  -f '<Domus-owned private key>' \
  -n limen.horrevm.apply_receipt.v1 \
  '<receipt.json>'
```

One exact apply names the receipt and detached signature. The caller cannot replace the trust root:

```bash
LIMEN_HORREVM_APPLY=1 \
  '/Library/Application Support/org.organvm.domus/limen/authority/bin/horrevm-custody' --push --apply \
  --receipt '<receipt.json>' \
  --signature '<receipt.json.sig>'
```

Receipt and signature inputs must be execution-identity-owned, single-link regular files that are
not group/world writable. The allowed-signers file and every authority path component must instead
be Domus-owner-owned and non-writable by the ordinary executor. Receipts expire within four hours
and are consumed by attempt ID in the fixed owner registry before the first apply subprocess. Source bytes are
opened without following links, streamed into private staging, and checked against the signed size
and SHA-256 manifest before final-destination copies. Every ciphertext must be a single-link
regular file with the ARCA envelope header and must unseal to the exact plaintext manifest.
Remote objects use versioned attempt-hash paths; every object has a before/after owner-journal
record, and the immutable set's `manifest-current.json` is last.

Limen does not provision the signer, private key, trust root, owner config, fixed rclone config,
apply temp root, or consumption registry. Those deployed paths are currently absent. Until Domus
installs them through an accepted receipt and retains their authority outside the ordinary executing
session, production apply, preview, doctor, and status fail closed. Authoritative freshness is
read only from `authority/state/horrevm.json`; checkout-local state cannot make status green. The
state must match every current config/tool/rail binding and prove a verified immutable manifest on
every rail. The ARCA and rclone executables are fixed Domus-installed binaries, never `PATH` lookups.

## Domus provision contract

All authority ancestors from `/` are root-owned, non-symlinked, and not
group/world writable. Config and executable leaves are single-link regular
files. State, consumed, temp, and run directories are owner-only. Domus installs:

- `bin/horrevm-custody`, `bin/arca`, and `bin/rclone`;
- `config/rclone.conf`, `trust/horrevm-apply.allowed-signers`;
- `state/horrevm.json`, `consumed/horrevm/`, `tmp/horrevm/`, and `run/`; and
- `config/horrevm.json` with exactly this shape:

```json
{
  "schema": "limen.horrevm.owner_config.v1",
  "rclone_binary": "/Library/Application Support/org.organvm.domus/limen/authority/bin/rclone",
  "rclone_config": "/Library/Application Support/org.organvm.domus/limen/authority/config/rclone.conf",
  "arca_binary": "/Library/Application Support/org.organvm.domus/limen/authority/bin/arca",
  "max_age_days": 7,
  "rails": {
    "gdrive": {"rail_id": "sha256:<64-lowercase-hex>", "budget_bytes": 5000000000},
    "dropbox": {"rail_id": "sha256:<64-lowercase-hex>", "budget_bytes": 1000000000}
  },
  "sources": {
    "arca-vault": "/absolute/canonical/source",
    "corpus-inventory": "/absolute/canonical/source",
    "kernel": ["/absolute/canonical/file"]
  }
}
```

`rail_id` is a Domus-attested identity for the account and remote root; a remote
display name is not identity proof. Every listed source is required. No `~`,
relative path, caller environment override, or silent missing-source skip is
accepted.
