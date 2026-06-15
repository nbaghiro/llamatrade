/**
 * Browser telemetry SDK for the LlamaTrade web app.
 *
 * One call — `initTelemetry()` in `main.tsx` — wires Core Web Vitals, global
 * error capture, and the pluggable sink. The `telemetryInterceptor` is added to
 * the Connect transports in `services/grpc-client.ts` to instrument every RPC
 * (latency, errors, W3C trace propagation to the backend).
 */

import { initErrorCapture } from './errors';
import { createDefaultSink, emit, flushSink, resolveConfig, setTelemetrySink } from './sink';
import type { TelemetryAttributes } from './types';
import { initWebVitals } from './vitals';

let initialized = false;

/**
 * Initialise browser telemetry. Idempotent; safe to call once at app start.
 */
export function initTelemetry(): void {
  if (initialized) return;
  initialized = true;

  setTelemetrySink(createDefaultSink(resolveConfig()));
  initWebVitals();
  initErrorCapture();

  if (typeof window !== 'undefined') {
    // Flush any batched events before the page goes away.
    window.addEventListener('pagehide', flushSink);
  }
}

/**
 * Record a feature/funnel event (e.g. "strategy_created", "backtest_started").
 */
export function recordEvent(name: string, props: TelemetryAttributes = {}): void {
  emit({ type: 'event', name, timestamp: Date.now(), attributes: props });
}

export { telemetryInterceptor } from './interceptor';
export type {
  TelemetryAttributes,
  TelemetryEvent,
  TelemetryEventType,
  TelemetrySink,
} from './types';
