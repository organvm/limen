import { createWebhookHandler } from '@surface-engine/webhook-receiver';

export const POST = createWebhookHandler({
  secret: process.env.WEBHOOK_SECRET,
  handlers: {
    onContentPublished: async (event) => {
      console.log('[tryptich] Content published event:', event.id, event.payload.title);
    },
    onContentUpdated: async (event) => {
      console.log('[tryptich] Content updated event:', event.id, event.payload.contentId);
    },
    onConversionRecorded: async (event) => {
      console.log('[tryptich] Conversion recorded event:', event.id, event.payload.source);
    },
    onIdentityMutated: async (event) => {
      console.log('[tryptich] Identity mutated event:', event.id, event.payload.brandId);
    },
    onAssetRendered: async (event) => {
      console.log('[tryptich] Asset rendered event:', event.id, event.payload.assetId);
    },
    onPing: async (event) => {
      console.log('[tryptich] Ping event received:', event.id, event.payload.message);
    },
  },
});
