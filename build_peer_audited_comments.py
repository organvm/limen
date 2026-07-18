import json

repo = 'organvm/peer-audited--behavioral-blockchain'
base = f'https://github.com/{repo}'

comments = {}
dispositions = {}

brainstorm = {
99: dict(core='a contract-ladder system that deliberately starts below ambition instead of asking new users to begin at full stake', seams='(1) a `gateway` oath tier with micro-stake ceilings, (2) a 5-step ladder generator per oath category, and (3) unlock rules tied to verified completions before stake/difficulty rises', related='That makes it complementary to reactive downscaling and to the sequential-unlock ideas already elsewhere in the backlog rather than duplicating them.'),
100: dict(core='a resistance-pattern classifier, not just generic churn analytics', seams='(1) concrete behavioral signals for displacement / self-dramatization / victimhood / healing-trap, (2) compassionate interventions per pattern, and (3) operator visibility so the system can distinguish avoidance from ordinary failure', related='The important design constraint here is keeping the outputs intervention-oriented instead of turning the platform into a vague psych-labeling engine.'),
101: dict(core='a triage engine for excuses where the interesting part is the decision policy, not “AI” by itself', seams='(1) classify emergency vs legitimate-but-not-blocking vs rationalization, (2) always preserve a human-reviewable audit trail, and (3) attach the classifier to grace-day / extension / dispute flows instead of free-floating chat analysis', related='Because this one is labeled `api`, I would keep the first deliverable narrow: a provider-agnostic classification contract plus deterministic fallback behavior when the model is unavailable.'),
102: dict(core='an active substitution engine for craving moments, distinct from simple awareness prompts', seams='(1) a per-category BBO library, (2) user-personalized substitutions captured during onboarding, and (3) outcome tracking so the system learns which replacements actually defuse a craving', related='That separation from RAIN-style “notice the urge” flows is the core spec insight worth preserving.'),
103: dict(core='a structured psychoeducation track that teaches the mechanism of the product, not just product onboarding', seams='(1) a 7-day lesson cadence, (2) short reflections/quizzes tied to each concept, and (3) per-oath examples so the same curriculum works for recovery, fitness, and other categories', related='The valuable distillation here is to treat this as curriculum + progress tracking, not as a loose content library.'),
104: dict(core='a momentum-preservation mechanic for the day a contract succeeds', seams='(1) prefilled next-contract proposals, (2) an opt-out rollover window instead of opt-in reactivation, and (3) analytics that measure whether immediate re-commitment actually reduces post-win drift', related='That keeps it separate from graduation UX and from generic reminders; it is specifically about closing the “gap after victory” attack surface.'),
105: dict(core='a post-success prosocial loop, not a failure-charity mechanic', seams='(1) an optional give-forward split from returned stake, (2) a pool/accounting layer for new-user bonuses, and (3) visible-but-anonymized impact feedback so generosity produces retention rather than spectacle', related='The financially sensitive part is the ledgering and policy surface; the product idea is good, but it needs to be framed as voluntary pooled funding, not gamified guilt.'),
106: dict(core='quality assurance for auditors as humans, not only accuracy scoring after the fact', seams='(1) fatigue / cadence signals, (2) anti-bias prompts and cooldowns at review time, and (3) instrumentation that distinguishes inattentive speed from healthy decisiveness', related='That makes it an operational integrity issue for the Fury network, not just a wellness add-on.'),
107: dict(core='second-order safety around social broadcasting of failure', seams='(1) resilient copy around failure events, (2) contagion detection at the pod level, and (3) a regroup intervention when multiple failures cluster inside a short window', related='The useful distillation is that this is about network effects of messaging, not merely adding another notification preference.'),
108: dict(core='a provider-agnostic passive-proof framework rather than “just add Strava and Duolingo”', seams='(1) shared proof-ingest abstractions, (2) per-provider adapters with anomaly checks, and (3) fallback to manual attestation when an API is missing or revokes scope', related='Given the existing wearable work, this issue’s main value is expanding the verification model to non-health domains without hard-coding every provider into product logic.'),
109: dict(core='a measurement of reward devaluation in the old behavior, which is clinically different from measuring compliance with the new one', seams='(1) repeated subjective rating capture, (2) trend visualization over time, and (3) milestone logic when the old reward meaningfully collapses', related='The distinction from urge level / stress pulse / new-habit automaticity is the part worth preserving in the spec.'),
110: dict(core='a re-engagement/acquisition trigger keyed to life transitions, not just another retention nudge', seams='(1) transition detection, (2) a time-bounded low-friction offer, and (3) messaging that explicitly uses disrupted routines as the opening for a new contract', related='I would keep the first version self-report-first; the calendar/email ideas are interesting but create a lot of privacy and consent complexity early.'),
111: dict(core='machine-readable implementation-intention syntax that binds contracts to time and place', seams='(1) explicit time/location fields on oath creation, (2) reminder / geofence behavior downstream, and (3) verification rules that compare proof timing/location against the declared intention', related='That keeps it clearly distinct from habit stacking: this one is calendar-and-geometry, not anchor-behavior chaining.'),
112: dict(core='a bidirectional calibration loop whose job is to keep users inside the challenge sweet spot', seams='(1) a completion-rate feedback policy, (2) first-contract overcommitment warnings, and (3) upward as well as downward adjustment suggestions', related='The key distillation is that this should tune difficulty proactively rather than waiting for three failures and only shrinking the contract.'),
}

