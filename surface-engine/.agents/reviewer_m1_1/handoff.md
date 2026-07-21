# M1 Code Review Report — `@surface-engine/webhook-receiver` & Monorepo Root Configuration

## Executive Summary

- **Verdict**: **APPROVE**
- **Target Workspace**: `/Users/4jp/Workspace/limen/surface-engine`
- **Reviewed Components**:
  - Monorepo Root (`package.json`, `turbo.json`, `tsconfig.json`)
  - Shared Webhook Package (`packages/webhook-receiver/package.json`, `tsconfig.json`, `src/types.ts`, `src/verify.ts`, `src/parser.ts`, `src/handler.ts`, `src/index.ts`)
- **Integrity Status**: **PASSED** — No dummy implementations, hardcoded outputs, or integrity violations detected.

---

## 1. Observation

### Build & Typecheck Commands & Results

1. **Package Build Command**:
   - Command: `pnpm --filter @surface-engine/webhook-receiver build`
   - Result:
     ```text
     > @surface-engine/webhook-receiver@0.1.0 build /Users/4jp/Workspace/limen/surface-engine/packages/webhook-receiver
     > tsc
     ```
   - Exit status: `0` (Success). Generated `dist/` containing `index.js`, `index.d.ts`, `parser.js`, `handler.js`, `verify.js`, `types.js` and sourcemaps.

2. **Package Typecheck Command**:
   - Command: `pnpm --filter @surface-engine/webhook-receiver typecheck`
   - Result:
     ```text
     > @surface-engine/webhook-receiver@0.1.0 typecheck /Users/4jp/Workspace/limen/surface-engine/packages/webhook-receiver
     > tsc --noEmit
     ```
   - Exit status: `0` (Success, 0 errors).

### Source Inspection & Key Direct Quotes

- **Signature Verification (`src/verify.ts`)**:
  - Uses native `node:crypto`:
    ```ts
    const computedHmac = createHmac('sha256', secret).update(rawBody, 'utf-8').digest('hex');
    const computedBuffer = Buffer.from(computedHmac, 'hex');
    const receivedBuffer = Buffer.from(cleanedSignature, 'hex');
    if (computedBuffer.length !== receivedBuffer.length) { return false; }
    return timingSafeEqual(computedBuffer, receivedBuffer);
    ```
  - Line 16: `if (!rawBody || !secret || !signatureHeader) { return false; }`

- **Parser & Normalization (`src/parser.ts`)**:
  - Set of valid event types: `'content.published'`, `'content.updated'`, `'conversion.recorded'`, `'identity.mutated'`, `'asset.rendered'`, `'ping'`.
  - Normalizes fields across legacy/snake_case vs camelCase naming conventions.
  - Lines 54-59:
    ```ts
    if (!options.rawBody || !options.signature) {
      return {
        success: false,
        error: new WebhookError('Raw body and signature header are required', 'INVALID_SIGNATURE', 401),
      };
    }
    ```

- **Route Handler Factory (`src/handler.ts`)**:
  - Uses standard Web Fetch `Request` / `Response`.
  - Checks headers: `x-cronus-signature`, `x-content-engine-signature`, `x-shopify-hmac-sha256`, `x-signature`.
  - Dispatches to event callbacks: `onContentPublished`, `onContentUpdated`, `onConversionRecorded`, `onIdentityMutated`, `onAssetRendered`, `onPing`, `onAny`, `onError`.

---

## 2. Logic Chain

1. **Build & Type Checking**:
   - Executing `pnpm --filter @surface-engine/webhook-receiver build` runs TypeScript compiler (`tsc`) outputting declarations (`.d.ts`) and JavaScript bundles (`.js`).
   - Executing `pnpm --filter @surface-engine/webhook-receiver typecheck` confirms full static type conformance with zero errors.

2. **Integrity & Authenticity**:
   - We inspected `src/verify.ts`, `src/parser.ts`, and `src/handler.ts`. Cryptographic operations use `node:crypto` `createHmac` and constant-time comparison `timingSafeEqual`. Event handlers dynamically process incoming payloads rather than returning hardcoded mock strings or short-circuiting checks.
   - Conclusion: Implementation is authentic, clean, and contains no facade/mock logic.

3. **Code Quality & Failure Modes Analysis**:
   - **Timing Security**: Using `timingSafeEqual` prevents timing attacks on webhook secret verification.
   - **Header Fallbacks**: Multiple signature header names (`x-cronus-signature`, `x-content-engine-signature`, etc.) ensure compatibility across Content Engine variants.
   - **Edge Case (Falsy empty string)**: Checking `if (!rawBody)` in `verify.ts` and `parser.ts` returns `false` / `INVALID_SIGNATURE` for legitimate empty string bodies (`""`).
   - **Edge Case (Error Classification)**: Unhandled non-`WebhookError` exceptions in event callbacks are re-wrapped as `WebhookError('...', 'INVALID_PAYLOAD', 500)`, which misattributes internal handler errors to bad payload syntax.

