# Runtime contract

Read `workstream.json` first. Its admitted deadline is executable: successor sessions inherit it,
and expired or contradictory state fails closed. Full non-destructive approval means reversible
in-scope work proceeds without confirmation; destructive, credential, paid-spend, public-send, and
runtime/host mutations remain gated.

Re-probe the exact remote head, PR state, host-admission status, active lease owner, token-family
report, paused receipt age, VITALS mode, swap, disk throughput, and Backblaze pressure before any
mutation. Project hook trust is confirmed interactively through `/hooks` only after the branch
lands; never edit trust evidence to manufacture success.

Use one conductor with no more than two bounded children, one mutation owner per worktree, and one
heavy surface machine-wide. Denial defers new heavy work; it never authorizes killing or restarting
Codex, Claude, Backblaze, or another peer.

At each packet boundary, re-read remaining runway and derive healthy lanes from live capabilities.
Do not fabricate a fallback provider or start work that has already crossed the admitted deadline.

Run each implicated focused predicate once per unchanged head and reuse its receipt. A changed head
or specific observed failure is required before another test. Never run full local verification
while host admission denies heavy work.
