# Deployment

Production deployment is separate from the agent dispatch protocol in `AGENTS.md`. Follow this file
when a task explicitly asks for SaaS deployment or deployment configuration.

## Required environment

For the web API:

| Variable | Required | Description |
|----------|----------|-------------|
| `LIMEN_API_TOKEN` | Yes | Bearer token for API auth |
| `LIMEN_ROOT` | Yes | Path to the Limen root on disk |
| `LIMEN_TASKS` | No | Alternative path to `tasks.yaml` |

For the Next.js dashboard, set `NEXT_PUBLIC_API_URL` to the API endpoint. Local development defaults
to `http://localhost:8000`.

## Execution-trajectory owner

`limen harvest` publishes each registered terminal attempt through an exact-head
compare-and-set update to a dedicated GitHub owner branch. The default owner is
`organvm/limen`, branch `execution-trajectories`, under
`receipts/execution-trajectories/`. Provision that branch through the GitHub
account/App owner before enabling a production harvest host.

The deployment knobs are:

| Variable | Default | Description |
|----------|---------|-------------|
| `LIMEN_TRAJECTORY_PUBLICATION` | `1` | Set `0` only for an explicit operational pause |
| `LIMEN_TRAJECTORY_OWNER_REPO` | `organvm/limen` | Exact owner repository |
| `LIMEN_TRAJECTORY_OWNER_REF` | `execution-trajectories` | Dedicated pre-provisioned branch |
| `LIMEN_TRAJECTORY_OWNER_ROOT` | `receipts/execution-trajectories` | Repository-relative receipt root |
| `LIMEN_TRAJECTORY_GH_BIN` | `gh` | Authenticated GitHub CLI |
| `LIMEN_TRAJECTORY_MAX_RECORDS` | `25` | Per-task record bound |
| `LIMEN_TRAJECTORY_MAX_BYTES` | `262144` | Per-task canonical byte bound |

Publication failure never changes task lifecycle or grants value. The exact
terminal board event records the blocker and a later harvest retries it. Success
records an immutable GitHub blob URL and canonical digest.

## Railway API

```bash
railway login
railway init
railway up
```

## Vercel dashboard

```bash
vercel login
vercel --prod
```

## Safety checks

- Do not paste tokens or secret values into logs, PRs, commits, or task output.
- Treat deploy-trigger paths as website-sensitive; follow `CLAUDE.md` → **Merge & Branch Protocol**
  and `scripts/merge-policy.sh`.
- Record deployment evidence with the target environment, command, result, and rollback path.
