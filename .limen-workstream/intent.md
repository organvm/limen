# Intent

Close the runaway-session prevention tranche without reviving any overnight transcript or spawning
an unbounded tree.

Implemented on this branch:

- transcript identity preserves real `thread_id`, records `root_session_id`, deduplicates sessions,
  treats fresh token events as liveness, and enforces the existing 800k meaningful-token ceiling
  per thread and root family;
- atomic machine-wide host admission exposes `acquire`, `refresh`, `release`, and `status`, cleans
  dead/stale leases, admits only one Limen execution turn, and denies new heavy work under declared
  Backblaze, swap, disk, or VITALS pressure without signaling peer processes;
- Codex project hooks provide lightweight accounting/denial messages while heavy entrypoints
  enforce the same lease because hook coverage is incomplete;
- `agents.max_threads = 3` and `agents.max_depth = 1`;
- a paused heartbeat maintains one byte-stable low-frequency receipt rather than respawning
  substantive probes every minute.

Governance cadence retry/output/scratch changes live in owner PR #1161 and must not be duplicated
here. Global host deployment and the non-backed Scratch authority belong to the Domus cartridge.
GitHub is operational; zero-step hosted jobs are verifier debt, not an external campaign gate.
