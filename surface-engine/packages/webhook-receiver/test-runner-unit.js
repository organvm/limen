import { createHmac } from 'node:crypto';
import { verifyWebhookSignature, parseWebhookPayload, WebhookError } from './dist/index.js';

let passed = 0;
let failed = 0;
const failures = [];

function assert(condition, message) {
  if (condition) {
    passed++;
    console.log(`  ✓ ${message}`);
  } else {
    failed++;
    console.error(`  ✗ ${message}`);
    failures.push(message);
  }
}

function assertEqual(actual, expected, message) {
  if (actual === expected) {
    passed++;
    console.log(`  ✓ ${message}`);
  } else {
    failed++;
    console.error(`  ✗ ${message} (Expected: ${expected}, Got: ${actual})`);
    failures.push(`${message} (Expected: ${expected}, Got: ${actual})`);
  }
}

function computeTestSignature(body, secret, prefix = 'sha256=') {
  const hmac = createHmac('sha256', secret).update(body, 'utf-8').digest('hex');
  return prefix ? `${prefix}${hmac}` : hmac;
}

console.log('====================================================');
console.log('WEBHOOK RECEIVER UNIT & STRESS TEST HARNESS');
console.log('====================================================\n');

// ----------------------------------------------------
// TEST SUITE 1: verifyWebhookSignature
// ----------------------------------------------------
console.log('--- SUITE 1: verifyWebhookSignature ---');

const secret = 'super-secret-key-12345';
const validBody = JSON.stringify({ event: 'ping', brandId: 'brand_777' });
const validSigWithPrefix = computeTestSignature(validBody, secret, 'sha256=');
const validSigNoPrefix = computeTestSignature(validBody, secret, '');

// 1.1 Valid signatures
assertEqual(
  verifyWebhookSignature(validBody, secret, validSigWithPrefix),
  true,
  '1.1 Valid signature with sha256= prefix'
);

assertEqual(
  verifyWebhookSignature(validBody, secret, validSigNoPrefix),
  true,
  '1.2 Valid signature without sha256= prefix'
);

// Uppercase signature
const upperSig = validSigNoPrefix.toUpperCase();
assertEqual(
  verifyWebhookSignature(validBody, secret, upperSig),
  true,
  '1.3 Valid signature in uppercase hex'
);

// 1.2 Tampered payload
const tamperedBody = JSON.stringify({ event: 'ping', brandId: 'brand_999' });
assertEqual(
  verifyWebhookSignature(tamperedBody, secret, validSigWithPrefix),
  false,
  '1.4 Tampered payload body returns false'
);

// 1.3 Invalid secret key
const wrongSecret = 'wrong-secret-key';
assertEqual(
  verifyWebhookSignature(validBody, wrongSecret, validSigWithPrefix),
  false,
  '1.5 Wrong secret key returns false'
);

// 1.4 Tampered signature
const tamperedSig = validSigWithPrefix.slice(0, -1) + (validSigWithPrefix.endsWith('a') ? 'b' : 'a');
assertEqual(
  verifyWebhookSignature(validBody, secret, tamperedSig),
  false,
  '1.6 Tampered signature header returns false'
);

// 1.5 Empty / missing inputs
assertEqual(
  verifyWebhookSignature('', secret, validSigWithPrefix),
  false,
  '1.7 Empty rawBody returns false'
);

assertEqual(
  verifyWebhookSignature(validBody, '', validSigWithPrefix),
  false,
  '1.8 Empty secret returns false'
);

assertEqual(
  verifyWebhookSignature(validBody, secret, ''),
  false,
  '1.9 Empty signatureHeader returns false'
);

// 1.6 Malformed signature strings
assertEqual(
  verifyWebhookSignature(validBody, secret, 'sha256=invalidhexchars!@#$'),
  false,
  '1.10 Non-hex signature returns false'
);

assertEqual(
  verifyWebhookSignature(validBody, secret, 'sha256=abc12'),
  false,
  '1.11 Odd-length / incorrect length signature returns false'
);

