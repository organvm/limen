# Capacity Fill

Generated: `2026-06-29T22:43:39+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `codex` | `underfilled` | 0 | 0 | 100 | 100 | 5 | 3 | route open work and dispatch before the window resets |
| `claude` | `no_work` | 0 | 0 | 15 | 15 | 0 | 0 | generate or route open work for this lane |
| `opencode` | `underfilled` | 0 | 0 | 100 | 100 | 5 | 4 | route open work and dispatch before the window resets |
| `agy` | `blocked` | 0 | 0 | 100 | 100 | 0 | 8 | clear gate/dispatch issues, then route and dispatch work |
| `gemini` | `no_work` | 0 | 0 | 10 | 10 | 0 | 8 | generate or route open work for this lane |
| `jules` | `underfilled` | 0 | 0 | 100 | 100 | 14 | 52 | route open work and dispatch before the window resets |
| `copilot` | `blocked` | 0 | 0 | 100 | 100 | 0 | 0 | fix lane reachability/auth/budget before feeding work |
| `warp` | `blocked` | 0 | 0 | 10 | 10 | 0 | 0 | fix lane reachability/auth/budget before feeding work |
| `oz` | `blocked` | 0 | 0 | 10 | 10 | 39 | 0 | fix lane reachability/auth/budget before feeding work |
| `github_actions` | `underfilled` | 0 | 0 | 10 | 10 | 40 | 0 | route open work and dispatch before the window resets |

## Evidence

- `codex`: productive 0/100; attempts 0/100
- `claude`: productive 0/15, but no open/any work is available
- `opencode`: productive 0/100; attempts 0/100
- `agy`: lane is down by the live dispatch gate
- `gemini`: productive 0/10, but no open/any work is available
- `jules`: productive 0/100; attempts 0/100
- `copilot`: productive 0/100, but the lane is not reachable
- `warp`: productive 0/10, but the lane is not reachable
- `oz`: productive 0/10, but the lane is not reachable
- `github_actions`: productive 0/10; attempts 0/10
