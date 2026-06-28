# Network Substrate Lane

Generated: `2026-06-28`

Status: `active`

## Identity

- Lane handle: `network-substrate`.
- Primary repo: `organvm/limen`.
- Local stream worktree: `/Users/4jp/Workspace/limen-network-substrate-20260628`.
- Dirty live root to reconcile: `/Users/4jp/Workspace/limen`.
- Domain: local connectivity, launchd timers, `netmode`, heartbeat survivability,
  and dispatch lessons learned from network incidents.

This is a workstream lane, not a new Limen `target_agent`. Route work to the
canonical agent fleet and add `network-substrate` as a label when queue state is
explicitly in scope.

## Current Ground Truth

As of the stream seed:

- The live Limen checkout is dirty on `feature/ORG-artist-organ-face-0628`.
- Dirty live files include `scripts/netmode.sh`,
  `container/launchd/com.user.netmeter.plist`, `tasks.yaml`, and untracked
  `organs/health/` plus `organs/media/`.
- Another session patched the immediate network issue:
  - background switching defaults off with `BACKGROUND_SWITCHING=0`;
  - `tick` meters/statuses unless background switching is explicitly enabled;
  - `netmode stop` / `panic` disables all netmode/netmeter launch agents;
  - the legacy `com.user.netmeter` template is disabled and no longer runs at
    load;
  - the patched script was installed to the live netmeter path.
- The live-state report said all netmode/netmeter launch agents were disabled
  and `mode=observe`, but every future session must recheck this before
  claiming it is current.

## Purpose

This lane exists to prevent "single lane patch, no system healing" as the
default agent behavior. Network incidents should produce:

- a minimal local fix;
- a repeatable local verification command;
- launchd/template hardening;
- documented operator gates for live reload and install;
- a dispatch/substrate lesson so future lanes do not depend on fragile network
  switching;
- a receipt that lets the main conductor decide whether to merge, install, or
  leave the live patch parked.

## Allowed Files

Primary implementation and receipts:

- `scripts/netmode.sh`
- `container/launchd/com.user.netmeter.plist`
- `container/launchd/com.user.netmode.keepalive.plist`
- `container/launchd/com.user.netmode.netwatch.plist`
- `container/launchd/com.user.netmode.recycle.plist`
- `docs/lanes/network-substrate.md`
- `docs/network-health.md`
- `docs/dispatch-health.md`
- `docs/live-root-gate.md`
- `docs/conductor-tranche.md`
- focused tests, fixtures, or scripts that directly verify these surfaces

Read-only comparison targets:

- `/Users/4jp/Workspace/limen`
- `$HOME/Library/Application Support/netmeter/netmode.sh`
- `$HOME/Library/LaunchAgents/com.user.net*.plist`
- `launchctl print-disabled "gui/$(id -u)"`

## Forbidden / Stop Gates

Stop before:

- changing the current network route or Wi-Fi service order;
- enabling background switching;
- bootstrapping, kickstarting, reloading, or deleting launchd jobs;
- writing live installed scripts or plists;
- changing credentials, keychain entries, `.env` files, or secret stores;
- mutating `tasks.yaml` without an explicit board-state request;
- touching `/Users/4jp/Workspace/4444J99/portvs`;
- doing creative placement work.

Read-only probes are allowed.

## Standard Work Packet

Use this shape for future queue packets:

```yaml
labels: [network-substrate, limen]
repo: organvm/limen
target_agent: <canonical Limen agent>
context: >
  Work in /Users/4jp/Workspace/limen-network-substrate-20260628 or a fresh
  worktree from origin/main. Reconcile the dirty live-root netmode patch into a
  clean branch, preserve observe-only background timers, verify with selftest
  and plutil, and leave a receipt. Stop before live launchd reload, install,
  network switching, credentials, or queue mutation unless explicitly gated.
```

## Resume Commands

Read-only orientation:

```bash
git status --branch --short
git log --oneline -5
git -C /Users/4jp/Workspace/limen status --branch --short
git -C /Users/4jp/Workspace/limen diff -- scripts/netmode.sh container/launchd/com.user.netmeter.plist
```

Verify the branch copy:

```bash
bash scripts/netmode.sh selftest
plutil -lint container/launchd/com.user.netmeter.plist
```

Probe live state without changing it:

```bash
bash scripts/netmode.sh status
launchctl print-disabled "gui/$(id -u)" | rg 'netmode|netmeter' || true
shasum -a 256 scripts/netmode.sh "$HOME/Library/Application Support/netmeter/netmode.sh"
```

## Merge / Install Gate

Merging code to `origin/main` is separate from installing it live.

Live installation requires an explicit operator gate and a receipt naming:

- current branch and commit;
- exact installed source and destination;
- before/after hashes;
- launchd labels touched;
- route and mode before/after;
- rollback command.