// 1.7 UTF-8 multi-byte characters
const utf8Body = JSON.stringify({ event: 'content.published', title: '🚀 Launch & 🎨 Art' });
const utf8Secret = '🔑-secret-999';
const utf8Sig = computeTestSignature(utf8Body, utf8Secret);
assertEqual(
  verifyWebhookSignature(utf8Body, utf8Secret, utf8Sig),
  true,
  '1.12 Multi-byte UTF-8 body & secret signature verification'
);

// ----------------------------------------------------
// TEST SUITE 2: parseWebhookPayload (Supported Event Types)
// ----------------------------------------------------
console.log('\n--- SUITE 2: parseWebhookPayload - Event Types ---');

const eventTypes = [
  { event: 'content.published', payload: { contentId: 'c1', title: 'Post 1', slug: 'post-1', contentType: 'article' } },
  { event: 'content.updated', payload: { contentId: 'c1', updatedFields: ['title'] } },
  { event: 'conversion.recorded', payload: { anonymousSessionId: 'sess_1', source: 'shopify' } },
  { event: 'identity.mutated', payload: { brandId: 'b1', thematicCoreKeywords: ['tech'], aestheticKeywords: ['dark'], unifiedScore: 0.95 } },
  { event: 'asset.rendered', payload: { assetId: 'a1', assetType: 'webgl_mesh', url: 'https://example.com/mesh.glb', format: 'glb' } },
  { event: 'ping', payload: { message: 'pong' } },
];

for (const et of eventTypes) {
  const input = {
    id: `evt_${et.event}`,
    event: et.event,
    timestamp: new Date().toISOString(),
    brandId: 'brand_123',
    payload: et.payload,
  };
  const res = parseWebhookPayload(input);
  assert(res.success === true && res.event.event === et.event, `2. Event type check: ${et.event}`);
}

// ----------------------------------------------------
// TEST SUITE 3: parseWebhookPayload (snake_case Normalization & Aliases)
// ----------------------------------------------------
console.log('\n--- SUITE 3: parseWebhookPayload - Normalization ---');

// 3.1 Legacy snake_case event_type, brand_id, project_id, created_at, event_id, data
const legacySnakePayload = {
  event_id: 'evt_legacy_001',
  event_type: 'content.published',
  created_at: '2026-07-21T12:00:00Z',
  brand_id: 'brand_legacy_1',
  project_id: 'proj_legacy_1',
  data: { contentId: 'c99', title: 'Legacy Title', slug: 'legacy-title', contentType: 'visual' },
};

const normRes1 = parseWebhookPayload(legacySnakePayload);
assert(normRes1.success, '3.1 Legacy snake_case payload parsed successfully');
if (normRes1.success) {
  assertEqual(normRes1.event.id, 'evt_legacy_001', '3.1.1 event_id mapped to id');
  assertEqual(normRes1.event.event, 'content.published', '3.1.2 event_type mapped to event');
  assertEqual(normRes1.event.timestamp, '2026-07-21T12:00:00Z', '3.1.3 created_at mapped to timestamp');
  assertEqual(normRes1.event.brandId, 'brand_legacy_1', '3.1.4 brand_id mapped to brandId');
  assertEqual(normRes1.event.projectId, 'proj_legacy_1', '3.1.5 project_id mapped to projectId');
  assertEqual(normRes1.event.payload.contentId, 'c99', '3.1.6 data mapped to payload');
}

// 3.2 Alternate field names: topic, eventType
const topicPayload = {
  topic: 'ping',
  brandId: 'b_topic',
  payload: { message: 'topic test' },
};
const normRes2 = parseWebhookPayload(topicPayload);
assert(normRes2.success && normRes2.event.event === 'ping', '3.2 topic alias normalized to event');

// 3.3 Autogenerated ID and timestamp when omitted
const minimalPayload = {
  event: 'ping',
  brandId: 'b_min',
};
const normRes3 = parseWebhookPayload(minimalPayload);
assert(normRes3.success, '3.3 Minimal payload with missing id & timestamp parsed successfully');
if (normRes3.success) {
  assert(typeof normRes3.event.id === 'string' && normRes3.event.id.startsWith('evt_'), '3.3.1 ID auto-generated with evt_ prefix');
  assert(typeof normRes3.event.timestamp === 'string' && !isNaN(Date.parse(normRes3.event.timestamp)), '3.3.2 Timestamp auto-generated with ISO string');
}

