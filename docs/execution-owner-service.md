# Execution owner service

Execution trajectories and value-bearing owner receipts fail closed unless a
separate, root-custodied owner service is installed. A checkout, environment
variable, shell `PATH`, local GitHub CLI login, or executor-writable file is
never a production trust root.

## Fixed custody contract

The owner installs exactly these two system files:

- `/Library/Application Support/org.limen.execution-owner/config.json`
- `/Library/PrivilegedHelperTools/org.limen.execution-owner`

Every path component must be a real, root-owned directory or file and must not
be group/world writable. Symlinks are rejected. The helper must be executable,
and its SHA-256 must equal the digest in the root-owned configuration. Limen
invokes it with an inert environment; the helper talks to the owner
LaunchDaemon, whose GitHub App and signing credentials are unavailable to the
executing agent session.

The configuration schema is `limen.execution_owner_service.v1` with exactly:

```json
{
  "schema": "limen.execution_owner_service.v1",
  "verifier": {
    "path": "/Library/PrivilegedHelperTools/org.limen.execution-owner",
    "sha256": "sha256:<64 lowercase hex>"
  },
  "trajectory_owner": {
    "repository": "OWNER/REPOSITORY",
    "ref": "DEDICATED_BRANCH",
    "root": "receipts/execution-trajectories"
  },
  "receipt_authorities": [
    {
      "kind": "github-signed",
      "owner": "OWNER_ID",
      "repository": "OWNER/REPOSITORY",
      "ref": "DEDICATED_BRANCH",
      "root": "receipts/value-authority",
      "signature_scheme": "owner-service-v1",
      "key_id": "OWNER_KEY_ID"
    }
  ]
}
```

The owner helper exposes only the bounded `api` operations needed by the
trajectory adapter and `verify-signature`. Signature verification returns the
owner, scheme, key ID, validity, and SHA-256 of the canonical unsigned payload.
It must not expose credentials, accept arbitrary commands, or inherit executor
authentication.

## Receipt and publication invariants

The stored receipt envelope contains a canonical unsigned evidence payload and
an owner signature. It never contains its Git commit URL or the digest of its
own envelope. Limen attaches those external locator claims only after proving
that the receipt commit is an ancestor of the configured current owner ref,
reading the exact bytes at that commit, matching the envelope digest, and
verifying the independent owner signature.

Trajectory publication returns custody only after the ref PATCH response,
current-ref readback, ancestor proof, and every exact-commit content readback
match. A later fast-forward preserves older reachable receipts; divergence
fails closed.

## Current provisioning blocker

The clean repository deliberately ships no authority registry, credentials, or
fallback GitHub CLI. Until the Domus-owned runtime installs the helper,
LaunchDaemon credential custody, and root-owned configuration above, execution
trajectory publication remains retry-visible and value credit remains zero.

The safe read-only predicate is:

```bash
python3 scripts/check-execution-owner-service.py --check
```

It exits `2` while unprovisioned and `0` only after the fixed system surface,
ownership/modes, symlink checks, and executable identity all pass. Provisioning
the GitHub App, signing key, helper, or account access remains an owner action;
this repository does not create credentials or weaken separation.
