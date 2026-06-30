# Capacity Fill

Generated: `2026-06-30T14:27:24+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `codex` | `healthy` | 5 | 50 | 3 | 100 | 15 | 5 | keep pacing normally |
| `claude` | `unproductive` | 0 | 25 | 1 | 15 | 13 | 5 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `opencode` | `unproductive` | 0 | 35 | 35 | 100 | 14 | 4 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `agy` | `blocked` | 0 | 39 | 35 | 100 | 13 | 5 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `unproductive` | 0 | 51 | 3 | 10 | 13 | 5 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `ollama` | `blocked` | 0 | 0 | 1 | 1 | 10 | 0 | fix lane reachability/auth/budget before routing more work |
| `jules` | `healthy` | 91 | 108 | 35 | 100 | 29 | 70 | keep pacing normally |
| `copilot` | `blocked` | 0 | 0 | 1 | 1 | 10 | 0 | fix lane reachability/auth/budget before routing more work |
| `warp` | `blocked` | 0 | 0 | 1 | 1 | 10 | 0 | fix lane reachability/auth/budget before routing more work |
| `oz` | `blocked` | 0 | 0 | 1 | 1 | 10 | 0 | fix lane reachability/auth/budget before routing more work |
| `github_actions` | `unproductive` | 0 | 1 | 1 | 1 | 42 | 0 | heal failed/rerouted dispatches so attempts become done/dispatched work |

## Evidence

- `codex`: productive 5/3; attempts 50/3
- `claude`: attempted 25/1, but productive board spend is 0/1
- `opencode`: attempted 35/35, but productive board spend is 0/35
- `agy`: lane is down by the live dispatch gate
- `gemini`: attempted 51/3, but productive board spend is 0/3
- `ollama`: productive 0/1, but the lane is not reachable
- `jules`: productive 91/35; attempts 108/35
- `copilot`: productive 0/1, but the lane is not reachable
- `warp`: productive 0/1, but the lane is not reachable
- `oz`: productive 0/1, but the lane is not reachable
- `github_actions`: attempted 1/1, but productive board spend is 0/1
