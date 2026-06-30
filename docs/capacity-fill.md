# Capacity Fill

Generated: `2026-06-29T23:13:04+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `no_work` | 50 | 48 | 72 | 100 | 0 | 46 | generate or route appropriate open work for this lane |
| `claude` | `no_work` | 0 | 5 | 8 | 15 | 0 | 0 | generate or route appropriate open work for this lane |
| `opencode` | `no_work` | 1 | 6 | 72 | 100 | 0 | 1 | generate or route appropriate open work for this lane |
| `agy` | `blocked` | 5 | 6 | 72 | 100 | 0 | 0 | clear the lane-down/auth/rate-limit gate, then route and dispatch this lane |
| `gemini` | `no_work` | 0 | 5 | 7 | 10 | 0 | 0 | generate or route appropriate open work for this lane |
| `codex` | `no_work` | 1 | 15 | 51 | 100 | 0 | 0 | generate or route appropriate open work for this lane |

## Evidence

- `jules`: productive 50/72, but no open/any work is available
- `claude`: productive 0/8, but no open/any work is available
- `opencode`: productive 1/72, but no open/any work is available
- `agy`: lane is down by the live dispatch gate
- `gemini`: productive 0/7, but no open/any work is available
- `codex`: productive 1/51, but no open/any work is available
