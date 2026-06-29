# Capacity Fill

Generated: `2026-06-29T23:45:46+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 63 | 65 | 74 | 100 | 14 | 56 | route open work to this lane and dispatch before the window resets |
| `claude` | `unproductive` | 0 | 8 | 1 | 15 | 0 | 0 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `opencode` | `underfilled` | 1 | 17 | 74 | 100 | 8 | 4 | route open work to this lane and dispatch before the window resets |
| `agy` | `blocked` | 5 | 36 | 74 | 100 | 3 | 9 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 28 | 7 | 10 | 4 | 8 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `healthy` | 6 | 27 | 6 | 100 | 7 | 10 | keep pacing normally |

## Evidence

- `jules`: productive 63/74; attempts 65/74
- `claude`: attempted 8/1, but productive board spend is 0/1
- `opencode`: productive 1/74; attempts 17/74
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 28/7, but productive board spend is 0/7
- `codex`: productive 6/6; attempts 27/6
