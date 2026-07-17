# Tabularius Writer Audit

<!-- tabularius-writer-audit:owner-recorded -->

Direct writer calls: `29`
Unclassified calls: `3`

## Owner Packets

| Packet | Tier | Calls | Owner | Predicate | Disposition |
|---|---|---:|---|---|---|
| `TAB-CREATION-FALLBACKS` | `creation-fallback` | `2` | `peer-integration` | `python3 scripts/task-writer-audit.py` | remove or gate legacy direct fallback branches after producer parity is proven live |
| `TAB-HUMAN-ATOM-STATUS-WRITERS` | `human-atom-status` | `3` | `peer-integration` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q` | convert continuity/routine needs_human atom upserts to keeper-owned status/upsert tickets |
| `TAB-MAINTENANCE-BOARD-FALLBACKS` | `board-maintenance` | `4` | `peer-integration` | `python3 scripts/task-writer-audit.py` | decide whether each maintenance writer belongs to Tabularius/io allowlist or becomes a ticket producer |
| `TAB-ROUTE-RESIDUE-MUTATORS` | `routing-metadata` | `3` | `peer-integration` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q` | convert routing, residue, and self-improve board patches to keeper-owned tickets |
| `TAB-STATUS-ASYNC-HEAL` | `status-result` | `6` | `peer-integration` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py cli/tests/test_async_dispatch.py -q` | convert async reserve/reap/heal transitions to task.status tickets with no double-dispatch window |
| `TAB-STATUS-DISPATCH-RESULTS` | `status-result` | `5` | `peer-integration` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q` | convert dispatch claim/result application to task.status tickets or keeper-drained status batches |
| `TAB-STATUS-HARVEST-RESULTS` | `status-result` | `3` | `peer-integration` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q` | convert harvest/Jules landing result application to task.status tickets |
| `TAB-UNCLASSIFIED-WRITER` | `unclassified` | `3` | `peer-integration` | `python3 scripts/task-writer-audit.py` | classify this writer before Step 2.2 can be owner-recorded |

## Direct Writers

| Path | Line | Call | Owner packet |
|---|---:|---|---|
| `cli/src/limen/cli.py` | `87` | `tasks_file.write_text` | `TAB-MAINTENANCE-BOARD-FALLBACKS` |
| `cli/src/limen/dispatch.py` | `4355` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/dispatch.py` | `5166` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/dispatch.py` | `5104` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/dispatch.py` | `5362` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/dispatch.py` | `5100` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/harvest.py` | `630` | `save_limen_file` | `TAB-STATUS-HARVEST-RESULTS` |
| `scripts/check-main-green.py` | `396` | `save_limen_file` | `TAB-UNCLASSIFIED-WRITER` |
| `scripts/check-main-green.py` | `375` | `save_limen_file` | `TAB-UNCLASSIFIED-WRITER` |
| `scripts/check-main-green.py` | `363` | `save_limen_file` | `TAB-UNCLASSIFIED-WRITER` |
| `scripts/dispatch-async.py` | `242` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/dispatch-async.py` | `1406` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/dispatch-async.py` | `659` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/dispatch-async.py` | `868` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/dispatch-async.py` | `1672` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/dispatch-continuity-check.py` | `338` | `save_limen_file` | `TAB-HUMAN-ATOM-STATUS-WRITERS` |
| `scripts/heal-board.py` | `331` | `atomic_write_text` | `TAB-MAINTENANCE-BOARD-FALLBACKS` |
| `scripts/heal-board.py` | `263` | `save_limen_file` | `TAB-MAINTENANCE-BOARD-FALLBACKS` |
| `scripts/heal-dispatch.py` | `298` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/jules-land.py` | `231` | `save_limen_file` | `TAB-STATUS-HARVEST-RESULTS` |
| `scripts/jules-land.py` | `228` | `save_limen_file` | `TAB-STATUS-HARVEST-RESULTS` |
| `scripts/mine-backlog.py` | `214` | `save_limen_file` | `TAB-CREATION-FALLBACKS` |
| `scripts/quicken.py` | `495` | `save_limen_file` | `TAB-ROUTE-RESIDUE-MUTATORS` |
| `scripts/rewrite-owners.py` | `107` | `save_limen_file` | `TAB-ROUTE-RESIDUE-MUTATORS` |
| `scripts/route.py` | `619` | `save_limen_file` | `TAB-ROUTE-RESIDUE-MUTATORS` |
| `scripts/routine-freshness-audit.py` | `294` | `save_limen_file` | `TAB-HUMAN-ATOM-STATUS-WRITERS` |
| `scripts/routine-freshness-audit.py` | `355` | `save_limen_file` | `TAB-HUMAN-ATOM-STATUS-WRITERS` |
| `scripts/self-heal.py` | `408` | `save_limen_file` | `TAB-CREATION-FALLBACKS` |
| `scripts/usage-telemetry.py` | `208` | `path.write_text` | `TAB-MAINTENANCE-BOARD-FALLBACKS` |

## Contract

- This receipt does not bless direct writers as done; it prevents hidden writer drift.
- Step 2.2 is owner-recorded when every remaining direct writer maps to a bounded packet and no row is unclassified.
- The burn-down remains complete only when this audit exits zero or the remaining writers are explicitly allowlisted as Tabularius/io ownership.
