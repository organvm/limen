# Network Substrate Healing Stream

Generated: `2026-06-28`

You are in a dedicated Limen worktree:

```bash
/Users/4jp/Workspace/limen-network-substrate-20260628
```

This stream exists because the network incident was not just an environmental
outage. It exposed a conductor failure mode: agents tend to patch the immediate
lane and stop, while the real substrate problem remains undocumented,
unverified, and likely to recur.

## First Read

Read these before editing:

```bash
sed -n '1,220p' AGENTS.md
sed -n '1,260p' docs/lanes/network-substrate.md
sed -n '1,220p' docs/DISPATCH-ARCHITECTURE.md
sed -n '1,220p' docs/dispatch-health.md 2>/dev/null || true
sed -n '1,220p' docs/network-health.md 2>/dev/null || true
sed -n '1,220p' docs/live-root-gate.md 2>/dev/null || true
```

Then compare against the dirty live root without modifying it:

```bash
git -C /Users/4jp/Workspace/limen status --branch --short
git -C /Users/4jp/Workspace/limen diff -- scripts/netmode.sh container/launchd/com.user.netmeter.plist
```

## Mission

Turn the patched network incident into a durable Limen substrate path:

- reconcile the live dirty `netmode` fix into a clean branch;
- preserve the invariant that background timers default to observe-only;
- verify launchd templates cannot silently re-enable switching;
- document the operator gates for `netmode stop`, `panic`, install, and reload;
- record the incident as dispatch/substrate learning, not only a local script fix;
- leave receipts so the next agent knows what is patched, what is verified, and
  what still needs an explicit human gate.

## Allowed Files

Stay inside this worktree unless a command is explicitly read-only against the
live root:

- `scripts/netmode.sh`
- `container/launchd/com.user.netmeter.plist`
- `container/launchd/com.user.netmode.*.plist`
- `docs/lanes/network-substrate.md`
- `docs/network-health.md`
- `docs/dispatch-health.md`
- `docs/live-root-gate.md`
- `docs/conductor-tranche.md`
- focused tests or fixtures for the files above

Do not mutate `tasks.yaml` unless the human explicitly asks for task-board
state changes.

## Stop Gates

Stop and report exact gates before:

- any real network switch;
- any `launchctl bootstrap`, `kickstart`, daemon reload, or live plist install;
- changing `~/.limen.env`, keychain, credentials, or private network config;
- deleting launch agents;
- touching `/Users/4jp/Workspace/4444J99/portvs`;
- broad creative placement work;
- claiming queue work unrelated to this stream.

Read-only live checks are allowed.

## Initial Verification

Use current repo truth. The patched live root previously reported:

- `mode=observe`;
- `com.user.netmode.keepalive`, `com.user.netmode.netwatch`,
  `com.user.netmeter`, and `com.user.netmode.recycle` disabled;
- `bash scripts/netmode.sh selftest` passing with 66 tests.

Treat those as stale until rechecked. Suggested non-mutating probes:

```bash
bash scripts/netmode.sh selftest
plutil -lint container/launchd/com.user.netmeter.plist
bash scripts/netmode.sh status
launchctl print-disabled "gui/$(id -u)" | rg 'netmode|netmeter' || true
```

If comparing the installed live script:

```bash
shasum -a 256 scripts/netmode.sh "$HOME/Library/Application Support/netmeter/netmode.sh"
```

## Receipt Required

Before handoff, leave a short receipt with:

- worktree and branch;
- changed paths;
- exact verification commands and results;
- live-root state compared against this branch;
- whether launchd/live install remains gated;
- next action for the main conductor stream.
