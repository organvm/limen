# Conductor Tranche

Generated: `2026-06-29T21:26:55+00:00`

Summary: `tranche-remote-receipts-disabled` -> `remote-receipts-disabled` (`blocker`); stop before: Stop before changing task states, launching live dispatch, or touching credentials unless the packet explicitly includes that gate.

## Cadence Contract

- Work in one-to-two-hour direct-session tranches.
- Start from current receipts, not memory.
- Implement reversible local fixes first.
- Close incident classes with reusable receipts and gates, not one-lane symptom patches.
- Leave owner receipts and exact verification commands before stopping.

## Selected Trench

| Field | Value |
|---|---|
| Packet | `tranche-remote-receipts-disabled` |
| Selected path | `remote-receipts-disabled` |
| Kind | `blocker` |
| Lane | `blocker` |
| Score | `72` |
| Agent fit | `codex` |
| Attack index generated | `2026-06-29T21:26:48+00:00` |
| Ranked paths read | `41` |
| Skipped family/human-gate/parked/observe/auth paths | `session_lifecycle`, `dispatch-heartbeat-substrate-unhealthy`, `worktree_lifecycle`, `github_review`, `github-app-limen-bot-not-wired`, `github-consolidation-collisions`, `agent_coordination`, `technical_debt_ci`, `local-lifecycle-disk-pressure`, `convergence_corpus`, `mirror-mirror`, `the-invisible-ledger`, `triptych-story`, `gen-organvm-universal-mail--automation-test-coverage-0625-151e`, `uncategorized`, `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b`, `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f`, `credential-codex-auth-sessions`, `cifix-organvm-i-theoria-conversation-corpus-engine-f02e`, `cifix-organvm-i-theoria-hierarchia-mundi-3145`, `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2`, `discover-organvm-kerygma-profiles-6c74`, `bld-mirror-mirror-harden-350f`, `bld-my--father-mother-harden-44b2`, `bld-promptscope-next-rev-3fde`, `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38`, `resolve-organvm-i-theoria-.github-459-1ade`, `auth_credentials` |

## Work Packet

Purpose: Repair dispatch/remote proof drift so the queue can distinguish healthy async work, stranded claims, merged PRs, and real blockers.

Repo/worktree: `organvm/limen` conductor checkout only.

Allowed files:

- `scripts/dispatch*.py`
- `scripts/verify-dispatch.py`
- `scripts/heal-dispatch.py`
- `cli/tests/test_async_dispatch.py`
- `docs/DISPATCH-ARCHITECTURE.md`
- `docs/conductor-tranche.md`

Forbidden:

- `/Users/4jp/Workspace/4444J99/portvs`
- `creative placement work`
- `plaintext secrets or credential values`
- `irreversible GitHub transfer/rename/App install/credential actions`
- `task-board mutation unless the direct request explicitly requires it`

Stop condition: Stop before changing task states, launching live dispatch, or touching credentials unless the packet explicitly includes that gate.

Receipt: docs/DISPATCH-ARCHITECTURE.md and docs/conductor-tranche.md.

Verification:

- `pytest -q cli/tests/test_async_dispatch.py`
- `python3 scripts/verify-dispatch.py`
- `python3 scripts/conductor-tranche.py --write`

## Source Next Action

Refresh with remote enabled before using GitHub state as closure proof.

## Refresh

- `python3 scripts/consolidation-gates.py --write`
- `python3 scripts/session-lifecycle-pressure.py --write`
- `python3 scripts/live-root-gate.py --write`
- `python3 scripts/session-blockers-ledger.py --write`
- `python3 scripts/session-attack-paths.py --write`
- `python3 scripts/conductor-tranche.py --write`
