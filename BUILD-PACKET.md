# BUILD PACKET — Fable role separation + runtime cap + vendor verdict

**Planned by a Fable session; BUILT by a non-Fable (Opus) builder.** This packet is the handoff.
Do not re-derive the analysis below — it is ground truth from a completed exploration. Build it.

Full plan: `/Users/4jp/.claude/plans/this-reset-yesterday-and-concurrent-squid.md`.

## The reframe (primary deliverable)
The root fix is **architectural, not just a cap**: **Fable is PLAN-ONLY. It plans, emits build
packets into worktrees, and hands off to a cheaper tier that builds.** The spend cap below is a
BACKSTOP. Encode the role separation as the primary control.

---

## Deliverable 1 — Encode "Fable plans, cheaper tiers build" (primary)
- Edit `docs/fable-allotment.md`: add a top section stating Fable's role is planning + handoff;
  building on Fable is prohibited. The runtime cap (Deliverable 2) is the safety net.
- Add the same one-paragraph rule to the charter tiering doctrine reference in `AGENTS.md`
  (model-tiering section) — cross-link, do not duplicate. Keep `scripts/check-agent-docs.py` green.

## Deliverable 2 — Fable runtime cap (backstop)
Ground truth:
- `scripts/fable-allotment.py` already has `PLAN`, `DELIBERATE_CAP=40`, `HARD_CAP=50`, `_week_key`,
  `_load_receipts`, `_spent`, `cmd_audit`. **Reuse them.**
- **Ledger wrinkle:** `organs/financial/token-usage.json` is a ROLLING 30-day window — it CANNOT
  give the weekly Fable %. The weekly figure must come from Claude Code's own per-session usage.
  `scripts/claude-usage.py` already reads `~/.claude/projects/**/*.jsonl` + `anthropic-ratelimit-*`
  headers — **reuse/extend it** to sum current-ISO-week `claude-fable-5` tokens and, if the
  `anthropic-ratelimit-unified-*` weekly limit/remaining headers are present, read the % directly.

Steps:
1. `fable-allotment.py balance` subcommand → writes `logs/fable-allotment.json`:
   `{week, spent_tokens, spent_pct, deliberate_cap: 40, hard_cap: 50, over_cap: bool}`. Idempotent;
   timestamps from data (no wall-clock in output body). Prefer ratelimit-header % if available,
   else token-sum vs a derived weekly budget.
2. Gate in `cli/src/limen/model_selection.py` (`_claude_fable_acceptance_present` caller +
   `dispatch._claude_tier_for` ~lines 3010–3055): a valid receipt is necessary-not-sufficient.
   Read `logs/fable-allotment.json`:
   - `spent_pct < 40` → Fable allowed (unchanged).
   - `40 ≤ spent_pct < 50` → only `reserve`-category current-week receipts pass; else
     `_fable_fallback_tier()` (Opus).
   - `spent_pct ≥ 50` → hard downgrade to Opus, no exception.
   Override = the EXISTING acceptance receipt only. No new `LIMEN_FABLE_OVER_CAP_OK` flag.
3. `scripts/fable-session-guard.py` — SessionStart hook: if the interactive session model is
   `claude-fable-5`, print the weekly balance loudly; if `over_cap` or no live receipt, hard-warn
   + print the exact `/model` switch. This closes the interactive bypass the fleet shim never
   covered (see `model_selection.py` shim notes: interactive/non-print spawns are never re-tiered).
4. Stage (do NOT self-arm) settings.json: (a) the SessionStart hook block for #3; (b) `model`
   pinned to a non-Fable default (opus). Write the exact validated block to
   `docs/keys/fable-guard-settings-snippet.json` and surface it as the ONE human copy-paste.
5. Wire `scripts/claude-workflow-guard.py`'s Fable check into `scripts/metabolize.sh` so an
   unaccepted/over-cap Fable run surfaces every beat (pattern: like `creds-hydrate --verify`).

## Deliverable 3 — portable vendor verdict (kills "cancel codex")
- `scripts/vendor-cancel-advisor.py`: for each vendor in `cli/src/limen/census.py`, emit
  KEEP / CANCEL-CANDIDATE from UTILIZATION ONLY (headroom % + rate-limit health across resets in
  `logs/usage.json`), never sticker cost. Hits caps → KEEP (relief valve). Idle across resets →
  CANCEL-CANDIDATE. It reads `logs/fable-allotment.json` and names **Fable-at-cap as the real
  overspend**, so "save money" routes to *cap/plan-gate Fable*, and **codex = KEEP**. Exit non-zero
  if any "cancel a capped pool" recommendation is implied. Output portable JSON + one-line summary.
- Point `organs/financial/ai-vendor-spend.md` at the advisor as source of truth (prose → predicate).

## Verification — `scripts/verify-fable-gate.sh` (new, committed, idempotent)
1. Seed mock over-cap `logs/fable-allotment.json`; assert `_claude_tier_for` on a Fable-class task
   returns `opus` even with a valid receipt; assert a `reserve` receipt passes at 40–50% but not ≥50%.
2. `fable-session-guard.py` exits non-zero/warns on Fable+over_cap; exits 0 on non-Fable model.
3. `vendor-cancel-advisor.py` on a fixture: codex=KEEP, idle mock=CANCEL-CANDIDATE, Fable named.
4. `python -m pytest cli/tests -q -k "model_selection or tier or dispatch"` green.
5. Re-run whole script → no state changes (fixed point).

## Gates before PR (run all locally, green end-to-end)
`python -m ruff check cli/src cli/tests web/api mcp ianva` · `python -m ruff format --check ...` ·
`python -m pytest web/api/tests cli/tests -q` · `scripts/verify-fable-gate.sh` ·
`scripts/verify-whole.sh`. Then push branch `feat/fable-runtime-cap`, open PR, self-merge on
`scripts/merge-policy.sh` CLEARED. Ship Deliverable 3 as its own branch `feat/vendor-cancel-advisor`
if it grows large; otherwise one PR is fine. settings.json snippet stays a human paste — do NOT arm it.

## Guardrails
- This is NOT a website-sensitive deploy path (no `web/app/**`, `web/api/**` changes) → merge on CLEAN.
- Do not edit daemon-contended runtime files or `tasks.yaml`. Stage explicitly with `git add <path>`,
  never `git add -A`.
