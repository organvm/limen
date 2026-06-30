# Capacity Fill

Generated: `2026-06-29T23:12:43+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `no_work` | 50 | 59 | 72 | 100 | 0 | 46 | generate or route appropriate open work for this lane |
| `claude` | `blocked` | 0 | 5 | 2 | 15 | 0 | 0 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `opencode` | `no_work` | 1 | 16 | 100 | 100 | 0 | 1 | generate or route appropriate open work for this lane |
| `agy` | `blocked` | 5 | 29 | 100 | 100 | 0 | 0 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 19 | 7 | 10 | 0 | 0 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `depleted` | 1 | 15 | 16 | 100 | 0 | 0 | wait for this lane's meter to refresh or fail over before feeding it again |

## Evidence

- `jules`: productive 50/72, but no open/any work is available
- `claude`: lane is down by the live dispatch gate
- `opencode`: productive 1/100, but no open/any work is available
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 19/7, but productive board spend is 0/7
- `codex`: usage meter health=throttle; observed=15, productive=1
