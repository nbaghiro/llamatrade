/** Invite form rules: the waitlist endpoint on the auth service, the email check and the reply. */

export const INVITE_DONE_KEY = 'lt_waitlist';
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const JOIN_WAITLIST_PATH = '/llamatrade.AuthService/JoinWaitlist';

export type WaitlistSource = 'landing' | 'join';

export const INVITE_COPY = {
  done: "You're on the list. We'll email you when a place opens.",
  invalid: 'Please enter a valid email address.',
  closed: "Invites aren't open from this page yet.",
  failed: "The request didn't go through. Please try again.",
  network: "The request couldn't be sent. Check your connection and try again.",
  rateLimited: 'Too many requests from this connection. Please wait a few minutes and try again.',
} as const;

/** A mailto link for asking for an invite by email, or null without a usable address. */
export function inviteMailto(address: string | undefined): string | null {
  const to = address?.trim();
  if (!to || !EMAIL_RE.test(to)) return null;
  return `mailto:${to}?subject=${encodeURIComponent('LlamaTrade invite')}`;
}

/** The JoinWaitlist URL on the auth service, or null when no usable base URL is configured. */
export function waitlistEndpoint(authUrl: string | undefined): string | null {
  const base = authUrl?.trim();
  if (!base) return null;
  let url: URL;
  try {
    url = new URL(base);
  } catch {
    return null;
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
  if (url.search || url.hash) return null;
  return `${url.origin}${url.pathname.replace(/\/+$/, '')}${JOIN_WAITLIST_PATH}`;
}

export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim());
}

/** Connect JSON request body; `company` is the honeypot the server checks. */
export function waitlistBody(email: string, source: WaitlistSource, company: string): string {
  return JSON.stringify({ email: email.trim(), source, company });
}

export type InviteResult = { ok: true } | { ok: false; message: string };

function connectCode(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null || !('code' in body)) return undefined;
  return typeof body.code === 'string' ? body.code : undefined;
}

/** Maps a Connect reply: `{ success }` on 2xx, `{ code, message }` on an error status. */
export function readInviteResponse(status: number, body: unknown): InviteResult {
  if (status >= 200 && status < 300) {
    const refused =
      typeof body === 'object' && body !== null && 'success' in body && body.success === false;
    return refused ? { ok: false, message: INVITE_COPY.failed } : { ok: true };
  }
  const code = connectCode(body);
  if (status === 429 || code === 'resource_exhausted') {
    return { ok: false, message: INVITE_COPY.rateLimited };
  }
  if (code === 'invalid_argument') return { ok: false, message: INVITE_COPY.invalid };
  return { ok: false, message: INVITE_COPY.failed };
}
