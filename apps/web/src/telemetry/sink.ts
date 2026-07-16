/**
 * Pluggable telemetry sink.
 *
 * Resolution order:
 *   1. If `VITE_TELEMETRY_OTLP_URL` is set, batch events and POST them as
 *      OTLP/HTTP JSON via `navigator.sendBeacon` (with a `fetch` fallback).
 *   2. Otherwise, in dev builds log each event via `console.debug`.
 *   3. Otherwise (prod, no collector) drop events (no-op).
 *
 * The active sink can be overridden via `setTelemetrySink` (useful for tests).
 * `record` never throws — telemetry must never break the host app.
 */

import type {
  TelemetryAttributes,
  TelemetryConfig,
  TelemetryEvent,
  TelemetrySink,
} from './types';

const SERVICE_NAME = 'llamatrade-web';

/** Max events held before an automatic flush. */
const BATCH_MAX_SIZE = 20;
/** Max time (ms) an event waits before an automatic flush. */
const BATCH_MAX_DELAY_MS = 5000;

/**
 * Resolve telemetry config from the Vite environment.
 */
export function resolveConfig(): TelemetryConfig {
  const otlpUrl = import.meta.env.VITE_TELEMETRY_OTLP_URL?.trim();
  return {
    dev: import.meta.env.DEV,
    otlpUrl: otlpUrl ? otlpUrl : undefined,
    serviceName: SERVICE_NAME,
  };
}

/**
 * A sink that drops everything. Used in prod when no collector is configured.
 */
const noopSink: TelemetrySink = {
  record() {
    /* intentionally empty */
  },
};

/**
 * A sink that logs each event to the console (dev default).
 */
function createConsoleSink(): TelemetrySink {
  return {
    record(event) {
      // eslint-disable-next-line no-console
      console.debug(`[telemetry:${event.type}] ${event.name}`, event.attributes);
    },
  };
}

/**
 * Convert an attribute bag into OTLP KeyValue entries, dropping undefined.
 */
function toOtlpAttributes(attributes: TelemetryAttributes): Array<{
  key: string;
  value: Record<string, string | number | boolean>;
}> {
  const out: Array<{ key: string; value: Record<string, string | number | boolean> }> = [];
  for (const [key, raw] of Object.entries(attributes)) {
    if (raw === undefined) continue;
    if (typeof raw === 'string') {
      out.push({ key, value: { stringValue: raw } });
    } else if (typeof raw === 'boolean') {
      out.push({ key, value: { boolValue: raw } });
    } else if (Number.isInteger(raw)) {
      out.push({ key, value: { intValue: raw } });
    } else {
      out.push({ key, value: { doubleValue: raw } });
    }
  }
  return out;
}

/**
 * Build an OTLP/HTTP JSON logs payload from a batch of events.
 *
 * We model telemetry events as OTLP LogRecords — this keeps the payload simple
 * and collector-agnostic while still being a recognized OTLP shape.
 */
function toOtlpPayload(events: TelemetryEvent[], serviceName: string): string {
  const logRecords = events.map((event) => ({
    timeUnixNano: String(event.timestamp * 1_000_000),
    body: { stringValue: event.name },
    attributes: toOtlpAttributes({
      'telemetry.type': event.type,
      ...event.attributes,
    }),
  }));

  return JSON.stringify({
    resourceLogs: [
      {
        resource: {
          attributes: toOtlpAttributes({ 'service.name': serviceName }),
        },
        scopeLogs: [{ scope: { name: 'llamatrade-web-telemetry' }, logRecords }],
      },
    ],
  });
}

/**
 * A batching sink that transports events to an OTLP/HTTP JSON collector.
 */
function createBeaconSink(otlpUrl: string, serviceName: string): TelemetrySink {
  let buffer: TelemetryEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;

  const send = (events: TelemetryEvent[]): void => {
    if (events.length === 0) return;
    const payload = toOtlpPayload(events, serviceName);
    try {
      // `sendBeacon` survives page unload and is non-blocking; prefer it.
      if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
        const blob = new Blob([payload], { type: 'application/json' });
        const queued = navigator.sendBeacon(otlpUrl, blob);
        if (queued) return;
      }
      // Fallback to keepalive fetch when beacon is unavailable or refused.
      void fetch(otlpUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true,
      }).catch(() => {
        /* swallow — telemetry must not surface transport errors */
      });
    } catch {
      /* swallow — telemetry must not throw */
    }
  };

  const flush = (): void => {
    if (timer !== undefined) {
      clearTimeout(timer);
      timer = undefined;
    }
    if (buffer.length === 0) return;
    const batch = buffer;
    buffer = [];
    send(batch);
  };

  return {
    record(event) {
      buffer.push(event);
      if (buffer.length >= BATCH_MAX_SIZE) {
        flush();
        return;
      }
      if (timer === undefined) {
        timer = setTimeout(flush, BATCH_MAX_DELAY_MS);
      }
    },
    flush,
  };
}

/**
 * Build the default sink from the resolved config.
 */
export function createDefaultSink(config: TelemetryConfig): TelemetrySink {
  if (config.otlpUrl) {
    return createBeaconSink(config.otlpUrl, config.serviceName);
  }
  if (config.dev) {
    return createConsoleSink();
  }
  return noopSink;
}

// Active sink registry — modules call `getSink()` to emit events.

let activeSink: TelemetrySink = noopSink;

/**
 * Replace the active sink. Called by `initTelemetry`; also useful in tests.
 */
export function setTelemetrySink(sink: TelemetrySink): void {
  activeSink = sink;
}

/**
 * Get the active sink.
 */
export function getSink(): TelemetrySink {
  return activeSink;
}

/**
 * Emit an event through the active sink, guarding against sink errors.
 */
export function emit(event: TelemetryEvent): void {
  try {
    activeSink.record(event);
  } catch {
    /* swallow — telemetry must never break the app */
  }
}

/**
 * Flush the active sink if it supports flushing.
 */
export function flushSink(): void {
  try {
    activeSink.flush?.();
  } catch {
    /* swallow */
  }
}
