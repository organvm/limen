# E2E Test Infrastructure & Methodology (`TEST_INFRA.md`)

## 1. Overview
The `surface-engine` monorepo houses a suite of five interactive visual applications (`tryptich`, `narcissus`, `ballerina`, `hospes`, and `live-camera`) and a shared backend integration package (`webhook-receiver`). 

This document defines the end-to-end (E2E) testing framework, verification methodology, and automated test runner designed to validate system structural integrity, package boundaries, cross-feature integration, and workspace build readiness.

---

## 2. Test Tier Architecture

The test suite is structured into four distinct, progressive verification tiers:

```
+-------------------------------------------------------------------+
|                     TIER 4: Application Build                     |
|           Monorepo root `npm run build` execution check           |
+-------------------------------------------------------------------+
                                  ^
                                  |
+-------------------------------------------------------------------+
|                 TIER 3: Cross-Feature Integration                 |
|  Dependency & import usage of `webhook-receiver` in 5 applications|
+-------------------------------------------------------------------+
                                  ^
                                  |
+-------------------------------------------------------------------+
|                    TIER 2: Boundary Verification                  |
| Valid Next.js app configs, package.json schemas, package exports  |
+-------------------------------------------------------------------+
                                  ^
                                  |
+-------------------------------------------------------------------+
|                    TIER 1: Feature Coverage                       |
| Existence of 5 Next.js apps & 1 shared webhook-receiver package   |
+-------------------------------------------------------------------+
```

### Tier 1: Feature Coverage (Structural Existence)
- **Objective**: Ensure all required sub-projects exist in the workspace filesystem.
- **Targets**:
  - `apps/tryptich` — React canvas carousel application
  - `apps/narcissus` — WebGL mirror application
  - `apps/ballerina` — Kinetic typography application
  - `apps/hospes` — Concierge interface application
  - `apps/live-camera` — Livestream broadcast framework application
  - `packages/webhook-receiver` — Shared webhook receiver package

### Tier 2: Boundary Verification (Configuration & Contract Integrity)
- **Objective**: Validate configuration integrity and package export specifications.
- **Checks**:
  - **App Boundaries**: Valid `package.json` in each app directory containing valid JSON, required metadata, and Next.js configuration (`next.config.js` / `next.config.mjs` / `next.config.ts` or standard Next.js directory structure).
  - **Package Boundaries**: Valid `package.json` in `packages/webhook-receiver` with configured `exports` or entry point references, and verification that referenced entry points actually exist on disk.

### Tier 3: Cross-Feature Integration (Dependency & Code Usage)
- **Objective**: Verify that the shared `webhook-receiver` package is wired into all 5 applications.
- **Checks**:
  - **Manifest Linkage**: Verification that `webhook-receiver` (or `@surface-engine/webhook-receiver`) is declared as a dependency in `package.json` for all 5 visual applications.
  - **Codebase Integration**: Verification that source code within each application (`apps/*/app/`, `apps/*/src/`, etc.) imports and utilizes exported functionality from the `webhook-receiver` package.

### Tier 4: Application Build & Execution (Full Monorepo Verification)
- **Objective**: Execute full monorepo compilation to guarantee production build readiness.
- **Checks**:
  - Execution of `npm run build` at workspace root.
  - Capture and analysis of process exit status (must be `0`) and build stdout/stderr output.

---

## 3. Test Runner Specification (`tests/e2e-runner.js`)

The automated runner is written in Node.js and located at `tests/e2e-runner.js`.

### Key Capabilities
1. **Dynamic Workspace Inspection**: Uses standard `fs` and `path` modules to inspect workspace structure dynamically without hardcoded outputs.
2. **AST / Import Scanning**: Recursively scans application source directories for module import patterns.
3. **Subprocess Build Execution**: Invokes workspace root build tasks programmatically and captures real exit codes and logs.
4. **Structured Terminal Output**: Formats results per tier with distinct pass/fail indicators, detailed failure diagnostics, and summary statistics.
5. **Exit Code Compliance**: Exits with code `0` on 100% test tier pass, or code `1` if any check fails.

---

## 4. Execution & Usage

To execute the test suite manually or in CI:

```bash
# Run via Node.js
node tests/e2e-runner.js

# Or via npm script (if configured)
npm run test:e2e
```

---

## 5. Verification & Baseline Protocol

When executed:
- Baseline passes prove system integrity.
- Failures isolate exact gaps (missing directories, malformed configurations, missing imports, or build compilation errors).
