# Shared Package `packages/webhook-receiver` Architecture & Design Specification

## 1. Observation
- **Workspace Context**: Monorepo root located at `/Users/4jp/Workspace/limen/surface-engine`.
- **Project Structure**:
  - `apps/tryptich`: React canvas carousel Next.js app
  - `apps/narcissus`: WebGL mirror Next.js app
  - `apps/ballerina`: Kinetic typography Next.js app
  - `apps/hospes`: Concierge interface Next.js app
  - `apps/live-camera`: Livestream broadcast framework Next.js app
  - Shared package path target: `packages/webhook-receiver`
- **Content Engine Integration**: Analysis of existing Content Engine webhook emitting patterns (`/Users/4jp/Workspace/limen/content-engine-check/apps/api/src/routes/webhooks.ts:1-267`) revealed signature header conventions (`x-cronus-signature`, `x-shopify-hmac-sha256`, `x-aetheria-signature`, `x-signature`) and event payload attributes (brand identification via `brandId`/`brand_id`, project identification via `projectId`/`project_id`, event types like conversion, content, identity mutation).
- **Design Objective**: Design a shared TypeScript package `@surface-engine/webhook-receiver` (or `webhook-receiver`) that provides type-safe event definitions, HMAC SHA-256 signature verification, robust payload parsing/normalization, and Next.js Route Handler factory functions for the 5 visual surface applications.

---

## 2. Logic Chain

### 2.1 Package Architecture Overview
The package `packages/webhook-receiver` provides the foundational interface for receiving, validating, parsing, and handling Content Engine webhook payloads across all `surface-engine` applications.

```
                  +--------------------------+
                  |  Content Engine Webhook  |
                  +------------+-------------+
                               | (HTTP POST)
                               v
               +-------------------------------+
               | Next.js Route Handler (POST)  |
               | (createWebhookHandler)        |
               +---------------+---------------+
                               |
                               v
               +-------------------------------+
               | HMAC Signature Verification   |
               | (verifyWebhookSignature)      |
               +---------------+---------------+
                               |
                               v
               +-------------------------------+
               | Payload Parsing & Validation  |
               | (parseWebhookPayload)         |
               +---------------+---------------+
                               |
                               v
               +-------------------------------+
               | Strongly-Typed Event Handlers |
               | (onContentPublished, etc.)    |
               +---------------+---------------+
                               |
           +-------------------+-------------------+
           |                   |                   |
           v                   v                   v
   apps/tryptich        apps/narcissus      apps/ballerina ...
(React Canvas Carousel) (WebGL Mirror)     (Kinetic Typography)
```

### 2.2 Domain Event Types & Schema
Content Engine emits several categories of events that surface applications must digest:
1. `content.published`: Emitted when new content (visuals, typography, articles, streams) is published.
2. `content.updated`: Emitted when existing content attributes or assets change.
3. `conversion.recorded`: Emitted when user conversions occur (Shopify, Aetheria, generic).
4. `identity.mutated`: Emitted when brand Natural Center keywords/scores refine dynamically.
5. `asset.rendered`: Emitted when media render pipelines finalize assets for surface canvas display.
6. `ping`: Health verification ping.

### 2.3 Required Files & Modules in `packages/webhook-receiver`
- `packages/webhook-receiver/package.json`: Package manifest exposing types and ES modules.
- `packages/webhook-receiver/tsconfig.json`: TypeScript compiler options with declaration emission.
- `packages/webhook-receiver/src/types.ts`: Discriminated union type definitions for all webhooks.
- `packages/webhook-receiver/src/verify.ts`: HMAC SHA-256 constant-time signature verification using Node `crypto`.
- `packages/webhook-receiver/src/parser.ts`: Schema parsing & snake_case/camelCase normalization.
- `packages/webhook-receiver/src/handler.ts`: Next.js App Router POST handler factory (`createWebhookHandler`).
- `packages/webhook-receiver/src/index.ts`: Central barrel export file.

---

### 2.4 Detailed Source Specifications

#### A. Build Export Specifications

##### `packages/webhook-receiver/package.json`
```json
{
  "name": "@surface-engine/webhook-receiver",
  "version": "0.1.0",
  "private": true,
  "main": "./src/index.ts",
  "module": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "import": "./src/index.ts",
      "require": "./src/index.ts"
    }
  },
  "scripts": {
    "build": "tsc --build",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "typescript": "^5.3.3"
  }
}
```

##### `packages/webhook-receiver/tsconfig.json`
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2022", "DOM"],
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "isolatedModules": true
  },
  "include": ["src/**/*"]
}
```

---

#### B. TypeScript Definitions (`packages/webhook-receiver/src/types.ts`)
```typescript
/**
 * Supported Content Engine Webhook Event Types
 */
