/**
 * Mobile service URLs — read from EXPO_PUBLIC_* env (set via app config / EAS),
 * falling back to the local dev ports. On a device, `localhost` is the device
 * itself, so point these at your machine's LAN IP (e.g. http://192.168.1.20:8990).
 */
import { LOCAL_SERVICE_URLS, type ServiceUrls } from '@llamatrade/core/net';

const e = process.env;

export const serviceUrls: ServiceUrls = {
  agent: e.EXPO_PUBLIC_AGENT_URL ?? LOCAL_SERVICE_URLS.agent,
  auth: e.EXPO_PUBLIC_AUTH_URL ?? LOCAL_SERVICE_URLS.auth,
  backtest: e.EXPO_PUBLIC_BACKTEST_URL ?? LOCAL_SERVICE_URLS.backtest,
  billing: e.EXPO_PUBLIC_BILLING_URL ?? LOCAL_SERVICE_URLS.billing,
  marketData: e.EXPO_PUBLIC_MARKET_DATA_URL ?? LOCAL_SERVICE_URLS.marketData,
  notification: e.EXPO_PUBLIC_NOTIFICATION_URL ?? LOCAL_SERVICE_URLS.notification,
  portfolio: e.EXPO_PUBLIC_PORTFOLIO_URL ?? LOCAL_SERVICE_URLS.portfolio,
  strategy: e.EXPO_PUBLIC_STRATEGY_URL ?? LOCAL_SERVICE_URLS.strategy,
  trading: e.EXPO_PUBLIC_TRADING_URL ?? LOCAL_SERVICE_URLS.trading,
};
