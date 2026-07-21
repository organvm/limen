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