export type WebhookEventType =
  | 'content.published'
  | 'content.updated'
  | 'conversion.recorded'
  | 'identity.mutated'
  | 'asset.rendered'
  | 'ping';

/**
 * Common Base Envelope for Webhook Payloads
 */
export interface WebhookBaseEvent<TType extends WebhookEventType, TPayload> {
  id: string;
  event: TType;
  timestamp: string; // ISO 8601 string
  brandId: string;
  projectId?: string;
  signature?: string;
  payload: TPayload;
}

/**
 * 1. Content Published Payload
 */
export interface ContentPublishedData {
  contentId: string;
  title: string;
  slug: string;
  contentType: 'article' | 'visual' | 'typography' | 'canvas' | 'livestream' | 'concierge';
  body?: string;
  mediaUrls?: string[];
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export type ContentPublishedEvent = WebhookBaseEvent<'content.published', ContentPublishedData>;

/**
 * 2. Content Updated Payload
 */
export interface ContentUpdatedData {
  contentId: string;
  updatedFields: string[];
  changes: Record<string, unknown>;
  publishedAt?: string;
}

export type ContentUpdatedEvent = WebhookBaseEvent<'content.updated', ContentUpdatedData>;

/**
 * 3. Conversion Recorded Payload
 */
export interface ConversionRecordedData {
  conversionId?: string;
  anonymousSessionId: string;
  source: 'shopify' | 'aetheria' | 'generic' | string;
  medium?: string;
  campaign?: string;
  amount?: number;
  unifiedScore?: number;
  metadata?: Record<string, unknown>;
}

export type ConversionRecordedEvent = WebhookBaseEvent<'conversion.recorded', ConversionRecordedData>;

/**
 * 4. Identity Mutated Payload (Natural Center Refinement)
 */
export interface IdentityMutatedData {
  brandId: string;
  thematicCoreKeywords: string[];
  aestheticKeywords: string[];
  unifiedScore: number;
  refinementReason?: string;
}

export type IdentityMutatedEvent = WebhookBaseEvent<'identity.mutated', IdentityMutatedData>;

/**
 * 5. Asset Rendered Payload
 */
export interface AssetRenderedData {
  assetId: string;
  assetType: 'canvas_carousel' | 'webgl_mesh' | 'kinetic_font' | 'concierge_card' | 'camera_overlay';
  url: string;
  dimensions?: { width: number; height: number };
  format: string;
}

export type AssetRenderedEvent = WebhookBaseEvent<'asset.rendered', AssetRenderedData>;

/**
 * 6. Ping Event Payload
 */
export interface PingData {
  message?: string;
}

export type PingEvent = WebhookBaseEvent<'ping', PingData>;

/**
 * Discriminated Union of all supported Webhook Events
 */
export type ContentWebhookPayload =
  | ContentPublishedEvent
  | ContentUpdatedEvent
  | ConversionRecordedEvent
  | IdentityMutatedEvent
  | AssetRenderedEvent
  | PingEvent;

/**
 * Parser Options
 */
export interface ParseWebhookOptions {
  secret?: string;
  enforceSignature?: boolean;
  rawBody?: string;
  signature?: string;
}

/**
 * Webhook Processing Error Class
 */
export class WebhookError extends Error {
  public readonly code: 'INVALID_SIGNATURE' | 'INVALID_PAYLOAD' | 'MISSING_SECRET' | 'UNKNOWN_EVENT';
  public readonly statusCode: number;