for num, cfg in brainstorm.items():
    comments[num] = (
        f"I read this against the current backlog as {cfg['core']}. The cleanest way to preserve the idea is to split it into {cfg['seams']}. "
        f"{cfg['related']}"
    )
    dispositions[num] = 'distilled'

comments[120] = (
    "I checked the live repo and remote state. The Ask Styx Pages workflow exists and has recent successful runs, but `gh variable list` shows no `ASK_STYX_WORKER_URL`, and `https://organvm.github.io/peer-audited--behavioral-blockchain/ask-styx/` is still 404 from a live fetch. That means this issue is still real: the worker deploy path may exist in source, but the end-to-end public surface is not yet verified live."
)
dispositions[120] = 'evolving'
comments[121] = (
    "I verified the wiring this issue depends on. GitHub Pages is enabled for the repo root (`https://organvm.github.io/peer-audited--behavioral-blockchain/`), but I do not see the required `ASK_STYX_WORKER_URL` repo variable, and the `/ask-styx/` path is not currently serving. The next concrete step here is to set the variable and prove the subpath deploy, not to treat the workflow file as sufficient evidence."
)
dispositions[121] = 'evolving'
comments[122] = (
    "I checked `src/ask-styx/worker/wrangler.toml` against the live Pages URL. `ALLOWED_ORIGIN` is still `https://organvm-iii-ergon.github.io`, while the repo’s Pages surface is `https://organvm.github.io/peer-audited--behavioral-blockchain/`, and the `/ask-styx/` route is not yet live. So this remains an active integration mismatch: the CORS origin should not be considered settled until it matches the actual deployed origin."
)
dispositions[122] = 'evolving'

issue_url = lambda n: f'{base}/issues/{n}'
commit_url = lambda sha: f'{base}/commit/{sha}'
pr_url = lambda n: f'{base}/pull/{n}'

