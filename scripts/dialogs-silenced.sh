#!/usr/bin/env bash
# dialogs-silenced.sh — the executable predicate for "no more permission/auth/fingerprint dialogs".
#
# Anthony's standing demand: never be asked for a permission, a fingerprint, or an OS dialog
# again — across Claude, the fleet, and the whole machine. The recurring dialogs are not random;
# they come from FOUR classes. Three are security boundaries that (by design) only a human with
# privilege can lower — a background agent physically cannot turn off the OS firewall, mint a
# 1Password service account, or widen its own permission gate; that impossibility IS the guardrail.
# The fourth (Gatekeeper on a duplicate quarantined install) is agent-curable and checked here so it
# can never silently reseed. This script names each class, reports whether it is silenced, and prints
# the EXACT one-time cure for any that is not. Each cure is one action, then silent forever.
#
# Idempotent, read-only, no sudo. Run anytime:  bash scripts/dialogs-silenced.sh
# Exit 0  ⟺  every recurring dialog class is silenced (the done-predicate).
set -uo pipefail

gaps=0
green(){ printf '  \033[32m✓\033[0m %s\n' "$1"; }
red(){   printf '  \033[31m✗\033[0m %s\n' "$1"; gaps=$((gaps+1)); }
cure(){  printf '      ↳ %s\n' "$1"; }
note(){  printf '      · %s\n' "$1"; }

echo "== dialogs-silenced — the four recurring permission classes =="
echo

# ── 1. Claude Code in-app permission prompts — the highest-volume "asking permission". ──
SETTINGS="$HOME/.claude/settings.json"
mode="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(""); raise SystemExit
print((d.get("permissions") or {}).get("defaultMode", ""))
PY
)"
if [ "$mode" = "auto" ]; then
  green "Claude prompts: permissions.defaultMode = auto (prompt-free with safety classifier)"
else
  red "Claude prompts: defaultMode is '${mode:-unset}' — safe unattended cleanup requires auto"
  cure "Set permissions.defaultMode to \"auto\" in $SETTINGS; keep the Auto \$defaults safety policy."
  note "acceptEdits/default still prompt for Bash; bypass cannot combine prompt-free rm with a path-sensitive personal-data gate."
fi

# ── 1b. Live-hook drift — deployed hooks must match the repo canonical sources. ──
# The PreToolUse trust hook is the fast path for compound-cd and path-gated reap work.
# It does NOT override a matching permission ask rule; class 1c checks that separate
# precedence seam before launch. A stale live copy still reintroduces the prompt flood,
# so parity remains a checked class.
ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
for hf in allow-trusted-cd-git.sh insights-capture.sh; do
  canon="$ROOT/scripts/hooks/$hf"; live="$HOME/.claude/hooks/$hf"
  [ -f "$canon" ] || continue
  if [ ! -f "$live" ]; then
    red "Hook drift: $live is MISSING (repo canonical exists)"
    cure "install -m 755 $canon $live"
  elif [ "$(shasum -a 256 < "$canon" | cut -d' ' -f1)" != "$(shasum -a 256 < "$live" | cut -d' ' -f1)" ]; then
    red "Hook drift: $live differs from repo canonical scripts/hooks/$hf"
    cure "install -m 755 $canon $live"
    note "Run from the MAIN checkout — comparing against a stale worktree copy will false-red."
  else
    green "Hook parity: $hf live == repo canonical"
  fi
done

# ── 1c. Effective packet preflight — ask beats Auto/bypass/hook allow. ──
# The synthetic packet is NEVER executed. It represents the recurring class that stalled
# HOSPES: enter a project, delete one declared generated-output directory, run tests.
# The checker reads the locally visible settings stack and proves that no ask/deny rule
# intercepts the packet while Auto's default safety backstop remains intact.
PREFLIGHT="$ROOT/scripts/claude-permission-preflight.py"
probe_cmd="cd \"$ROOT\" && rm -rf .limen-permission-preflight-output && python3 -m pytest -q"
if [ -f "$PREFLIGHT" ] && preflight_out="$(python3 "$PREFLIGHT" \
    --project-root "$ROOT" \
    --generated-path .limen-permission-preflight-output \
    --command "$probe_cmd" 2>&1)"; then
  green "Unattended packet preflight: safe generated cleanup + test command cannot prompt"
