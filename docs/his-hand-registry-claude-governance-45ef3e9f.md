# His-Hand Registry — Claude operating charter (session 45ef3e9f, 2026-06-24)

Everything from the "codify Claude operating insights into durable governance" build that is
**yours to pull or decide** — hung here (a committed, non-contended owned record) instead of left
hanging on you in chat or parked in an agent's head. Both items are gated by harness boundaries an
AI cannot cross (settings self-edit is hard-denied; merge/push is release-gated); neither is a nag,
neither sends or deletes, both are reversible. The work itself is committed + lint-green at `463e28d`.

## ITEM 1 — Activate the lint hook (settings.json paste)
- **Owner:** Anthony (human). AI self-edit of `settings.json` is **hard-denied** by the classifier,
  so this is the single irreducible paste.
- **Cheapest path (~30s):** copy `/Users/4jp/.claude/jobs/45ef3e9f/tmp/proposed-claude-settings.json`
  into `.claude/settings.json`. It adds a `PostToolUse` `Write|Edit` hook →
  `"$CLAUDE_PROJECT_DIR"/scripts/hooks/lint-edited-file.sh`, plus the `Bash(...)` allow rules.
- **Unblocks:** the advisory `ruff`-on-edit hook shipped in `463e28d` (runs ruff on each edited
  `*.py`, always exits 0 — never blocks a lane). Inert until the paste lands.
- **Reversible:** delete the `hooks` block to undo.

## ITEM 2 — Release the charter (open the gate to push + merge)
- **Owner:** Anthony (release gate-hold).
- **State:** branch `worktree-mighty-enchanting-pinwheel` @ `463e28d` is committed and lint-green —
  `CLAUDE.md` (operating charter), `.claude/skills/closeout/SKILL.md`, `scripts/hooks/lint-edited-file.sh`.
- **Cheapest path:** say "open the gate" → push branch → merge to `main`.
- **Unblocks:** the charter + closeout skill + lint-hook script reaching `main` (they only land on
  merge). On merge, this registry doc lands too, and ITEM 2 self-resolves; ITEM 1 stays visible here.
- **Reversible:** nothing is live until merged.

## Canonical-queue note (optional, your grant)
The system's permanent home for human-gated items is the live `needs_human` queue
(`tasks.yaml` → surfaced by `docs/NEEDS-HUMAN-DIGEST.md`). Writing it from a worktree was
classifier-blocked as shared-fleet-state mutation. If you want these two in the live digest, grant a
`Bash` rule for the locked atomic writer and they fold in as `LIMEN-101` / `LIMEN-102`; otherwise this
committed doc is their durable home and they converge to `main` on merge (ITEM 2).

## Verification
- `python3 -m ruff check cli/src cli/tests web/api mcp` → clean.
- Hook is `chmod +x`, `bash -n` clean, exits 0 on any non-`*.py` payload (advisory, never blocks).
- `done.sh` predicate (`/Users/4jp/.claude/jobs/45ef3e9f/tmp/done.sh`) exits 0.