comments[123] = (
    f"I checked the current repo state against this older blocker. `docs/FEATURE-BACKLOG.md` still names `F-MOBILE-01` as a stub, but `src/mobile/screens/ProofCaptureScreen.tsx` and `src/mobile/components/CameraModule.tsx` show there is now a real beta capture path that intentionally omits gallery import. The unresolved delta is the native anti-bypass enforcement layer and verifier-bound nonce path, which is captured more concretely in {issue_url(168)}."
)
dispositions[123] = f'superseded:{issue_url(168)}'
comments[124] = (
    "I do not see a native iOS HealthKit bridge in `src/mobile`; what exists today is the surrounding contract/compliance scaffolding, not the Swift-side read-only bridge itself. So this is still a real blocker, but the remaining work is sharply defined now: HealthKit permissions, native sample ingestion, and a trustworthy native→JS/API handoff rather than more backend speculation."
)
dispositions[124] = 'engaged'
comments[125] = (
    "Same conclusion on Android: I do not see a Kotlin/Health Connect bridge in the mobile workspace, only the surrounding product and verification architecture. This issue still matters, and the next useful move is a concrete native adapter with provenance metadata so the platform can distinguish device-sourced health data from manual self-report."
)
dispositions[125] = 'engaged'
comments[126] = (
    "I checked for actual Fitbit/WHOOP integration code and do not see provider adapters or auth flows in the repo yet. The important thing to preserve here is that this should hang off the broader passive-proof framework, not become a one-off vendor tangle: unified ingest contract first, provider-specific connectors second, partnership/vendor approval third."
)
dispositions[126] = 'engaged'
comments[127] = (
    f"The repo already has the local pieces: `src/mobile/services/NotificationService.ts` handles device registration flow and the backlog explicitly says local notifications are done while remote push is not. The unresolved work is the APNs/FCM credentialed server dispatch path, which is restated more precisely in {issue_url(176)}."
)
dispositions[127] = f'superseded:{issue_url(176)}'
comments[128] = (
    "I don’t see biometric proof-capture enforcement implemented in the mobile workspace. The current code shows camera-path work and proof plumbing, but not Face ID / voice-auth gating around submission. This stays open as a distinct trust-layer issue, because it is not the same problem as simply having a camera screen."
)
dispositions[128] = 'engaged'
comments[129] = (
    "I checked for Plaid client/provider code and don’t see a Link integration in the repo today. This is still a valid idea, but it should probably be treated as one passive-proof provider inside a broader verification abstraction (same family as issue #108), because the real complexity here is not UI wiring alone — it is consent boundaries, data minimization, and read-only financial habit semantics."
)
dispositions[129] = 'engaged'
comments[130] = (
    "I do not see EVM escrow contracts or on-chain deployment artifacts in the codebase; the existing money rails remain Stripe/FBO-centered. That means this issue is still in the research/design lane. The next useful distillation is to decide whether this is a true product path or a parallel experimental rail, because the trust, custody, dispute, and fee models diverge sharply once escrow leaves the current ledger."
)
dispositions[130] = 'engaged'
comments[131] = (
    "There is proof-oriented thinking in the repo (for example `src/shared/privacy/zk-exhaust.verifier.ts`), but I do not see a milestone-verification proving pipeline that would satisfy this issue. So the core ask is still alive. What would help next is pinning the proving target: which milestone facts must remain private, what verifier sees, and whether this belongs in the product path or only in a future cryptography lane."
)
dispositions[131] = 'engaged'
comments[132] = (
    f"This one has moved from pure concept into partial implementation. The repo already has compliance controllers, an identity-provider abstraction, and `KYC_ENFORCEMENT_ENABLED` policy logic under `src/api/src/modules/compliance/`, but the production-enforcement ticket is now framed more concretely in {issue_url(167)} around runtime thresholds, vendor hookup, and DPA/legal readiness."
)
dispositions[132] = f'superseded:{issue_url(167)}'
comments[133] = (
    f"I checked the settlement side and the repo already contains real settlement / reconciliation / Stripe-FBO codepaths plus a legal activation brief. The remaining gap here is external underwriting and live activation, which is captured more concretely by {issue_url(169)}. In other words: code no longer appears to be the bottleneck; the merchant/custody lane is."
)
dispositions[133] = f'superseded:{issue_url(169)}'
comments[134] = (
    "This aggregate blocker still describes reality pretty well. The backend and surrounding verification scaffolding exist, but the native truth surfaces are still the gap: the current mobile proof path is a transparent beta preview, not a production-native HealthKit + secure-camera bridge. I’d keep this open as the umbrella receipt for the mobile truth-gap even while narrower execution tickets move underneath it."
)
dispositions[134] = 'evolving'
comments[135] = (
    "I checked the desktop workspace and the forensic UI components are no longer imaginary — there are concrete panels under `src/desktop/src/components/`. What still makes this issue real is the operational/video lane around them: release-grade pipeline work, richer evidence handling, and the broader Phase Delta handoff items. So this is no longer a blank implementation gap, but it is not fully absorbed either."
)
dispositions[135] = 'engaged'
comments[136] = (
    f"There is now a substantive whitepaper artifact in `docs/legal/legal--skill-based-contest-whitepaper.md`, so the issue has evolved beyond “someone should write this.” The remaining unresolved part is the formal release gate and counsel sign-off path, which is spelled more concretely in {issue_url(177)}."
)
dispositions[136] = f'superseded:{issue_url(177)}'
comments[137] = (
    "I do not see an insurance procurement receipt in the repo, which is consistent with this being a true external dependency rather than an unbuilt code feature. This should stay alive as a business/legal lane until it has a carrier path, underwriting assumptions, and policy constraints written down; there is nothing here that code can fake into existence."
)
dispositions[137] = 'engaged'
comments[138] = (
    "This is correctly framed as a mixed policy + implementation issue. I do not see a finished neutral-notice/payment-routing solution in the repo, and the Apple-facing constraints are not something the current web shop code can solve by itself. The next productive step is to split legal review, storefront UX, and region-routing behavior into separately testable receipts instead of leaving them braided together as one vague blocker."
)
dispositions[138] = 'engaged'
comments[139] = (
    "I don’t see any executable partnership-program surface in the repo yet; this remains strategic/business development work rather than dormant code. The part worth preserving is the spec kernel: what does 'Styx-certified' actually certify — provenance, secure capture, continuous attestation, or something else? Without that definition, the partnership conversation stays too mushy to operationalize."
)
dispositions[139] = 'engaged'
comments[140] = (
    "I do not see a concrete insurance-partnership artifact for this lane, so this is still a live business-development item. The useful next distillation would be to specify whether the product wants distribution, underwriting, wellness-program embedding, or claims-data partnership here, because those are very different outbound motions even if they all sit under 'insurance'."
)
dispositions[140] = 'engaged'
comments[141] = (
    "I found explicit references to this blocker in the founder-ops / release planning docs, and I don’t see any in-repo evidence that App Store Connect / TestFlight control has been fully provisioned. That means the issue is still real, and it is correctly human/ops-gated: the repo can prepare the binary and the runbooks, but it cannot fabricate Apple account control as proof."
)
dispositions[141] = 'engaged'
comments[142] = (
    "I do not see C2PA/TSA integration artifacts in the product code, only planning and backlog references. This should stay open as a future cryptography/provenance lane. The important design question is whether the platform needs full content provenance for every proof, or only for specific high-risk proof classes where tamper cost justifies the signing/timestamp infrastructure."
)
dispositions[142] = 'engaged'
comments[143] = (
    "I don’t see an app-attestation SDK adapter or procurement receipt in the repo, which matches the issue’s framing as an external dependency. This remains a real mobile trust-layer gap. The next useful move is to turn the SDK choice into an evaluation matrix (device coverage, offline behavior, jailbreak/root signal quality, pricing, privacy) rather than keep it at the label level."
)
dispositions[143] = 'engaged'
comments[144] = (
    "The repo contains proof/privacy thinking, but not a ZK proving engine that would satisfy this broader digital-exhaust privacy layer. So this remains an active future-facing issue. The kernel to preserve is that privacy here is not only about hiding content; it is about proving limited facts from sensitive exhaust without centralizing the raw artifact."
)
dispositions[144] = 'engaged'
comments[146] = (
    "I can see moderation obligations discussed in research/planning surfaces, but I do not see a finished App Store UGC moderation packet or submission-ready policy bundle. That keeps this issue live. The right shape is a concrete packet: policy, escalation path, reporting flow, reviewer evidence, and whatever in-product moderation controls Apple will expect to see demonstrated."
)
dispositions[146] = 'engaged'
comments[147] = (
    "I do not see stablecoin staking activated in runtime code, which makes this correctly a policy-first issue rather than a hidden implementation bug. The unresolved work is the external pathway: regulatory classification, banking/vendor willingness, settlement design, and jurisdiction scope. That should stay explicit instead of being treated as something engineering can silently unblock alone."
)
dispositions[147] = 'engaged'
comments[148] = (
    "I agree this should remain open. I do not see a single counsel-reviewed cross-jurisdiction consent matrix artifact in the repo yet, and that absence matters because consent language here varies with data type, region, and product mode. The next useful receipt is a matrix with concrete rows/columns, not just a generic 'needs legal review' note."
)
dispositions[148] = 'engaged'

