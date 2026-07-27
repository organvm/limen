# Mail-send authorization boundary

`scripts/mail-send` is a narrow shim, not the mail authority. It executes only the
Domus-installed UMA delegate at:

```text
/Library/Application Support/org.organvm.domus/limen/uma/bin/mail-send
```

The delegate and every path component must be owner-owned, non-symlinked, and
non-writable by the ordinary executor. `LIMEN_UMA_ROOT`, `UMA_ROOT`, `PATH`, and
`PYTHONPATH` cannot select executable mail code.

The wrapper is authorization-request-only. It never sends mail, resolves
credentials, reads caller/default mail files, opens IMAP/SMTP, or selects an
apply attempt store. `--apply`, caller-selected credential/authority paths, and
live `--from-draft` / `--reply-to-search` preview sources are refused before the
delegate can execute.

Before any `execve`, the wrapper requires a root-custodied
`config/mail-send-delegate-contract.json` with schema
`uma.mail.authorization_request_delegate.v1`. The contract binds the exact
delegate SHA-256 and UMA commit, the fixed
`--authorization-request-only` protocol, an owner test predicate and receipt
hash, and the ordered attestation that the delegate returns before credential
resolution, default-file resolution, IMAP, SMTP, and mutation. The delegate is
always invoked with that request flag first, `--dry-run`, a minimal environment,
and fixed owner HOME/TMPDIR/working directory.

Domus provisions the fixed `uma/` subtree with root-owned, non-symlinked,
non-group/world-writable ancestors and these exact leaves:

- executable `bin/mail-send`;
- `config/mail-send-delegate-contract.json`;
- owner-only directories `state/mail-source-receipts`,
  `state/mail-source-snapshots`, `home`, `tmp`, and `run`.

An owner-produced immutable source may be named only by the basename of a
single-link JSON receipt in `state/mail-source-receipts`. Schema
`uma.mail.immutable_source_snapshot.v1` binds the delegate-contract hash,
`draft` or `search` source kind, snapshot basename, byte size, and SHA-256 of a
single-link file in `state/mail-source-snapshots`. The wrapper verifies all of
those bindings and passes only the owner receipt path. It never accepts a live
provider lookup as a substitute.

## Current UMA owner blocker

The re-audited UMA candidate at `0bd0dd8` does not publish this contract or a
mechanically verifiable early-return integration receipt, so it must not be
treated as accepted and the Limen wrapper honestly fails closed. UMA clears the
blocker only when an exact installed commit provides:

1. the contract above with `delegate_sha256` equal to the installed executable;
2. an owner-held integration receipt whose hash equals
   `owner_receipt_sha256`;
3. the named `owner_predicate` passing against that exact commit and proving
   zero credential/default-file resolution, SMTP, IMAP, and mutation; and
4. immutable owner snapshot receipts for any draft/search-derived request.

A newer commit number by itself does not clear the predicate.
