# Capacity Fill

Generated: `2026-06-30T01:24:02+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 77 | 77 | 81 | 100 | 1 | 69 | route open work to this lane and dispatch before the window resets |
| `claude` | `blocked` | 0 | 0 | 9 | 15 | 0 | 0 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `opencode` | `no_work` | 1 | 9 | 86 | 100 | 0 | 3 | generate or route appropriate open work for this lane |
| `agy` | `blocked` | 5 | 19 | 86 | 100 | 18 | 0 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 15 | 8 | 10 | 0 | 7 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `depleted` | 15 | 10 | 59 | 100 | 0 | 1 | wait for this lane's meter to refresh or fail over before feeding it again |

## Evidence

- `jules`: productive 77/81; attempts 77/81
- `claude`: lane is down by the live dispatch gate
- `opencode`: productive 1/86, but no open/any work is available
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 15/8, but productive board spend is 0/8
- `codex`: usage meter health=throttle; observed=15, productive=15
