# Truth-first evidence map

## Owner heads

| Owner | PR | Exact source head |
|---|---:|---|
| schema-definitions | #12 | `20de01dfc3bcc46c444cb16270e6de274807c446` |
| session-meta | #166 | `04ab5023d7d251044b24bb56579c0492644f779b` |
| conversation-corpus-engine | #62 | `6340e762607859194302ddb98a02128b6915d0c4` |
| organvm-ontologia | #18 | `2bb7248a24b7ac0515bfea21db6aca43f6dbfe05` |
| organvm-engine | #168 | `0f7ecc0545577c1b13e9f62e9f4b8e5254d85036` |
| CORPVS | #534 | `45f2d6ce63b1a1935a800624a3fffae99aca5898` |
| Limen code baseline | #1161 | `40bad7a15a8fdabbedc8567201ac312a81ced96c` |

Derive the current Limen head after this capsule commit. All seven branches include their fetched
`origin/main` (`rev-list --left-right --count origin/main...HEAD` reported zero commits behind at
the refresh boundary).

## Frozen custody

- Snapshot identity and timestamp are supplied through `LIMEN_GOV_SNAPSHOT_ID` and
  `LIMEN_GOV_SNAPSHOT_AT`.
- The exact private digest and custody path remain in the owner-native private receipt.
- The superseding config is supplied through `LIMEN_GOV_CONFIG`; the original Archive4T config and
  7.456 GiB of historical output stay in place.
- The bounded run root is
  `$LIMEN_SCRATCH_ROOT/limen-private/governance-memory/runs/$LIMEN_GOV_SNAPSHOT_ID`
  and requires an exact Domus-owned mount/device/backup-exclusion receipt.
- Final custody is
  `$LIMEN_GOV_FINAL_RECEIPT_ROOT/$LIMEN_GOV_SNAPSHOT_ID`, containing only the two aggregate
  collections, the post-proof observation, and the final bundle.

Preserve the owner-native failed stage-9 run and the explicitly superseded owner-revision run; they
are evidence, not completion receipts.

## Established facts

- March and July operator events are present as immutable native source envelopes.
- CORPVS is ratified against ready constitutional coverage. Global source coverage remains
  non-ready and must not erase that constitutional authority.
- The frozen census has 17 raw units: 9 acquired/parsed and 8 owner-blocked.
- Normalization contains 62,976 events and source envelopes, with 1,715 quarantines.
- Atlas compilation preserves one verified operator assertion, 22 registered self-images,
  two populated timelines, all six populated zoom levels, and zero citation debt.
- Global readiness is honestly false while blocked exports, quarantines, and incomplete ideal
  predicates remain.

## Hosted-runner verifier state

GitHub API, pull requests, remotes, and Actions configuration are operational. Some historical jobs
ended before allocating a runner and executed zero steps; preserve that result as unexecuted
hosted-runner verifier debt. It is not a GitHub outage, external campaign gate, or reason to stop
local exact-head predicates, preservation, PR updates, or owner-authorized merges.
