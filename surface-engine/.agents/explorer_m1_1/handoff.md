# Handoff Report — M1 Scaffolding Explorer 1

## 1. Observation

### Tool & Environment Diagnostics
Tool inspection executed in `/Users/4jp/Workspace/limen/surface-engine`:
- Command: `node -v && npm -v && pnpm -v && npx turbo --version`
- Output:
  - Node.js: `v26.5.0` (path: `/opt/homebrew/bin/node`)
  - npm: `11.17.0` (path: `/opt/homebrew/bin/npm`)
  - pnpm: `10.34.4` (path: `/opt/homebrew/bin/pnpm`)
  - Turborepo: `2.10.5`

### Workspace File System Inspection
Observed files in root directory `/Users/4jp/Workspace/limen/surface-engine`:
- `ORIGINAL_REQUEST.md` (lines 12–26):
  - R1: Monorepo initialization using Turborepo and Next.js.
  - R2: Scaffolding 5 core visual applications (`tryptich`, `narcissus`, `ballerina`, `hospes`, `live-camera`).
  - R3: Shared package (`packages/webhook-receiver`).
  - Acceptance Criteria: `npm run build` at workspace root builds all applications/packages without errors.
- `TEST_INFRA.md`:
  - Tier 1: Feature coverage (`apps/tryptich`, `apps/narcissus`, `apps/ballerina`, `apps/hospes`, `apps/live-camera`, `packages/webhook-receiver`).
  - Tier 2: Boundary verification (`package.json` in each app/package, Next.js config).
  - Tier 3: Cross-feature integration (`webhook-receiver` declared and imported by all 5 apps).
  - Tier 4: Application build verification (`npm run build` exit code `0`).
- `tests/e2e-runner.js`: Automated runner checking Tiers 1–4.

---

## 2. Logic Chain

1. **Environment Compatibility**: The environment has Node.js `v26.5.0`, npm `11.17.0`, pnpm `10.34.4`, and Turborepo `2.10.5` available globally/via npx.
2. **Turborepo v2 Configuration Standard**: Turborepo 2.10.5 uses `tasks` top-level schema in `turbo.json` with topological dependency graph (`"dependsOn": ["^build"]`).
3. **Workspace Layout**:
   - `apps/tryptich` — Next.js 14/15 app (React canvas carousel)
   - `apps/narcissus` — Next.js 14/15 app (WebGL mirror)
   - `apps/ballerina` — Next.js 14/15 app (Kinetic typography)
   - `apps/hospes` — Next.js 14/15 app (Concierge interface)
   - `apps/live-camera` — Next.js 14/15 app (Livestream broadcast framework)
   - `packages/webhook-receiver` — Shared webhook receiver package (`@surface-engine/webhook-receiver`)
4. **Package Manager & Workspaces**: To satisfy `npm run build` requirement in `TEST_INFRA.md` while remaining compatible with pnpm, `package.json` includes `"workspaces": ["apps/*", "packages/*"]` and `pnpm-workspace.yaml` is provided.
5. **TypeScript Config Architecture**: Base `tsconfig.json` in workspace root defines strict type checking and path mapping (`@surface-engine/webhook-receiver` -> `./packages/webhook-receiver/src`), allowing standard TypeScript resolution across workspace packages.

---

## 3. Caveats

- **Read-Only Scope**: Per explorer role constraints, this report provides templates and step-by-step instructions. Implementation must be performed by implementer agents.
- **Node v26 Runtime**: Node.js `v26.5.0` is an active cutting-edge runtime. Standard ES modules and Next.js `14.2.x` / `15.x` bundler options should be configured to ensure full compatibility.

---

## 4. Conclusion & Precise Templates

The optimal monorepo setup for `surface-engine` uses Turborepo 2.x, Next.js, and npm/pnpm workspaces. Below are the precise JSON templates and instructions for implementing the root setup.

### Template 1: Root `package.json`
Path: `/Users/4jp/Workspace/limen/surface-engine/package.json`
```json
{
  "name": "surface-engine",
  "version": "0.1.0",
  "private": true,
  "description": "Public Audience Surfaces suite with unified webhook integration",
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "scripts": {
    "build": "turbo run build",
    "dev": "turbo run dev",
    "lint": "turbo run lint",
    "check-types": "turbo run check-types",
    "clean": "turbo run clean",
    "test:e2e": "node tests/e2e-runner.js"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "prettier": "^3.2.5",
    "turbo": "^2.10.5",
    "typescript": "^5.3.3"
  },
  "engines": {
    "node": ">=18.0.0",
    "npm": ">=9.0.0"
  }
}
```

