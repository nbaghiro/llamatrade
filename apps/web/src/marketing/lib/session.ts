/** Whether a visitor is signed in to the app, read from the app's persisted auth store. */

/** Must match the persist `name` in apps/core/src/stores/auth.ts; the site and app share an origin. */
export const AUTH_STORAGE_KEY = 'llamatrade-auth';

/** True when the JWT is missing, malformed or past its `exp`; mirrors core's isTokenExpired. */
export function tokenExpired(token: string | null | undefined, now = Date.now()): boolean {
  if (!token) return true;
  try {
    const { exp } = JSON.parse(atob(token.split('.')[1])) as { exp?: unknown };
    return typeof exp !== 'number' || exp * 1000 <= now;
  } catch {
    return true;
  }
}

/** Signed in the same way the app's "/" decides it: authenticated with a live access token. */
export function readSignedIn(raw: string | null, now = Date.now()): boolean {
  if (!raw) return false;
  try {
    const { state } = JSON.parse(raw) as {
      state?: { isAuthenticated?: unknown; accessToken?: unknown };
    };
    const token = typeof state?.accessToken === 'string' ? state.accessToken : null;
    return state?.isAuthenticated === true && !tokenExpired(token, now);
  } catch {
    return false;
  }
}

/**
 * A link into the app. Served inside the app, paths stay relative. The standalone build links to
 * `appUrl` when it's set and hides app links when it isn't.
 */
export function appHref(
  path: string,
  { standalone, appUrl }: { standalone: boolean; appUrl?: string }
): string | null {
  if (!standalone) return path;
  if (!appUrl) return null;
  return `${appUrl.replace(/\/+$/, '')}${path}`;
}
