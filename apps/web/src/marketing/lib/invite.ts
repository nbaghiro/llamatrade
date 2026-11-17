/** Invite form rules: the waitlist endpoint on the auth service, the email check and the reply. */

export const INVITE_DONE_KEY = 'lt_waitlist';
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const JOIN_WAITLIST_PATH = '/llamatrade.AuthService/JoinWaitlist';

export type WaitlistSource = 'landing' | 'join';

export const INVITE_COPY = {
  done: "You're on the list. We'll email you when a place opens.",
  invalid: 'Please enter a valid email address.',
  closed: "Invites aren't open from this page yet.",
  mailed: 'Your email app should open with the request ready to send.',
  failed: "The request didn't go through. Please try again.",
  network: "The request couldn't be sent. Check your connection and try again.",
  rateLimited: 'Too many requests from this connection. Please wait a few minutes and try again.',
} as const;

/** A mailto link asking for an invite for `from`, or null without a usable address to send to. */
export function inviteMailto(address: string | undefined, from = ''): string | null {
  const to = address?.trim();
  if (!to || !EMAIL_RE.test(to)) return null;
  const subject = encodeURIComponent('LlamaTrade invite');
  const who = from.trim();
  const body = who
    ? `&body=${encodeURIComponent(`Please add ${who} to the LlamaTrade waitlist.`)}`
    : '';
  return `mailto:${to}?subject=${subject}${body}`;
}

const LOOPS_FORM_BASE = 'https://app.loops.so/api/newsletter-form/';
const LOOPS_ID_RE = /^[a-z0-9]+$/i;

/** The Loops form endpoint for `formId`, or null when no usable form ID is configured. */
export function loopsEndpoint(formId: string | undefined): string | null {
  const id = formId?.trim();
  if (!id || !LOOPS_ID_RE.test(id)) return null;
  return `${LOOPS_FORM_BASE}${id}`;
}

/** Form-encoded Loops body; `source` lands on the contact so landing and join signups stay apart. */
export function loopsBody(email: string, source: WaitlistSource): string {
  const params = new URLSearchParams({
    email: email.trim(),
    source: `waitlist-${source}`,
    userGroup: 'waitlist',
  });
  return params.toString();
}

/** Maps a Loops form reply: `{ success }` with 200, `{ success: false, message }` otherwise. */
export function readLoopsResponse(status: number, body: unknown): InviteResult {
  if (status === 429) return { ok: false, message: INVITE_COPY.rateLimited };
  const success =
    typeof body === 'object' && body !== null && 'success' in body && body.success === true;
  if (status >= 200 && status < 300 && success) return { ok: true };
  const message =
    typeof body === 'object' &&
    body !== null &&
    'message' in body &&
    typeof body.message === 'string'
      ? body.message
      : '';
  if (/email/i.test(message) && /invalid|valid/i.test(message)) {
    return { ok: false, message: INVITE_COPY.invalid };
  }
  return { ok: false, message: INVITE_COPY.failed };
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
