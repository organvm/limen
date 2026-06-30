# Capacity Fill

Generated: `2026-06-30T01:44:17+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 81 | 23 | 83 | 100 | 5 | 69 | route open work to this lane and dispatch before the window resets |
| `claude` | `unproductive` | 0 | 4 | 2 | 15 | 0 | 4 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `opencode` | `underfilled` | 1 | 12 | 83 | 100 | 2 | 4 | route open work to this lane and dispatch before the window resets |
| `agy` | `blocked` | 5 | 15 | 83 | 100 | 0 | 0 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 18 | 8 | 10 | 0 | 4 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `healthy` | 16 | 15 | 14 | 100 | 0 | 6 | keep pacing normally |

## Evidence

- `jules`: productive 81/83; attempts 23/83
- `claude`: attempted 4/2, but productive board spend is 0/2
- `opencode`: productive 1/83; attempts 12/83
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 18/8, but productive board spend is 0/8
- `codex`: productive 16/14; attempts 15/14
