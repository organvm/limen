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

The active window is recorded in `logs/overnight-trial-window.json`. It seals the
existing byte prefixes of the ordinary watch log and the dedicated
`logs/overnight-trial-observations.jsonl` chain, plus every task-event ID already
present. An exclusive content-addressed anchor records the marker's actual file
creation time, and monotonic-clock custody must also span the full eight hours;
changing the wall clock cannot backfill the run. Finalization writes
`logs/overnight-trial.json`, a counts-only,
content-addressed receipt. A passing receipt requires:

- a prospective, single active marker whose evaluator remains unchanged for exactly eight hours;
- complete prospective sample coverage with no gap over ten minutes, with each sample bound to
  exactly one newly appended ordinary watch row and the previous observation hash;
- a newly first-observed typed `done` or owner-blocked event, whose predicate passes and whose
  durable receipt target resolves, whose dispatch timestamp is inside the already-observed trial
  interval (never pre-window or future-dated), with no rolling activity gap over 90 minutes
  including both trial boundaries;
- a fresh warm handoff at the end;
- at least one newly observed `in_progress` event whose provider-native session is independently
  present in a supported source (currently Jules remote sessions or a GitHub Actions run);
- a fresh, validated, exact `all/all` prompt-atom snapshot on every sample, with zero increase in
  operator occurrence IDs from the preserved append-only prompt journal; and
- zero watch alerts.

The receipt contains only window/count summaries plus SHA-256 hashes of the
evaluator and normalized inputs. Re-finalizing the same window is byte-idempotent.
The checker reconstructs the receipt from the prospective observation hash chain,
verifies every preserved watch and prompt-journal prefix, rejects task-event
removal or rewriting, and confirms that credited proof IDs first appeared after
the sealed baseline. Pre-seeded future timestamps, self-consistent sample lies,
source truncation, and rewritten source prefixes do not count.

Predicate proof never invokes a shell. It executes only classified read-only
GitHub/Git/test commands or tracked repository check scripts as direct argument
vectors; shell pipes, backgrounding, control operators, redirection, and mutating
GitHub operations are rejected before execution.

Trial start and finalization intentionally have no backfill arguments; finalization
also refuses to run before the marker's real end time. Trial start refuses to replace an active
marker. Prompt authority is fail-closed: while issue
[`#957`](https://github.com/organvm/limen/issues/957) remains `partial:all`, or while its
source cursor cannot prove a fresh exact scan, `--start-trial` fails instead of
manufacturing a zero-operator receipt.

The prompt scan may be at most the narrow clock-skew tolerance ahead of the
sample; the ten-minute sample-gap allowance is not a prompt-freshness allowance.
At finalization and every later receipt check, the terminal handoff, prompt cursor,
and private prompt snapshot must still byte-match their recorded live custody.
Repeating `--finalize-trial` against that unchanged terminal state returns the same
receipt with `changed:false`, exits successfully, and writes no bytes.

Verify it with:

```bash
python3 scripts/overnight-watch.py --check-trial
```
