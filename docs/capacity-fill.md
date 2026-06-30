# Capacity Fill

Generated: `2026-06-30T01:44:02+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 81 | 81 | 83 | 100 | 5 | 69 | route open work to this lane and dispatch before the window resets |
| `claude` | `no_work` | 0 | 4 | 10 | 15 | 0 | 4 | generate or route appropriate open work for this lane |
| `opencode` | `underfilled` | 1 | 12 | 89 | 100 | 2 | 4 | route open work to this lane and dispatch before the window resets |
| `agy` | `blocked` | 5 | 19 | 89 | 100 | 0 | 0 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 19 | 8 | 10 | 0 | 4 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `depleted` | 16 | 15 | 67 | 100 | 0 | 6 | wait for this lane's meter to refresh or fail over before feeding it again |

## Evidence

- `jules`: productive 81/83; attempts 81/83
- `claude`: productive 0/10, but no open/any work is available
- `opencode`: productive 1/89; attempts 12/89
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 19/8, but productive board spend is 0/8
- `codex`: usage meter health=throttle; observed=16, productive=16
