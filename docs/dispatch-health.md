# Dispatch Health

Generated: `2026-06-29T21:37:17+00:00`

Status: `blocked`

## Incident Class

- Dispatch/heartbeat health is not proven by tests in a detached worktree alone.
- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.
- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.

## Heartbeat

- LaunchAgent plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Plist KeepAlive: `True`; RunAtLoad: `True`.
- Plist LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Plist LIMEN_DISPATCH_ASYNC: `0`.
- Loaded launchd state: `running` pid `1656`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `0`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-06-29T21:37:17.727383+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `False`.
- Async dry-run ok: `None`; timed out `False`.
- Async dry-run summary: ``.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 1]`.
- HEAD: `78f7de9f8c31c75d68cce82fd8800d72be249145`.
- origin/main: `7ecdd65a529802a581d173b4cb390d19bcb20e55`.
- Matches origin/main: `False`; ahead `9` behind `0`.
- Dirty entries: `27`.
  - `cli/tests/test_aug1_view.py`
  - `cli/tests/test_corpus_command_center.py`
  - `docs/conductor-tranche.md`
  - `docs/corpus-command-center.md`
  - `docs/dispatch-health.md`
  - `docs/live-root-gate.md`
  - `docs/positioning/public-record-data-scrapper-case-study.md`
  - `docs/positioning/public-record-data-scrapper-contact-path.md`
  - `docs/positioning/public-record-data-scrapper-proof-page.md`
  - `docs/positioning/public-record-data-scrapper-sample-output.json`
  - `docs/prompt-batch-review-ledger.md`
  - `docs/prompt-lifecycle-ledger.md`
  - `docs/prompt-packet-ledger.md`
  - `docs/prompt-packet-resolution-receipts.json`
  - `docs/prompt-priority-map.md`
  - `docs/root-to-leaf-acceptance-packet-2026-06-29.md`
  - `docs/session-attack-paths.md`
  - `docs/session-lifecycle-blockers.md`
  - `scripts/aug1-view.py`
  - `scripts/corpus-command-center.py`
  - `scripts/verify-whole.sh`
  - `state/aug1/pipeline-scoreboard.json`
  - `cli/tests/test_prompt_acceptance_ledger.py`
  - `docs/prompt-acceptance-ledger.md`
  - `docs/prompt-acceptance-standard.md`
  - `scripts/prompt-acceptance-ledger.py`
  - `state/outward-reciprocity.json`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 1]`.
- HEAD matches origin/main: `False`.

## Blockers

- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head 78f7de9f8c31 differs from origin/main 7ecdd65a5298.
- `live-root-dirty`: live root has 27 dirty entries.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
