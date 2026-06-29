# Capacity Fill

Generated: `2026-06-29T22:15:32+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 51 | 51 | 68 | 100 | 15 | 44 | route open work to this lane and dispatch before the window resets |
| `claude` | `underfilled` | 0 | 5 | 15 | 15 | 15 | 0 | route open work to this lane and dispatch before the window resets |
| `opencode` | `underfilled` | 1 | 10 | 100 | 100 | 15 | 1 | route open work to this lane and dispatch before the window resets |
| `agy` | `underfilled` | 5 | 11 | 100 | 100 | 15 | 0 | route open work to this lane and dispatch before the window resets |
| `gemini` | `blocked` | 0 | 5 | 7 | 10 | 7 | 0 | fix lane reachability/auth/budget before routing more work |
| `codex` | `depleted` | 1 | 17 | 100 | 100 | 0 | 0 | wait for this lane's meter to refresh or fail over before feeding it again |

## Evidence

- `jules`: productive 51/68; attempts 51/68
- `claude`: productive 0/15; attempts 5/15
- `opencode`: productive 1/100; attempts 10/100
- `agy`: productive 5/100; attempts 11/100
- `gemini`: productive 0/7, but the lane is not reachable
- `codex`: usage meter health=throttle; observed=17, productive=1
