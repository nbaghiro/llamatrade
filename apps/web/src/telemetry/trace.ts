/**
 * Minimal W3C Trace Context helpers.
 *
 * We generate a fresh trace/span id per RPC and emit a `traceparent` header so
 * that the backend (running `llamatrade_telemetry` / OTel) can link its server
 * span to the originating browser call. We do not maintain a browser-side span
 * tree — the browser is the trace root.
 *
 * Format: `version-traceid-spanid-flags`
 *   version = 00
 *   traceid = 16 bytes (32 hex chars)
 *   spanid  = 8 bytes (16 hex chars)
 *   flags   = 01 (sampled)
 *
 * @see https://www.w3.org/TR/trace-context/
 */

const SAMPLED_FLAG = '01';

/**
 * Generate `length` random bytes as a lowercase hex string.
 *
 * Uses the Web Crypto API when available, falling back to `Math.random` (the
 * fallback is only for non-secure contexts; ids remain unique enough for
 * trace correlation).
 */
function randomHex(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < byteLength; i += 1) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  let hex = '';
  for (const byte of bytes) {
    hex += byte.toString(16).padStart(2, '0');
  }
  return hex;
}

/**
 * A generated W3C trace context for a single RPC.
 */
export interface TraceContext {
  traceId: string;
  spanId: string;
  traceparent: string;
}

/**
 * Create a new sampled trace context.
 */
export function createTraceContext(): TraceContext {
  const traceId = randomHex(16);
  const spanId = randomHex(8);
  return {
    traceId,
    spanId,
    traceparent: `00-${traceId}-${spanId}-${SAMPLED_FLAG}`,
  };
}
