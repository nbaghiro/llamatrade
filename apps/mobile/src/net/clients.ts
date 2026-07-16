/**
 * Configures @llamatrade/core's Connect clients for React Native, then re-exports
 * the shared client proxies so existing imports keep working.
 *
 * The one native-specific line is `fetch: expoFetch` — Expo's WinterCG fetch
 * exposes a streaming `response.body`, which is what lets server-streaming RPCs
 * (agent.streamMessage, backtest.streamBacktestProgress) deliver chunk-by-chunk.
 */
import {
  agentClient,
  authClient,
  backtestClient,
  billingClient,
  configure,
  marketDataClient,
  notificationClient,
  portfolioClient,
  strategyClient,
  tradingClient,
} from '@llamatrade/core/net';
import { fetch as expoFetch } from 'expo/fetch';

import { tenantContext, useAuthStore } from '../stores/auth';
import { serviceUrls } from './config';

configure({
  urls: serviceUrls,
  getToken: () => useAuthStore.getState().accessToken,
  getTenantContext: () => tenantContext(),
  onUnauthenticated: () => useAuthStore.getState().logout(),
  // On a 401, mint a fresh access token from the stored refresh token and retry
  // once — so a 30-min access-token expiry doesn't bounce the user to login.
  refreshTokens: async () => {
    const { refreshToken, updateTokens } = useAuthStore.getState();
    if (!refreshToken) return false;
    try {
      const res = await authClient.refreshToken({ refreshToken });
      if (!res.accessToken) return false;
      updateTokens(res.accessToken, res.refreshToken || refreshToken);
      return true;
    } catch {
      return false;
    }
  },
  fetch: expoFetch as unknown as typeof globalThis.fetch,
});

export {
  agentClient,
  authClient,
  backtestClient,
  billingClient,
  marketDataClient,
  notificationClient,
  portfolioClient,
  strategyClient,
  tradingClient,
};
