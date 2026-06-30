# Capacity Fill

Generated: `2026-06-30T11:51:32+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `codex` | `no_work` | 0 | 29 | 61 | 100 | 0 | 0 | generate or route appropriate open work for this lane |
| `claude` | `blocked` | 0 | 18 | 9 | 15 | 1 | 0 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `opencode` | `no_work` | 0 | 40 | 46 | 100 | 0 | 1 | generate or route appropriate open work for this lane |
| `agy` | `no_work` | 0 | 42 | 46 | 100 | 0 | 0 | generate or route appropriate open work for this lane |
| `gemini` | `unproductive` | 0 | 46 | 2 | 10 | 0 | 0 | heal failed/rerouted dispatches so attempts become done/dispatched work |
| `ollama` | `blocked` | 0 | 0 | 1 | 1 | 0 | 0 | fix lane reachability/auth/budget before routing more work |
| `jules` | `blocked` | 88 | 106 | 24 | 100 | 15 | 71 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `copilot` | `blocked` | 0 | 0 | 1 | 1 | 0 | 0 | fix lane reachability/auth/budget before routing more work |
| `warp` | `blocked` | 0 | 0 | 1 | 1 | 0 | 0 | fix lane reachability/auth/budget before routing more work |
| `oz` | `blocked` | 0 | 0 | 1 | 1 | 0 | 0 | fix lane reachability/auth/budget before routing more work |
| `github_actions` | `underfilled` | 0 | 0 | 1 | 1 | 31 | 0 | route open work to this lane and dispatch before the window resets |

## Evidence

- `codex`: productive 0/61, but no open/any work is available
- `claude`: lane is down by the live dispatch gate
- `opencode`: productive 0/46, but no open/any work is available
- `agy`: productive 0/46, but no open/any work is available
- `gemini`: attempted 46/2, but productive board spend is 0/2
- `ollama`: productive 0/1, but the lane is not reachable
- `jules`: lane is down by the live dispatch gate
- `copilot`: productive 0/1, but the lane is not reachable
- `warp`: productive 0/1, but the lane is not reachable
- `oz`: productive 0/1, but the lane is not reachable
- `github_actions`: productive 0/1; attempts 0/1
