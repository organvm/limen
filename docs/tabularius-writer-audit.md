# TABVLARIVS Writer Audit

<!-- tabularius-writer-audit:zero-unauthorized -->

Unauthorized lifecycle writers: `72`

## Authorized Projection Writers

| Path | Role |
|---|---|
| `cli/src/limen/io.py` | noncanonical local cache/export serializer; no lifecycle authority |
| `web/worker/src/conduct/projection.js` | sole lifecycle writer; authenticated remote GitHub SHA-CAS |

## Unauthorized Findings

| Path | Line | Kind | Call | Function |
|---|---:|---|---|---|
| `AGENTS.md` | `36` | `direct-board-git-guidance` | `(?:git\s+(?:add|commit|push)[^\n]{0,100}tasks\.ya?ml|(?:commit|push|stage)\s+`?tasks\.ya?ml`?)` | `<instructions>` |
| `AGENTS.md` | `595` | `direct-board-git-guidance` | `(?:git\s+(?:add|commit|push)[^\n]{0,100}tasks\.ya?ml|(?:commit|push|stage)\s+`?tasks\.ya?ml`?)` | `<instructions>` |
| `AGENTS.md` | `629` | `direct-board-write-guidance` | `(?:edit|write|mutate|update|rewrite|read/write)\s+`?tasks\.ya?ml`?\s+directly` | `<instructions>` |
| `cli/src/limen/cli.py` | `87` | `direct-yaml-writer` | `tasks_file.write_text` | `init` |
| `cli/src/limen/cli.py` | `375` | `direct-yaml-writer` | `save_limen_file` | `channels` |
| `cli/src/limen/dispatch.py` | `4773` | `direct-yaml-writer` | `save_limen_file` | `_commit_dispatch_results` |
| `cli/src/limen/dispatch.py` | `5534` | `direct-yaml-writer` | `save_limen_file` | `dispatch_parallel` |
| `cli/src/limen/dispatch.py` | `5538` | `direct-yaml-writer` | `save_limen_file` | `dispatch_parallel` |
| `cli/src/limen/dispatch.py` | `5615` | `direct-yaml-writer` | `save_limen_file` | `dispatch_parallel` |
| `cli/src/limen/dispatch.py` | `5835` | `direct-yaml-writer` | `save_limen_file` | `release_stale_tasks` |
| `cli/src/limen/harvest.py` | `630` | `direct-yaml-writer` | `save_limen_file` | `harvest_results` |
| `cli/src/limen/jules_landing_transaction.py` | `331` | `direct-yaml-writer` | `save_limen_file` | `prepare_landing_intent` |
| `cli/src/limen/jules_landing_transaction.py` | `402` | `direct-yaml-writer` | `save_limen_file` | `commit_landing_receipt` |
| `cli/src/limen/jules_landing_transaction.py` | `437` | `direct-yaml-writer` | `save_limen_file` | `commit_terminal_landing_outcome` |
| `cli/src/limen/jules_landing_transaction.py` | `491` | `direct-yaml-writer` | `save_limen_file` | `commit_landing_failure` |
| `cli/src/limen/tabularius.py` | `1416` | `direct-yaml-writer` | `save_limen_file` | `drain_once` |
| `scripts/cells.sh` | `142` | `direct-shell-board-writer` | `[ -f "$cell_board" ] || cp "$p/tasks.yaml" "$cell_board" 2>/dev/null || write_empty_board "$cell_board"` | `<shell>` |
| `scripts/check-main-green.py` | `557` | `direct-yaml-writer` | `save_limen_file` | `_emit_heal_task` |
| `scripts/check-main-green.py` | `569` | `direct-yaml-writer` | `save_limen_file` | `_emit_heal_task` |
| `scripts/check-main-green.py` | `590` | `direct-yaml-writer` | `save_limen_file` | `_emit_heal_task` |
| `scripts/claim-task.py` | `163` | `direct-yaml-writer` | `args.tasks.open` | `main` |
| `scripts/discover-value.py` | `300` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/dispatch-async.py` | `249` | `direct-yaml-writer` | `save_limen_file` | `_rollback_unlaunched_reservation` |
| `scripts/dispatch-async.py` | `666` | `direct-yaml-writer` | `save_limen_file` | `harvest` |
| `scripts/dispatch-async.py` | `885` | `direct-yaml-writer` | `save_limen_file` | `reap_stale` |
| `scripts/dispatch-async.py` | `1425` | `direct-yaml-writer` | `save_limen_file` | `recover_exact_task` |
| `scripts/dispatch-async.py` | `1691` | `direct-yaml-writer` | `save_limen_file` | `reserve_and_launch` |
| `scripts/dispatch-continuity-check.py` | `344` | `direct-yaml-writer` | `save_limen_file` | `_upsert_starved_atom` |
| `scripts/done-insight-cadence.sh` | `16` | `direct-shell-board-writer` | `printf 'version: "1.0"\ntasks: []\n' > "$LIMEN_TASKS"` | `<shell>` |
| `scripts/done-session-orient.sh` | `55` | `direct-shell-board-writer` | `cp "tasks.yaml" "$tasks_snapshot"` | `<shell>` |
| `scripts/generate-backlog.py` | `430` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/generate-experience-backlog.py` | `242` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/generate-organ-backlog.py` | `295` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/generate-revenue-backlog.py` | `318` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/generate-seo-backlog.py` | `244` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/heal-board.py` | `263` | `direct-yaml-writer` | `save_limen_file` | `repair_lifecycle` |
| `scripts/heal-board.py` | `331` | `direct-yaml-writer` | `atomic_write_text` | `main` |
| `scripts/heal-dispatch.py` | `312` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/ingest-backlog.py` | `183` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/mine-backlog.py` | `214` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/probe-local-runtime.sh` | `59` | `direct-shell-board-writer` | `cat > "$TASKS_PATH" <<'YAML'` | `<shell>` |
| `scripts/quicken.py` | `501` | `direct-yaml-writer` | `save_limen_file` | `_hang_asks` |
| `scripts/rebalance.py` | `117` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/reclassify-needs-human.py` | `234` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/recover.py` | `206` | `direct-yaml-writer` | `save_limen_file` | `_recover` |
| `scripts/rewrite-owners.py` | `107` | `direct-yaml-writer` | `save_limen_file` | `apply_tasks` |
| `scripts/route.py` | `727` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/routine-freshness-audit.py` | `300` | `direct-yaml-writer` | `save_limen_file` | `hang_down_atoms` |
| `scripts/routine-freshness-audit.py` | `363` | `direct-yaml-writer` | `save_limen_file` | `retire_recovered_atoms` |
| `scripts/self-heal.py` | `471` | `direct-yaml-writer` | `save_limen_file` | `main` |
| `scripts/self-improve.py` | `435` | `direct-yaml-writer` | `save_limen_file` | `apply_proposal` |
| `scripts/sync-release.sh` | `164` | `direct-shell-board-writer` | `[ -f tasks.yaml ] && cp -f tasks.yaml "$TMP" 2>/dev/null || true` | `<shell>` |
| `scripts/sync-release.sh` | `184` | `direct-shell-board-writer` | `git checkout --quiet HEAD -- tasks.yaml 2>/dev/null || true       # clean the queue for the switch` | `<shell>` |
| `scripts/sync-release.sh` | `187` | `direct-shell-board-writer` | `git checkout --quiet HEAD -- tasks.yaml 2>/dev/null || true     # a beat re-wrote it mid-valve — once more` | `<shell>` |
| `scripts/sync-release.sh` | `190` | `direct-shell-board-writer` | `[ -f "$TMP" ] && cp -f "$TMP" tasks.yaml 2>/dev/null || true` | `<shell>` |
| `scripts/sync-release.sh` | `239` | `direct-shell-board-writer` | `[ -f tasks.yaml ] && cp -f tasks.yaml "$TMP" 2>/dev/null || true` | `<shell>` |
| `scripts/sync-release.sh` | `243` | `direct-shell-board-writer` | `[ -f "$TMP" ] && cp -f "$TMP" tasks.yaml 2>/dev/null || true` | `<shell>` |
| `scripts/sync-release.sh` | `259` | `direct-shell-board-writer` | `[ -f tasks.yaml ] && cp -f tasks.yaml "$TMP" 2>/dev/null || true` | `<shell>` |
| `scripts/sync-release.sh` | `293` | `direct-shell-board-writer` | `[ -f "$TMP" ] && cp -f "$TMP" tasks.yaml 2>/dev/null || true   # live queue wins over the snapshot` | `<shell>` |
| `web/api/main.py` | `492` | `direct-board-writer` | `save_github_board` | `save_board` |
| `web/api/main.py` | `1256` | `direct-board-writer` | `save_board` | `create_task` |
| `web/api/main.py` | `1283` | `direct-board-writer` | `save_board` | `update_task` |
| `web/api/main.py` | `1325` | `direct-board-writer` | `save_board` | `assign_task` |
| `web/api/main.py` | `1345` | `direct-board-writer` | `save_board` | `archive_task` |
| `web/api/main.py` | `1363` | `direct-board-writer` | `save_board` | `verify_task` |
| `web/api/main.py` | `1435` | `direct-board-writer` | `save_board` | `dispatch` |
| `web/api/main.py` | `1478` | `direct-board-writer` | `save_board` | `release_stale` |
| `web/worker/src/index.js` | `665` | `direct-board-writer` | `function saveBoard` | `saveBoard` |
| `web/worker/src/index.js` | `765` | `direct-board-writer` | `saveBoard` | `<javascript>` |
| `web/worker/src/index.js` | `825` | `direct-board-writer` | `saveBoard` | `<javascript>` |
| `web/worker/src/index.js` | `887` | `direct-board-writer` | `saveBoard` | `<javascript>` |
| `web/worker/src/index.js` | `899` | `direct-board-writer` | `saveBoard` | `<javascript>` |

## Predicate

```bash
python3 scripts/task-writer-audit.py --enforce-zero
```

The predicate is a zero gate, not a baseline ratchet. It scans production Python, shell, Cloudflare Worker JavaScript, and canonical agent instructions. TABVLARIVS itself is scanned and has no local projection exemption. Derived inspection/exports may use the noncanonical serializer or an exact-line sandbox marker, but lifecycle mutation must submit immutable tickets or conduct packets and wait for the remote keeper receipt.
