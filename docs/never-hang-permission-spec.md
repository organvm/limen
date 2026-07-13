# Never-hang permission spec — the operator's standing requirements

> Synthesized 2026-07-09 by a 10-agent sweep of every session source on the host —
> 1,224 Claude transcript directories, codex/gemini CLI history, memory files, the
> charter, `his-hand-levers.json`, and issues #183/#289/#320/#762 — after the operator
> demanded the fix honor *every* time he has raised this, not just the latest eruption.
> **25 distinct raisings, 2026-06-12 → 2026-07-09.** Verbatim quote ledger (raw prompt
> text never lands in this public repo): `.limen-private/session-corpus/never-hang-permission-ledger.md`.
>
> Implementing artifacts: `scripts/hooks/allow-trusted-cd-git.sh` (the enforcement),
> `scripts/tests/allow-trusted-cd-git.test.sh` (the decision matrix),
> `scripts/claude-permission-preflight.py` plus its hermetic tests (the launch gate),
> `scripts/dialogs-silenced.sh` classes 1/1b/1c/1d (the recurrence predicate).

## The requirements (R1–R13)

| # | Requirement | Anchors |
|---|-------------|---------|
| R1 | **Zero approval questions for non-destructive work is the default.** A prompt on safe work is a defect. | 2026-06-23, 2026-07-01 sessions; Auto with built-in safety defaults retained |
| R2 | **The request itself IS the authorization** — never re-gate what was asked for. | charter §Standing Autonomy; memory `asking-is-the-authorization` |
| R3 | **Solve root-to-leaf; a fixed prompt-class must never recur.** Idempotent verification, not incremental patching. | 2026-06-24 TCC directive; `dialogs-silenced.sh` |
| R4 | **Fix the whole prompt class at its owning layer, never re-approve one literal string.** Authorization remains operation/path bounded; “whole class” never means a broad deletion bypass. | charter §Standing Autonomy; #762: "Grant broad, root-to-leaf permission rules… so Claude doesn't stall on repeated prompts" |
| R5 | **Fleet/plan/auto agents must not be flooded by the compound-`cd` guard** (upstream #32985; no allow rule suppresses it — only a PreToolUse hook). | lever L-AGENT-BASH-PROMPT (#183); PR #202 |
| R6 | **CLI flags must not silently defeat configured defaults** — `--permission-mode auto` overrides `bypassPermissions`, so the fix must hold in auto mode too. | memory `permission-prompts-auto-mode-override` |
| R7 | **Permission state is consistent across all modes** (agents mode, chat, headless, daemon). | 2026-06-21, 2026-07-08 sessions |
| R8 | **Credentials/tokens/secrets are never a chat question** — organ-owned (Wall #320). | 2026-06-25 session; charter §Credentials |
| R9 | **Save/commit/push/deploy/merge/release run autonomously** — shipment steps are not gates. | 2026-06-22/25 sessions; memory `saving-pushing-never-needs-him` |
| R10 | **Never hang/stall a session on a prompt for exempt work** — the hang IS the failure, headless jobs freeze. | 2026-07-09 session; #762 |
| R11 | **Permission hooks/allowlists are version-controlled** — canonical sources in-repo, deployed copies drift-checked. | PR #202 lesson; `dialogs-silenced.sh` 1b |
| R12 | **Reroute blocked steps through compliant paths; never surface a reroutable gate as human work.** | charter §Compliant Gate Reroute |
| R13 | **Verify the real property across ALL invocation paths** before claiming solved (interactive, auto-mode, daemon, headless). Exact unattended command packets must pass the permission preflight before launch. | memory `macos-tcc-gatekeeper-dialogs-solved` multi-vector rule |

## Calibration — what never asks vs. what still gates

**Never asks (auto-approved):**

- Non-destructive, reversible work of any kind, including commit/push/deploy/merge
  (subject only to the website guardrail below).
- Deletion of **disposable session artifacts**: worktrees under `.claude/worktrees`,
  `~/.claude/jobs`, `/tmp`, `$TMPDIR`, and caller-declared generated build paths strictly
  *inside* a repo under `~/Workspace`/`~/Code`. Reap traffic (`rm -rf <worktree>`,
  `git worktree remove --force`, `git branch -D`) is the dominant prompt source and is
  pre-authorized by path, per #762's "pre-authorize specific destructive operations".
- Read-only diagnostics measured from real prompt fossils: `ps`, `route -n get`,
  `diskutil list|info`, `tmutil` read verbs, `gh repo view|list|clone`.

**Still gates (his deliberate exceptions — do not "fix" these):**

- Destruction of non-disposable things: any path outside the trusted classes, a repo
  root itself, `~`, `/`, the worktrees container as a whole, `main`/`master` branch
  deletion, `git reset --hard`/`git clean` in a **primary** checkout (a fleet reset
  once wiped the live checkout — disposable-roots-only).
- Force-push in any form, remote branch deletion (`push --delete` / `:refspec` /
  `+refspec`) — the charter reroutes these (new branch + superseding PR), it does not
  approve them.
- `sudo`, `dd`, `mkfs`, `shred`, `chmod/chown -R`, `curl|sh`, `xargs rm`,
  `find -delete` — hard class, never hook-approved.
- Website-sensitive merges require green CI first (charter §Merge & Branch Protocol).
- Mass cross-org merges, anything that **sends**, wipes remotes at scale, or spends.

**Irreducible human atoms (accepted as legitimate guardrails, not bugs):**

- Widening the agent's own live permission files (`~/.claude/settings.json`,
  `~/.claude/hooks/*`) is classifier-blocked — the agent lands the canonical repo
  source + hands ONE `install -m 755` paste; `dialogs-silenced.sh` 1b prints it on drift.
- `sudo`-gated OS changes (Application Firewall — lever L-FIREWALL-PROMPT/#289).

## Design consequences (preflight + Auto policy + hook)

1. Permission rules resolve `deny` → `ask` → `allow`; specificity does not change that
   order. A matching `ask` rule forces a prompt in Auto and bypass modes, and a PreToolUse
   hook `allow` decision does **not** override permission rules. The former claim that the
   trusted-directory hook preempted `ask` was false and caused the July 13 HOSPES stall.
2. Exact Bash packets are checked *before* an unattended launch. The preflight merges the
   locally visible permission scopes, splits compound commands the same way permission
   rules do, and fails when `ask` or `deny` will intercept a clause. Deletion passes only
   for literal targets under caller-declared `--generated-path` roots.
3. Generated cleanup runs in Auto with `$defaults` retained. Broad `Bash(rm:*)` and
   `Bash(rmdir:*)` ask rules cannot coexist with prompt-free cleanup because `ask` has no
   narrower allow exception. Bypass cleanup is rejected: removing those asks in bypass
   would also remove the path-sensitive personal-data backstop.
4. Force-push, remote-ref deletion, shred, credential/account changes, spending, public
   sends, and destruction outside declared disposable roots remain gated. The path-aware
   hook is still the fast path for the compound-`cd` and disposable-root classes, but it is
   not a substitute for permission-policy preflight.
5. Every hook allow class retains its regression case, the preflight has a settings/packet
   decision matrix, and `dialogs-silenced.sh` composes both checks. A fixed prompt class
   cannot silently recur (R3).

## Evolution (no true conflicts)

The trajectory across the 25 raisings: *fix this prompt* (June 12–23) → *fix this
class, root-to-leaf* (June 24–25) → *never be asked at all; only destruction gates,
pre-authorized up front* (July 1–9). The destructive-only boundary is stable across
the whole window; what shrank is tolerance for how it is enforced. The operator's own
`--dangerously-skip-permissions` stopgap (July 3, both `claude` and gemini CLIs) is
broader than his stated calibration. The July 13 correction resolves this toward Auto
plus an exact packet preflight, which keeps prompt-free generated cleanup without
silently widening personal-data deletion.

## Scope beyond Claude Bash prompts (same demand, other surfaces — already homed)

macOS TCC/Gatekeeper (memory: solved; move/unregister, never click Allow) · macOS
Application Firewall (#289, sudo-gated lever) · 1Password/Touch-ID (`op` opt-in +
service-account lane, `dialogs-silenced.sh` class 2) · claude.ai connector re-auth
(L-IANVA-CLOUD) · Chrome bridge auto-recovery (relaunch + retry, never a parked
blocker) · cross-CLI parity (codex/gemini run with their own skip flags by his hand).
