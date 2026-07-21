# Handoff Report — M1 Architecture Review: `@surface-engine/webhook-receiver`

**Reviewer**: M1 Architecture Reviewer 2 (`reviewer_m1_2`)  
**Target Package**: `packages/webhook-receiver` (`@surface-engine/webhook-receiver`)  
**Workspace**: `/Users/4jp/Workspace/limen/surface-engine`  
**Date**: 2026-07-21  

---

## Review Summary

**Verdict**: **APPROVE** (with Minor Recommendations)

`packages/webhook-receiver` provides a clean, secure, and performant webhook handling module for Content Engine event streams. The cryptographic signature verification uses Node's `timingSafeEqual` with proper length checking to mitigate timing side-channel attacks, the event payloads are properly typed and discriminated, and module export mappings conform to modern Node.js subpath export conventions (`NodeNext`). The package builds cleanly without errors.

---

## 1. Observations

- **Constant-Time Signature Verification (`src/verify.ts`)**:
  - `verifyWebhookSignature` computes SHA-256 HMAC using Node's `node:crypto` `createHmac`.
  - Converts hex digests into `Buffer` instances and compares byte lengths (`if (computedBuffer.length !== receivedBuffer.length) return false;`).
  - Calls `timingSafeEqual(computedBuffer, receivedBuffer)` when byte lengths match.
  - Strips leading `sha256=` signature prefixes automatically when provided.
  - Wraps parsing in a `try...catch` block to safely catch non-hex or odd-length hex strings.

- **Type Discrimination & Envelope Definition (`src/types.ts`)**:
  - `WebhookEventType` is defined as a 6-member literal string union: `'content.published' | 'content.updated' | 'conversion.recorded' | 'identity.mutated' | 'asset.rendered' | 'ping'`.
  - Generic base envelope `WebhookBaseEvent<TType, TPayload>` ensures strong type association between `event` field literals and payload interface structures (`ContentPublishedData`, `ContentUpdatedData`, `ConversionRecordedData`, `IdentityMutatedData`, `AssetRenderedData`, `PingData`).
  - `ContentWebhookPayload` is a discriminated union over the `event` field.
  - `createWebhookHandler` (`src/handler.ts`) uses exhaustive `switch (event.event)` statements to dispatch events to typed callback handlers (`onContentPublished`, `onContentUpdated`, etc.).

- **Export Mappings & Package Configuration (`package.json`, `tsconfig.json`)**:
  - `package.json` specifies:
    ```json
    "main": "./dist/index.js",
    "module": "./dist/index.js",
    "types": "./dist/index.d.ts",
    "exports": {
      ".": {
        "types": "./dist/index.d.ts",
        "import": "./dist/index.js",
        "require": "./dist/index.js"
      }
    }
    ```
  - `tsconfig.json` uses `"module": "NodeNext"` and `"moduleResolution": "NodeNext"` with `"declaration": true` and `"declarationMap": true`.
  - Dist directory output (`dist/index.js`, `dist/index.d.ts`, `dist/verify.js`, `dist/parser.js`, `dist/handler.js`, `dist/types.js`) maps 1:1 with source ESM imports (`export * from './types.js';`).

- **Build & Test Verification**:
  - `pnpm --filter @surface-engine/webhook-receiver build` executed clean with 0 exit code.
  - `node test-runner-unit.js`: 52/52 assertions passed (including HMAC boundary tests, multi-byte UTF-8 secrets, normalization of legacy snake_case formats, and stress performance >600k HMAC ops/sec).
  - `node test-runner-handler.js`: 10/10 integration tests passed (simulating Next.js App Router POST Requests, verifying custom `onError` overrides, signature validation failures, and event handler routing).

---

## 2. Logic Chain

1. **HMAC Cryptographic Integrity**:
   - `verifyWebhookSignature` computes HMAC using `createHmac('sha256', secret).update(rawBody, 'utf-8').digest('hex')`.
   - Creating buffers from hex digests (`Buffer.from(computedHmac, 'hex')`) and checking length equality before calling `timingSafeEqual` guarantees constant-time comparison for equal-length buffers without throwing length mismatch errors from `crypto.timingSafeEqual`.
   - *Conclusion*: Zero timing leak vulnerabilities detected for signature validation.

2. **Type Discrimination & Runtime Validation**:
   - Runtime validation (`src/parser.ts`) checks `VALID_EVENT_TYPES` set (`'content.published'`, `'content.updated'`, etc.).
   - Normalization maps legacy fields (`event_type` -> `event`, `brand_id` -> `brandId`, `created_at` -> `timestamp`, `event_id` -> `id`, `data` -> `payload`).
   - Handler (`src/handler.ts`) safely switches on `event.event` and triggers matching callbacks typed by `WebhookEventHandlers`.
   - *Conclusion*: Type discrimination is sound at both compile-time and runtime.

3. **Monorepo Export & Build Conformance**:
   - Root exports match `tsconfig.json` `rootDir` and `outDir`.
   - Import paths retain `.js` extensions for NodeNext module resolution.
   - `pnpm --filter @surface-engine/webhook-receiver build` compiles TypeScript without warnings or errors.

---

## 3. Caveats

- **Fallback Fall-Through in Normalization**:
  In `src/parser.ts`, `normalizeRawBody` uses `(raw.payload || raw.data || raw)` as the payload. If an incoming raw object does not contain `payload` or `data`, the entire raw object is passed as `payload`. While convenient for non-standard pay-loaders, consumers should remain aware of potential field key pollution.
- **Node module type warning**:
  `test-runner-unit.js` triggers a Node warning because `package.json` omits `"type": "module"`. Adding `"type": "module"` or `"type": "commonjs"` (depending on workspace policy) would silence Node warnings during test execution.

---

## 4. Conclusion

`packages/webhook-receiver` meets all architectural, security, and monorepo contract requirements. No integrity violations, dummy implementations, or security shortcuts were identified.

---

## 5. Verification Method

To independently verify this report:

1. **Clean & Build Package**:
   ```bash
   cd /Users/4jp/Workspace/limen/surface-engine
   pnpm --filter @surface-engine/webhook-receiver run clean
   pnpm --filter @surface-engine/webhook-receiver build
   ```
2. **Execute Test Runners**:
   ```bash
   cd /Users/4jp/Workspace/limen/surface-engine/packages/webhook-receiver
   node test-runner-unit.js
   node test-runner-handler.js
   ```
3. **Inspect Output & Exports**:
   Inspect `packages/webhook-receiver/dist/index.d.ts` and `package.json` to confirm export mapping alignment.

---

## Review Findings & Assessment

### [Minor] Finding 1: Package Type Notice
- **Where**: `packages/webhook-receiver/package.json`
- **What**: `"type": "module"` is not explicitly defined in `package.json`.
- **Why**: Node prints a `MODULE_TYPELESS_PACKAGE_JSON` warning when running ES module test runners directly.
- **Suggestion**: Add `"type": "module"` to `package.json` to explicitly register the package as ESM in Node environments.

---

## Verified Claims

- Constant-time HMAC comparison -> Verified via code inspection of `src/verify.ts` and 12 unit tests -> PASS
- Type discrimination & base envelope -> Verified via `src/types.ts`, `src/handler.ts`, `src/parser.ts` -> PASS
- Package export mappings -> Verified via `package.json` and `dist/` compilation -> PASS
- Package build -> Verified via `pnpm --filter @surface-engine/webhook-receiver build` -> PASS
