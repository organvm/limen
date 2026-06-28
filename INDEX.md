# Limen Main Conductor Trench

Generated: `2026-06-28`

You are in a dedicated Limen worktree:

```bash
/Users/4jp/Workspace/limen-main-trench-20260628
```

This is the main session stream: make Limen self-conducting instead of merely
documented. Do not treat the prompt as a license to mutate GitHub, credentials,
launchd, or queue state without the exact gates below.

## First Read

Read the current repo truth first:

```bash
sed -n '1,220p' AGENTS.md
sed -n '1,260p' docs/lanes/main-conductor-trench.md
sed -n '1,260p' docs/consolidation/RUNBOOK.md
sed -n '1,260p' docs/consolidation/SCOPE-AND-APP.md
sed -n '1,260p' docs/consolidation/COLLISION-RENAMES.md
sed -n '1,260p' docs/github-app-architecture.md
sed -n '1,260p' docs/DISPATCH-ARCHITECTURE.md
sed -n '1,220p' logs/session-orientation.md 2>/dev/null || true
```

Then orient read-only:

```bash
git status --branch --short
git log --oneline -5
git -C /Users/4jp/Workspace/limen status --branch --short
```

## Mission

Advance the self-conducting enforcement path:

- finish or packetize the GitHub/org consolidation enforcement path;
- resolve or update the collision rename packet;
- verify the `organvm` migration state;
- wire `limen[bot]` only if the App and secrets already exist, otherwise leave a
  precise blocked packet;
- verify async dispatch and heartbeat behavior;
- fold the network substrate lesson into conductor behavior;
- leave receipts that future Codex, Claude, Gemini, OpenCode, Jules, Warp, and
  Oz sessions can resume without rediscovery.

## Allowed Files

Use the narrowest needed set. Expected surfaces:

- `docs/lanes/main-conductor-trench.md`
- `docs/consolidation/**`
- `docs/github-app-architecture.md`
- `docs/DISPATCH-ARCHITECTURE.md`
- `docs/dispatch-health.md`
- `docs/live-root-gate.md`
- `docs/network-health.md`
- `scripts/consolidate-github.py`
- `scripts/rewrite-owners.py`
- `scripts/gh-app-token.sh`
- `scripts/dispatch-async.py`
- `scripts/async-run-one.py`
- `cli/src/limen/**`
- `cli/tests/test_async_dispatch.py`
- focused receipts under `docs/**`

Do not mutate `tasks.yaml` unless the human explicitly asks for board-state
changes or the work itself is a scoped task-state update.

## Hard Stop Gates

Stop and report exact commands before any:

- `gh repo rename`;
- `gh api -X POST repos/*/*/transfer`;
- `PYTHONPATH=cli/src python3 scripts/consolidate-github.py --apply`;
- `PYTHONPATH=cli/src python3 scripts/rewrite-owners.py --apply`;
- GitHub App creation/install;
- `bash scripts/set-credential.sh ...`;
- secret, keychain, `.env`, or credential write;
- heartbeat launchd reload or live plist install;
- force push, destructive cleanup, branch deletion, or Portvs work.

Read-only `gh` probes and dry runs are allowed.

## Exact Gates To Produce

Start with these commands and record their results:

```bash
gh auth status
gh api /orgs/organvm/installations --jq '.installations[] | .app_slug'
bash scripts/gh-app-token.sh --which
PYTHONPATH=cli/src python3 scripts/consolidate-github.py
PYTHONPATH=cli/src python3 scripts/rewrite-owners.py
pytest -q cli/tests/test_async_dispatch.py
python3 scripts/watchdog.py --dry-run
```

For async state, also inspect without changing live launchd:

```bash
PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run
```

## Work Style

If paid lanes are used later, conduct them. Every lane packet needs:

- purpose;
- repo/worktree;
- allowed files;
- stop condition;
- verification command;
- receipt path.

The main stream should not absorb everything. If an issue belongs to
`network-substrate` or `rob-game`, hand it to that lane with a bounded packet.

## Receipt Required

Before handoff, leave:

- branch and commit;
- current collision count;
- current `organvm` repo count;
- current GitHub App/token path state;
- async dispatch test result;
- watchdog/heartbeat result;
- exact remaining human gates;
- next trench for the following session.