### Template 2: Root `turbo.json`
Path: `/Users/4jp/Workspace/limen/surface-engine/turbo.json`
```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": [
        "^build"
      ],
      "inputs": [
        "$TURBO_DEFAULT$",
        ".env*"
      ],
      "outputs": [
        ".next/**",
        "!.next/cache/**",
        "dist/**",
        "build/**"
      ]
    },
    "lint": {
      "dependsOn": [
        "^lint"
      ]
    },
    "check-types": {
      "dependsOn": [
        "^check-types"
      ]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "clean": {
      "cache": false
    }
  }
}
```

### Template 3: Root `tsconfig.json`
Path: `/Users/4jp/Workspace/limen/surface-engine/tsconfig.json`
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": [
      "dom",
      "dom.iterable",
      "esnext"
    ],
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
    "paths": {
      "@surface-engine/webhook-receiver": [
        "./packages/webhook-receiver/src"
      ]
    }
  },
  "exclude": [
    "node_modules",
    "dist",
    ".next",
    ".agents"
  ]
}
```

### Template 4: `pnpm-workspace.yaml`
Path: `/Users/4jp/Workspace/limen/surface-engine/pnpm-workspace.yaml`
```yaml
packages:
  - "apps/*"
  - "packages/*"
```

### Template 5: `.gitignore`
Path: `/Users/4jp/Workspace/limen/surface-engine/.gitignore`
```gitignore
# dependencies
node_modules
.pnpm-store

# Next.js build output
.next/
out/

# turbo
.turbo

# build outputs
dist/
build/

# logs
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*

# environment variables
.env*.local
.env

# OS / IDE
.DS_Store
*.pem
.vscode/
.idea/
```

---

## 5. Implementation Step-by-Step Instructions

1. **Create Root Configuration Files**:
   - Write `package.json`, `turbo.json`, `tsconfig.json`, `pnpm-workspace.yaml`, and `.gitignore` at `/Users/4jp/Workspace/limen/surface-engine/` using Templates 1–5 above.

2. **Create Workspace Directory Structure**:
   ```bash
   mkdir -p apps/tryptich apps/narcissus apps/ballerina apps/hospes apps/live-camera packages/webhook-receiver
   ```

3. **Initialize `packages/webhook-receiver`**:
   - Create `packages/webhook-receiver/package.json`:
     ```json
     {
       "name": "@surface-engine/webhook-receiver",
       "version": "0.1.0",
       "main": "./dist/index.js",
       "types": "./dist/index.d.ts",
       "exports": {
         ".": {
           "types": "./dist/index.d.ts",
           "default": "./dist/index.js"
         }
       },
       "scripts": {
         "build": "tsc",
         "clean": "rm -rf dist"
       },
       "devDependencies": {
         "typescript": "^5.3.3"
       }
     }
     ```
   - Create `packages/webhook-receiver/src/index.ts` with webhook receiver exports.

4. **Initialize 5 Next.js Applications**:
   - For each app in `apps/tryptich`, `apps/narcissus`, `apps/ballerina`, `apps/hospes`, `apps/live-camera`:
     - Create `package.json` declaring dependency `"@surface-engine/webhook-receiver": "workspace:*"` (or `"file:../../packages/webhook-receiver"`).
     - Create `next.config.mjs` (or `next.config.js`).
     - Create standard App Router entry point (`app/layout.tsx` and `app/page.tsx`).
     - Import and invoke `@surface-engine/webhook-receiver` in each app to satisfy Tier 3 cross-feature integration.

5. **Install & Verify**:
   - Run `npm install` or `pnpm install` at workspace root.
   - Run `node tests/e2e-runner.js` to verify Tiers 1–3 pass.
   - Run `npm run build` at workspace root to verify Tier 4 pass.

---

## 6. Verification Method

- **Tier 1–3 Verification**:
  ```bash
  cd /Users/4jp/Workspace/limen/surface-engine
  node tests/e2e-runner.js
  ```
- **Tier 4 Build Verification**:
  ```bash
  cd /Users/4jp/Workspace/limen/surface-engine
  npm run build
  ```
- **Invalidation Conditions**:
  - Missing any of the 5 app directories in `apps/` or `packages/webhook-receiver`.
  - Exit code != 0 from `npm run build` or `node tests/e2e-runner.js`.
