# Capacity Fill

Generated: `2026-06-29T23:15:34+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 59 | 61 | 72 | 100 | 18 | 56 | route open work to this lane and dispatch before the window resets |
| `claude` | `unproductive` | 0 | 8 | 1 | 15 | 0 | 0 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `opencode` | `underfilled` | 1 | 15 | 72 | 100 | 5 | 3 | route open work to this lane and dispatch before the window resets |
| `agy` | `blocked` | 5 | 33 | 72 | 100 | 1 | 9 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 20 | 7 | 10 | 0 | 0 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `unproductive` | 3 | 23 | 4 | 100 | 2 | 6 | heal failed/rerouted dispatches so attempts become done/dispatched work |

## Evidence

- `jules`: productive 59/72; attempts 61/72
- `claude`: attempted 8/1, but productive board spend is 0/1
- `opencode`: productive 1/72; attempts 15/72
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 20/7, but productive board spend is 0/7
- `codex`: attempted 23/4, but productive board spend is 3/4
