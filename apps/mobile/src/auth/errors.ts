/** What a failed auth request means for the form: which field it belongs under and what to say. */

/** Connect status codes this module reads (see @connectrpc/connect `Code`). */
export const RpcCode = {
  Canceled: 1,
  Unknown: 2,
  InvalidArgument: 3,
  DeadlineExceeded: 4,
  NotFound: 5,
  AlreadyExists: 6,
  PermissionDenied: 7,
  ResourceExhausted: 8,
  Aborted: 10,
  Internal: 13,
  Unavailable: 14,
  Unauthenticated: 16,
} as const;

/** A failure reduced to plain data: the Connect code when there was one, and the server's words. */
export interface AuthFailure {
  code: number | null;
  message: string;
  /** True when the request never got an answer (a fetch TypeError). */
  network?: boolean;
}

export const UNREACHABLE = "LlamaTrade couldn't be reached. Check your connection and try again.";
export const WRONG_PASSWORD = "That email and password don't match. Check both, or reset your password.";
export const TOO_MANY = 'Too many attempts. Wait a few minutes, then try again or reset your password.';

const TRANSIENT: ReadonlySet<number> = new Set([
  RpcCode.Unavailable,
  RpcCode.Unknown,
  RpcCode.DeadlineExceeded,
  RpcCode.Internal,
  RpcCode.Canceled,
  RpcCode.Aborted,
]);

export function isUnreachable(f: AuthFailure): boolean {
  return f.network === true || (f.code !== null && TRANSIENT.has(f.code));
}

function sentence(s: string): string {
  const t = s.trim();
  if (!t) return t;
  const cap = t.charAt(0).toUpperCase() + t.slice(1);
  return /[.!?]$/.test(cap) ? cap : `${cap}.`;
}

export type SignInField = 'email' | 'password';

export interface FieldErrors<F extends string> {
  field: F | null;
  message: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Checks the sign-in form before it is sent. */
export function checkSignIn(email: string, password: string): FieldErrors<SignInField> | null {
  if (!email.trim()) return { field: 'email', message: 'Enter the email address you signed up with.' };
  if (!EMAIL_RE.test(email.trim())) return { field: 'email', message: "That doesn't look like an email address. Check for a typo." };
  if (!password) return { field: 'password', message: 'Enter your password.' };
  return null;
}

/** Wrong credentials go under the password field; anything else is a note over the form. */
export function signInError(f: AuthFailure): FieldErrors<SignInField> {
  if (isUnreachable(f)) return { field: null, message: UNREACHABLE };
  if (f.code === RpcCode.Unauthenticated) return { field: 'password', message: WRONG_PASSWORD };
  if (f.code === RpcCode.ResourceExhausted) return { field: null, message: TOO_MANY };
  if (f.code === RpcCode.PermissionDenied) {
    return { field: null, message: 'This account is switched off. Email support to have it turned back on.' };
  }
  return { field: null, message: f.message ? sentence(f.message) : "You couldn't be signed in. Please try again." };
}

export type RegisterField = 'workspace' | 'email' | 'password' | 'inviteCode';

export function checkRegister(input: {
  workspace: string;
  email: string;
  password: string;
  inviteCode: string;
}): FieldErrors<RegisterField> | null {
  if (!input.workspace.trim()) return { field: 'workspace', message: 'Give the workspace a name. You can change it later.' };
  if (!EMAIL_RE.test(input.email.trim())) return { field: 'email', message: 'Use the address your invite was sent to.' };
  if (input.password.length < 8) return { field: 'password', message: 'Use at least 8 characters.' };
  if (!input.inviteCode.trim()) return { field: 'inviteCode', message: 'Enter the code from your invite email.' };
  return null;
}

/** Which field a failed sign-up belongs under, with the words to show there. */
export function registerError(f: AuthFailure): FieldErrors<RegisterField> {
  if (isUnreachable(f)) return { field: null, message: UNREACHABLE };
  if (/invite code/i.test(f.message)) return { field: 'inviteCode', message: sentence(f.message) };
  if (f.code === RpcCode.AlreadyExists) {
    return { field: 'email', message: 'An account already uses this email address. Sign in, or reset your password.' };
  }
  if (/^password/i.test(f.message)) return { field: 'password', message: sentence(f.message) };
  return { field: null, message: f.message ? sentence(f.message) : "The account couldn't be created. Please try again." };
}

/** The states the reset screen can be in. */
export type ResetState = 'request' | 'sent' | 'choose' | 'expired' | 'done';

/** A failed ResetPassword: an expired or used link changes the whole screen; a weak password stays on the field. */
export function resetError(f: AuthFailure): { state: ResetState; message: string } {
  if (isUnreachable(f)) return { state: 'choose', message: UNREACHABLE };
  if (/expired|invalid.*link|reset link/i.test(f.message)) return { state: 'expired', message: '' };
  return { state: 'choose', message: f.message ? sentence(f.message) : "The password couldn't be changed. Please try again." };
}