else
  red "Unattended packet preflight: effective settings would block or prompt"
  [ -n "${preflight_out:-}" ] && note "$preflight_out"
  cure "Run python3 $PREFLIGHT --project-root <repo> --mode auto --generated-path <generated-dir> --command '<exact packet>'; fix only the named contradiction, retain real human gates, and rerun."
fi

# ── 1d. Hook wiring — settings must actually run the trust hook on Bash PreToolUse. ──
wired="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("no"); raise SystemExit
for m in (d.get("hooks") or {}).get("PreToolUse") or []:
    for h in m.get("hooks") or []:
        if str(h.get("command", "")).endswith("/.claude/hooks/allow-trusted-cd-git.sh"):
            print("yes"); raise SystemExit
print("no")
PY
)"
if [ "$wired" = "yes" ]; then
  green "Hook wired: hooks.PreToolUse runs ~/.claude/hooks/allow-trusted-cd-git.sh"
else
  red "Trust hook NOT wired in $SETTINGS hooks.PreToolUse — the compound-cd guard floods every fleet job"
  cure "Add hooks.PreToolUse matcher \"Bash\" -> command \$HOME/.claude/hooks/allow-trusted-cd-git.sh to $SETTINGS; then rerun class 1c because hook allow does not override ask."
fi
echo

# ── 2. 1Password / Touch-ID — the fingerprint dialogs. ──
# SILENCED when NO automated path calls `op` — then a locked vault can never pop Touch-ID unattended.
# creds-hydrate.py is the only `op` caller; it now reads op ONLY with an explicit --op flag (opt-in),
# so a bare TTY (every daemon beat AND every interactive session) no longer triggers it — that TTY
# clause WAS the storm. A service-account token (the only promptless `op`) is the PERMANENT cure: install
# it ONCE at $SA_FILE and every op:// read goes silent forever — the daemon beat, the op:// lanes, and the
# --sweep-all catch-all all hydrate with ZERO Touch-ID. Absent the token, op stays strictly opt-in (--op),
# so nothing pops unattended either way. Install via scripts/op-service-account.sh. [[macos-tcc-gatekeeper-dialogs-solved]]
CREDS="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/scripts/creds-hydrate.py"
SA_FILE="${LIMEN_OP_SA_TOKEN_FILE:-$HOME/.config/op/service-account-token}"
if [ -f "$CREDS" ] && grep -q 'op_ok = op_can_read_silently() or args\.op' "$CREDS" \
   && ! grep -Eq 'op_ok *=.*running_interactively\(\)' "$CREDS"; then
  green "1Password: op:// reads are OPT-IN (--op only) → no daemon beat or session can pop Touch-ID"
  note "SSH agent routing is also opt-in (LIMEN_USE_1PASSWORD_SSH; organvm/domus-genoma#130) — git is HTTPS, so SSH never hits 1Password either."
  if [ -n "${OP_SERVICE_ACCOUNT_TOKEN:-}" ] || { [ -f "$SA_FILE" ] && [ -s "$SA_FILE" ]; }; then
    green "service-account token present → op:// lanes AND --sweep-all hydrate unattended, promptless, forever."
  else
    note "op:// lanes hydrate via 'creds-hydrate --apply --op' at a terminal (one deliberate touch), OR — to go"
    note "promptless FOREVER (no touch, ever) — install the service-account token once:  scripts/op-service-account.sh install"
  fi
else
  red "1Password: creds-hydrate still auto-reads 'op' (no opt-in gate) → can pop Touch-ID unattended"
  cure "Make 'op read' opt-in in scripts/creds-hydrate.py:  op_ok = op_can_read_silently() or args.op  (drop the running_interactively() clause; add a --op flag)."
  note "This is a CODE fix an agent CAN land (no human needed). To also make op:// promptless forever, install a service-account token: scripts/op-service-account.sh install."
