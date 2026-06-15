/**
 * Shared telemetry types.
 *
 * These describe the events the SDK emits and the pluggable sink that receives
 * them. The shapes are deliberately simple JSON-friendly records so they can be
 * serialized to an OTLP/HTTP JSON payload without further transformation.
 */

/**
 * The category of a telemetry event. Used by sinks to route/group events.
 */
export type TelemetryEventType =
  | 'rpc' // a Connect RPC completed (success or error)
  | 'web_vital' // a Core Web Vitals metric was reported
  | 'js_error' // an uncaught JS error or unhandled rejection
  | 'event'; // a generic feature/funnel event via recordEvent()

/**
 * A JSON-serializable attribute value. We avoid `any`: attributes are scalars
 * (or undefined, which is dropped during serialization).
 */
export type TelemetryAttributeValue = string | number | boolean | undefined;

/**
 * A bag of structured attributes attached to an event.
 */
export type TelemetryAttributes = Record<string, TelemetryAttributeValue>;

/**
 * A single telemetry event. The sink is responsible for transporting these.
 */
export interface TelemetryEvent {
  /** Event category. */
  type: TelemetryEventType;
  /** Event name (e.g. RPC method, web-vital name, or a feature event name). */
  name: string;
  /** Epoch milliseconds when the event was recorded. */
  timestamp: number;
  /** Structured attributes. */
  attributes: TelemetryAttributes;
}

/**
 * A telemetry sink receives recorded events. Implementations may log, batch,
 * beacon, or drop them. `record` must never throw — telemetry must not break
 * the app.
 */
export interface TelemetrySink {
  record(event: TelemetryEvent): void;
  /** Optional flush hook (e.g. before page unload). */
  flush?(): void;
}

/**
 * Runtime configuration resolved from Vite env vars at init time.
 */
export interface TelemetryConfig {
  /** Whether we're running in a dev build (import.meta.env.DEV). */
  dev: boolean;
  /** Optional OTLP/HTTP JSON collector URL (VITE_TELEMETRY_OTLP_URL). */
  otlpUrl: string | undefined;
  /** Logical service name reported with every event. */
  serviceName: string;
}
