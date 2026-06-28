# Main Conductor Trench Lane

Generated: `2026-06-28`

Status: `active`

## Identity

- Lane handle: `main-conductor-trench`.
- Primary repo: `organvm/limen`.
- Local stream worktree: `/Users/4jp/Workspace/limen-main-trench-20260628`.
- Live dirty root to watch but not casually mutate:
  `/Users/4jp/Workspace/limen`.
- Domain: GitHub/org consolidation, `limen[bot]`, async dispatch, heartbeat,
  worktree/root reconciliation, and durable session receipts.

This is a workstream lane, not a new Limen `target_agent`. Use canonical
agents only.

## Current Ground Truth

As of the stream seed:

- `origin/main` includes the Rob game lane receipt at commit `fec929a`.
- The live root is on `feature/ORG-artist-organ-face-0628`, behind `main`, and
  dirty with network-related edits plus unrelated local state.
- `docs/consolidation/RUNBOOK.md` reports:
  - `gh` is logged in as `4444J99` with `admin:org`, `workflow`, `repo`, and
    `gist`;
  - `organvm` exists and holds 264 repos;
  - 34 source repos remain outside `organvm`;
  - 13 collision groups remain;
  - bulk consolidation `--apply` aborts while collisions remain unless an
    explicit partial gate is supplied;
  - `limen[bot]` is not installed/wired and the token helper falls back to PAT;
  - async dispatch is implemented and tested but not enabled in the live plist.

Every future session must recheck these facts before using them as current.

## Purpose

This lane exists to make Limen self-conducting:

- consolidate owner/org state with reversible packets before irreversible
  mutation;
- keep collision renames exact and reviewable;
- distinguish temporary personal-token bridges from durable App identity;
- make async dispatch and heartbeat behavior observable before activation;
- reconcile live-root dirt without hiding or reverting unrelated user work;
- create bounded packets for other lanes instead of sending everything to one
  agent by default;
- leave committed receipts so the next model starts from evidence, not memory.

## Allowed Files

Primary implementation and receipts:

- `docs/lanes/main-conductor-trench.md`
- `docs/lanes/README.md`
- `docs/consolidation/**`
- `docs/github-app-architecture.md`
- `docs/DISPATCH-ARCHITECTURE.md`
- `docs/dispatch-health.md`
- `docs/live-root-gate.md`
- `docs/network-health.md`
- `docs/conductor-tranche.md`
- `scripts/consolidate-github.py`
- `scripts/rewrite-owners.py`
- `scripts/gh-app-token.sh`
- `scripts/dispatch-async.py`
- `scripts/async-run-one.py`
- `scripts/watchdog.py`
- `scripts/heartbeat-loop.sh`
- `container/launchd/com.limen.heartbeat.plist`
- `cli/src/limen/**`
- `cli/tests/test_async_dispatch.py`

Board-state files:

- `tasks.yaml` only when explicitly requested or when a scoped dispatch-mode
  task-state update is the work.

Read-only comparison targets:

- `/Users/4jp/Workspace/limen`
- GitHub org/repo state via read-only `gh` commands
- launchd heartbeat state via read-only probes

## Forbidden / Stop Gates

Stop before:

- `gh repo rename`;
- repository transfer API calls;
- consolidation `--apply`;
- owner rewrite `--apply`;
- GitHub App creation or installation;
- credential, keychain, secret, or `.env` writes;
- heartbeat launchd reloads or live plist installs;
- force pushes, destructive cleanup, branch deletion, or broad remote mutation;
- touching `/Users/4jp/Workspace/4444J99/portvs`;
- creative placement work.

## Standard Work Packet

Use this shape for future queue packets:

```yaml
labels: [main-conductor-trench, limen]
repo: organvm/limen
target_agent: <canonical Limen agent>
context: >
  Work in /Users/4jp/Workspace/limen-main-trench-20260628 or a fresh worktree
  from origin/main. Recheck consolidation, App identity, async dispatch, and
  heartbeat state from current repo truth. Produce exact gates before any
  irreversible GitHub, credential, launchd, or queue mutation. Leave a receipt
  with commands, results, changed paths, and the next trench.
```

## Resume Commands

Read-only orientation:

```bash
git status --branch --short
git log --oneline -5
git -C /Users/4jp/Workspace/limen status --branch --short
sed -n '1,220p' logs/session-orientation.md 2>/dev/null || true
```

Consolidation and identity probes:

```bash
gh auth status
gh api /orgs/organvm/installations --jq '.installations[] | .app_slug'
bash scripts/gh-app-token.sh --which
PYTHONPATH=cli/src python3 scripts/consolidate-github.py
PYTHONPATH=cli/src python3 scripts/rewrite-owners.py
```

Dispatch and heartbeat probes:

```bash
pytest -q cli/tests/test_async_dispatch.py
PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run
python3 scripts/watchdog.py --dry-run
```

## Receipt Required

Every completed main-conductor packet should record:

- branch and commit;
- exact commands run;
- collision count and remaining rename packet state;
- current source-owner and `organvm` counts;
- App installation/token path state;
- async dispatch/heartbeat result;
- network-substrate interaction, if any;
- remaining human gates;
- next worktree or lane to open.
