# Capacity Fill

Generated: `2026-06-29T23:45:39+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `codex` | `healthy` | 6 | 0 | 6 | 100 | 7 | 10 | keep pacing normally |
| `claude` | `no_work` | 0 | 0 | 6 | 100 | 0 | 0 | generate or route appropriate open work for this lane |
| `opencode` | `underfilled` | 1 | 0 | 74 | 100 | 8 | 4 | route open work to this lane and dispatch before the window resets |
| `agy` | `blocked` | 5 | 0 | 74 | 100 | 3 | 9 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `underfilled` | 0 | 0 | 7 | 10 | 4 | 8 | route open work to this lane and dispatch before the window resets |
| `jules` | `underfilled` | 63 | 0 | 74 | 100 | 14 | 56 | route open work to this lane and dispatch before the window resets |

## Evidence

- `codex`: productive 6/6; attempts 0/6
- `claude`: productive 0/6, but no open/any work is available
- `opencode`: productive 1/74; attempts 0/74
- `agy`: lane is down by the live dispatch gate
- `gemini`: productive 0/7; attempts 0/7
- `jules`: productive 63/74; attempts 0/74
