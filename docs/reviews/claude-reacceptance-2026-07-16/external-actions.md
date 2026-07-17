# Already-Observed External Actions

This is an inventory, not an authorization to repeat, undo, or validate an action by performing it
again. Details that identify people, private records, accounts, objects, or host paths remain in
their private owner receipts.

| Category | Observed action | Current treatment |
|---|---|---|
| Remote backup configuration | Backblaze XML exclusions were changed | Hold further mutation; reconcile current live XML in Domus before any repair |
| Mail | Four messages and one mail self-test were reported sent | Do not resend; reconcile against private mail receipts and repair authorization binding |
| Calendar | One calendar mutation was reported | Do not replay; reconcile against the calendar owner receipt |
| Media | Media visibility was changed | Preserve current evidence; verify owner policy before any further visibility change |
| Artifact delivery | An artifact was delivered through iCloud | Preserve two-copy custody evidence; do not redeliver |
| Worktree lifecycle | Worktrees were moved or reclaimed | Reconcile each root against remote custody before further movement or deletion |
| Private records | Private ARCA seals were written | Keep private; tracked ledger records only the redacted receipt state |
| Privacy containment | Affected repositories were temporarily changed from public to private on 2026-07-16 | Keep restricted until current-tree and history predicates pass; do not republish by reverting visibility |

No destructive history rewrite, personal-data deletion, credential action, blind host rollback, or
live-storage reversal is authorized by this inventory.
