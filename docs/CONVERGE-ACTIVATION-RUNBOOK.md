# converge() — Activation Runbook

`converge()` is **built, staged, and dormant**. Everything below is the *one motion* to make
it live — to be run only when Anthony opens the release gate (see the release-gate HOLD).
Until then: nothing here is executed.

## What is already done (behind the gate)
- `cli/src/limen/converge.py` — the organ: `converge(idea, shots) -> {better_version, cited_losers, next_shots}`.
- `cli/tests/test_converge.py` — 9 tests, green, hermetic (fake adapters).
- `scripts/metabolize.sh` — a step 6 `converge`, gated **OFF** by default (`LIMEN_CONVERGE` unset → skip).
- Verified end-to-end on real corpus faces in `--dry-run` (fallback adapters, no API, no promotion).

## The activation sequence (run in order, only on gate-open)

1. **Release the code** — `gh pr ready 35 && gh pr merge 35 --squash` (the draft PR on `converge/build-organ`). *This is the release; it's what the HOLD gates.*
2. **Install the live adapters' deps** (each is import-guarded until present):
   - `pip install anthropic` in limen's env, and set `ANTHROPIC_API_KEY` (the LLM-judge synthesis core).
   - `mesh`: `pip install -e ~/Workspace/organvm-i-theoria/mesh` in its own `.venv` (ranker + gap-finder). `OPENAI_API_KEY` only if using semantic dead-zones; structural needs nothing.
   - `cce`: `pip install -e ~/Workspace/conversation-corpus-engine` (safe-promotion machine).
3. **Smoke-test live, WITHOUT promotion first** — run the organ with the real `AnthropicSynthesizer` but `NoopPromoter` on one real cluster (e.g. a `knowledge-corpus/reduced/*.md` set) and inspect the `better_version`. Confirm the alchemy is real before any promotion side-effect.
4. **Smoke-test the promote→rollback path** on a throwaway CCE candidate: confirm `stage→review→promote` then `rollback` round-trips cleanly (reversible, nothing destroyed).
5. **Activate in the heartbeat** — set `LIMEN_CONVERGE=1` in the metabolize environment. The default `python -m limen.converge` invocation runs in safe mode (no promotion unless an explicit promote flag is added); promotion stays gated.
6. **Wire into continuous operation** — once steps 3–5 pass, enable the converge step in the live `metabolize.sh` cycle / auto-scaler so `diverge (route.py) → converge (converge.py) → one` runs on every cycle. Feed `next_shots` (dead-zones) back as the next divergence.

## Invariants that do not bend on activation
- Promotion is reversible (CCE `rollback`) — nothing is destroyed; losers are kept as cited provenance.
- The convergence is alchemical distillation, never janitorial dedup.
- Gate the irreversible: keep promotion behind an explicit flag even after `LIMEN_CONVERGE=1`.
- Derive, never pin: budgets/identities/counts regenerate from live sources, never hardcoded.

*Staged 2026-06-19. Nothing in this runbook has been executed; it is the prepared one-motion release.*