  constructor(message: string, code: WebhookError['code'], statusCode = 400) {
    super(message);
    this.name = 'WebhookError';
    this.code = code;
    this.statusCode = statusCode;
  }
}

/**
 * Parser Result Union
 */
export type ParseWebhookResult =
  | { success: true; event: ContentWebhookPayload }
  | { success: false; error: WebhookError };

/**
 * Event Handlers Map for Handler Factory
 */
export interface WebhookEventHandlers {
  onContentPublished?: (event: ContentPublishedEvent) => Promise<void> | void;
  onContentUpdated?: (event: ContentUpdatedEvent) => Promise<void> | void;
  onConversionRecorded?: (event: ConversionRecordedEvent) => Promise<void> | void;
  onIdentityMutated?: (event: IdentityMutatedEvent) => Promise<void> | void;
  onAssetRendered?: (event: AssetRenderedEvent) => Promise<void> | void;
  onPing?: (event: PingEvent) => Promise<void> | void;
  onAny?: (event: ContentWebhookPayload) => Promise<void> | void;
  onError?: (error: WebhookError, req: Request) => Promise<Response> | Response;
}

/**
 * Handler Factory Options
 */
export interface WebhookHandlerOptions {
  secret?: string;
  enforceSignature?: boolean;
  handlers: WebhookEventHandlers;
}
```

---

#### C. HMAC Signature Verification (`packages/webhook-receiver/src/verify.ts`)
```typescript
import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * Verifies HMAC SHA-256 signature for incoming webhook raw body.
 *
 * @param rawBody - Raw string representation of request body
 * @param secret - Webhook secret key
 * @param signatureHeader - Signature from request headers
 * @returns boolean - true if signature matches using timingSafeEqual
 */
export function verifyWebhookSignature(
  rawBody: string,
  secret: string,
  signatureHeader: string
): boolean {
  if (!rawBody || !secret || !signatureHeader) {
    return false;
  }

  try {
    const cleanedSignature = signatureHeader.startsWith('sha256=')
      ? signatureHeader.slice(7)
      : signatureHeader;

    const computedHmac = createHmac('sha256', secret)
      .update(rawBody, 'utf-8')
      .digest('hex');

    const computedBuffer = Buffer.from(computedHmac, 'hex');
    const receivedBuffer = Buffer.from(cleanedSignature, 'hex');

    if (computedBuffer.length !== receivedBuffer.length) {
      return false;
    }

    return timingSafeEqual(computedBuffer, receivedBuffer);
  } catch {
    return false;
  }
}
```

---

#### D. Payload Parser & Normalizer (`packages/webhook-receiver/src/parser.ts`)
```typescript
import { verifyWebhookSignature } from './verify.js';
import {
  ContentWebhookPayload,
  ParseWebhookOptions,
  ParseWebhookResult,
  WebhookError,
  WebhookEventType,
} from './types.js';

const VALID_EVENT_TYPES: Set<WebhookEventType> = new Set([
  'content.published',
  'content.updated',
  'conversion.recorded',
  'identity.mutated',
  'asset.rendered',
  'ping',
]);

/**
 * Normalizes input payload to handle legacy snake_case vs camelCase field variations.
 */
function normalizeRawBody(raw: Record<string, unknown>): Record<string, unknown> {
  const event = (raw.event || raw.event_type || raw.eventType || raw.topic) as string;
  const brandId = (raw.brandId || raw.brand_id) as string;
  const projectId = (raw.projectId || raw.project_id) as string | undefined;
  const timestamp = (raw.timestamp || raw.created_at || new Date().toISOString()) as string;
  const id = (raw.id || raw.event_id || `evt_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`) as string;
  const payload = (raw.payload || raw.data || raw) as Record<string, unknown>;

  return {
    id,
    event,
    timestamp,
    brandId,
    projectId,
    payload,
  };
}

/**
 * Parses and validates incoming Content Engine webhook payload.
 */
export function parseWebhookPayload(
  body: unknown,
  options?: ParseWebhookOptions
): ParseWebhookResult {
  if (options?.enforceSignature) {
    if (!options.secret) {
      return {
        success: false,
        error: new WebhookError('Webhook secret is required for signature verification', 'MISSING_SECRET', 500),
      };
    }
    if (!options.rawBody || !options.signature) {
      return {
        success: false,
        error: new WebhookError('Raw body and signature header are required', 'INVALID_SIGNATURE', 401),
      };
    }
    const isValid = verifyWebhookSignature(options.rawBody, options.secret, options.signature);
    if (!isValid) {
      return {
        success: false,
        error: new WebhookError('HMAC signature verification failed', 'INVALID_SIGNATURE', 401),
      };
    }
  }

  if (!body || typeof body !== 'object') {
    return {
      success: false,
      error: new WebhookError('Payload must be a non-null JSON object', 'INVALID_PAYLOAD', 400),
    };
  }

  const normalized = normalizeRawBody(body as Record<string, unknown>);

  if (!normalized.event || typeof normalized.event !== 'string') {
    return {
      success: false,
      error: new WebhookError('Missing or invalid event type', 'INVALID_PAYLOAD', 400),
    };
  }

  if (!VALID_EVENT_TYPES.has(normalized.event as WebhookEventType)) {
    return {
      success: false,
      error: new WebhookError(`Unsupported event type: ${normalized.event}`, 'UNKNOWN_EVENT', 400),
    };
  }

  return {
    success: true,
    event: normalized as unknown as ContentWebhookPayload,
  };
}
```

---

#### E. Next.js Handler Factory (`packages/webhook-receiver/src/handler.ts`)
```typescript
import { parseWebhookPayload } from './parser.js';
import { WebhookHandlerOptions, WebhookError } from './types.js';

/**
 * Creates a Next.js App Router POST Route Handler for receiving Content Engine webhooks.
 *
 * Example usage in apps/tryptich/src/app/api/webhooks/route.ts:
 * ```ts
 * import { createWebhookHandler } from '@surface-engine/webhook-receiver';
 *
 * export const POST = createWebhookHandler({
 *   secret: process.env.WEBHOOK_SECRET,
 *   handlers: {
 *     onContentPublished: async (event) => {
 *       console.log('New content published:', event.payload.title);
 *     },
 *   },
 * });
 * ```
 */
export function createWebhookHandler(options: WebhookHandlerOptions) {
  return async function handleWebhookRequest(request: Request): Promise<Response> {
    try {
      const rawBody = await request.text();
      const signature =
        request.headers.get('x-cronus-signature') ||
        request.headers.get('x-content-engine-signature') ||
        request.headers.get('x-shopify-hmac-sha256') ||
        request.headers.get('x-signature') ||
        undefined;

      let jsonBody: unknown;
      try {
        jsonBody = JSON.parse(rawBody);
      } catch {
        throw new WebhookError('Invalid JSON request body', 'INVALID_PAYLOAD', 400);
      }

      const parseResult = parseWebhookPayload(jsonBody, {
        secret: options.secret,
        enforceSignature: options.enforceSignature ?? Boolean(options.secret),
        rawBody,
        signature,
      });

      if (!parseResult.success) {
        if (options.handlers.onError) {
          return await options.handlers.onError(parseResult.error, request);
        }
        return Response.json(
          { error: parseResult.error.message, code: parseResult.error.code },
          { status: parseResult.error.statusCode }
        );
      }

      const event = parseResult.event;

      switch (event.event) {
        case 'content.published':
          await options.handlers.onContentPublished?.(event);
          break;
        case 'content.updated':
          await options.handlers.onContentUpdated?.(event);
          break;
        case 'conversion.recorded':
          await options.handlers.onConversionRecorded?.(event);
          break;
        case 'identity.mutated':
          await options.handlers.onIdentityMutated?.(event);
          break;
        case 'asset.rendered':
          await options.handlers.onAssetRendered?.(event);
          break;
        case 'ping':
          await options.handlers.onPing?.(event);
          break;
      }

      await options.handlers.onAny?.(event);

      return Response.json({ success: true, eventId: event.id, status: 'processed' }, { status: 200 });
    } catch (err: unknown) {
      if (err instanceof WebhookError) {
        if (options.handlers.onError) {
          return await options.handlers.onError(err, request);
        }
        return Response.json({ error: err.message, code: err.code }, { status: err.statusCode });
      }

      const error = new WebhookError(
        err instanceof Error ? err.message : 'Internal server error processing webhook',
        'INVALID_PAYLOAD',
        500
      );

      if (options.handlers.onError) {
        return await options.handlers.onError(error, request);
      }

      return Response.json({ error: error.message }, { status: 500 });
    }
  };
}
```

---

#### F. Barrel Exports (`packages/webhook-receiver/src/index.ts`)
```typescript
export * from './types.js';
export * from './verify.js';
export * from './parser.js';
export * from './handler.js';
```

---

## 3. Caveats
- **Execution Context**: As an explorer agent, no code changes were written directly to `packages/webhook-receiver/src`. All designs and source contents in this report are complete and ready for implementer agents to scaffold.
- **Node Crypto Header Dependency**: `verifyWebhookSignature` relies on `node:crypto`. Next.js Route Handlers run in Node.js runtime (`export const runtime = 'nodejs'`). If Edge Runtime is targeted in any surface app, Web Crypto API (`crypto.subtle`) or Edge-compatible HMAC logic can be substituted.
- **Signature Headers**: Header lookup checks multiple standard headers (`x-cronus-signature`, `x-content-engine-signature`, `x-shopify-hmac-sha256`, `x-signature`). Additional vendor signature headers can be added to `createWebhookHandler` if needed.

---

## 4. Conclusion
The design of `packages/webhook-receiver` provides a lightweight, strictly-typed, and robust shared receiver package for the `surface-engine` monorepo. It cleanly encapsulates signature verification, payload parsing, event discrimination, and Route Handler generation. Implementers can immediately generate the package files according to the specification outlined above.

---

## 5. Verification Method

### 5.1 Static Verification
1. Inspect `packages/webhook-receiver/package.json` to verify name `@surface-engine/webhook-receiver` (or `webhook-receiver`) and export configuration.
2. Inspect `packages/webhook-receiver/src/index.ts` to ensure `types`, `verify`, `parser`, and `handler` are re-exported.

### 5.2 Build & Typecheck Commands
Run from monorepo root `/Users/4jp/Workspace/limen/surface-engine`:
```bash
npm run build
```
Or build the package directly:
```bash
cd packages/webhook-receiver && npm run build
```

### 5.3 Invalidation Conditions
- Any missing export in `src/index.ts` that prevents surface apps (`apps/tryptich`, `apps/narcissus`, etc.) from importing `{ createWebhookHandler, parseWebhookPayload, ContentWebhookPayload }`.
- Inability for Next.js App Router POST handlers to consume `createWebhookHandler` without runtime error.