competitors = {
149: ('stickK', 'docs/research/research--competitor-stickk-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
150: ('Beeminder', 'docs/research/research--competitor-beeminder-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
151: ('Forfeit', 'docs/research/research--competitor-forfeit-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
152: ('HealthyWage / DietBet / StepBet', 'docs/research/research--competitor-waybetter-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
153: ('Habitica', 'docs/research/research--competitor-habitica-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
154: ('Accountable AI', 'docs/research/research--competitor-accountable-ai-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
155: ('the relationship-recovery niche', 'docs/research/research--competitor-no-contact-niche-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
156: ('Pavlok', 'docs/research/research--competitor-pavlok-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
157: ('TaskRatchet', 'docs/research/research--competitor-taskratchet-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
158: ('Focusmate', 'docs/research/research--competitor-focusmate-deep-dive.md', '7b6bfc52c08c8689e4a97ecf91923ce1b3b52ee4'),
}
for num, (name, path, sha) in competitors.items():
    url = commit_url(sha)
    comments[num] = (
        f"I checked this one against the repo and the requested teardown already exists as `{path}`. The raw research ask for {name} has been carried into the docs corpus, so the remaining work is synthesis/consumption, not re-opening the original deep-dive request. Keeping the issue open for lineage makes sense, but the specific deliverable is already covered by {url}."
    )
    dispositions[num] = f'superseded:{url}'

comments[159] = (
    f"I verified this one against current code and GitHub history. The Ask Styx worker now declares a `RATE_LIMIT_KV` binding in `src/ask-styx/worker/wrangler.toml`, and the concrete fix landed in PR {pr_url(640)}. So the original vulnerability was real, but the 'replace per-isolate Map with edge-consistent storage' ask is now covered by the merged fix."
)
dispositions[159] = f'superseded:{pr_url(640)}'
comments[160] = (
    "I searched the repo for executable load-test harnesses and do not see k6/artillery scripts yet, but there *is* a load-test strategy artifact in `docs/departments/eng/artifacts/load-test-report.md` / `docs/architecture/load-test-report.md`. That means the problem has been analyzed but not yet operationalized. The next step is to convert the plan into runnable scenarios plus dated result appendices, especially for Fury queue throughput and SSE fan-out."
)
dispositions[160] = 'evolving'
comments[163] = (
    "I don’t see a centralized failure-copy contract yet. There are individual notification strings in the codebase (for example `src/api/src/modules/notifications/notifications.service.ts`), but not a shared, cross-surface standard for emotionally safe stake-failure messaging. I would distill this into a copy matrix keyed by surface (private vs public), contract class (recovery vs general), and moment (warning / failure / post-failure recovery path)."
)
dispositions[163] = 'distilled'
comments[164] = (
    "I verified the structural complaint: `render.yaml` and `.config/docker/docker-compose.yml` still point at a single Redis service, so queueing, realtime, and cache concerns remain coupled to one instance. This is therefore still a real resilience issue, not a stale audit note. The next useful refinement is to decide whether the answer is HA Redis, role separation, or graceful degradation rules when Redis is absent."
)
dispositions[164] = 'engaged'
comments[165] = (
    "I checked the three AI surfaces this issue names. The repo is configurable — Ask Styx already exposes `LLM_BASE_URL` / `LLM_MODEL`, and the docs mention OpenAI-compatible backends — but I do not see an automatic fallback policy spanning Grill-me, ELI5, and Ask Styx. So the issue remains: configurability exists, resilience orchestration does not."
)
dispositions[165] = 'engaged'
comments[166] = (
    "I found review expectations scattered across the repo (`docs/MANIFEST.md`, `docs/departments/eng/REGE.md`, audit notes), but not a crisp protocol that guarantees a second set of human eyes on the highest-risk lanes. So the bus-factor concern is still substantive. The next useful move is to turn 'review culture' into an executable rule: which paths require independent review, what counts as approval, and how that proof is recorded."
)
dispositions[166] = 'engaged'
comments[167] = (
    "This ticket sits on top of code that already exists: there are compliance controllers, an identity-provider abstraction, and explicit `KYC_ENFORCEMENT_ENABLED` policy logic in `src/api/src/modules/compliance/`. What is still unresolved is the production flip: vendor-backed verification at the right thresholds plus the legal/DPA conditions for enabling it outside mock mode."
)
dispositions[167] = 'evolving'
comments[168] = (
    "I checked the mobile surface and the repo is in a partial state: `src/mobile/screens/ProofCaptureScreen.tsx` and related proof-media utilities show a live-capture oriented beta flow, but the native module that makes gallery bypass impossible is still missing. So this remains the right execution ticket for turning the current preview path into a real nonce-bound iOS camera truth surface."
)
dispositions[168] = 'evolving'
comments[169] = (
    "Production settlement is no longer hypothetical in the codebase: there are payment, settlement-worker, and reconciliation paths already present. What keeps this ticket open is the last mile — live FBO routing, merchant underwriting, and custody-governed activation. In other words, the repo is ready to talk to this issue; the external finance/compliance lane is the remaining gate."
)
dispositions[169] = 'evolving'
comments[170] = (
    "I checked for concrete implementation seams and found real timelock endpoints in `src/api/src/modules/contracts/contracts.controller.ts` (`status`, `queue`, `cancel` for intentional recovery breaks). That suggests this ticket is partially absorbed already. What I still would want proven end-to-end is the full danger-zone lockdown behavior from policy detection through UI and scheduler enforcement, not just the existence of timelock endpoints."
)
dispositions[170] = 'evolving'
comments[171] = (
    f"The core weekend-multiplier mechanism is already in the codebase: `src/shared/behavioral-physics/volatility.engine.ts`, `src/api/services/health/aegis.service.ts`, `src/api/src/modules/contracts/contracts.service.ts`, and related tests all implement Friday/Saturday risk amplification. So the original 'build the multiplier engine' ask is now covered by {commit_url('4ce722fa272909fb9bedc8b41b3a9531f17cbb24')}; if this issue stays open, it should be about tuning/presentation, not first implementation."
)
dispositions[171] = f"superseded:{commit_url('4ce722fa272909fb9bedc8b41b3a9531f17cbb24')}"
comments[172] = (
    f"I checked this against runtime routes and tests. The repo now has accountability-partner invite / accept / co-sign / veto / status endpoints in `contracts.controller.ts` plus behavior coverage in `contracts.full-breath.spec.ts`. That means the original 'complete the lifecycle' request is materially covered by {commit_url('8a95c9ee735886082da25dae7ced7257086a2405')}, even if the broader product still has future UX refinements."
)
dispositions[172] = f"superseded:{commit_url('8a95c9ee735886082da25dae7ced7257086a2405')}"
comments[173] = (
    "I found one half of this issue in code and the other half missing. Downscale behavior is real in both `src/api/src/modules/contracts/contracts.service.ts` and `src/web/app/contracts/new/page.tsx`, but I do not see an implemented 'endowed progress' / artificial-momentum surface yet. So this should stay open as a partial-completion ticket rather than be treated as all-or-nothing."
)
dispositions[173] = 'evolving'
comments[174] = (
    "I searched for `Identity Oath` / identity-based onboarding and only found planning references, not a finished onboarding flow in product code. So this is still a live product ticket. The useful boundary to keep is that this is not generic marketing copy; it is a specific onboarding ritual/spec that needs form state, persistence, and likely downstream reminder surfaces."
)
dispositions[174] = 'evolving'
comments[175] = (
    f"There is already substantive implementation here: `dashboard.controller.ts` exposes goal-gradient telemetry, the API exposes leaderboard endpoints/SSE, and the Tavern UI renders leaderboard state. That means the initial 'build live leaderboard + goal-gradient plumbing' ask is covered by {commit_url('a2281faf78a215c4a76c1e99d6770a32c73b447c')}; remaining work, if any, is iteration on presentation rather than absent foundation."
)
dispositions[175] = f"superseded:{commit_url('a2281faf78a215c4a76c1e99d6770a32c73b447c')}"
comments[176] = (
    "The repo has the prep work but not the final pipeline. `src/mobile/services/NotificationService.ts` handles token registration and the planning docs explicitly say local notifications are done while APNs/FCM-backed remote dispatch is not. So this is still the right ticket for the credentialed, server-routed push path."
)
dispositions[176] = 'evolving'
comments[177] = (
    "This ticket is in the right shape. There is already a substantial whitepaper artifact in `docs/legal/legal--skill-based-contest-whitepaper.md`; what remains is the actual release gate around signed counsel approval, versioning, and the conditions under which launch surfaces are allowed to claim readiness. That keeps this as active governance infrastructure, not just more prose-writing."
)
dispositions[177] = 'evolving'
comments[178] = (
    "I checked current code before writing this off. There is already a `BetaReadinessService` under `src/api/src/modules/ops/beta-readiness.service.ts`, so the repo has some executable readiness logic. But it is not yet the full contract/service surface described here (shared interface, broader gate coverage, formal exports). I’d keep this open as 'promote the existing service into a first-class contract' rather than re-describe the idea from scratch."
)
dispositions[178] = 'engaged'
comments[179] = (
    "I looked for actual `scripts/doc-intelligence/*` automation and do not see it yet. What *does* exist is a large amount of manual triage/planning output, including `docs/triage.json`. So the issue remains valid: the intellectual work happened, but the reproducible ingest/parse/drift-check pipeline has not obviously been turned into tooling."
)
dispositions[179] = 'engaged'
comments[180] = (
    f"This issue’s outcome appears to have landed as artifacts already: `docs/planning/planning--research-ticket-pack--2026-03-04.md` and its JSON companion are exactly the kind of research-to-ticket conversion product the issue describes. So the raw conversion ask is now covered by {commit_url('98df4902af75fafbe33b29aa5c7fce4f97b429cf')}."
)
dispositions[180] = f"superseded:{commit_url('98df4902af75fafbe33b29aa5c7fce4f97b429cf')}"
comments[181] = (
    "I found the narrative source material (`docs/planning/planning--state-of-the-union--2026-03-04.md` and the definitive roadmap), but I do not see the investor-facing output package the issue calls for (`docs/investor/*`, risk matrix, resource-plan deck). So this is still real. The useful distinction is that the content substrate exists; what’s missing is the investor-format transformation."
)
dispositions[181] = 'engaged'
comments[182] = (
    f"I checked the desktop workspace and the core forensic panels named here are present: `DisputeTimeline`, `AuditTrailViewer`, `EvidenceComparator`, `LedgerInspector`, `MacroReview`, and `ExilePanel` all exist under `src/desktop/src/components/`. So the original 'build the forensic panels' request is already covered by {commit_url('81bb3702edc7e0f3be9ab263a612eb417ba3f308')}; any remaining work is refinement/integration, not panel absence."
)
dispositions[182] = f"superseded:{commit_url('81bb3702edc7e0f3be9ab263a612eb417ba3f308')}"
comments[183] = (
    f"There is now at least one strong synthesis artifact in the repo — `docs/doc--evaluation-to-growth-review.md` — that consolidates E2G findings into an implementation-oriented report. That makes the original 'produce an authoritative mapping report' ask materially covered by {commit_url('5cb28f20436e56b480092a08fefd39099bcd2d9e')}, even if future passes keep refining it."
)
dispositions[183] = f"superseded:{commit_url('5cb28f20436e56b480092a08fefd39099bcd2d9e')}"
comments[186] = (
    "The dissertation lane is no longer empty: `docs/thesis/` exists, Chapter 1 is drafted, notation and bibliography are present, and at least two theorem proofs have been formalized. But the issue’s own scope is much larger (full chapter set, nine proofs, 45k words, defense-ready structure). So this remains an active epic rather than a dormant placeholder."
)
dispositions[186] = 'evolving'
comments[188] = (
    "I checked for the promised final business/ops report path and did not find `docs/planning/planning--business-ops-gap-analysis.md`. I *did* find partial material (for example `docs/thesis/notes/gap-analysis.md` plus the broader planning/research corpus). So this epic still matters: inputs exist, but the named business/ops synthesis receipt is not yet clearly landed where the issue says it should."
)
dispositions[188] = 'evolving'
comments[189] = (
    f"This epic has already produced a durable output: `docs/planning/planning--stub-inventory.md` is present and contains the multi-phase scan findings the sequence was meant to produce. So the broad 'run the stub/placeholder inventory sequence' ask is covered by {commit_url('265f5f183fa09f3b0b48322e54bbe0f855b41579')}."
)
dispositions[189] = f"superseded:{commit_url('265f5f183fa09f3b0b48322e54bbe0f855b41579')}"
comments[190] = (
    "I do not yet see a single published architecture-completeness-matrix report artifact, even though the repo contains strong review material and the triage ledger references downstream publishing work. So I would keep this epic open. The useful next move is to turn the architecture audit into an explicit matrix artifact with scoring rules, not leave it diffused across notes and review docs."
)
dispositions[190] = 'engaged'
comments[191] = (
    "This one claims 90% complete, and I can see neighboring synthesis artifacts, but I did not find an unmistakable final 'cross-tool comprehensive audit summary' deliverable with that exact identity. So I would keep it open as an integration receipt rather than assume nearby reports already satisfy it. The next helpful step is to link or mint the canonical summary artifact explicitly."
)
dispositions[191] = 'engaged'
comments[192] = (
    "This issue has partially landed in reality: the repo now self-identifies Styx as `flagship` / `GRADUATED` in the generated context blocks, and governance files like `seed.yaml` exist. What I cannot prove from this repo alone is the external registry receipt that the issue originally mentioned. So I’d keep this open as a governance reconciliation thread: local promotion looks real, cross-system registration proof should be explicit."
)
dispositions[192] = 'engaged'
for num, path, sha, note in [
    (193, 'docs/thesis/00-preliminary-pages.md', '473089380ede8e35e9fa5b6460373709fa36982d', 'The `docs/thesis/` scaffold and preliminary pages are present.'),
    (194, 'docs/thesis/thesis.bib', '473089380ede8e35e9fa5b6460373709fa36982d', 'A real bibliography file now exists.'),
    (195, 'docs/thesis/notation.md', '473089380ede8e35e9fa5b6460373709fa36982d', 'A notation guide is already checked in.'),
    (196, 'docs/thesis/notes/reading-notes--category-1-behavioral-economics.md', '473089380ede8e35e9fa5b6460373709fa36982d', 'Reading-note templates/instances now exist under `docs/thesis/notes/`.'),
    (197, 'docs/thesis/notes/literature-matrix.md', '473089380ede8e35e9fa5b6460373709fa36982d', 'The chapter/source mapping work now has a durable artifact.'),
    (198, 'docs/thesis/01-introduction.md', '473089380ede8e35e9fa5b6460373709fa36982d', 'Chapter 1 is already drafted in the thesis tree.'),
]:
    url = commit_url(sha)
    comments[num] = f"{note} I checked the repo directly and the requested deliverable is already present at `{path}`. So the specific task tracked by this issue is now covered by {url}."
    dispositions[num] = f'superseded:{url}'
comments[199] = (
    "This subtask is only partially absorbed. The repo already contains theorem files such as `docs/thesis/proofs/theorem-01-ledger-balance-invariant.md` and `theorem-08-anti-isolation-guarantee.md`, so proof formalization has started. But the issue promised nine theorem proofs, and I cannot find all nine in the thesis tree yet."
)
dispositions[199] = 'engaged'
comments[200] = (
    "I do not see a full thesis production pipeline (Pandoc/LaTeX build, citation validator, word-count tooling) checked in yet. The thesis corpus exists, but the build/release machinery this issue asks for is not obvious in the repo. So this remains a real operations/documentation task, not a duplicate of the thesis content work."
)
dispositions[200] = 'engaged'
comments[206] = (
    "The architecture appears to have shifted since this was filed: Ask Styx now lives as a workspace inside this monorepo (`src/ask-styx`) rather than as a separate repo needing its own fresh governance bootstrap. The underlying need is still valid — make sure the surface is covered by ORGAN-III governance metadata — but the clean restatement today is monorepo inheritance plus any workspace-local docs, not 'create standalone repo boilerplate'."
)
dispositions[206] = 'distilled'
comments[208] = (
    "I verified the two halves of this issue separately. The build/test side appears wired (the Ask Styx workflow runs successfully), but the `ALLOWED_ORIGIN` side is still not reconciled: `wrangler.toml` points at `organvm-iii-ergon.github.io` while the repo’s live Pages root is `organvm.github.io/peer-audited--behavioral-blockchain/`. So this is still an active integration ticket, not a stale chore."
)
dispositions[208] = 'evolving'
comments[209] = (
    "I checked the live surface rather than trusting the plan text. Today Ask Styx lives inside this monorepo, not a fresh standalone repo, and the public `/ask-styx/` route is still 404 from a live fetch. So the intent of this issue — prove the deployed surface is truly live — remains valid even though the repo-topology assumption in the original wording has changed."
)
dispositions[209] = 'engaged'
phase_comments = {
210: 'I can see the strategic/planning source material this phase is supposed to consume, but I do not yet see a dedicated phase receipt proving the readout was folded into the final business/ops synthesis. So I would keep this open until the phase is explicitly deposited into the parent report rather than inferred from nearby docs.',
211: 'The market/research inputs are definitely present in the repo, but the question is whether this phase has emitted a durable synthesis receipt. I don’t see that receipt clearly linked yet, so the phase still deserves explicit engagement instead of being silently assumed complete.',
212: 'Infrastructure/ops inputs like `render.yaml`, env examples, and container config exist, but I did not find a clean phase-output artifact that says this audit pass was completed and absorbed. That means the reading surface exists while the accountability receipt is still fuzzy.',
213: 'Operational-detail search material exists across monitoring / ops / support style docs, but I do not see a dedicated result packet that closes this phase on its own terms. I would keep it open until the parent audit can point back to an explicit phase output.',
214: 'Marketing/content artifacts are present, but this phase still needs a visible synthesis receipt rather than silent background consumption. The issue is valuable as the pointer to that specific audit slice.',
215: 'Growth/retention evidence exists in the repo, but I did not find a crisp phase closeout artifact tying those findings into the parent gap analysis. So this still warrants an explicit accounting pass.',
216: 'Business-model / metrics materials exist, but the final parent report path is still not obvious, so I would not treat this phase as self-evidently done. It still needs a durable sink for its findings.'
}
for num, body in phase_comments.items():
    comments[num] = body
    dispositions[num] = 'engaged'
comments[217] = (
    "I went looking for the exact deliverable named here and did not find `docs/planning/planning--business-ops-gap-analysis.md`. There *is* related material (`docs/thesis/notes/gap-analysis.md` and broader planning docs), which tells me the thinking happened. But the promised named report is still not clearly present, so this should remain an active synthesis issue."
)
dispositions[217] = 'engaged'
for num in [218,219,220,221,222,223]:
    url = commit_url('265f5f183fa09f3b0b48322e54bbe0f855b41579')
    comments[num] = (
        f"I checked this subphase against the repo and its findings appear to be absorbed into `docs/planning/planning--stub-inventory.md`, which records the scan scope, findings, and command evidence. So the standalone sweep requested here is now covered by {url}."
    )
    dispositions[num] = f'superseded:{url}'
comments[224] = (
    f"The named deliverable now exists: `docs/planning/planning--stub-inventory.md` is present and reads like the receipt this issue asked for, including scope, findings, and command evidence. So this issue’s requested artifact is covered by {commit_url('265f5f183fa09f3b0b48322e54bbe0f855b41579')}."
)
dispositions[224] = f"superseded:{commit_url('265f5f183fa09f3b0b48322e54bbe0f855b41579')}"
comments[225] = (
    "I did not find a standalone service-layer deep-dive report with this issue’s exact identity, even though the repo contains service-heavy review material and later architecture-audit references. So I would keep this open as a precise audit receipt: the service layer deserves its own explicit findings packet rather than being assumed from broader reviews."
)
dispositions[225] = 'engaged'

issues = [99,100,101,102,103,104,105,106,107,108,109,110,111,112,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,186,188,189,190,191,192,193,194,195,196,197,198,199,200,206,208,209,210,211,212,213,214,215,216,217,218,219,220,221,222,223,224,225]
missing = [n for n in issues if n not in comments]
if missing:
    raise SystemExit(f'missing comments for {missing}')
Path = __import__('pathlib').Path
Path('/Users/4jp/Workspace/limen/peer_audited_comment_map.json').write_text(json.dumps({str(k): {'body': comments[k], 'disposition': dispositions[k]} for k in issues}, indent=2))
print('wrote', len(issues), 'comments')
