# Capacity Fill

Generated: `2026-06-30T01:12:45+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 73 | 16 | 80 | 100 | 5 | 65 | route open work to this lane and dispatch before the window resets |
| `claude` | `no_work` | 0 | 0 | 2 | 15 | 0 | 0 | generate or route appropriate open work for this lane |
| `opencode` | `no_work` | 1 | 7 | 80 | 100 | 0 | 6 | generate or route appropriate open work for this lane |
| `agy` | `blocked` | 5 | 15 | 80 | 100 | 0 | 21 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 8 | 8 | 10 | 0 | 8 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `codex` | `healthy` | 12 | 9 | 12 | 100 | 0 | 13 | keep pacing normally |

## Evidence

- `jules`: productive 73/80; attempts 16/80
- `claude`: productive 0/2, but no open/any work is available
- `opencode`: productive 1/80, but no open/any work is available
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 8/8, but productive board spend is 0/8
- `codex`: productive 12/12; attempts 9/12
