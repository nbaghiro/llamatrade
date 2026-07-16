/**
 * Connect transport factory — platform-neutral.
 *
 * The web app and the mobile app share this factory; the ONLY difference is the
 * `fetch` they inject. On the web, omit it (Connect uses the global `fetch`). On
 * React Native, pass `expo/fetch` (or a streaming-fetch polyfill) — its
 * streaming `response.body` is what lets server-streaming RPCs (Copilot,
 * backtest progress) deliver chunk-by-chunk instead of buffering. See the
 * architecture spec's streaming spike.
 *
 * This module imports NO store and NO generated proto, so it stays reusable and
 * type-checks without native deps.
 */

import { Code, ConnectError, type Interceptor } from '@connectrpc/connect';
import { createConnectTransport } from '@connectrpc/connect-web';

/** Public methods that must NOT carry a bearer token (they mint/refresh it). */
const PUBLIC_METHODS = ['Login', 'Register', 'RefreshToken'];

/** Attach `Authorization: Bearer <token>` to non-public calls. */
export function authInterceptor(getToken: () => string | null | undefined): Interceptor {
  return (next) => async (req) => {
    if (!PUBLIC_METHODS.includes(req.method.name)) {
      const token = getToken();
      if (token) {
        req.header.set('Authorization', `Bearer ${token}`);
      }
    }
    return next(req);
  };
}

/**
 * On an UNAUTHENTICATED response: if a `refreshTokens` callback is provided, try
 * to mint a fresh access token (concurrent 401s share one in-flight refresh) and
 * retry the call once. Only when refresh is absent or fails do we drop the
 * session via `onUnauthenticated`. Public methods bypass this entirely.
 */
export function authRetryInterceptor(opts: {
  onUnauthenticated?: () => void;
  refreshTokens?: () => Promise<boolean>;
}): Interceptor {
  let inflight: Promise<boolean> | null = null;
  const refresh = (): Promise<boolean> => {
    if (!opts.refreshTokens) return Promise.resolve(false);
    if (!inflight) {
      inflight = opts.refreshTokens().finally(() => {
        inflight = null;
      });
    }
    return inflight;
  };

  return (next) => async (req) => {
    if (PUBLIC_METHODS.includes(req.method.name)) return next(req);
    try {
      return await next(req);
    } catch (err) {
      if (!(err instanceof ConnectError) || err.code !== Code.Unauthenticated) throw err;
      if (opts.refreshTokens && (await refresh())) {
        try {
          // Re-runs the inner auth interceptor, which reads the refreshed token.
          return await next(req);
        } catch (retryErr) {
          if (retryErr instanceof ConnectError && retryErr.code === Code.Unauthenticated) {
            opts.onUnauthenticated?.();
          }
          throw retryErr;
        }
      }
      opts.onUnauthenticated?.();
      throw err;
    }
  };
}

export interface TransportOptions {
  /** Reads the current access token (e.g. from the auth store). */
  getToken: () => string | null | undefined;
  /** Called when the server rejects a call as UNAUTHENTICATED (after a failed/absent refresh). */
  onUnauthenticated?: () => void;
  /**
   * Refresh the access token (e.g. via the RefreshToken RPC + session update),
   * resolving true on success. When present, a 401 triggers a refresh + one
   * retry before the session is dropped. Omit to keep drop-on-401 behavior.
   */
  refreshTokens?: () => Promise<boolean>;
  /**
   * Fetch implementation. Omit on web (uses global fetch). On React Native pass
   * a streaming-capable fetch (`expo/fetch`) — required for server-streaming.
   */
  fetch?: typeof globalThis.fetch;
  /** JSON (false, default — debuggable) vs binary protobuf. */
  useBinaryFormat?: boolean;
  /** Prepended (outermost) — e.g. telemetry. */
  extraInterceptors?: Interceptor[];
}

/** Build a Connect transport for a single service base URL. */
export function makeTransport(baseUrl: string, opts: TransportOptions) {
  const interceptors: Interceptor[] = [
    ...(opts.extraInterceptors ?? []),
    authRetryInterceptor({ onUnauthenticated: opts.onUnauthenticated, refreshTokens: opts.refreshTokens }),
    authInterceptor(opts.getToken),
  ];
  return createConnectTransport({
    baseUrl,
    useBinaryFormat: opts.useBinaryFormat ?? false,
    interceptors,
    ...(opts.fetch ? { fetch: opts.fetch } : {}),
  });
}
