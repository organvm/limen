# organvm/limen — Value Thesis

**Discovered 2026-06-22** · [auto-discovery] · status: **promoted to ranked tier**

## What It Is

Limen is a **universal agent task intake system** — a protocol (`AGENTS.md`), file format (`tasks.yaml`), CLI (`limen
dispatch/harvest/status`), and SaaS dashboard that coordinates multiple AI coding agents across multiple repositories
under budget-capped, lifecycle-tracked autonomous operation.

## The Value

Limen is not a direct revenue product. It is the **operating system for the organvm agent fleet** — the layer that
converts fixed-cost agent subscriptions (Claude Code, Gemini CLI, Jules, Codex, OpenCode, Agy, Copilot, Warp/Oz) into
autonomous completed work at full saturation. Without Limen, every agent session is manual: open a terminal, read a
task, run it, write back, repeat. With Limen, a single daemon saturates 7+ paid lanes with no human in the loop —
budget-capped, stale-claim-recovered, lifecycle-tracked, and dashboard-visible.

The concrete value to the organvm estate:

1. **Agent cost arbitrage** — ensures no paid subscription sits idle; every seat dollar is converted to shipped work.
   The daemon's heartbeat loop routes work to whichever lane has budget remaining, so underutilized agents (Gemini,
   Copilot, Warp) are kept busy, not wasted.
2. **Cross-agent coordination** — six concurrent agents touching the same repos without conflict, without duplicate
   work, without overspend. The dispatch/harvest lifecycle with cross-process `_queue_lock` makes this safe.
3. **SaaS product asset** — the AGENTS.md protocol specifies a universal intake format any agent fleet could adopt.
   A multi-tenant "Limen as a Service" where teams pay per agent-lane is a real revenue path: every org using Claude
   Code + Gemini + Jules today manually juggles across terminals.
4. **Portable protocol** — the `tasks.yaml` schema is generic; it can be vendored into any repo as a
   `curl | bash` install. This is already done for 15+ organvm repos and is the mechanism by which every agent
   session starts.

## First Build-Out Task

**Extract the AGENTS.md lifecycle protocol into a formal spec (`spec/agent-protocol-v1.md`) and add `limen serve`**
— a TCP/Unix-socket listener that accepts task claims from any compatible agent, validating the SaaS thesis with a
single-tenant daemon before building the multi-tenant dashboard. This surfaces a concrete `limen serve` endpoint
that other teams could point their agents at, turning the protocol from convention into product.

---

# organvm/media-ark — Value Thesis

**Discovered 2026-06-22** · [auto-discovery] · status: **promoted to ranked tier**

## What It Is

Media Ark is a local-first, zero-dependency media archive pipeline that discovers, deduplicates (SHA-256 content
hash), processes, enriches (OCR, PDF text extraction, thumbnails, keyword extraction), and indexes images, video,
PDFs, and documents into a persistent canonical store with JSON sidecars, event logs, and a queryable manifest.
It ships as a Python CLI, an HTTP API + web dashboard, and an MCP stdio bridge (5 tools), with a brand domain
(media-ark.org), documented Pro tier ($7/mo), and wired Stripe billing integration.

## The Value

Media Ark is the organvm estate's **first standalone revenue-capable SaaS product**. Its highest latent value is a
concrete, shippable Pro tier: encrypted cloud sync at $7/mo, with the auth, billing, dashboard, and API scaffolding
already built and tested. The repo also delivers reusable assets for the estate: (1) a zero-dependency file-processing
pipeline engine (`process_captures.py`) that any organvm repo could use for content ingestion; (2) a self-contained
auth module (SQLite + PBKDF2, stdlib-only) usable as a shared library; (3) a production-quality Stripe checkout +
webhook integration ready to be extracted as a shared payment microservice for other organvm SaaS products; (4) the
`conductor/` directory defining agent routing tables and dispatch instructions consumed directly by the limen fleet.
The product addresses a validated market (CleanShot X, Snagit, ShareX users) with a differentiated angle: local-first,
open-core, agent-friendly (MCP-native). The main gap before shipping is not code quality but operational — the CI
runner-pickup infrastructure issue on this repo and the placeholder (keystream XOR) cloud sync cipher that must be
replaced with AES-GCM before the Pro tier can go live.

## First Build-Out Task

**Swap the placeholder cloud-sync cipher (SHA-256 keystream XOR) with production AEAD (AES-256-GCM via
`cryptography` or stdlib `hashlib` + `os.urandom`), write the integration test against the sync module, and deploy
a self-hosted GitHub Actions runner so CI goes green.** This unblocks both the Pro tier revenue path (encrypted sync
is the paid feature) and the release pipeline (CI must pass to ship 1.0), making it the single highest-leverage task
in the repo.
