/**
 * Alpaca OAuth browser flows. These hit the auth service's plain HTTP routes
 * (OAuth is redirect-based, so not Connect RPCs). The auth base URL mirrors the
 * Connect client config in `grpc-client.ts`.
 */
import type { AuthUser } from '../store/auth';

const AUTH_URL = import.meta.env.VITE_AUTH_URL || 'http://localhost:8810';

export interface OAuthSession {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
}

export interface CompleteSignupPayload {
  ticket: string;
  email: string;
  password: string;
  firstName?: string;
  lastName?: string;
  /** Sign-up is invite-only; the auth service checks this against the email. */
  inviteCode?: string;
}

/** Full-page redirect to Alpaca to sign in / sign up (no session yet). */
export function startAuthWithAlpaca(): void {
  window.location.href = `${AUTH_URL}/oauth/alpaca/authorize?intent=auth`;
}

/** From Settings (authenticated): fetch the authorize URL, then redirect. */
export async function startAlpacaLink(accessToken: string): Promise<void> {
  const res = await fetch(`${AUTH_URL}/oauth/alpaca/start`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error('Could not start the Alpaca connection.');
  const body = (await res.json().catch(() => null)) as { authorizeUrl?: unknown } | null;
  const authorizeUrl = body?.authorizeUrl;
  if (typeof authorizeUrl !== 'string' || !/^https?:\/\//.test(authorizeUrl)) {
    throw new Error('Could not start the Alpaca connection.');
  }
  window.location.href = authorizeUrl;
}

/** Exchange a one-time login handoff code for a session. */
export async function exchangeHandoff(handoff: string): Promise<OAuthSession> {
  const res = await fetch(`${AUTH_URL}/oauth/alpaca/exchange`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ handoff }),
  });
  if (!res.ok) throw new Error('This sign-in link has expired. Please try again.');
  return (await res.json()) as OAuthSession;
}

/** Finish sign-up-with-Alpaca: create the account and return a session. */
export async function completeAlpacaSignup(payload: CompleteSignupPayload): Promise<OAuthSession> {
  const res = await fetch(`${AUTH_URL}/oauth/alpaca/complete-signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail || 'Could not complete sign up.');
  }
  return (await res.json()) as OAuthSession;
}

/** Plain copy for the `error` Alpaca returns when a link round trip doesn't finish. */
export function alpacaLinkErrorMessage(code: string): string {
  if (code === 'access_denied') {
    return 'The connection was cancelled on Alpaca, so nothing was connected.';
  }
  return "Alpaca didn't finish connecting, so nothing was changed. Please try again.";
}

/** Only an in-app path is accepted as a place to return to after connecting. */
export function safeReturnPath(next: string | null, fallback = '/dashboard'): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : fallback;
}
