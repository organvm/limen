# Capacity Fill

Generated: `2026-06-30T01:51:17+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 81 | 26 | 83 | 100 | 28 | 72 | route open work to this lane and dispatch before the window resets |
| `claude` | `unproductive` | 0 | 9 | 2 | 15 | 0 | 9 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `opencode` | `underfilled` | 1 | 14 | 83 | 100 | 2 | 6 | route open work to this lane and dispatch before the window resets |
| `agy` | `blocked` | 5 | 20 | 83 | 100 | 0 | 5 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 21 | 8 | 10 | 0 | 8 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `healthy` | 16 | 20 | 14 | 100 | 0 | 11 | keep pacing normally |

## Evidence

- `jules`: productive 81/83; attempts 26/83
- `claude`: attempted 9/2, but productive board spend is 0/2
- `opencode`: productive 1/83; attempts 14/83
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 21/8, but productive board spend is 0/8
- `codex`: productive 16/14; attempts 20/14
