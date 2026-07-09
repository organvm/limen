# Local Residency

Generated: 2026-07-09

## Invariant

The laptop is hot cache and control plane only. Durable custody, public endpoints, revenue state,
mail state, media intake, and credentials must survive the laptop being shut, lost, unplugged, or
offline. Local Login Items are not an acceptable durability layer.

## Current Host Receipt

On 2026-07-09, the local user LaunchAgent set was reduced to one Limen-owned resident service:

- Kept: `com.limen.heartbeat`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.limen.moneta`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.limen.moneta-tunnel`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.ianva.gateway`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.limen.overnight-watch`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.limen.watchdog`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.limen.creds-hydrate`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.4jp.mail-triage`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.user.photos-screen-capture-importer`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.user.netmode.keepalive`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.user.netmode.netwatch`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.user.netmode.recycle`
- Disabled and moved out of `~/Library/LaunchAgents`: `com.user.netmeter`
- Disabled launchd record: `com.4jp.desktop-router`

The disabled files were preserved under `~/Library/LaunchAgents.disabled/` with timestamped names.
No local secrets, order files, mail reports, media, or personal data were deleted or moved.

## Return Criteria

A local resident job may return only if all of these are true:

- It cannot be a heartbeat voice, one-shot command, remote service, or external-custody job.
- Its durable state is already owned by a remote repo/service or external custody receipt.
- It has a recovery command that rebuilds local cache from that owner.
- Its plist label, program, state root, logs, and rollback path are recorded here or in a narrower
  owner document.

## Migration Owners

- `moneta` and `moneta-tunnel`: public/revenue surfaces must move to a remote deploy or remain
  stopped locally. A local tunnel is not a durability plan.
- `ianva.gateway`: gateway work must move behind a remote owner or be started only as an explicit
  one-shot local development command.
- `mail-triage`: mail sweep ownership belongs to the heartbeat mail cadence or a remote/mail owner,
  not a second LaunchAgent.
- `creds-hydrate`, `watchdog`, and `overnight-watch`: fold into the single supervisor or replace
  with remote receipts; do not add more local resident jobs.
- `photos-screen-capture-importer`: media intake must prove external custody and restore gates
  before it runs unattended.
