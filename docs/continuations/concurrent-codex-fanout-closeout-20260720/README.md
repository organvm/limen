# Truth-first activation boundary

The Limen implementation exists as a verified local overlay on exact head
`22adab82c67d322ca7d21c48325b6339d6d5fb3b`. It adds the dual-state Codex lease
protocol, constant-time Claude SessionEnd breadcrumbs, and WorkLoanV1 admission.
It is not installed, merged, or remotely custodied from this restricted session.

[`activation.json`](activation.json) is the machine-readable ground-truth receipt.
It keeps remote state `unverified`, records the host-pressure denial that prevented
the scoped gate, and names each owner, predicate, and next command. In particular:

- PR #1323's immutable head was not rewritten.
- Domus PR #315 is present in cached `origin/master`, but its installed wrapper has
  no capability handshake and its Claude breadcrumb hook is absent from live settings.
- The live queue has only 2 underwritten active tasks out of 1,206 and no verified
  receipt credit, so generic fanout remains closed.
- Prompt authority is not current, Omega is `BROKEN`, and the data volume is at 85%.
- No board transition, paid action, public send, account mutation, or destructive
  cleanup was attempted.

Resume through the admitted capsule, preserving its original deadline:

```bash
bash .limen-workstream/kickstart.sh
```

The first Git-ref-writable continuation must create
`work/truth-first-system-advance-20260720` before committing this overlay. It must
not push these changes onto PR #1323's branch.
