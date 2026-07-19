# Copilot instructions for `limen`

Limen is a cross-agent, cross-repo, budget-capped task intake system. A single `tasks.yaml`
(local file or GitHub-Contents mode) is the source of truth every AI agent reads/writes; a CLI,
FastAPI/Cloudflare Worker runtime, and Next.js dashboard sit around it.

For the full agent dispatch protocol, task-state machine, and merge/credential rules, read
**`AGENTS.md`** (protocol authority) and **`CLAUDE.md`** (Claude-specific execution charter) — this
file only covers what's needed to build/test/navigate the code.

## Build, test, lint

```bash
pip install -e 'cli[test]'                            # CLI + test extras
pip install -e mcp/                                    # MCP server (optional)
(cd web/app && npm install)                             # dashboard (optional)

python -m ruff check cli/src cli/tests web/api mcp     # lint (py311, line-length 120)
python -m pytest web/api/tests cli/tests -q            # full test suite
python -m pytest cli/tests/test_dispatch.py -q         # one test file
python -m pytest cli/tests/test_dispatch.py::test_x    # one test case
python scripts/check-agent-docs.py                     # agent-doc <-> code state-vocab drift
node scripts/validate-contract-schemas.mjs             # spec/contracts JSON Schema validation
scripts/verify-whole.sh                                # whole-system predicate; exit 0 = green
scripts/verify-scoped.sh                               # default push gate: only diff-implicated gates
```

- `web/worker`: `npm run check` (`node --check src/index.js && node --test`).
- `web/app`: `npm run build` (prebuild generates static data, fetches PR status, validates
  surface contracts against `spec/contracts/`).
- Never run the full gate matrix as a routine local habit — `scripts/verify-scoped.sh` maps the
  changed paths to only the gates they implicate and prints what it skipped. Run the full matrix
  (or let CI run it) only when the diff touches a deploy-trigger path (declared in
  `institutio/governance/gates.yaml`) or scoping can't attribute the change.

## Architecture (why files span multiple directories)

```
tasks.yaml (source of truth: task list + portal.budget)
    │
    ├── cli/           limen CLI — dispatch.py, harvest.py, capacity.py, model_selection.py,
    │                  converge.py (logic); models.py (data shapes); io.py (local file vs
    │                  GitHub-Contents storage, selected by LIMEN_TASKS vs LIMEN_GITHUB_REPO)
    ├── mcp/            MCP server exposing tasks.yaml over Model Context Protocol
    │                  (mcp/src/limen_mcp/server.py — canonical VALID_STATUSES lives here)
    ├── ianva/          MCP doorway/aggregator
    ├── web/api/        FastAPI runtime adapter (same HTTP contract as the Worker)
    ├── web/worker/     Cloudflare Worker — the LIVE runtime, GitHub-Contents storage;
    │                  deploys on-demand via wrangler, not on merge
    ├── web/app/        Next.js dashboard (static export). Surfaces: / (owner), /qa, /client,
    │                  /public — gated by persona bearer tokens (LIMEN_OWNER_TOKEN/
    │                  LIMEN_API_TOKEN, LIMEN_CLIENT_TOKEN)
    ├── spec/contracts/ Portable JSON Schemas the generated surface contracts must satisfy
    └── scripts/        ~120 operational scripts: metabolize.sh/heartbeat-loop.sh (the beat),
                       verify-whole.sh / verify-scoped.sh (predicates), merge-policy.sh
                       (merge decision), organ-health.py, creds-hydrate.py (credentials)
```

- **Storage mode is env-selected, not hardcoded**: `LIMEN_TASKS=/path` → local file; else
  `LIMEN_GITHUB_REPO` + `LIMEN_GITHUB_TOKEN` (+ optional `_BRANCH`/`_PATH`) → GitHub Contents API.
  Code in `cli/src/limen/io.py` must keep both paths working.
- **Task lifecycle is the durable contract, providers are swappable adapters.** Normal flow:
  `open → dispatched → in_progress → done → archived`; from `in_progress` a task may instead move
  to `failed`, `failed_blocked`, or `needs_human`. The canonical state set is `VALID_STATUSES` in
  `mcp/src/limen_mcp/server.py` — **do not invent new states**; `scripts/check-agent-docs.py`
  checks doc/code parity.
- **Gate and beat-sensor estates are declared data, not hand-maintained tables**:
  `institutio/governance/gates.yaml` (GATES registry: command, implicating paths, cost tier) and
  `institutio/governance/sensors.yaml` (continuous-runtime sensors). `scripts/verify.py` and
  `scripts/beat-sensors.py` derive their behavior from these files; `check-gates.py` /
  `check-sensors.py` enforce registry↔workflow parity in CI. Add a gate/sensor = add one registry
  entry, not a new shell block.
- **Declarative registries drive automation** — don't hardcode facts already owned by:
  `organ-ladder.json` (self-* organ ladder), `pillars.yaml` (platform pillars),
  `his-hand-levers.json` (human-gated lever registry), `runtime.config.json`.

## Key conventions

- Python targets 3.11, Ruff line-length 120. CLI logic goes in small testable modules under
  `cli/src/limen/`; tests mirror them under `cli/tests/test_*.py` (`test_<behavior>` case names).
  API tests live under `web/api/tests/`.
- Model/tier selection for any Claude sub-agent fan-out is **derived**, not memorized:
  `cli/src/limen/model_selection.py` is the tier authority (job class → tier). Never hardcode
  model IDs/catalog snapshots — treat provider catalogs as live external state.
- Branch naming is intent-based: `feat/`, `fix/`, `heal/`, `chore/`, `docs/`, `refactor/`,
  `worktree-*`. One PR per branch → `main`, squash-merge. Never commit to `main` directly except
  the machine board-write lane (`tasks.yaml` via the keeper/worker).
- A merge to `main` auto-deploys the live site/API **only** when the diff touches a path listed in
  `institutio/governance/gates.yaml`'s `deploy_triggers` block — that's the one merge guardrail;
  `scripts/merge-policy.sh <PR#>` is the executable decision (CLEARED/HOLD/BLOCKED), not memory.
- Credentials/secrets are never hardcoded or pasted into code, commits, or config: they route
  through `scripts/creds-hydrate.py`'s `DEFAULT_MAP` (1Password `op://` source → env/file/
  `gh_secret` sinks).
- Shell scripts should be idempotent and safe to re-run (`set -euo pipefail` for new scripts).

## Cross-repo mission (github-universe)

- The canonical cross-repo doctrine lives at `$HOME/.copilot/copilot-instructions.md`; keep this
  repo-scoped file brief and defer to that charter for the broader `organvm` + `4444J99` universe.
- In this repo, `scripts/github-universe-sweep.py` enumerates repositories, issues, and PRs, and
  `github-universe-ledger.json` records durable per-item dispositions:
  `queued` / `engaged` / `evolving` / `distilled` / `merged` / `superseded` / `reopen-candidate`.
- Do not use `closed` or `dismissed` as terminal doctrine labels in that ledger.
- `docs/github-universe-mission.md` carries the fuller mechanism writeup.
