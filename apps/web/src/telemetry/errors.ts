/**
 * Global JS error capture.
 *
 * Records uncaught errors and unhandled promise rejections as `js_error` events.
 * Capped per session so a tight error loop can't flood the sink.
 */

import { emit } from './sink';

const MAX_ERRORS_PER_SESSION = 50;

let installed = false;
let count = 0;

function reasonMessage(reason: unknown): string {
  if (reason instanceof Error) return reason.message;
  if (typeof reason === 'string') return reason;
  return 'unhandledrejection';
}

function record(name: string, attributes: Record<string, string | number | boolean | undefined>): void {
  if (count >= MAX_ERRORS_PER_SESSION) return;
  count += 1;
  emit({ type: 'js_error', name, timestamp: Date.now(), attributes });
}

/**
 * Install window error + unhandledrejection listeners. Idempotent; no-op on SSR.
 */
export function initErrorCapture(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;

  window.addEventListener('error', (event: ErrorEvent) => {
    record(event.message || 'error', {
      kind: 'error',
      source: event.filename || undefined,
      line: event.lineno,
      col: event.colno,
    });
  });

  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    record(reasonMessage(event.reason), { kind: 'unhandledrejection' });
  });
}
