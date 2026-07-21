import { createWebhookHandler } from '@surface-engine/webhook-receiver';

export const POST = createWebhookHandler({
  secret: process.env.WEBHOOK_SECRET,
  handlers: {
    onContentPublished: async (event) => {
      console.log('[hospes] Content published event:', event.id, event.payload.title);
    },
    onContentUpdated: async (event) => {
      console.log('[hospes] Content updated event:', event.id, event.payload.contentId);
    },
    onConversionRecorded: async (event) => {
      console.log('[hospes] Conversion recorded event:', event.id, event.payload.source);
    },
    onIdentityMutated: async (event) => {
      console.log('[hospes] Identity mutated event:', event.id, event.payload.brandId);
    },
    onAssetRendered: async (event) => {
      console.log('[hospes] Asset rendered event:', event.id, event.payload.assetId);
    },
    onPing: async (event) => {
      console.log('[hospes] Ping event received:', event.id, event.payload.message);
    },
  },
});
