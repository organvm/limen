#!/usr/bin/env bash
# Hermetic regression for scripts/start-worktree-session.sh. It proves task agents are not
# launched from a shared live checkout and that separate task sessions get separate worktrees.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/scripts/start-worktree-session.sh"

FIX="$(mktemp -d)"
trap 'git -C "$LIVE" worktree prune >/dev/null 2>&1 || true; rm -rf "$FIX"' EXIT

LIVE_RAW="$FIX/live"
git init -q -b main "$LIVE_RAW"
LIVE="$(cd "$LIVE_RAW" && pwd -P)"
git -C "$LIVE" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init

out="$(
  cd "$LIVE"
  bash "$SCRIPT" --shell "$LIVE" task-one 2>&1
)" && {
  printf 'expected shared-checkout launch refusal, got success:\n%s\n' "$out" >&2
  exit 1
}
printf '%s' "$out" | grep -q 'refusing to launch a task agent from shared checkout' || {
  printf 'missing refusal text:\n%s\n' "$out" >&2
  exit 1
}

out="$(
  cd "$LIVE"
  bash "$SCRIPT" --codex "$LIVE" task-codex-blocked 2>&1
)" && {
  printf 'expected shared-checkout codex refusal, got success:\n%s\n' "$out" >&2
  exit 1
}
printf '%s' "$out" | grep -q 'refusing to launch a task agent from shared checkout' || {
  printf 'missing codex refusal text:\n%s\n' "$out" >&2
  exit 1
}

FAKE_BIN="$FIX/bin"
mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/fake-shell" <<'SH'
#!/usr/bin/env bash
pwd > "$SESSION_PWD_OUT"
exit 0
SH
chmod +x "$FAKE_BIN/fake-shell"
cat > "$FAKE_BIN/codex" <<'SH'
#!/usr/bin/env bash
pwd > "$SESSION_PWD_OUT"
exit 0
SH
chmod +x "$FAKE_BIN/codex"

SESSION_PWD_OUT="$FIX/session-one.pwd" SHELL="$FAKE_BIN/fake-shell" \
  bash "$SCRIPT" --control-plane --shell "$LIVE" task-one >/dev/null
SESSION_PWD_OUT="$FIX/session-two.pwd" SHELL="$FAKE_BIN/fake-shell" \
  bash "$SCRIPT" --control-plane --shell "$LIVE" task-two >/dev/null
SESSION_PWD_OUT="$FIX/session-codex.pwd" PATH="$FAKE_BIN:$PATH" \
  bash "$SCRIPT" --control-plane --codex "$LIVE" task-codex >/dev/null

wt_one="$(cat "$FIX/session-one.pwd")"
wt_two="$(cat "$FIX/session-two.pwd")"
wt_codex="$(cat "$FIX/session-codex.pwd")"
top_one="$(git -C "$wt_one" rev-parse --show-toplevel)"
top_two="$(git -C "$wt_two" rev-parse --show-toplevel)"
top_codex="$(git -C "$wt_codex" rev-parse --show-toplevel)"
live_top="$(git -C "$LIVE" rev-parse --show-toplevel)"

expected_one="$(cd "$LIVE/.worktrees/task-one" && pwd -P)"
expected_two="$(cd "$LIVE/.worktrees/task-two" && pwd -P)"
expected_codex="$(cd "$LIVE/.worktrees/task-codex" && pwd -P)"

[[ "$top_one" == "$expected_one" ]] || {
  printf 'task one launched in wrong checkout: %s\n' "$top_one" >&2
  exit 1
}
[[ "$top_two" == "$expected_two" ]] || {
  printf 'task two launched in wrong checkout: %s\n' "$top_two" >&2
  exit 1
}
[[ "$top_codex" == "$expected_codex" ]] || {
  printf 'codex launched in wrong checkout: %s\n' "$top_codex" >&2
  exit 1
}
[[ "$top_one" != "$top_two" && "$top_one" != "$top_codex" && "$top_two" != "$top_codex" ]] || {
  printf 'task sessions share a checkout: one=%s two=%s codex=%s\n' "$top_one" "$top_two" "$top_codex" >&2
  exit 1
}
[[ "$top_one" != "$live_top" && "$top_two" != "$live_top" && "$top_codex" != "$live_top" ]] || {
  printf 'task session launched in live checkout: live=%s one=%s two=%s codex=%s\n' \
    "$live_top" "$top_one" "$top_two" "$top_codex" >&2
  exit 1
}

branches="$(git -C "$LIVE" worktree list --porcelain | awk '/^branch / {print $2}' | sort)"
printf '%s\n' "$branches" | grep -qx 'refs/heads/work/task-one' || {
  printf 'missing task-one worktree branch:\n%s\n' "$branches" >&2
  exit 1
}
printf '%s\n' "$branches" | grep -qx 'refs/heads/work/task-two' || {
  printf 'missing task-two worktree branch:\n%s\n' "$branches" >&2
  exit 1
}
printf '%s\n' "$branches" | grep -qx 'refs/heads/work/task-codex' || {
  printf 'missing task-codex worktree branch:\n%s\n' "$branches" >&2
  exit 1
}

printf 'start-worktree-session.test: ok\n'
