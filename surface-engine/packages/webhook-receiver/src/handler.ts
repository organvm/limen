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
