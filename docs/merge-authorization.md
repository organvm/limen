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
named principal must exist in the Domus-installed, root-owned registry at
`/Library/Application Support/org.organvm.domus/limen/merge-authorization.allowed-signers`.
That path is fixed in the effector, outside every checkout, and intentionally ships
unprovisioned. There is no CLI or environment override. Until Domus installs it, apply fails
closed. The executor opens that owner file with `O_NOFOLLOW`, validates the opened
descriptor, reads at most 64 KiB, and verifies the receipt against a private temporary snapshot
rather than allowing `ssh-keygen` to reopen the owner path.

The signed receipt authorizes attempting only the named PR at the named head; it is not evidence
that the PR is acceptable. This signer registry is merge-effector custody only. It is never passed
to the review gate and cannot replace a native GitHub peer review.

```bash
python3 scripts/merge-drain.py \
  --apply \
  --authorization-receipt /private/path/merge-owner-repository-123.json
```

`LIMEN_REVIEW_ALLOWED_SIGNERS`, `LIMEN_ROOT`, and executable-path overrides are ignored by the live
merge path. Immediately before `gh pr merge --squash --match-head-commit`, the executor revalidates the unchanged signed
receipt and the SHA-256 digest of its trust snapshot, requires the dedicated App's complete,
successful `limen.pr_review_gate.v1` receipt on the exact head, and runs `scripts/merge-policy.sh`
from the same checked-in script root on the exact head.
Replacement of either owner file before the effect, including replacement while predicates run,
fails closed. Missing, stale, mismatched, tampered, or unknown-signer evidence fails closed.
Scheduled `scripts/drain.sh` invocations are preview-only and cannot consume authorization
implicitly.

`merge-drain.py` is the only executable merge surface. `await-pr.sh --merge` delegates to it and
requires the same receipt; signer custody remains implicit and pinned. The waiter also passes its policy-derived repository,
PR number, and exact head as an immutable target constraint; a valid receipt for any other target is
refused, and a drain attempt that does not confirm the exact target merged exits nonzero.
`ship-docs.sh` opens and preserves a PR but does not self-merge; the autonomy governor only observes
an already-merged terminal state.