// ----------------------------------------------------
// TEST SUITE 4: parseWebhookPayload (Signature Verification Options)
// ----------------------------------------------------
console.log('\n--- SUITE 4: parseWebhookPayload - Enforce Signature ---');

const optBodyStr = JSON.stringify({ id: 'e1', event: 'ping', brandId: 'b1', payload: {} });
const optSecret = 'opts-secret-key';
const optSig = computeTestSignature(optBodyStr, optSecret);

// 4.1 Enforce signature pass
const optRes1 = parseWebhookPayload(JSON.parse(optBodyStr), {
  enforceSignature: true,
  secret: optSecret,
  rawBody: optBodyStr,
  signature: optSig,
});
assert(optRes1.success, '4.1 Signature enforcement succeeds with matching signature');

// 4.2 Enforce signature failure (bad signature)
const optRes2 = parseWebhookPayload(JSON.parse(optBodyStr), {
  enforceSignature: true,
  secret: optSecret,
  rawBody: optBodyStr,
  signature: 'sha256=badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb',
});
assert(!optRes2.success, '4.2 Signature enforcement fails with bad signature');
if (!optRes2.success) {
  assertEqual(optRes2.error.code, 'INVALID_SIGNATURE', '4.2.1 Error code is INVALID_SIGNATURE');
  assertEqual(optRes2.error.statusCode, 401, '4.2.2 Status code is 401');
}

// 4.3 Enforce signature failure (missing secret)
const optRes3 = parseWebhookPayload(JSON.parse(optBodyStr), {
  enforceSignature: true,
  rawBody: optBodyStr,
  signature: optSig,
});
assert(!optRes3.success, '4.3 Signature enforcement fails with missing secret');
if (!optRes3.success) {
  assertEqual(optRes3.error.code, 'MISSING_SECRET', '4.3.1 Error code is MISSING_SECRET');
  assertEqual(optRes3.error.statusCode, 500, '4.3.2 Status code is 500');
}

// 4.4 Enforce signature failure (missing rawBody or signature)
const optRes4 = parseWebhookPayload(JSON.parse(optBodyStr), {
  enforceSignature: true,
  secret: optSecret,
});
assert(!optRes4.success, '4.4 Signature enforcement fails with missing rawBody/signature');
if (!optRes4.success) {
  assertEqual(optRes4.error.code, 'INVALID_SIGNATURE', '4.4.1 Error code is INVALID_SIGNATURE');
  assertEqual(optRes4.error.statusCode, 401, '4.4.2 Status code is 401');
}

// ----------------------------------------------------
// TEST SUITE 5: Malformed & Boundary Inputs
// ----------------------------------------------------
console.log('\n--- SUITE 5: Malformed & Boundary Inputs ---');

// 5.1 Null input
const err1 = parseWebhookPayload(null);
assert(!err1.success && err1.error.code === 'INVALID_PAYLOAD', '5.1 Null body returns INVALID_PAYLOAD');

// 5.2 Undefined input
const err2 = parseWebhookPayload(undefined);
assert(!err2.success && err2.error.code === 'INVALID_PAYLOAD', '5.2 Undefined body returns INVALID_PAYLOAD');

// 5.3 Primitive inputs
const err3 = parseWebhookPayload('string body');
assert(!err3.success && err3.error.code === 'INVALID_PAYLOAD', '5.3 String body returns INVALID_PAYLOAD');

const err4 = parseWebhookPayload(12345);
assert(!err4.success && err4.error.code === 'INVALID_PAYLOAD', '5.4 Number body returns INVALID_PAYLOAD');

const err5 = parseWebhookPayload(true);
assert(!err5.success && err5.error.code === 'INVALID_PAYLOAD', '5.5 Boolean body returns INVALID_PAYLOAD');

// 5.4 Empty object
const err6 = parseWebhookPayload({});
assert(!err6.success && err6.error.code === 'INVALID_PAYLOAD', '5.6 Empty object returns INVALID_PAYLOAD');

// 5.5 Missing event field
const err7 = parseWebhookPayload({ brandId: 'b1' });
assert(!err7.success && err7.error.code === 'INVALID_PAYLOAD', '5.7 Missing event field returns INVALID_PAYLOAD');

