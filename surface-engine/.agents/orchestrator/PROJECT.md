# Project: surface-engine

## Architecture
Monorepo using Turborepo and Next.js.
- `apps/tryptich`: React canvas carousel Next.js app
- `apps/narcissus`: WebGL mirror Next.js app
- `apps/ballerina`: Kinetic typography Next.js app
- `apps/hospes`: Concierge interface Next.js app
- `apps/live-camera`: Livestream broadcast framework Next.js app
- `packages/webhook-receiver`: Shared package for receiving Content Engine webhook payloads, exported and imported by apps.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Monorepo Scaffolding & Webhook Receiver | Root setup (package.json, turbo.json, tsconfig) + `packages/webhook-receiver` | none | DONE |
| 2 | Core Visual Apps Batch A | Scaffold `apps/tryptich`, `apps/narcissus`, `apps/ballerina` importing webhook-receiver | M1 | DONE |
| 3 | Core Visual Apps Batch B | Scaffold `apps/hospes`, `apps/live-camera` importing webhook-receiver | M1 | DONE |
| 4 | Final Integration & E2E Validation | Pass 100% E2E tests, root build verification (`npm run build`) | M2, M3 | DONE |

## Interface Contracts
### `packages/webhook-receiver` ↔ `apps/*`
- Exports:
  - Webhook payload types (`ContentWebhookPayload`, `WebhookEvent`, etc.)
  - Webhook receiver handler / parser functions (`parseWebhookPayload`, `createWebhookHandler`, etc.)
- Package name: `@surface-engine/webhook-receiver`

## Code Layout
```
/Users/4jp/Workspace/limen/surface-engine/
├── package.json
├── turbo.json
├── tsconfig.json
├── pnpm-workspace.yaml
├── .gitignore
├── TEST_INFRA.md
├── TEST_READY.md
├── tests/
│   └── e2e-runner.js
├── apps/
│   ├── tryptich/
│   │   ├── package.json
│   │   ├── next.config.mjs
│   │   ├── tsconfig.json
│   │   └── app/
│   │       ├── layout.tsx
│   │       ├── page.tsx
│   │       └── api/webhook/route.ts
│   ├── narcissus/
│   │   ├── package.json
│   │   ├── next.config.mjs
│   │   ├── tsconfig.json
│   │   └── app/
│   │       ├── layout.tsx
│   │       ├── page.tsx
│   │       └── api/webhook/route.ts
│   ├── ballerina/
│   │   ├── package.json
│   │   ├── next.config.mjs
│   │   ├── tsconfig.json
│   │   └── app/
│   │       ├── layout.tsx
│   │       ├── page.tsx
│   │       └── api/webhook/route.ts
│   ├── hospes/
│   │   ├── package.json
│   │   ├── next.config.mjs
│   │   ├── tsconfig.json
│   │   └── app/
│   │       ├── layout.tsx
│   │       ├── page.tsx
│   │       └── api/webhook/route.ts
│   └── live-camera/
│       ├── package.json
│       ├── next.config.mjs
│       ├── tsconfig.json
│       └── app/
│           ├── layout.tsx
│           ├── page.tsx
│           └── api/webhook/route.ts
└── packages/
    └── webhook-receiver/
        ├── package.json
        ├── tsconfig.json
        ├── test-runner-unit.js
        ├── test-runner-handler.js
        └── src/
            ├── index.ts
            ├── types.ts
            ├── verify.ts
            ├── parser.ts
            └── handler.ts
```
