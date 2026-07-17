# HORREVM apply authorization

HORREVM previews and freshness checks are zero-write. Egress requires all four independent inputs:

1. an explicit `--apply` invocation for `--push` or `--probe`;
2. the safety valve `LIMEN_HORREVM_APPLY=1`, rechecked at each mutation boundary;
3. an exact `limen.horrevm.apply_receipt.v1` JSON document and detached OpenSSH signature under
   the dedicated `limen.horrevm.apply_receipt.v1` namespace; and
4. the repository-pinned Domus owner trust root at
   `docs/keys/horrevm-apply.allowed-signers`.

The signed JSON binds the signer principal, action, attempt ID, issue and expiry times, canonical
source-manifest hash, every source content hash, payload hash, rail root, and every remote object
that the attempt may touch. The command boundary permits only `copy`, `copyto`, and probe-only
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
LIMEN_HORREVM_APPLY=1 python3 scripts/horrevm-custody.py --push --apply \
  --receipt '<receipt.json>' \
  --signature '<receipt.json.sig>'
```

Receipt, signature, and allowed-signers inputs must be effective-user-owned, single-link regular
files that are not group/world writable. Receipts expire within four hours and are consumed before
the first apply subprocess. Source bytes are opened without following links, streamed into private
staging, and checked against the signed size and SHA-256 manifest before final-destination copies.

Limen does not provision the signer or private key. The pinned trust root is intentionally empty.
Until Domus publishes a dedicated owner public key through an accepted PR and retains the private
key in custody unavailable to the executing session, production apply remains unavailable.
