/// <reference types="vite/client" />

/**
 * Typed Vite environment variables.
 *
 * Vite exposes `import.meta.env` with a permissive index signature by default.
 * Declaring the variables we rely on here keeps access strict and discoverable.
 */
interface ImportMetaEnv {
  // Direct Connect service URLs.
  readonly VITE_AGENT_URL?: string;
  readonly VITE_AUTH_URL?: string;
  readonly VITE_BACKTEST_URL?: string;
  readonly VITE_BILLING_URL?: string;
  readonly VITE_MARKET_DATA_URL?: string;
  readonly VITE_NOTIFICATION_URL?: string;
  readonly VITE_PORTFOLIO_URL?: string;
  readonly VITE_STRATEGY_URL?: string;
  readonly VITE_TRADING_URL?: string;

  // Real-time + billing.
  readonly VITE_WS_URL?: string;
  readonly VITE_STRIPE_PUBLISHABLE_KEY?: string;

  // Optional OTLP/HTTP JSON collector for browser telemetry. When unset,
  // telemetry falls back to console (dev) or a no-op (prod).
  readonly VITE_TELEMETRY_OTLP_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
