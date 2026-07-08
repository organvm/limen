# Credential Token Tombstone Audit

Date: 2026-07-08

Receipt target: `AW-CREDENTIAL-WALL-TOKEN-HYGIENE`

## Verdict

The current credential wall owns the live credential estate, and the historical
token residue has a durable tombstone receipt. This file records existence,
custody, revocation, supersession, or parked status only. It intentionally records
no secret values, token prefixes, token suffixes, checksums, hashes, screenshots,
or provider response bodies that could help reconstruct a credential.

Current structural source of truth:

- Credential wall generator: `scripts/credential-wall.py`
- Hydration map and verifier: `scripts/creds-hydrate.py`
- Pinned wall owner surface: `https://github.com/organvm/limen/issues/320`
- Related owner packet: `https://github.com/organvm/limen/issues/686`

## Harvest

Existing local receipts and owner packets were harvested before this receipt was
created:

- `tasks.yaml` contains `AW-CREDENTIAL-WALL-TOKEN-HYGIENE`, with the stop
  condition requiring this tombstone receipt and the current wall predicate.
- `tasks.yaml` also contains `GH-organvm-limen-686`, the matching GitHub issue
  packet for a historical token tombstone audit.
- `docs/estate-custody-primitives.md` and
  `docs/estate-custody-implementation-receipts.json` route historical token
  tombstone custody to `organvm/limen#686`.
- `docs/agent-code-diff-review.md` records the prior credential-wall merge:
  PR #321 landed the credential wall pattern, issue #320 exists, and current
  structural checks were green in that review.

Remote live harvest was attempted with `gh issue view 320`, `gh issue view 686`,
and a credential/tombstone PR search. The sandbox could not connect to
`api.github.com`, so this receipt does not claim fresh remote metadata beyond the
local owner packet records.

## Current Wall Snapshot

The counts-only credential wall census reported:

- Hydration lanes: 12
- Enabled lanes: 6
- Parked lanes: 6
- Derived lanes: 2
- Probed lanes: 3
- CI/runtime secret classes: 5
- Homeless secret atoms: 0
- Wall issue: 320

The live current-home predicate remains `python3 scripts/credential-wall.py
--check`.

## Tombstone Ledger

| Historical atom | Former risk | Current custody | Owner surface | Value custody |
|---|---|---|---|---|
| Static GitHub PAT item `op://GitHub-Tokens/master-org-token-011726/password` | A revoked static PAT could shadow the valid local GitHub keyring when materialized into `GH_TOKEN` or `GITHUB_TOKEN`. | `scripts/creds-hydrate.py` now prefers `derive: ["gh", "auth", "token"]` with those env vars scrubbed from the child process; the static 1Password item remains a last-resort provenance record only. | `scripts/creds-hydrate.py` `gh/copilot/jules` and `laurea` lanes; wall issue #320. | No value recorded here. The historical revoked value remains outside the repo in its credential store, and live hydration derives from the keyring instead. |
| Phantom OpenAI API key for codex/opencode | Repeated work chased a key that was not minted or required by the live Codex lane. | Lane is parked: Codex authenticates through ChatGPT OAuth, and no fleet code requires `OPENAI_API_KEY` for the current Codex lane. | `scripts/creds-hydrate.py` `codex/opencode (openai)` lane; wall issue #320. | No value exists in this receipt; no current secret value is required for this lane. |
| Phantom OpenRouter API key for opencode | Repeated work chased an env var not consumed by the active opencode path. | Lane is parked: opencode uses its own auth path or free model fallback unless a future OpenRouter integration is explicitly introduced. | `scripts/creds-hydrate.py` `opencode (openrouter)` lane; wall issue #320. | No value exists in this receipt; no current secret value is required for this lane. |
| Superseded GCP deploy service-account lane | Inherited deploy config created a phantom `GCP_SA_KEY` need after the hosting path moved to Cloudflare. | Lane is parked as a superseded multi-sink example. `GCP_SA_KEY` remains cataloged as optional CI/runtime state, but it is not the active hosting path. | `scripts/creds-hydrate.py` GCP superseded lane; `scripts/credential-wall.py` CI/runtime catalog; wall issue #320. | No key material recorded here. Any future GCP revival must mint/store the key through the credential wall before use. |
| Cloudflare deploy token false-negative history | A prior verifier endpoint produced a false invalid-token reading for account-scoped tokens. | Verification uses the generic `/accounts` probe instead, and the Cloudflare token remains the owned deploy credential for Cloudflare lanes. | `scripts/creds-hydrate.py` `cloudflare (wrangler deploy)` lane; wall issue #320. | No value recorded here. The live token home stays in 1Password and GitHub secret sinks named by the wall. |
| Gmail app-password paste burden | The same existing secret could be handed back as a manual "paste this GitHub secret" task. | The wall models it as a `gh_secret` sink for the consuming repo and keeps local env hydration parked unless a local consumer is introduced. | `scripts/creds-hydrate.py` `gmail (domus CI secret)` and `gmail (C_MAIL app-password)` lanes; issue #261; wall issue #320. | No value recorded here. Value streams only from the credential store to the GitHub secret sink when that owner action runs. |
| IANVA cloud connector bearer token | Re-minting rotates the bearer token, so an automatic hydration loop could break the live connector. | Lane is parked as a registered information home. Rotation remains an explicit owner action through the credential wall, not a beat-time action. | `scripts/creds-hydrate.py` `ianva (cloud connector bearer)` lane; issue #263; wall issue #320. | No value recorded here. The current bearer stays outside git in its env/cache home. |
| Claude auth token / budget poll token | The same credential class can feed both login self-heal and exact budget polling; duplicating it would create another human atom. | Lane remains parked under the Rung-0 credential-race self-heal. If that handler is retired, the same wall entry becomes the enablement point. | `scripts/creds-hydrate.py` `claude` lane; wall issue #320. | No value recorded here. The token is not duplicated into this receipt. |
| 1Password service-account token | Promptless reads can exist while vault grants are insufficient; without a receipt this can look like a recurring auth mystery. | `OP_SERVICE_ACCOUNT_TOKEN` is cataloged as a CI/runtime class with its file/env home and a non-blocking vault-grant residual. | `scripts/credential-wall.py` CI/runtime catalog; issue #288; wall issue #320. | No token value, prefix, suffix, or grant material recorded here. |
| Limen API/client bearer secrets | Runtime bearer tokens could be treated as ad hoc deploy facts instead of registered secret classes. | Both are cataloged as CI/runtime secret classes with GitHub Actions and GCP Secret Manager homes. | `scripts/credential-wall.py` CI/runtime catalog; wall issue #320. | No bearer values recorded here. |
| Warp API key | Optional paid-service lane could appear as an unexplained failure when unset. | Cataloged as an optional CI/runtime secret class; unset means the warp/oz lane is off rather than homeless. | `scripts/credential-wall.py` CI/runtime catalog; wall issue #320. | No value recorded here. |

## Acceptance

This receipt closes the historical tombstone gap when both conditions are true:

1. `python3 scripts/credential-wall.py --check` exits `0`, proving every current
   credential atom has a registered home.
2. This file exists at `docs/credential-token-tombstone-audit.md`, proving the
   historical/rotated token residue has an owner receipt without values.

Future credential pain points should update `scripts/creds-hydrate.py`,
`scripts/credential-wall.py`, the credential-labelled issue set, or this
tombstone receipt. They should not be recited in chat.
