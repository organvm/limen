# Capacity Fill

Generated: `2026-06-29T22:45:13+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 54 | 57 | 70 | 100 | 14 | 52 | route open work to this lane and dispatch before the window resets |
| `claude` | `unproductive` | 0 | 8 | 1 | 15 | 0 | 0 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `opencode` | `underfilled` | 1 | 12 | 70 | 100 | 5 | 4 | route open work to this lane and dispatch before the window resets |
| `agy` | `blocked` | 5 | 24 | 70 | 100 | 0 | 8 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 20 | 7 | 10 | 0 | 8 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `unproductive` | 0 | 20 | 2 | 100 | 5 | 3 | heal failed/rerouted dispatches so attempts become done/dispatched work |

## Evidence

- `jules`: productive 54/70; attempts 57/70
- `claude`: attempted 8/1, but productive board spend is 0/1
- `opencode`: productive 1/70; attempts 12/70
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 20/7, but productive board spend is 0/7
- `codex`: attempted 20/2, but productive board spend is 0/2
