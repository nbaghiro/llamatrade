/** Invite form rules: the Loops endpoint, the email check and the response. */

export const INVITE_DONE_KEY = 'lt_waitlist';
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PLACEHOLDER = 'REPLACE_WITH_LOOPS_FORM_ID';

export const INVITE_COPY = {
  done: "You're on the list. We'll email you when a place opens.",
  invalid: 'Please enter a valid email address.',
  closed: "Invites aren't open from this page yet.",
  failed: "The request didn't go through. Please try again.",
  network: "The request couldn't be sent. Check your connection and try again.",
} as const;

/** The Loops endpoint, or null when no real form id is configured. */
export function inviteEndpoint(formId: string | undefined): string | null {
  const id = formId?.trim();
  if (!id || id === PLACEHOLDER || !/^[A-Za-z0-9_-]+$/.test(id)) return null;
  return `https://app.loops.so/api/newsletter-form/${id}`;
}

export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim());
}

export function inviteBody(email: string): URLSearchParams {
  const body = new URLSearchParams();
  body.append('email', email.trim());
  body.append('source', 'landing');
  return body;
}

export type InviteResult = { ok: true } | { ok: false; message: string };

/** Loops answers `{ success, message }`; a body that isn't JSON falls back to the HTTP status. */
export function readInviteResponse(status: number, body: unknown): InviteResult {
  const ok = status >= 200 && status < 300;
  if (typeof body !== 'object' || body === null) {
    return ok ? { ok: true } : { ok: false, message: INVITE_COPY.failed };
  }
  const { success, message } = body as { success?: unknown; message?: unknown };
  if (success === true || (success === undefined && ok)) return { ok: true };
  return {
    ok: false,
    message: typeof message === 'string' && message.trim() ? message : INVITE_COPY.failed,
  };
}
