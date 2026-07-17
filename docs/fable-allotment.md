# Fable 5 Allotment

## Primary control: Fable plans, provider Auto builds

**Fable is PLAN-ONLY.** Its role is planning + handoff: it does the deep analysis and returns one
complete continuation packet as its final stdout, then hands implementation to a provider-Auto
non-Fable builder. The launcher—not Fable's tool surface—materializes the packet; Fable itself has
no write-capable tool.
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
- the selected provider model is an opaque live-catalog identity bound by a fresh
  `limen.claude_model_selection.v1` owner receipt to the exact Fable execution profile; an explicit
  override with no current receipt, a removed/stale identity, or role/profile disagreement fails
  blocked before provider execution;
- Fable receives an explicit read-only tool surface; unknown, mutation-capable, fan-out, and MCP
  write tools are denied rather than inferred safe;
- only a canonical `docs/continuations/fable/<task>.md` regular file inside the worktree is a valid
  plan artifact, and its receipt binds the exact SHA-256 content digest; traversal, path aliases,
  symlinks, missing files, and digest drift are rejected; and
- the launcher captures at most 1 MiB of final stdout, writes through no-symlink directory handles,
  verifies both the exact committed blob and unchanged worktree bytes, and publishes a receipt only
  after the live preserving PR resolves to that exact commit as its current head; PR-only,
  commit-only, wrong-repository, stale-head, empty-output, unsafe-path, and drifted custody all fail
  closed; and
- implementation returns to provider Auto under requirements that explicitly set
  `fable_allowed=false`. Receipts never pin a provider model or tier.

Fable is an opaque planning role, not a model-name pattern or provider catalog promise. Live
provider capability and model selection remain execution-time state; catalog role metadata and the
accepted execution profile, never identifier text, decide whether the Fable restrictions apply. It
is for bounded owner-accepted planning work, not an async worker pool or a coverage grinder.

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
launch gate must call `fable_contract.authorization_status()` with the exact role-bound execution
profile and proceed only on `reason == "ok"`. A fresh
`LIMEN_CLAUDE_MODEL_SELECTION_RECEIPT=<receipt>` must separately bind the opaque selected model to
that profile and current live catalog. There is no named-model fallback in this contract; a closed
Fable role fails blocked, while ordinary non-Fable work remains on provider Auto. Receipts issued
before the plan-only, provider-neutral handoff, live selection, and exact PR-head fields existed
must be re-issued.

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
