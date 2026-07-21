# Original User Request

## 2026-07-21T19:46:01Z

Initialize and build the `surface-engine` monorepo, a unified Public Audience Surfaces suite containing five interactive visual applications (Tryptich, Narcissus, Ballerina, Hospes, and Live Camera) that interface with the backend Content Engine via webhooks.

Working directory: /Users/4jp/Workspace/limen/surface-engine
Integrity mode: benchmark

## Requirements

### R1. Scaffolding the Surface Engine Monorepo
Initialize a new monorepo using Turborepo and Next.js. This will serve as the foundation for the visual application suite.

### R2. Core Visual Applications
Create the scaffolding and basic placeholder structure for the five core visual applications within the monorepo: `tryptich` (React canvas carousel), `narcissus` (WebGL mirror), `ballerina` (kinetic typography), `hospes` (concierge interface), and `live-camera` (livestream broadcast framework). 

### R3. Webhook Integration Module
Create a shared package within the monorepo designed to receive webhook payloads from the backend Content Engine.

## Acceptance Criteria

### Build and Structure
- [ ] Running `npm run build` at the root of the monorepo successfully builds all applications and packages without errors.
- [ ] The directories `apps/tryptich`, `apps/narcissus`, `apps/ballerina`, `apps/hospes`, and `apps/live-camera` must exist and contain valid Next.js applications.
- [ ] A shared package (e.g., `packages/webhook-receiver`) must exist and be importable by the apps.