fi
echo

# ── 3. macOS Application Firewall — 'python/node wants to accept incoming connections'. ──
FW=/usr/libexec/ApplicationFirewall/socketfilterfw
if [ ! -x "$FW" ]; then
  green "Firewall: socketfilterfw not present — nothing to silence"
elif "$FW" --getglobalstate 2>/dev/null | grep -qi 'disabled'; then
  green "Firewall: application firewall is off → no incoming-connection prompts, ever"
else
  cur_node="$(readlink -f "$(command -v node 2>/dev/null)" 2>/dev/null || true)"
  if [ -n "$cur_node" ] && "$FW" --listapps 2>/dev/null | grep -qF "$cur_node"; then
    green "Firewall: on, but the current node ($cur_node) is allow-listed"
    note "A future 'brew upgrade node' rotates the path and re-prompts — turn the firewall off, or 'brew pin node', to make it durable."
  else
    red "Firewall: on, and the current node is not allow-listed → mcphub (binds all interfaces) will re-prompt"
    cure "Zero prompts forever (recommended — single-user box behind NAT, fully reversible):"
    cure "   sudo $FW --setglobalstate off"
    cure "Or keep the firewall on and allow the one offender (re-prompts on each node upgrade unless you also 'brew pin node'):"
    cure "   N=\"\$(readlink -f \$(command -v node))\"; sudo $FW --add \"\$N\" --unblockapp \"\$N\""
    note "Homed as L-FIREWALL-PROMPT."
  fi
fi
echo

# ── 4. Gatekeeper — "'claude' is an app downloaded from the Internet" (Dialog 6, 2026-07-04). ──
# ROOT: a DUPLICATE install of Claude Code via a Homebrew cask. Casks (unlike bottled formulae)
# stamp com.apple.quarantine on every download, so each cask upgrade = a fresh quarantined binary
# at a new Caskroom path = a Gatekeeper first-open prompt — and `brew upgrade --greedy-auto-updates`
# re-seeds it forever, silently defeating DISABLE_AUTOUPDATER (which only stops the native updater).
# The sanctioned install is the native ~/.local/bin/claude (deliberate updates). Agent-curable.
if command -v brew >/dev/null 2>&1 && brew list --cask 2>/dev/null | grep -qx 'claude-code'; then
  red "Gatekeeper: duplicate Homebrew cask 'claude-code' installed → quarantined per upgrade, prompts on first exec"
  cure "brew uninstall --cask claude-code   # native ~/.local/bin/claude is the one sanctioned install"
  note "Never click Open/Allow on the dialog — futile vs version churn; never brew-install claude in provisioning."
else
  quarantined=""
  for c in $(which -a claude 2>/dev/null | sort -u); do
    xattr -p com.apple.quarantine "$(readlink -f "$c" 2>/dev/null || echo "$c")" >/dev/null 2>&1 && quarantined="$quarantined $c"
  done
  if [ -n "$quarantined" ]; then
    red "Gatekeeper: quarantined claude binary on PATH:$quarantined → will prompt on first exec"
    cure "xattr -d com.apple.quarantine <binary>   # or remove the duplicate install entirely"
  else
    green "Gatekeeper: single unquarantined claude install (no brew-cask duplicate) — no first-open prompt possible"
  fi
fi
echo

if [ "$gaps" -eq 0 ]; then
  echo "ALL CLEAR — no recurring permission dialog remains. (re-run anytime to confirm it stays so)"
  exit 0
fi
printf '%s class(es) still prompt. Each cure above is ONE one-time action, then silent forever.\n' "$gaps"
echo "Do them, then re-run this script — it must print ALL CLEAR."
echo "(Residual one-offs like 'python wants to access Documents' = grant Full Disk Access to your terminal in"
echo " System Settings ▸ Privacy & Security ▸ Full Disk Access — a catch-all for file-access TCC dialogs.)"
exit 1