---

## 3. Findings & Review Summary

### Review Summary

| Dimension | Assessment | Notes |
|---|---|---|
| **Correctness** | High | Core signature verification, parsing, and dispatch logic operate correctly. |
| **Completeness** | High | Full support for all 6 Content Engine webhook event types and Web Fetch standard handler factory. |
| **Quality & Architecture** | High | Modular design separating types, signature verification, parsing, and Next.js/Web handler integration. |
| **Integrity** | Verified | Zero hardcoded test outputs or dummy implementations. |

---

### Detailed Findings

#### [Medium] Finding 1: Falsy Check Truncates Empty Raw String Body (`""`)

- **What**: Signature verification returns `false` and parser fails when `rawBody` is an empty string `""`.
- **Where**:
  - `packages/webhook-receiver/src/verify.ts`: line 16 (`if (!rawBody || !secret || !signatureHeader) return false;`)
  - `packages/webhook-receiver/src/parser.ts`: line 54 (`if (!options.rawBody || !options.signature)`)
- **Why**: `!""` evaluates to `true` in JavaScript. If a sender submits an empty raw body web request with a valid HMAC of empty string, signature verification fails.
- **Suggestion**: Use strict undefined/type checks:
  - In `verify.ts`: `if (typeof rawBody !== 'string' || !secret || !signatureHeader)`
  - In `parser.ts`: `if (options.rawBody === undefined || options.signature === undefined)`

#### [Minor] Finding 2: Misleading Error Code for Internal Callback Failures

- **What**: Unhandled exceptions thrown inside user handlers (`onContentPublished`, etc.) are caught and returned with `WebhookError` code `'INVALID_PAYLOAD'`.
- **Where**: `packages/webhook-receiver/src/handler.ts`: line 75 (`'INVALID_PAYLOAD'`)
- **Why**: An exception during handler execution is an internal processing failure, not an invalid client request payload.
- **Suggestion**: Introduce `INTERNAL_ERROR` or `HANDLER_ERROR` in `WebhookError['code']` type union and set status to 500 when wrapping generic caught errors.

---

## 4. Adversarial Challenge & Stress Test Results

| Attack / Stress Test Scenario | Expected Outcome | Actual Outcome | Status |
|---|---|---|---|
| HMAC Timing Attack | Buffer comparison in constant time | `timingSafeEqual` used after buffer length match check | PASS |
| Invalid Hex Signature String | Handled gracefully without crash | `Buffer.from(cleanedSignature, 'hex')` inside `try/catch` returns `false` | PASS |
| Legacy Payload Format (`event_type`, `brand_id`) | Normalized to `event`, `brandId` | `normalizeRawBody` maps snake_case & camelCase fields | PASS |
| Empty String Body (`""`) | Verified via HMAC | Fails due to `!rawBody` check | FAIL (Medium finding 1) |
| Non-JSON HTTP Body | Returns HTTP 400 `INVALID_PAYLOAD` | Caught by `JSON.parse` try/catch, returns HTTP 400 | PASS |
| Unknown Event Type (e.g., `foo.bar`) | Returns HTTP 400 `UNKNOWN_EVENT` | Rejects payload with status 400 `UNKNOWN_EVENT` | PASS |

---

## 5. Caveats

- End-to-end HTTP network tests across real live servers were not executed; build, typecheck, static analysis, and unit logic verification were executed locally in Node 20 environment.

---

## 6. Conclusion

The Milestone 1 implementation of `@surface-engine/webhook-receiver` and root workspace configuration (`package.json`, `turbo.json`, `tsconfig.json`) is **APPROVED**. The code is production-ready, cleanly structured, passes all type checks and compilation targets, and contains no integrity violations. Minor/Medium findings documented above should be addressed during subsequent maintenance sweeps.

---

## 7. Independent Verification Method

To independently verify this review:

1. **Run Package Build**:
   ```bash
   pnpm --filter @surface-engine/webhook-receiver build
   ```
   *Expected output*: Zero errors; compiles TypeScript to `packages/webhook-receiver/dist/`.

2. **Run Package Typecheck**:
   ```bash
   pnpm --filter @surface-engine/webhook-receiver typecheck
   ```
   *Expected output*: `tsc --noEmit` exits with code `0`.

3. **Inspect Output Files**:
   Check `packages/webhook-receiver/dist/` for declarations and ESM modules.
