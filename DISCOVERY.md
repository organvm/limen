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
