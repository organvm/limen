# Privacy Containment Receipt

At `2026-07-16T19:52Z`, live remote inspection confirmed that the material associated with Limen
PR #1089 remained reachable at the public default-branch head, while material removed by
application-pipeline PR #78 remained reachable in that public repository's Git history. Both
repositories reported zero public forks.

The two affected repositories, `organvm/limen` and `organvm/application-pipeline`, were temporarily
changed from `PUBLIC` to `PRIVATE`. Authenticated GitHub reads confirmed `isPrivate=true`; fresh
unauthenticated requests to both repository URLs and the application-pipeline Pages URL returned
HTTP 404. No file content, identifier, private path, or personal record is reproduced here.

This is containment, not deletion or reacceptance:

- Limen's current public-serving path still needs a redacted replacement committed through an
  isolated repair PR.
- Both repositories' histories still require a private reachability scan and a deletion packet.
- Rewriting history, requesting cache purges, deleting personal records, or restoring public
  visibility remains a human-gated step after two-copy custody proof.
- Existing local clones and any copies made while the repositories were public remain outside the
  technical reach of this visibility change.

Release predicate: current trees contain no sensitive material; the human-approved history action
is completed or explicitly owner-blocked; unauthenticated repository and Pages probes remain
unreachable until that predicate passes; and the corresponding ledger rows have durable receipts.
