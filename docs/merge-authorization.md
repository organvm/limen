# Merge authorization

Merge effectors are zero-write previews unless `--apply` is explicit. Apply also requires one
short-lived `limen.merge_authorization.v1` JSON receipt for each exact target:

```json
{
  "schema": "limen.merge_authorization.v1",
  "authorization_id": "merge-example-001",
  "action": "merge",
  "repository": "owner/repository",
  "pull_request": 123,
  "head_sha": "0123456789abcdef0123456789abcdef01234567",
  "issued_at": "2026-07-16T18:00:00Z",
  "expires_at": "2026-07-16T18:10:00Z",
  "review_gate_context": "limen.pr_review_gate.v1",
  "signer_principal": "keeper-principal",
  "signature": "-----BEGIN SSH SIGNATURE-----\n...\n-----END SSH SIGNATURE-----\n"
}
```

The window may not exceed 15 minutes. The receipt must be an executing-user-owned, non-symlink
regular file that is not group- or world-writable. Its signature covers the canonical JSON payload
excluding `signature`, under the dedicated OpenSSH namespace `limen.merge_authorization.v1`. The
named principal must exist in the explicit Domus-owned allowed-signers file. The trust registry is
never tracked in Limen. The executor opens that owner file with `O_NOFOLLOW`, validates the opened
descriptor, reads at most 64 KiB, and verifies the receipt against a private temporary snapshot
rather than allowing `ssh-keygen` to reopen the owner path.

The signed receipt authorizes attempting only the named PR at the named head; it is not evidence
that the PR is acceptable.

```bash
python3 scripts/merge-drain.py \
  --apply \
  --authorization-receipt /private/path/merge-owner-repository-123.json \
  --allowed-signers /domus-owned/path/allowed-signers
```

`LIMEN_REVIEW_ALLOWED_SIGNERS` may supply the same trust path instead of the CLI flag. Immediately
before `gh pr merge --squash --match-head-commit`, the executor revalidates the unchanged signed
receipt and the SHA-256 digest of its trust snapshot, re-runs `limen.pr_review_gate.v1` on the exact
head, and runs `scripts/merge-policy.sh` with an immutable copy of that same trust snapshot and head.
Replacement of either owner file before the effect, including replacement while predicates run,
fails closed. Missing, stale, mismatched, tampered, or unknown-signer evidence fails closed.
Scheduled `scripts/drain.sh` invocations are preview-only and cannot consume authorization
implicitly.
