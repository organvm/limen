# Execution Plan: surface-engine Monorepo

## Overview
Scaffold and build `surface-engine` monorepo using Turborepo and Next.js, with 5 visual applications and 1 shared webhook receiver package.

## Tracks & Milestones

### E2E Testing Track (Parallel)
- Create `TEST_INFRA.md` defining requirements-driven opaque-box E2E testing.
- Scaffold automated E2E test harness verifying root build, folder structure, app validity, and package imports.
- Publish `TEST_READY.md`.

### Implementation Track
- **M1: Monorepo Scaffolding & Webhook Receiver**
  - Root `package.json` with Turborepo, script `build`, workspace configuration.
  - Root `turbo.json` and TypeScript configuration.
  - `packages/webhook-receiver`: package setup, types, handler, exports, build setup.
- **M2: Core Visual Apps Batch A (`tryptich`, `narcissus`, `ballerina`)**
  - Scaffold valid Next.js app in `apps/tryptich` (React canvas carousel) importing `webhook-receiver`.
  - Scaffold valid Next.js app in `apps/narcissus` (WebGL mirror) importing `webhook-receiver`.
  - Scaffold valid Next.js app in `apps/ballerina` (kinetic typography) importing `webhook-receiver`.
- **M3: Core Visual Apps Batch B (`hospes`, `live-camera`)**
  - Scaffold valid Next.js app in `apps/hospes` (concierge interface) importing `webhook-receiver`.
  - Scaffold valid Next.js app in `apps/live-camera` (livestream broadcast framework) importing `webhook-receiver`.
- **M4: Final Integration & E2E Validation**
  - Run full E2E test suite.
  - Verify root `npm run build` succeeds without errors.
  - Perform Forensic Audit and Challenger verification.
