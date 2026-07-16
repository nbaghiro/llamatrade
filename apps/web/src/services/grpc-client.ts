/**
 * Connect client setup for the web app.
 *
 * The clients themselves live in @llamatrade/core (shared with mobile); this file
 * just configures them for the browser — service URLs from Vite env, the auth
 * token + tenant context from the auth store, and the telemetry interceptor.
 * Web uses the global `fetch` (no override).
 */
import { configure } from '@llamatrade/core/net';

import { getTenantContext, useAuthStore } from '../store/auth';
import { telemetryInterceptor } from '../telemetry';

configure({
  urls: {
    agent: import.meta.env.VITE_AGENT_URL || 'http://localhost:8990',
    auth: import.meta.env.VITE_AUTH_URL || 'http://localhost:8810',
    backtest: import.meta.env.VITE_BACKTEST_URL || 'http://localhost:8830',
    billing: import.meta.env.VITE_BILLING_URL || 'http://localhost:8880',
    marketData: import.meta.env.VITE_MARKET_DATA_URL || 'http://localhost:8840',
    notification: import.meta.env.VITE_NOTIFICATION_URL || 'http://localhost:8870',
    portfolio: import.meta.env.VITE_PORTFOLIO_URL || 'http://localhost:8860',
    strategy: import.meta.env.VITE_STRATEGY_URL || 'http://localhost:8820',
    trading: import.meta.env.VITE_TRADING_URL || 'http://localhost:8850',
  },
  getToken: () => useAuthStore.getState().accessToken,
  getTenantContext,
  onUnauthenticated: () => {
    if (useAuthStore.getState().isAuthenticated) useAuthStore.getState().logout();
  },
  // telemetry first (outermost) so it times the full call and sets traceparent
  extraInterceptors: [telemetryInterceptor],
});

export {
  agentClient,
  authClient,
  backtestClient,
  billingClient,
  // LedgerService is served by the portfolio process (book-of-record kernel).
  ledgerClient,
  marketDataClient,
  notificationClient,
  portfolioClient,
  strategyClient,
  tradingClient,
} from '@llamatrade/core/net';

// Feature flag - Connect is always enabled
export const grpcEnabled = true;
