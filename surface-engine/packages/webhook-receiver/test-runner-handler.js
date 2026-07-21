/**
 * Integration test runner for `@surface-engine/webhook-receiver` createWebhookHandler.
 * Simulates Next.js App Router HTTP Request/Response flow.
 */

const crypto = require('node:crypto');
const { createWebhookHandler, WebhookError } = require('./dist/index.js');

const SECRET = 'test-webhook-secret-key-321';

function computeHmac(payloadStr, secret = SECRET) {
  return crypto.createHmac('sha256', secret).update(payloadStr, 'utf-8').digest('hex');
}

async function runTests() {
  console.log('====================================================');
  console.log('  Integration Tests: Webhook Handler Verification  ');
  console.log('====================================================\n');

  let passed = 0;
  let failed = 0;
  const observations = [];

  async function assertCase(name, testFn) {
    try {
      await testFn();
      console.log(`  ✅ PASS: ${name}`);
      passed++;
    } catch (err) {
      console.error(`  ❌ FAIL: ${name}`);
      console.error(`     Error: ${err.message}`);
      failed++;
    }
  }

  // ----------------------------------------------------
  // Test 1: Valid signature request (200 response)
  // ----------------------------------------------------
  await assertCase('Valid signature request returns 200 and processes event', async () => {
    let publishedEventCalled = false;
    let anyEventCalled = false;

    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {
        onContentPublished: async (evt) => {
          publishedEventCalled = true;
          if (evt.payload.title !== 'Visual Showcase Article') {
            throw new Error(`Unexpected title: ${evt.payload.title}`);
          }
        },
        onAny: async (evt) => {
          anyEventCalled = true;
        },
      },
    });

    const bodyObj = {
      event: 'content.published',
      brandId: 'brand_tryptich_01',
      payload: {
        contentId: 'cnt_1001',
        title: 'Visual Showcase Article',
        slug: 'visual-showcase-article',
        contentType: 'article',
      },
    };
    const rawBody = JSON.stringify(bodyObj);
    const signature = computeHmac(rawBody);

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-cronus-signature': signature,
      },
      body: rawBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (response.status !== 200) {
      throw new Error(`Expected status 200, got ${response.status}: ${JSON.stringify(responseData)}`);
    }
    if (responseData.status !== 'processed' || !responseData.success) {
      throw new Error(`Unexpected response structure: ${JSON.stringify(responseData)}`);
    }
    if (!publishedEventCalled) {
      throw new Error('onContentPublished callback was not executed');
    }
    if (!anyEventCalled) {
      throw new Error('onAny callback was not executed');
    }
  });

  // ----------------------------------------------------
  // Test 2: Invalid signature request (401 response)
  // ----------------------------------------------------
  await assertCase('Invalid signature request returns 401 response', async () => {
    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {},
    });

    const bodyObj = {
      event: 'content.published',
      brandId: 'brand_tryptich_01',
      payload: { title: 'Unauthorized Post' },
    };
    const rawBody = JSON.stringify(bodyObj);
    const invalidSignature = computeHmac(rawBody, 'wrong-secret-key');

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-cronus-signature': invalidSignature,
      },
      body: rawBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (response.status !== 401) {
      throw new Error(`Expected status 401, got ${response.status}: ${JSON.stringify(responseData)}`);
    }
    if (responseData.code !== 'INVALID_SIGNATURE') {
      throw new Error(`Expected code INVALID_SIGNATURE, got ${responseData.code}`);
    }
  });

  // ----------------------------------------------------
  // Test 3: Malformed JSON request (400 response)
  // ----------------------------------------------------
  await assertCase('Malformed JSON request body returns 400 response', async () => {
    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {},
    });

    const malformedBody = '{ "event": "content.published", "brandId": '; // Unclosed JSON
    const signature = computeHmac(malformedBody);

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-cronus-signature': signature,
      },
      body: malformedBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (response.status !== 400) {
      throw new Error(`Expected status 400, got ${response.status}: ${JSON.stringify(responseData)}`);
    }
    if (responseData.code !== 'INVALID_PAYLOAD') {
      throw new Error(`Expected code INVALID_PAYLOAD, got ${responseData.code}`);
    }
  });

  // ----------------------------------------------------
  // Test 4: Custom Event Callbacks (onContentPublished, onAny, onError)
  // ----------------------------------------------------
  await assertCase('Custom onError handler intercepts errors and returns custom Response', async () => {
    let customOnErrorCalled = false;

    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {
        onError: async (error, req) => {
          customOnErrorCalled = true;
          return Response.json(
            { customInterception: true, message: error.message, errorType: error.code },
            { status: 418 }
          );
        },
      },
    });

    const bodyObj = { event: 'content.published', brandId: 'brand_01' };
    const rawBody = JSON.stringify(bodyObj);
    const badSignature = '0000000000000000000000000000000000000000000000000000000000000000';

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-cronus-signature': badSignature,
      },
      body: rawBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (!customOnErrorCalled) {
      throw new Error('Custom onError handler was not called');
    }
    if (response.status !== 418) {
      throw new Error(`Expected custom status 418, got ${response.status}`);
    }
    if (!responseData.customInterception || responseData.errorType !== 'INVALID_SIGNATURE') {
      throw new Error(`Unexpected custom onError body: ${JSON.stringify(responseData)}`);
    }
  });

  // ----------------------------------------------------
  // Test 5: Verify sha256= signature prefix handling
  // ----------------------------------------------------
  await assertCase('Signature with sha256= prefix is parsed and verified correctly', async () => {
    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {},
    });

    const bodyObj = {
      event: 'ping',
      brandId: 'brand_narcissus_02',
      payload: { message: 'keepalive' },
    };
    const rawBody = JSON.stringify(bodyObj);
    const rawHmac = computeHmac(rawBody);
    const prefixedSignature = `sha256=${rawHmac}`;

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-cronus-signature': prefixedSignature,
      },
      body: rawBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (response.status !== 200) {
      throw new Error(`Expected status 200, got ${response.status}: ${JSON.stringify(responseData)}`);
    }
  });

  // ----------------------------------------------------
  // Test 6: Verify alternate signature headers
  // ----------------------------------------------------
  await assertCase('Alternate signature headers (x-content-engine-signature) are supported', async () => {
    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {},
    });

    const bodyObj = {
      event: 'conversion.recorded',
      brandId: 'brand_ballerina_03',
      payload: { anonymousSessionId: 'sess_123', source: 'shopify' },
    };
    const rawBody = JSON.stringify(bodyObj);
    const signature = computeHmac(rawBody);

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-content-engine-signature': signature,
      },
      body: rawBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (response.status !== 200) {
      throw new Error(`Expected status 200, got ${response.status}: ${JSON.stringify(responseData)}`);
    }
  });

  // ----------------------------------------------------
  // Test 7: Verify all event callbacks
  // ----------------------------------------------------
  await assertCase('All supported event handlers execute for their respective event types', async () => {
    const eventsTriggered = new Set();

    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {
        onContentUpdated: async () => eventsTriggered.add('content.updated'),
        onConversionRecorded: async () => eventsTriggered.add('conversion.recorded'),
        onIdentityMutated: async () => eventsTriggered.add('identity.mutated'),
        onAssetRendered: async () => eventsTriggered.add('asset.rendered'),
        onPing: async () => eventsTriggered.add('ping'),
      },
    });

    const eventTypes = [
      'content.updated',
      'conversion.recorded',
      'identity.mutated',
      'asset.rendered',
      'ping',
    ];

    for (const evtType of eventTypes) {
      const bodyObj = { event: evtType, brandId: 'brand_test', payload: {} };
      const rawBody = JSON.stringify(bodyObj);
      const signature = computeHmac(rawBody);

      const req = new Request('http://localhost/api/webhooks', {
        method: 'POST',
        headers: { 'x-cronus-signature': signature },
        body: rawBody,
      });

      const res = await handler(req);
      if (res.status !== 200) {
        throw new Error(`Event type ${evtType} failed with status ${res.status}`);
      }
    }

    if (eventsTriggered.size !== eventTypes.length) {
      throw new Error(`Expected ${eventTypes.length} event types triggered, got ${eventsTriggered.size}`);
    }
  });

  // ----------------------------------------------------
  // Test 8: Unsupported event type returns 400 UNKNOWN_EVENT
  // ----------------------------------------------------
  await assertCase('Unsupported event type returns 400 UNKNOWN_EVENT', async () => {
    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {},
    });

    const bodyObj = { event: 'invalid.event.name', brandId: 'brand_test' };
    const rawBody = JSON.stringify(bodyObj);
    const signature = computeHmac(rawBody);

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: { 'x-cronus-signature': signature },
      body: rawBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (response.status !== 400) {
      throw new Error(`Expected status 400, got ${response.status}`);
    }
    if (responseData.code !== 'UNKNOWN_EVENT') {
      throw new Error(`Expected code UNKNOWN_EVENT, got ${responseData.code}`);
    }
  });

  // ----------------------------------------------------
  // Test 9: Handler runtime error produces 500 response
  // ----------------------------------------------------
  await assertCase('Event handler runtime error converts to 500 status response', async () => {
    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {
        onPing: () => {
          throw new Error('Database connection failed during ping');
        },
      },
    });

    const bodyObj = { event: 'ping', brandId: 'brand_test' };
    const rawBody = JSON.stringify(bodyObj);
    const signature = computeHmac(rawBody);

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: { 'x-cronus-signature': signature },
      body: rawBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (response.status !== 500) {
      throw new Error(`Expected status 500, got ${response.status}`);
    }
    if (responseData.error !== 'Database connection failed during ping') {
      throw new Error(`Unexpected error message: ${responseData.error}`);
    }
  });

  // ----------------------------------------------------
  // Test 10: Missing signature header returns 401 INVALID_SIGNATURE
  // ----------------------------------------------------
  await assertCase('Missing signature header returns 401 INVALID_SIGNATURE', async () => {
    const handler = createWebhookHandler({
      secret: SECRET,
      handlers: {},
    });

    const bodyObj = { event: 'ping', brandId: 'brand_test' };
    const rawBody = JSON.stringify(bodyObj);

    const request = new Request('http://localhost/api/webhooks', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: rawBody,
    });

    const response = await handler(request);
    const responseData = await response.json();

    if (response.status !== 401) {
      throw new Error(`Expected status 401, got ${response.status}`);
    }
    if (responseData.code !== 'INVALID_SIGNATURE') {
      throw new Error(`Expected code INVALID_SIGNATURE, got ${responseData.code}`);
    }
  });

  console.log('\n====================================================');
  console.log(`  Summary: ${passed} passed, ${failed} failed`);
  console.log('====================================================\n');

  if (failed > 0) {
    process.exit(1);
  }
}

runTests().catch((err) => {
  console.error('Fatal test runner error:', err);
  process.exit(1);
});
