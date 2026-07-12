# Overnight Watch

Use `scripts/overnight-watch.py` for overnight proof. Do not keep any
interactive agent turn attached just to poll heartbeat output.

Default mode is one-shot:

```bash
python3 scripts/overnight-watch.py
```

It writes:

- `logs/overnight-watch.jsonl` append-only receipts
- `logs/overnight-watch-state.json` repeated-tick state
- `logs/overnight-watch.md` latest human-readable status
- `logs/overnight-watch-alert.json` only when a `WATCH_ALERT` is active

Recommended supervisor cadence is a cheap one-shot invocation every five
minutes. The script exits non-zero only when it has concrete evidence of a
blocker, such as a missing heartbeat log, stale heartbeat log, repeated latest
tick with no active workers, or optional dispatch-env drift.

The repo includes a launchd job for that cadence:

```bash
cp container/launchd/com.limen.overnight-watch.plist \
  "$HOME/Library/LaunchAgents/com.limen.overnight-watch.plist"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.limen.overnight-watch.plist"
```

For the overnight fleet profile, run with explicit expectations:

```bash
LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_ASYNC=1 \
LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_LANES=auto \
python3 scripts/overnight-watch.py
```

`--watch` exists for a local terminal, but it is not the interactive-agent
pattern. Agents should inspect the receipt or respond to `WATCH_ALERT`; they
should not spend a large conversation context on routine five-minute polling.

## Eight-hour unattended trial

Start the fixed contract once; the normal five-minute one-shot producer will
finalize it automatically after eight hours:

```bash
python3 scripts/overnight-watch.py --start-trial
```

The active window is recorded in `logs/overnight-trial-window.json`. Finalization
writes `logs/overnight-trial.json`, a counts-only, content-addressed receipt. A
passing receipt requires:

- a prospective, single active marker whose evaluator remains unchanged for exactly eight hours;
- complete sample coverage with no gap over ten minutes;
- a newly appended typed `done` event or typed owner-blocked event in every 90-minute window;
- a fresh warm handoff at the end;
- at least one newly appended structured `in_progress` session event;
- a fresh, validated, exact `all/all` prompt-atom snapshot on every sample, with zero increase in
  `coverage.operator_occurrences`; and
- zero watch alerts.

The receipt contains only window/count summaries plus SHA-256 hashes of the
evaluator and normalized inputs. Re-finalizing the same window is byte-idempotent.
The checker reconstructs the receipt from the exact bounded watch log and current
append-only task dispatch history; a self-consistent but fabricated hash is rejected.

Trial start intentionally has no backfill arguments and refuses to replace an active
marker. Prompt authority is fail-closed: while issue
[`#957`](https://github.com/organvm/limen/issues/957) remains `partial:all`, or while its
source cursor cannot prove a fresh exact scan, `--start-trial` fails instead of
manufacturing a zero-operator receipt.

Verify it with:

```bash
python3 scripts/overnight-watch.py --check-trial
```
