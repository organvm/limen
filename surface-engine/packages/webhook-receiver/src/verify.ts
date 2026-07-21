import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * Verifies HMAC SHA-256 signature for incoming webhook raw body.
 *
 * @param rawBody - Raw string representation of request body
 * @param secret - Webhook secret key
 * @param signatureHeader - Signature from request headers
 * @returns boolean - true if signature matches using timingSafeEqual
 */
export function verifyWebhookSignature(
  rawBody: string,
  secret: string,
  signatureHeader: string
): boolean {
  if (!rawBody || !secret || !signatureHeader) {
    return false;
  }

  try {
    const cleanedSignature = signatureHeader.startsWith('sha256=')
      ? signatureHeader.slice(7)
      : signatureHeader;

    const computedHmac = createHmac('sha256', secret)
      .update(rawBody, 'utf-8')
      .digest('hex');

    const computedBuffer = Buffer.from(computedHmac, 'hex');
    const receivedBuffer = Buffer.from(cleanedSignature, 'hex');

    if (computedBuffer.length !== receivedBuffer.length) {
      return false;
    }

    return timingSafeEqual(computedBuffer, receivedBuffer);
  } catch {
    return false;
  }
}
