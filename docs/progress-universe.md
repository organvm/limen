# Limen Progress Universe

`limen progress` is the terminal projection for the whole known work universe. It answers different
questions without collapsing their authority:

- **What is due?** Explicit obligations and deadlines.
- **What did the human ask for?** Prompt atoms and later corrections with lineage.
- **What does the system recommend?** Evidence-ranked proposals that remain recommendations until
  accepted or otherwise authorized.
- **Where are hands allocated?** Purpose workstreams such as financial, correspondence,
  contributions, prompt parity, and dynamically derived organ lanes.
- **When does the work belong?** Past recovery, present delivery, or future option-building.
- **What debt exists?** Every nonterminal task plus dark or stale coverage sources, remote PR/branch
  debt, worktree custody debt, failing checks, unresolved prompts, and exact human/external gates.

## Terminal use

```bash
# Portfolio summary plus the highest-priority 50 debt leaves
limen progress

# Zoom the macro and micro view by a different dimension
limen progress --view origin
limen progress --view horizon --scope past
limen progress --view workstream --scope financial

# Print every matching debt leaf or return the complete lossless dataset
limen progress --all
limen progress --json-output
limen progress --report-file logs/progress-universe.json
```

Macro bars show only `done` or `archived` tasks divided by the explicit group denominator. Micro bars
show canonical lifecycle stage; they are deliberately not percent-of-effort estimates. A blocked or
human-routed task remains visible until the board records its terminal custody. The source coverage
section makes stale and dark sensors visible, so a missing portfolio census can never masquerade as
zero portfolio debt.

## Required normalized leaf contract

New universe producers should supply the following without guessing from task titles:

| Field | Meaning |
|---|---|
| `origin` / `origin:*` | `obligation`, `human_prompt`, `agent_recommendation`, or `system_debt` |
| `horizon` / `horizon:*` | `past`, `present`, or `future` |
| `workstream` | Purpose lane, distinct from the execution provider |
| `due_at` / `due:*` | Exact deadline when one exists |
| `repo` and `urls` | Durable owner surface and evidence |
| `predicate` | Executable definition of done |
| `receipt_target` | Durable terminal custody target |

The view is intentionally coverage-aware. Until every producer supplies these fields and every estate
collector is fresh, the corresponding coverage bar remains below 100%.

## Work-loan underwriting

Agent, provider, token, elapsed-time, and host capacity are operating capital. A task asks to borrow
that capital. The `WORK LOANS` bar counts an active task as underwritten only when it has an explicit
origin, horizon, value case, owner repo, run cost, executable predicate, and durable receipt target.
Urgency, cost of delay, confidence, dependencies, reversibility, and resource pressure can then rank
otherwise eligible loans dynamically. Completion reconciles intended value against actual durable
credit and actual spend; requested value is never booked as achieved value.
