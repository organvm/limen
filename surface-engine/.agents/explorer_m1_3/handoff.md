# Handoff Report: Next.js Monorepo Workspace Import Strategy for `packages/webhook-receiver`

**Explorer**: M1 Integration Explorer 3 (`explorer_m1_3`)  
**Workspace Root**: `/Users/4jp/Workspace/limen/surface-engine`  
**Target Package**: `@surface-engine/webhook-receiver` (`packages/webhook-receiver`)  
**Consumer Apps**: `apps/tryptich`, `apps/narcissus`, `apps/ballerina`, `apps/hospes`, `apps/live-camera`

---

## 1. Observation

- **Tool Execution & Environment**:
  - `node -v` returned `v26.5.0`
  - `npm -v` returned `11.17.0`
  - `pnpm -v` returned `10.34.4`
  - `npx turbo --version` returned `2.10.5`
- **Monorepo Architecture** (from `/Users/4jp/Workspace/limen/surface-engine/.agents/orchestrator/PROJECT.md`, lines 4–10 & 21–26):
  - Shared package: `packages/webhook-receiver` (package name `@surface-engine/webhook-receiver`).
  - Consumer Next.js applications: 5 visual apps (`tryptich`, `narcissus`, `ballerina`, `hospes`, `live-camera`).
  - Monorepo tooling: Turborepo (`turbo.json`) and Next.js (13+ / 14 / 15).
- **Workspace Requirements**:
  - Next.js applications require seamless transpilation and type resolution of local workspace packages (`packages/webhook-receiver`) without requiring manual module pre-compilation during development (`next dev`) or build failures in Webpack/Turbopack.

---

## 2. Logic Chain

1. **Observation**: Monorepo structure contains Next.js apps under `apps/*` and shared package under `packages/webhook-receiver`.
2. **Step 1 — Package Dependency Protocol**:
   - In package managers (pnpm / npm / yarn workspaces), specifying `"@surface-engine/webhook-receiver": "workspace:*"` (or `"*"`) inside an app's `package.json` establishes a symlink inside `apps/<app-name>/node_modules/@surface-engine/webhook-receiver` pointing to `packages/webhook-receiver`.
3. **Step 2 — Next.js Package Transpilation (`transpilePackages`)**:
   - Standard Next.js builds ignore `node_modules` during SWC/Babel transpilation. If a local workspace package exports TypeScript (`.ts`/`.tsx`) source directly or modern ES modules, `next build` and `next dev` will fail unless the package is declared in `transpilePackages`.
   - Next.js 13.1+ provides native `transpilePackages: ['@surface-engine/webhook-receiver']` in `next.config.js`. This forces the Next.js compiler (SWC/Webpack/Turbopack) to transpile the package source code seamlessly inline with the app build.
4. **Step 3 — TypeScript Type Resolution (`tsconfig.json`)**:
   - Next.js apps require TypeScript to recognize types exported by `@surface-engine/webhook-receiver`.
   - Defining `package.json` `exports` and `types` in `packages/webhook-receiver` allows Node/Bundler resolution.
   - Additionally, configuring `compilerOptions.paths` in each app's `tsconfig.json` (`"@surface-engine/webhook-receiver": ["../../packages/webhook-receiver/src/index.ts"]`) guarantees zero-latency IDE type resolution and build resilience before or after `npm install`.
5. **Step 4 — Turborepo Pipeline Orchestration (`turbo.json`)**:
   - Setting `"dependsOn": ["^build"]` in `turbo.json` ensures Turborepo executes upstream package builds before running downstream Next.js app builds, enforcing correct build sequence across the monorepo graph.

---

## 3. Caveats

- **Node vs Edge Runtime**:
  `packages/webhook-receiver` may utilize Node.js built-in modules (such as `crypto` for HMAC signature validation). Next.js App Router Route Handlers default to the `nodejs` runtime. If an app route explicitly configures `export const runtime = 'edge'`, Node `crypto` will not be available unless Web Crypto API (`globalThis.crypto.subtle`) is used.
