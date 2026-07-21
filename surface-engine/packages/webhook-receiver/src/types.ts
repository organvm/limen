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
