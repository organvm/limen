#!/usr/bin/env node

/**
 * surface-engine E2E Test Runner
 * Checks Tier 1 (Feature coverage), Tier 2 (Boundaries), Tier 3 (Cross-feature), Tier 4 (Application build)
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const WORKSPACE_ROOT = path.resolve(__dirname, '..');

const APPS = [
  'tryptich',
  'narcissus',
  'ballerina',
  'hospes',
  'live-camera'
];

const PACKAGES = [
  'webhook-receiver'
];

const results = {
  tier1: { pass: true, checks: [] },
  tier2: { pass: true, checks: [] },
  tier3: { pass: true, checks: [] },
  tier4: { pass: true, checks: [] },
};

function logCheck(tierKey, label, success, details = '') {
  const check = { label, success, details };
  results[tierKey].checks.push(check);
  if (!success) {
    results[tierKey].pass = false;
  }
  const mark = success ? '✅ PASS' : '❌ FAIL';
  console.log(`  [${mark}] ${label}${details ? ' - ' + details : ''}`);
}

function checkTier1() {
  console.log('\n--- Tier 1: Feature Coverage (Existence Verification) ---');
  
  for (const app of APPS) {
    const appPath = path.join(WORKSPACE_ROOT, 'apps', app);
    const exists = fs.existsSync(appPath) && fs.statSync(appPath).isDirectory();
    logCheck('tier1', `Directory apps/${app}`, exists, exists ? 'Found' : 'Directory missing');
  }

  for (const pkg of PACKAGES) {
    const pkgPath = path.join(WORKSPACE_ROOT, 'packages', pkg);
    const exists = fs.existsSync(pkgPath) && fs.statSync(pkgPath).isDirectory();
    logCheck('tier1', `Directory packages/${pkg}`, exists, exists ? 'Found' : 'Directory missing');
  }
}

function checkTier2() {
  console.log('\n--- Tier 2: Boundary Verification (Config & Package Structure) ---');

  // Check Apps
  for (const app of APPS) {
    const appDir = path.join(WORKSPACE_ROOT, 'apps', app);
    const pkgJsonPath = path.join(appDir, 'package.json');

    if (!fs.existsSync(appDir)) {
      logCheck('tier2', `Next.js App Config [apps/${app}]`, false, `App directory apps/${app} missing`);
      continue;
    }

    let pkgValid = false;
    let pkgObj = null;
    if (fs.existsSync(pkgJsonPath)) {
      try {
        const raw = fs.readFileSync(pkgJsonPath, 'utf8');
        pkgObj = JSON.parse(raw);
        pkgValid = Boolean(pkgObj && pkgObj.name);
      } catch (err) {
        pkgValid = false;
      }
    }

    logCheck('tier2', `package.json [apps/${app}]`, pkgValid, pkgValid ? `name: "${pkgObj.name}"` : 'Missing or invalid JSON');

    // Check Next.js config or structure
    const hasNextConfig = ['next.config.js', 'next.config.mjs', 'next.config.ts', 'next.config.cjs'].some(f => 
      fs.existsSync(path.join(appDir, f))
    );
    const hasNextDep = pkgObj && pkgObj.dependencies && Boolean(pkgObj.dependencies.next);
    const hasNextDirs = fs.existsSync(path.join(appDir, 'app')) || fs.existsSync(path.join(appDir, 'pages')) || fs.existsSync(path.join(appDir, 'src/app'));

    const isValidNextApp = pkgValid && (hasNextConfig || hasNextDep || hasNextDirs);
    logCheck('tier2', `Next.js App Setup [apps/${app}]`, isValidNextApp, 
      isValidNextApp ? `Config/App dir found` : 'Missing next.config or app/pages structure');
  }

  // Check Webhook Receiver Package
  for (const pkg of PACKAGES) {
    const pkgDir = path.join(WORKSPACE_ROOT, 'packages', pkg);
    const pkgJsonPath = path.join(pkgDir, 'package.json');

    if (!fs.existsSync(pkgDir)) {
      logCheck('tier2', `Package Configuration [packages/${pkg}]`, false, `Package directory missing`);
      continue;
    }

    let pkgValid = false;
    let pkgObj = null;
    if (fs.existsSync(pkgJsonPath)) {
      try {
        const raw = fs.readFileSync(pkgJsonPath, 'utf8');
        pkgObj = JSON.parse(raw);
        pkgValid = Boolean(pkgObj && pkgObj.name);
      } catch (err) {
        pkgValid = false;
      }
    }

    logCheck('tier2', `package.json [packages/${pkg}]`, pkgValid, pkgValid ? `name: "${pkgObj.name}"` : 'Missing or invalid JSON');

    // Verify exports / entry points
    let hasExportEntry = false;
    if (pkgValid) {
      if (pkgObj.exports) {
        hasExportEntry = true;
      } else if (pkgObj.main || pkgObj.module || pkgObj.types) {
        hasExportEntry = true;
      } else {
        // Check default index entry points
        const defaultEntries = ['src/index.ts', 'src/index.js', 'index.ts', 'index.js'];
        hasExportEntry = defaultEntries.some(e => fs.existsSync(path.join(pkgDir, e)));
      }
    }

    logCheck('tier2', `Exports / Entry Points [packages/${pkg}]`, hasExportEntry, 
      hasExportEntry ? 'Package entry points configured' : 'No exports, main, or entry files found');
  }
}

function searchImportsInDir(dirPath, searchTerms) {
  if (!fs.existsSync(dirPath)) return false;
  
  const entries = fs.readdirSync(dirPath, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.next' || entry.name === 'build' || entry.name === 'dist') {
        continue;
      }
      if (searchImportsInDir(fullPath, searchTerms)) return true;
    } else if (entry.isFile() && /\.(js|jsx|ts|tsx|mjs)$/.test(entry.name)) {
      try {
        const content = fs.readFileSync(fullPath, 'utf8');
        for (const term of searchTerms) {
          if (content.includes(term)) return true;
        }
      } catch (e) {
        // ignore read error
      }
    }
  }
  return false;
}

function checkTier3() {
  console.log('\n--- Tier 3: Cross-Feature Integration (Webhook Receiver Linkage) ---');

  const pkgNames = ['webhook-receiver', '@surface-engine/webhook-receiver'];

  for (const app of APPS) {
    const appDir = path.join(WORKSPACE_ROOT, 'apps', app);
    const pkgJsonPath = path.join(appDir, 'package.json');

    let hasDep = false;
    if (fs.existsSync(pkgJsonPath)) {
      try {
        const pkgObj = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
        const allDeps = {
          ...pkgObj.dependencies,
          ...pkgObj.devDependencies,
          ...pkgObj.peerDependencies
        };
        hasDep = pkgNames.some(p => Boolean(allDeps[p]));
      } catch (e) {
        hasDep = false;
      }
    }

    logCheck('tier3', `Dependency declaration [apps/${app} -> webhook-receiver]`, hasDep, 
      hasDep ? 'Dependency registered in package.json' : 'webhook-receiver not in package.json dependencies');

    const codeImports = searchImportsInDir(appDir, pkgNames);
    logCheck('tier3', `Code import usage [apps/${app} imports webhook-receiver]`, codeImports, 
      codeImports ? 'Import statement verified in source files' : 'No import of webhook-receiver found in app code');
  }
}

function checkTier4() {
  console.log('\n--- Tier 4: Application Build & Execution (npm run build) ---');

  const pkgJsonPath = path.join(WORKSPACE_ROOT, 'package.json');
  if (!fs.existsSync(pkgJsonPath)) {
    logCheck('tier4', 'Workspace Root package.json', false, 'Root package.json missing');
    return;
  }

  let hasBuildScript = false;
  try {
    const rootPkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
    hasBuildScript = Boolean(rootPkg.scripts && rootPkg.scripts.build);
  } catch (e) {
    hasBuildScript = false;
  }

  logCheck('tier4', 'Root build script defined', hasBuildScript, 
    hasBuildScript ? 'npm run build script present' : 'No build script in root package.json');

  if (!hasBuildScript) {
    logCheck('tier4', 'npm run build execution', false, 'Skipped due to missing build script');
    return;
  }

  console.log('  Running `npm run build` at workspace root...');
  const startTime = Date.now();
  try {
    const output = execSync('npm run build', {
      cwd: WORKSPACE_ROOT,
      encoding: 'utf8',
      stdio: 'pipe',
      timeout: 300000 // 5 minutes max
    });
    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    logCheck('tier4', 'npm run build execution', true, `Completed successfully in ${duration}s`);
  } catch (error) {
    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    const stderr = error.stderr ? error.stderr.toString() : error.message;
    const firstLineErr = stderr.split('\n').filter(Boolean)[0] || 'Build process failed';
    logCheck('tier4', 'npm run build execution', false, `Failed after ${duration}s: ${firstLineErr}`);
  }
}

function main() {
  console.log('====================================================');
  console.log('      surface-engine End-to-End Test Suite         ');
  console.log(`Root: ${WORKSPACE_ROOT}`);
  console.log(`Time: ${new Date().toISOString()}`);
  console.log('====================================================');

  checkTier1();
  checkTier2();
  checkTier3();
  checkTier4();

  console.log('\n====================================================');
  console.log('                  TEST SUMMARY                      ');
  console.log('====================================================');

  let totalChecks = 0;
  let totalPassed = 0;
  let allTiersPass = true;

  const tierKeys = ['tier1', 'tier2', 'tier3', 'tier4'];
  const tierLabels = {
    tier1: 'Tier 1: Feature Coverage',
    tier2: 'Tier 2: Boundary Verification',
    tier3: 'Tier 3: Cross-Feature Integration',
    tier4: 'Tier 4: Application Build'
  };

  for (const key of tierKeys) {
    const tier = results[key];
    const passCount = tier.checks.filter(c => c.success).length;
    const checkCount = tier.checks.length;
    totalChecks += checkCount;
    totalPassed += passCount;
    if (!tier.pass) allTiersPass = false;

    const statusMark = tier.pass ? '✅ PASS' : '❌ FAIL';
    console.log(`${statusMark} | ${tierLabels[key]} (${passCount}/${checkCount} checks passed)`);
  }

  console.log('----------------------------------------------------');
  console.log(`Overall Status: ${allTiersPass ? '✅ PASSED' : '❌ FAILED'}`);
  console.log(`Total Checks Passed: ${totalPassed} / ${totalChecks}`);
  console.log('====================================================\n');

  if (!allTiersPass) {
    process.exit(1);
  } else {
    process.exit(0);
  }
}

main();
