/**
 * Service endpoint configuration — platform-neutral.
 *
 * The web app reads these from `import.meta.env.VITE_*`; the mobile app reads
 * them from `process.env.EXPO_PUBLIC_*` (via app config). Both build a
 * `ServiceUrls` and hand it to `createClients` so this package never touches a
 * platform-specific env API.
 */

export interface ServiceUrls {
  agent: string;
  auth: string;
  backtest: string;
  billing: string;
  marketData: string;
  notification: string;
  portfolio: string;
  strategy: string;
  trading: string;
}

export type ServiceName = keyof ServiceUrls;

/** Local dev defaults (per-service ports), mirroring apps/web/src/services/grpc-client.ts. */
export const LOCAL_SERVICE_URLS: ServiceUrls = {
  agent: 'http://localhost:8990',
  auth: 'http://localhost:8810',
  backtest: 'http://localhost:8830',
  billing: 'http://localhost:8880',
  marketData: 'http://localhost:8840',
  notification: 'http://localhost:8870',
  portfolio: 'http://localhost:8860',
  strategy: 'http://localhost:8820',
  trading: 'http://localhost:8850',
};
