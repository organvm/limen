# Capacity Fill

Generated: `2026-06-30T00:33:19+00:00`

Status: `blocked`

| Lane | Status | Productive | Attempts | Expected now | Target | Open work | Active | Action |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `jules` | `underfilled` | 63 | 7 | 78 | 100 | 9 | 60 | route open work to this lane and dispatch before the window resets |
| `claude` | `no_work` | 0 | 0 | 1 | 15 | 0 | 0 | generate or route appropriate open work for this lane |
| `opencode` | `underfilled` | 1 | 2 | 78 | 100 | 3 | 5 | route open work to this lane and dispatch before the window resets |
| `agy` | `no_work` | 5 | 6 | 78 | 100 | 0 | 23 | generate or route appropriate open work for this lane |
| `gemini` | `no_work` | 0 | 5 | 8 | 10 | 0 | 10 | generate or route appropriate open work for this lane |
| `codex` | `underfilled` | 6 | 5 | 9 | 100 | 1 | 10 | route open work to this lane and dispatch before the window resets |

## Evidence

- `jules`: productive 63/78; attempts 7/78
- `claude`: productive 0/1, but no open/any work is available
- `opencode`: productive 1/78; attempts 2/78
- `agy`: productive 5/78, but no open/any work is available
- `gemini`: productive 0/8, but no open/any work is available
- `codex`: productive 6/9; attempts 5/9
