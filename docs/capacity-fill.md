# Capacity Fill

Generated: `2026-06-30T00:51:20+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 68 | 12 | 79 | 100 | 9 | 65 | route open work to this lane and dispatch before the window resets |
| `claude` | `no_work` | 0 | 0 | 2 | 15 | 0 | 0 | generate or route appropriate open work for this lane |
| `opencode` | `no_work` | 1 | 4 | 79 | 100 | 0 | 4 | generate or route appropriate open work for this lane |
| `agy` | `blocked` | 5 | 15 | 79 | 100 | 0 | 20 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `no_work` | 0 | 5 | 8 | 10 | 0 | 5 | generate or route appropriate open work for this lane |
| `codex` | `healthy` | 11 | 6 | 10 | 100 | 0 | 10 | keep pacing normally |

## Evidence

- `jules`: productive 68/79; attempts 12/79
- `claude`: productive 0/2, but no open/any work is available
- `opencode`: productive 1/79, but no open/any work is available
- `agy`: lane is down by the live dispatch gate
- `gemini`: productive 0/8, but no open/any work is available
- `codex`: productive 11/10; attempts 6/10