// 5.6 Non-string event
const err8 = parseWebhookPayload({ event: 999, brandId: 'b1' });
assert(!err8.success && err8.error.code === 'INVALID_PAYLOAD', '5.8 Non-string event returns INVALID_PAYLOAD');

// 5.7 Unknown / Unsupported event string
const err9 = parseWebhookPayload({ event: 'unsupported.event.type', brandId: 'b1' });
assert(!err9.success && err9.error.code === 'UNKNOWN_EVENT', '5.9 Unsupported event type returns UNKNOWN_EVENT');
if (!err9.success) {
  assertEqual(err9.error.statusCode, 400, '5.9.1 UNKNOWN_EVENT status code is 400');
}

// ----------------------------------------------------
// TEST SUITE 6: Stress & Performance Benchmark
// ----------------------------------------------------
console.log('\n--- SUITE 6: Stress & Performance Benchmark ---');

const STRESS_ITERATIONS = 10000;
const benchBody = JSON.stringify({
  id: 'evt_bench_123',
  event: 'conversion.recorded',
  timestamp: new Date().toISOString(),
  brandId: 'brand_bench',
  payload: { anonymousSessionId: 'sess_bench', source: 'aetheria', amount: 199.99 },
});
const benchSecret = 'bench-secret-key-999';
const benchSig = computeTestSignature(benchBody, benchSecret);
const benchParsedBody = JSON.parse(benchBody);

// Benchmark verifyWebhookSignature
const startSigTime = performance.now();
for (let i = 0; i < STRESS_ITERATIONS; i++) {
  verifyWebhookSignature(benchBody, benchSecret, benchSig);
}
const endSigTime = performance.now();
const sigDurationMs = endSigTime - startSigTime;
const sigOpsPerSec = Math.round((STRESS_ITERATIONS / sigDurationMs) * 1000);
console.log(`  ⚡ verifyWebhookSignature: ${STRESS_ITERATIONS} ops in ${sigDurationMs.toFixed(2)}ms (${sigOpsPerSec} ops/sec)`);
assert(sigOpsPerSec > 1000, '6.1 verifyWebhookSignature stress test (> 1000 ops/sec)');

// Benchmark parseWebhookPayload
const startParseTime = performance.now();
for (let i = 0; i < STRESS_ITERATIONS; i++) {
  parseWebhookPayload(benchParsedBody);
}
const endParseTime = performance.now();
const parseDurationMs = endParseTime - startParseTime;
const parseOpsPerSec = Math.round((STRESS_ITERATIONS / parseDurationMs) * 1000);
console.log(`  ⚡ parseWebhookPayload: ${STRESS_ITERATIONS} ops in ${parseDurationMs.toFixed(2)}ms (${parseOpsPerSec} ops/sec)`);
assert(parseOpsPerSec > 10000, '6.2 parseWebhookPayload stress test (> 10,000 ops/sec)');

// Large payload stress test (1MB payload)
const largePayloadStr = 'x'.repeat(1024 * 1024);
const largeBody = JSON.stringify({ event: 'ping', brandId: 'b_large', payload: { data: largePayloadStr } });
const largeSig = computeTestSignature(largeBody, benchSecret);
const largeParsed = JSON.parse(largeBody);

const startLargeTime = performance.now();
for (let i = 0; i < 100; i++) {
  verifyWebhookSignature(largeBody, benchSecret, largeSig);
  parseWebhookPayload(largeParsed);
}
const endLargeTime = performance.now();
console.log(`  ⚡ 1MB Large Payload Stress Test (100 ops): ${(endLargeTime - startLargeTime).toFixed(2)}ms`);
assert(endLargeTime - startLargeTime < 5000, '6.3 1MB Large payload stress test completed under 5 seconds');

// ----------------------------------------------------
// SUMMARY REPORT
// ----------------------------------------------------
console.log('\n====================================================');
console.log(`TEST SUMMARY: ${passed} PASSED, ${failed} FAILED`);
console.log('====================================================');

if (failed > 0) {
  console.error('\nFAILURES DETECTED:');
  failures.forEach((f, idx) => console.error(` ${idx + 1}. ${f}`));
  process.exit(1);
} else {
  console.log('ALL TESTS PASSED SUCCESSFULLY! ✅');
  process.exit(0);
}
