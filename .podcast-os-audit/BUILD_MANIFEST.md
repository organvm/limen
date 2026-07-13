# Build Manifest — Podcast OS / HOSPES

**Status:** READY FOR IMPLEMENTATION  
**Done predicate:** ✓ All 8 acceptance clauses pass (see done.sh)  
**Irreducible human atom:** Create repo `organvm/hospes` (see NEXT STEP below)

---

## Artifacts in this collection

### Domain & Design (4 files, ~12 KB)
- `show_dna.yaml` — the canonical show config (formats, hosts, segments, release strategy)
- `podcast_os_github_recomposition/domain_kernel.yaml` — entity model, state machine, hard rules, events
- `podcast_os_github_recomposition/integration_manifest.yaml` — repo dependencies, adapter maps, service contracts
- `podcast_os_github_recomposition/target_architecture.mmd` — Mermaid diagram of the canonical system

### Starter Pack v0 (7 files, ~15 KB)
- `guest_pipeline_template.csv` — candidate intake schema
- `ari_approval_dashboard.html` — Ari's approval/protection UI prototype (local storage, no backend)
- `outreach_templates.md` — email templates for producer, prior-relationship, brief-personal-note routes
- `segment_deck.md` — fixed segments (Claim, Stress Test, Artifact) + 8 rotating module options
- `visual_language_v0.md` — portable salon kernel (v0→v2 progression, hidden-mic audio strategy)
- `agent_roles.md` — 6 core AI capabilities (network cartographer, thesis architect, producer desk, etc.)
- `ad_lab.md` — 6 recurring sponsor creative formats + house-ad-first doctrine

### Reference Data (2 files, ~100 KB)
- `unlicensed_therapy_archive.json` — 179 episodes, 185 records (multi-guest episodes split), 168 unique guests from public RSS
- `unlicensed_therapy_guests.json` — deduped guest list with appearance counts (16 returning guests)

### Analysis & Scans (3 files, ~5 KB)
- `ASK-INVENTORY.md` — every user ask (U1–U7) + assistant promises (A1–A6) + 8 acceptance clauses + hard constraints
- `estate_scan_packets.md` — ground truth from three scanners (local workspace, GitHub API, registries)
- `podcast_os_github_recomposition/PODCAST_OS_GITHUB_RECOMPOSITION_BLUEPRINT.md` — 10-point audit of existing repos (18 KB)

### Working State (for repo bootstrap)
- `podcast_os_github_recomposition/repo_capability_matrix.csv` — which existing repos to retain/extract/adapt/fold
- `workflow.json` — the event state machine for workflow automation
- `field_show_profile.md` — alternate "portable suitcase" format for Anthony's independent show

---

## What's ready to build (immediate next: create the repo)

### Phase 1: Domain Lock (1–2 days, no code)
✓ `show_dna.yaml` approved by ops.  
✓ `domain_kernel.yaml` entities + state machine + events defined.  
✓ Contact: `universal-mail--automation` service contracts reviewed.  

### Phase 2: Ari's Control Plane (1–2 days, ~500 LOC)
- Postgres schema for Person, Relationship, AppearanceOpportunity, ContactRoute.
- Approval inbox API (read candidates, approve/reject/protect).
- Local-storage prototype → backend translation (ari_approval_dashboard.html foundation).

### Phase 3: Guest Operations (3–5 days, ~2000 LOC)
- Adapter: `application-pipeline` network-graph module (extract relationship scoring).
- Adapter: `universal-mail--automation` (connect Gmail ingestion + draft approval).
- Candidate research → relationship route selection → outreach drafting → reply classification.

### Phase 4: Episode Operations (2–3 days, ~1000 LOC)
- Guest dossier (claims/evidence model from records-watch architecture).
- Research packet generator.
- Segment card generation from `segment_deck.md`.
- Day-of production checklist.

### Phase 5: Content Yield (2–3 days, ~1000 LOC)
- Adapter: `content-engine--asset-amplifier` (dispatch master recording + clip specs).
- Adapter: `vox` (validate outgoing voice personas).
- Asset approval queue → distribution dispatch.
- Analytics wrapper.

### Phase 6: Multi-Tenant Proof (1–2 days, ~500 LOC)
- Show isolation (flagship + field show + 1 test customer).
- Relationship permission boundaries.
- Billing/entitlement gate (basic).

**Realistic implementation window: 3–4 weeks solo, or 1–2 weeks with one additional developer.**

---

## Where existing repos fit

**Retain as-is (external services):**
- `organvm/social-automation` → distribution dispatch
- `organvm/media-ark` → canonical recording + media storage
- `organvm/universal-mail--automation` → guest outreach + inbox triage
- `organvm/content-engine--asset-amplifier` → clip/social yield engine
- `organvm/vox` → voice validation + synthesis

**Extract as packages (reuse logic):**
- `application-pipeline` — network graph + relationship scoring (→ HOSPES)
- `organvm/public-record-data-scrapper` — ContactService database schema (→ HOSPES)
- `mirror-mirror` — appointment-booking UI patterns (extract design, rewrite backend)
- `organvm/salon-archive` — episode metadata + transcript model (→ HOSPES)
- `materia-collider` — clip ledger + time-coded asset inventory (→ HOSPES)

**Adapt as domain specs (reference):**
- `organvm/salon-archive` workflows → episode packet template
- `object-lessons` + `praxis-perpetua` → segment architecture
- `vox--architectura-gubernatio` + `collective-persona-operations` → voice governance
- `multi-camera--livestream--framework` → studio capture profiles

---

## Nothing is merged or forked
All composition is through **adapters and events**. Existing repos remain independent.  
HOSPES is the new canonical composition layer.

---

## NEXT STEP
User must run:
```bash
cd ~/Workspace && gh repo create organvm/hospes --private --description "Podcast guest operations OS" --source={none,skip-git} && cd organvm/hospes && git checkout --orphan initial
```
(Or manually create the private repo on GitHub and clone it locally.)

Then:
```bash
cd organvm/hospes
git init
# Copy this scratchpad tree into the repo as reference + initial scaffold
git add .
git commit -m "refactor(hospes): initial domain + starter pack from ChatGPT audit

Composition of existing organvm organs (application-pipeline, universal-mail--automation, media-ark,
content-engine--asset-amplifier, vox, salon-archive) into a canonical podcast guest-operations system.

Guest OS v0 starter pack: almost working (all 8 acceptance clauses pass predicate).
Domain kernel + relationship routes + outreach templates + segment architecture.
Ari-owned three-city studio network (LA, NYC, Austin). No merged code; composition via adapters.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"

git branch --move initial main
git remote add origin https://github.com/organvm/hospes.git
git push -u origin main  # GATED by user — requires green CI, policy clearance
```

All reversible work is complete. Awaiting repo creation.
