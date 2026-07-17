# Fable 5 Allotment

## Primary control: Fable plans, provider Auto builds

**Fable is PLAN-ONLY.** Its role is planning + handoff: it does the deep analysis, emits a build
packet into an isolated worktree, and hands off to a provider-Auto non-Fable builder.
**Building on Fable is prohibited** — no coding grind, no coverage sweeps, no PR babysitting, no
detached async dispatch on the Fable rung. A Fable session's deliverable is a *plan a non-Fable
builder can execute*, not the implementation itself.

This role separation is the root control. The weekly runtime cap below is the **backstop / safety
net**, not the primary mechanism: it exists so that even a mis-scoped Fable run cannot silently
drain the week's allotment. `scripts/fable-allotment.py balance` publishes
`limen.fable_balance.v1`; `cli/src/limen/fable_contract.py` rejects stale, dark, malformed, or
unreconciled observations. A transcript-token sum is ready only with an owner-supplied denominator;
the code never invents a weekly allotment or scans a provider runtime. Inputs are explicit exported
owner artifacts through `LIMEN_FABLE_USAGE_METER_PATH` or
`LIMEN_FABLE_USAGE_TRANSCRIPTS_DIR`.

The contract is mechanical for fleet launches:

- the task and execution profile bind `execution_role=fable-planner`, `planning_only=true`,
  `build_allowed=false`, and `fanout_allowed=false`;
- the acceptance receipt binds `mode=plan-only`, `deliverable=continuation-capsule`, the
  5,400-second durable-receipt deadline, and a provider-neutral builder handoff;
- the balance receipt must be current-week, fresh, source-ready, finite, and internally coherent;
  absent, stale, malformed, or dark state closes the Fable planner role;
- Fable receives a read/plan/capsule-only tool surface, never an implementation or fan-out surface;
- only `docs/continuations/fable/<task>.md` is a valid plan artifact; and
- implementation returns to provider Auto under requirements that explicitly set
  `fable_allowed=false`. Receipts never pin a provider model or tier.

Fable is an opaque planning role, not a provider catalog promise. Live provider capability and model
selection remain execution-time state. It is for the small set of jobs justified by long-horizon
reasoning, huge-context synthesis, ambiguous root-cause work, or final canonical decisions. It is
not an async worker pool or a coverage grinder.

## Weekly Budget

Hard ceiling: 50% of the weekly Fable allotment.

Planned spend: 40%.

Reserve: 10%, spendable only when a first-pass Fable run exposes one bounded repair that can be
verified immediately.

| Category | Cap | Use |
|---|---:|---|
| `substrate` | 15% | Claude async dispatch failures, auth/connectors, model tiering, and Fable integration. |
| `prompt-corpus` | 10% | Redacted/source-indexed compression of open prompt/session review batches into owner records, receipts, or discard decisions. |
| `governance` | 10% | Publication Policy, closeout doctrine, agent-neutral fleet rules, public/private boundaries, and contradiction removal. |
| `adversarial-review` | 5% | Skeptical review of recent budget gauge, clone-reap, closeout, board-healing, and Publication Policy changes. |
| `reserve` | 10% | One follow-up repair only, with `--reserve-unlock`, after first-pass evidence identifies it. |

## Acceptance Command

Every Fable run needs a written acceptance receipt before it starts:

```bash
python3 scripts/fable-allotment.py accept \
  --category governance \
  --percent 10 \
  --slug publication-policy-canon-synthesis \
  --why "validator-backed resolution of conflicting governance docs" \
  --source docs/fable-allotment.md \
  --redacted-packet .limen-private/session-corpus/packets/<packet>.json \
  --verification "python3 scripts/publication-policy.py --verify" \
  --verification "python3 scripts/claude-workflow-guard.py audit-transcript <session.jsonl>" \
  --verification "bash scripts/verify-whole.sh"
```

The command prints:

```bash
export LIMEN_FABLE_ACCEPTANCE=<receipt>
```

Run the Fable planner only after exporting that variable into the same process environment. The
launch gate must call `fable_contract.authorization_status()` and proceed only on `reason == "ok"`.
There is no named-model fallback in this contract; a closed Fable role returns to provider Auto.
Receipts issued before the plan-only and provider-neutral handoff fields existed must be re-issued.

Audit current receipts:

```bash
python3 scripts/fable-allotment.py audit
```

Inspect the plan data:

```bash
python3 scripts/fable-allotment.py plan
```

## Operating Rules

- Prefer one large, bounded Fable session over many exploratory chats.
- Use only redacted or source-indexed packets for private corpus work; do not feed raw secrets,
  credentials, private personal data, or unnecessary sensitive transcripts.
- Do not spend Fable on routine generated test coverage, broad PR sweeps, copy editing, summaries,
  status reports, or detached async dispatch while Claude/Fable auth is not proven.
- Fable never fans out. Its build packet hands implementation back to provider Auto with Fable
  explicitly excluded.
- Treat Fable refusals/fallbacks as normal integration behavior. A refused request is not a failed
  run by itself; record the fallback path and verification result.
- Ninety minutes of Fable motion without a durable packet receipt is a contract violation. A fleet
  launcher may stop only the process group it created and must preserve a bounded residual packet;
  it never enumerates, signals, pauses, resumes, closes, or retunes a co-equal peer session.
- The staged interactive hook is read-only and report-only. It validates only the invocation whose
  hook payload it receives and never emits a model-switch or peer-control action.

## Verification Gates

For substrate/Fable-integration changes, run:

```bash
python3 scripts/claude-workflow-guard.py audit-transcript <session-or-jsonl>
python3 scripts/verify-budget-gauge.py
python3 scripts/validate-task-board.py --tasks tasks.yaml
bash scripts/verify-scoped.sh
```

For governance output, add the owner predicate, for example:

```bash
python3 scripts/publication-policy.py --verify
python3 scripts/check-agent-docs.py
```

## Sources

- Anthropic Platform docs, "Introducing Claude Fable 5 and Claude Mythos 5": capability,
  context, safety-classifier behavior, fallback, billing, availability, and retention notes.
  <https://platform.claude.com/docs/en/about-claude/models/introducing-claude-fable-5-and-claude-mythos-5>
- Anthropic Claude Fable page: positioning for hard knowledge work and coding problems.
  <https://www.anthropic.com/claude/fable>
