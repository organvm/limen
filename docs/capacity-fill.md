# Capacity Fill

Generated: `2026-06-30T04:01:00+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `healthy` | 96 | 35 | 92 | 100 | 60 | 57 | keep pacing normally |
| `claude` | `unproductive` | 0 | 12 | 1 | 15 | 0 | 3 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `opencode` | `no_work` | 1 | 20 | 92 | 100 | 0 | 4 | generate or route appropriate open work for this lane |
| `agy` | `blocked` | 5 | 20 | 92 | 100 | 0 | 3 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 29 | 9 | 10 | 0 | 3 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `unproductive` | 0 | 23 | 1 | 100 | 1 | 13 | heal failed/rerouted dispatches so attempts become done/dispatched work |

## Evidence

- `jules`: productive 96/92; attempts 35/92
- `claude`: attempted 12/1, but productive board spend is 0/1
- `opencode`: productive 1/92, but no open/any work is available
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 29/9, but productive board spend is 0/9
- `codex`: attempted 23/1, but productive board spend is 0/1
