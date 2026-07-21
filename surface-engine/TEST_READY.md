# E2E Test Suite Readiness (`TEST_READY.md`)

## Status
- **Test Suite Status**: Ready & Configured
- **Test Runner Location**: `tests/e2e-runner.js`
- **Execution Command**: `node tests/e2e-runner.js`

---

## E2E Test Suite Overview
The end-to-end (E2E) testing framework for `surface-engine` validates all 5 visual applications (`tryptich`, `narcissus`, `ballerina`, `hospes`, `live-camera`) and the shared `webhook-receiver` package.

---

## Test Coverage Checklist

### Tier 1: Feature Coverage (Existence Check)
- [x] `apps/tryptich` directory existence check
- [x] `apps/narcissus` directory existence check
- [x] `apps/ballerina` directory existence check
- [x] `apps/hospes` directory existence check
- [x] `apps/live-camera` directory existence check
- [x] `packages/webhook-receiver` directory existence check

### Tier 2: Boundary Verification (Config & Exports Check)
- [x] `apps/tryptich` package.json & Next.js config verification
- [x] `apps/narcissus` package.json & Next.js config verification
- [x] `apps/ballerina` package.json & Next.js config verification
- [x] `apps/hospes` package.json & Next.js config verification
- [x] `apps/live-camera` package.json & Next.js config verification
- [x] `packages/webhook-receiver` package.json & entry points / exports verification

### Tier 3: Cross-Feature Integration (Webhook Receiver Linkage)
- [x] `apps/tryptich` dependency & code import verification
- [x] `apps/narcissus` dependency & code import verification
- [x] `apps/ballerina` dependency & code import verification
- [x] `apps/hospes` dependency & code import verification
- [x] `apps/live-camera` dependency & code import verification

### Tier 4: Application Build & Execution
- [x] Workspace root `package.json` build script presence check
- [x] Workspace root `npm run build` execution & zero exit-code assertion

---

## Execution Instructions

```bash
# Run test suite directly with Node.js
node tests/e2e-runner.js
```

---

## CI / Baseline Verification Method
1. Run `node tests/e2e-runner.js`.
2. Ensure exit code is `0` and all 4 tiers report `✅ PASS`.
3. Check generated handoff logs at `.agents/e2e_worker/handoff.md` for baseline metrics.
