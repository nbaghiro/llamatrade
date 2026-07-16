/**
 * Configured Connect clients — the single client set for both apps.
 *
 * Each app calls `configure()` once at startup with its platform bits (service
 * URLs, token accessor, tenant-context accessor, and — on native — a streaming
 * `fetch`). Stores then import the named client proxies (`portfolioClient`, …)
 * and call them exactly as the web code always has.
 */
import { createClient, type Client } from '@connectrpc/connect';

import { AgentService } from '../proto/agent_pb';
import { AuthService } from '../proto/auth_pb';
import { BacktestService } from '../proto/backtest_pb';
import { BillingService } from '../proto/billing_pb';
import { LedgerService } from '../proto/ledger_pb';
import { MarketDataService } from '../proto/market_data_pb';
import { NotificationService } from '../proto/notification_pb';
import { PortfolioService } from '../proto/portfolio_pb';
import { StrategyService } from '../proto/strategy_pb';
import { TradingService } from '../proto/trading_pb';

import type { ServiceUrls } from './config';
import { makeTransport, type TransportOptions } from './transport';

export interface TenantCtx {
  tenantId: string;
  userId: string;
  roles?: string[];
}

const SERVICES = {
  agent: AgentService,
  auth: AuthService,
  backtest: BacktestService,
  billing: BillingService,
  ledger: LedgerService,
  marketData: MarketDataService,
  notification: NotificationService,
  portfolio: PortfolioService,
  strategy: StrategyService,
  trading: TradingService,
} as const;

type ServiceKey = keyof typeof SERVICES;
type ClientMap = { [K in ServiceKey]: Client<(typeof SERVICES)[K]> };

/** Which service URL each client uses. Ledger is served by the portfolio process. */
const URL_FOR: Record<ServiceKey, keyof ServiceUrls> = {
  agent: 'agent',
  auth: 'auth',
  backtest: 'backtest',
  billing: 'billing',
  ledger: 'portfolio',
  marketData: 'marketData',
  notification: 'notification',
  portfolio: 'portfolio',
  strategy: 'strategy',
  trading: 'trading',
};

let _clients: ClientMap | null = null;
let _getTenantContext: () => TenantCtx | undefined = () => undefined;

export interface ConfigureOptions {
  urls: ServiceUrls;
  getToken: () => string | null | undefined;
  getTenantContext: () => TenantCtx | undefined;
  onUnauthenticated?: () => void;
  /** Refresh the access token on a 401 and retry once (see TransportOptions). */
  refreshTokens?: () => Promise<boolean>;
  /** Native only: streaming-capable fetch (expo/fetch). Omit on web. */
  fetch?: typeof globalThis.fetch;
  /** Prepended (outermost) — e.g. telemetry. */
  extraInterceptors?: TransportOptions['extraInterceptors'];
}

export function configure(opts: ConfigureOptions): void {
  const tOpts: TransportOptions = {
    getToken: opts.getToken,
    onUnauthenticated: opts.onUnauthenticated,
    ...(opts.refreshTokens ? { refreshTokens: opts.refreshTokens } : {}),
    ...(opts.fetch ? { fetch: opts.fetch } : {}),
    ...(opts.extraInterceptors ? { extraInterceptors: opts.extraInterceptors } : {}),
  };
  const map: Record<string, unknown> = {};
  (Object.keys(SERVICES) as ServiceKey[]).forEach((k) => {
    map[k] = createClient(SERVICES[k], makeTransport(opts.urls[URL_FOR[k]], tOpts));
  });
  _clients = map as ClientMap;
  _getTenantContext = opts.getTenantContext;
}

export function getClients(): ClientMap {
  if (!_clients) {
    throw new Error('@llamatrade/core: configure() must be called before using clients');
  }
  return _clients;
}

export function getTenantContext(): TenantCtx | undefined {
  return _getTenantContext();
}

/** Lazy proxy so `portfolioClient.listPortfolios(...)` resolves the configured client at call time. */
function lazyClient<K extends ServiceKey>(key: K): ClientMap[K] {
  return new Proxy({} as object, {
    get: (_t, prop) => (getClients()[key] as Record<string | symbol, unknown>)[prop],
  }) as ClientMap[K];
}

export const agentClient = lazyClient('agent');
export const authClient = lazyClient('auth');
export const backtestClient = lazyClient('backtest');
export const billingClient = lazyClient('billing');
export const ledgerClient = lazyClient('ledger');
export const marketDataClient = lazyClient('marketData');
export const notificationClient = lazyClient('notification');
export const portfolioClient = lazyClient('portfolio');
export const strategyClient = lazyClient('strategy');
export const tradingClient = lazyClient('trading');
