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

Added from the operator correction in this continuation:

- workstreams now carry one configurable finite runway (`15m..30d`, default `1d`) whose admitted
  deadline survives session and provider boundaries;
- Codex, Agy, and OpenCode packet launches are no-modal and fail closed before spawn on contract
  drift; Jules, Copilot, and every other routed lane share the same expiry gate;
- fleet fanout now uses the live capacity registry, including Jules and Copilot when healthy, rather
  than the broken static fallback;
- capsule identity, admission, and launch locking bind the executable module set, preserve the
  originally admitted deadline, and reject drift, symlink escapes, stale ownership, or unsafe
  identity fields before a provider process starts;
- result commits and remote mutations are fenced against fresh execution and lifecycle ownership so
  a stale packet cannot overwrite a newer claim, human gate, terminal state, or concurrent receipt;
- other isolated streams, active agents, and an ambient autonomy-pause marker are expected concurrent
  state, not a stop condition for this bounded lane. They do not authorize this lane to mutate the
  live root, merge a PR, or bypass its own finite contract;
- current branch and PR custody must always be derived from the exact live remote head. Re-probe the
  default branch and exact PR head immediately before push, review, or merge rather than preserving a
  checkpoint-specific claim in this capsule.
