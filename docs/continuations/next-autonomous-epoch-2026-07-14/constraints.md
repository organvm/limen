# Authorities and constraints

## Current operator override

- Autonomous execution is intentionally paused for restart and study. No lane launch, merge, rebase,
  PR mutation, worktree reclaim, or cleanup is authorized until an explicit post-study resume.
- The pause marker is a deliberate human gate, not stale runtime residue. Do not auto-clear it merely
  because the computer restarted or an earlier PR merged.
- The user-led Claude processes remain a separate owner. This closeout did not kill or mutate them;
  the operating-system restart is their termination boundary.

- Follow the nearest `AGENTS.md`, typed task contracts, and owner receipts on GitHub.
- Treat GitHub as remote truth and local checkouts as disposable caches or preservation surfaces.
- Routine isolated code PRs, focused verification, and policy-cleared serial merges are authorized.
- Mass merges, force pushes, public messaging unrelated to an owner PR, paid overages, remote branch
  deletion, credential/account actions, and personal-data deletion remain gated.
- Keep code, board projection, lifecycle receipts, and analysis in separate commits/PRs.
- Never edit `tasks.yaml` directly; submit changes through TABVLARIVS.

## Inherited safety boundaries

- The user-led Claude session is a separate owner. Re-probe it by counts/process/remote receipts only.
  Do not inspect raw transcript bodies or active worktree diffs, and do not kill, answer, approve,
  rebase, push, merge, comment on, or rerun its work.
- External volumes were cleanly ejected. Treat `/Volumes/*` work as unavailable unless the expected
  mount is observed live; never infer that a drive has been reconnected.
- The installed heartbeat and overnight-watch jobs were idle at closeout. The current pause marker
  made `autonomy-governor.py explain` report `mode=paused` and `dispatchAllowed=false`; the latest
  overnight-watch receipt reported `autonomy_paused` with zero active workers.
- Preserve dirty, divergent, open-PR, locked, active, and non-Git roots. Only the accepted reaper may
  remove a root after exact remote custody and its configured lifecycle predicate pass.
