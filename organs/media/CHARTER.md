# Carrier-Wave Media — CHARTER

## The rival institution
A cross-platform media empire (the carrier-wave position: Bowie/Tarantino of systems). 

## The AI roles

- **Editor-in-Chief (Logos):** Validates frontmatter, ensures editorial standards and the carrier-wave tone are met before drafts enter the distribution pipeline.
- **Distribution Orchestrator (Kerygma):** Takes an approved essay or product launch and fans it out across the POSSE network (Publish Own Site, Syndicate Everywhere). Translates the core message into channel-specific idioms (e.g., short-form for Twitter/Mastodon, long-form for LinkedIn/Discord).
- **Engagement Analyst:** Monitors reach and penetration, feeding insights back into the topic suggester.

## The workflows

1. **Essay -> Kerygma Pipeline**
   - **Trigger:** A new essay or product event is generated.
   - **Action:** The Kerygma orchestrator drafts syndication content for each configured channel using announcement templates.
   - **Gate:** The human creator reviews the drafts.
   - **Publish:** Once approved, the orchestrator dispatches the payload to the respective APIs (Mastodon, Discord, etc.).
   
2. **Weekly Intelligence Gathering**
   - **Trigger:** Cadence (weekly).
   - **Action:** Topic suggester analyzes the `reading-observatory` and system corpus to propose high-value essay topics.
   
## Staging and State

The media organ's outputs are staged as drafts in the `kerygma-pipeline` or `essay-pipeline` repositories. They remain in the "armed" but "never fired" state until the creator provides explicit approval.
