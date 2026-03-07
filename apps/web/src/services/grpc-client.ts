/**
 * Connect client setup for direct service communication.
 *
 * Uses Connect protocol over HTTP/1.1 for browser compatibility.
 * No proxy required - browsers connect directly to services.
 *
 * Usage:
 *   import { marketDataClient, tradingClient } from './grpc-client';
 *
 *   const bars = await marketDataClient.getHistoricalBars({
 *     symbol: 'AAPL',
 *     timeframe: 'TIMEFRAME_1DAY',
 *   });
 */

import { createClient, type Interceptor } from '@connectrpc/connect';
import { createConnectTransport } from '@connectrpc/connect-web';

import { AuthService } from '../generated/proto/auth_pb';
import { BacktestService } from '../generated/proto/backtest_pb';
import { BillingService } from '../generated/proto/billing_pb';
import { MarketDataService } from '../generated/proto/market_data_pb';
import { NotificationService } from '../generated/proto/notification_pb';
import { PortfolioService } from '../generated/proto/portfolio_pb';
import { StrategyService } from '../generated/proto/strategy_pb';
import { TradingService } from '../generated/proto/trading_pb';
import { useAuthStore } from '../store/auth';

// Direct service URLs (no proxy needed)
const SERVICE_URLS = {
  auth: import.meta.env.VITE_AUTH_URL || 'http://localhost:8810',
  backtest: import.meta.env.VITE_BACKTEST_URL || 'http://localhost:8830',
  billing: import.meta.env.VITE_BILLING_URL || 'http://localhost:8880',
  marketData: import.meta.env.VITE_MARKET_DATA_URL || 'http://localhost:8840',
  notification: import.meta.env.VITE_NOTIFICATION_URL || 'http://localhost:8870',
  portfolio: import.meta.env.VITE_PORTFOLIO_URL || 'http://localhost:8860',
  strategy: import.meta.env.VITE_STRATEGY_URL || 'http://localhost:8820',
  trading: import.meta.env.VITE_TRADING_URL || 'http://localhost:8850',
};

/**
 * Authentication interceptor.
 * Adds Bearer token to requests if available.
 * Skips auth for login/register endpoints.
 */
const authInterceptor: Interceptor = (next) => async (req) => {
  // Don't send auth for public endpoints
  const publicMethods = ['Login', 'Register', 'RefreshToken'];
  const methodName = req.method.name;

  if (!publicMethods.includes(methodName)) {
    const token = useAuthStore.getState().accessToken;
    if (token) {
      req.header.set('Authorization', `Bearer ${token}`);
    }
  }
  return next(req);
};

/**
 * Create Connect transport for a service.
 * Uses JSON format for easy debugging in browser DevTools.
 */
function createServiceTransport(baseUrl: string) {
  return createConnectTransport({
    baseUrl,
    interceptors: [authInterceptor],
    useBinaryFormat: false, // JSON for debugging - set to true for production
  });
}

// ============================================================================
// Service clients - each connects directly to its service
// ============================================================================

export const authClient = createClient(
  AuthService,
  createServiceTransport(SERVICE_URLS.auth)
);

export const backtestClient = createClient(
  BacktestService,
  createServiceTransport(SERVICE_URLS.backtest)
);

export const billingClient = createClient(
  BillingService,
  createServiceTransport(SERVICE_URLS.billing)
);

export const marketDataClient = createClient(
  MarketDataService,
  createServiceTransport(SERVICE_URLS.marketData)
);

export const notificationClient = createClient(
  NotificationService,
  createServiceTransport(SERVICE_URLS.notification)
);

export const portfolioClient = createClient(
  PortfolioService,
  createServiceTransport(SERVICE_URLS.portfolio)
);

export const strategyClient = createClient(
  StrategyService,
  createServiceTransport(SERVICE_URLS.strategy)
);

export const tradingClient = createClient(
  TradingService,
  createServiceTransport(SERVICE_URLS.trading)
);

// Feature flag - Connect is always enabled
export const grpcEnabled = true;