- **npm vs pnpm Workspace Syntax**:
  `workspace:*` is standard in `pnpm` and modern `yarn`/`npm`. If using standard `npm` workspaces without `workspace:` protocol, `"@surface-engine/webhook-receiver": "*"` can also be used. Both templates are provided below.

---

## 4. Conclusion & Exact Configuration Templates

### A. Next.js App Configuration (`next.config.js` / `next.config.mjs`)

#### Template 1: `apps/<app-name>/next.config.js` (CommonJS format)
```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@surface-engine/webhook-receiver'],
};

module.exports = nextConfig;
```

#### Template 2: `apps/<app-name>/next.config.mjs` (ESM format)
```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@surface-engine/webhook-receiver'],
};

export default nextConfig;
```

---

### B. Next.js App `package.json`

#### Template: `apps/<app-name>/package.json`
```json
{
  "name": "tryptich",
  "version": "0.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@surface-engine/webhook-receiver": "workspace:*",
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.4.0"
  }
}
```
*(Note: Replace `"name": "tryptich"` with the respective app name: `narcissus`, `ballerina`, `hospes`, or `live-camera`. For standard npm workspace compatibility, `"@surface-engine/webhook-receiver": "*"` is equally supported).*

---

### C. Next.js App `tsconfig.json`

#### Template: `apps/<app-name>/tsconfig.json`
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"],
      "@surface-engine/webhook-receiver": ["../../packages/webhook-receiver/src/index.ts"],
      "@surface-engine/webhook-receiver/*": ["../../packages/webhook-receiver/src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

---

### D. Shared Package Configuration (`packages/webhook-receiver/package.json`)

#### Template: `packages/webhook-receiver/package.json`
```json
{
  "name": "@surface-engine/webhook-receiver",
  "version": "0.0.0",
  "private": true,
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "default": "./src/index.ts"
    }
  },
  "scripts": {
    "build": "tsc",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist"
  },
  "devDependencies": {
    "typescript": "^5.4.0"
  }
}
```

---

### E. Turborepo Pipeline Configuration (`turbo.json`)

#### Template: `turbo.json` (Root)
```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["$TURBO_DEFAULT$", ".env*"],
      "outputs": [".next/**", "!.next/cache/**", "dist/**"]
    },
    "typecheck": {
      "dependsOn": ["^typecheck"]
    },
    "lint": {
      "dependsOn": ["^lint"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    }
  }
}
```

---

### F. Example App Usage Pattern (`apps/<app-name>/app/api/webhook/route.ts`)

```typescript
import { NextResponse } from 'next/server';
import { parseWebhookPayload, WebhookEvent } from '@surface-engine/webhook-receiver';

export async function POST(request: Request) {
  try {
    const rawBody = await request.text();
    const signature = request.headers.get('x-content-engine-signature') || undefined;

    const payload = parseWebhookPayload(rawBody, signature);

    if (payload.event === WebhookEvent.CONTENT_UPDATED) {
      // Handle content updated event
      return NextResponse.json({ status: 'success', processed: payload.event });
    }

    return NextResponse.json({ status: 'ignored', event: payload.event });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Invalid webhook payload';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
```

---

## 5. Verification Method

To independently verify that Next.js apps correctly transpile and resolve `@surface-engine/webhook-receiver`:

1. **Workspace Linking Verification**:
   Execute from workspace root:
   ```bash
   npm install # or pnpm install
   ```
   Check that `apps/tryptich/node_modules/@surface-engine/webhook-receiver` exists as a symlink pointing to `packages/webhook-receiver`.

2. **TypeScript Compilation & Typecheck**:
   Execute from workspace root:
   ```bash
   npx turbo run typecheck
   ```
   Ensure zero TypeScript compilation errors in any app or package.

3. **Next.js Production Build Verification**:
   Execute from workspace root:
   ```bash
   npx turbo run build
   ```
   Confirm that `next build` compiles successfully for all 5 Next.js applications (`apps/tryptich`, `apps/narcissus`, `apps/ballerina`, `apps/hospes`, `apps/live-camera`) without transpile or module resolution errors.
