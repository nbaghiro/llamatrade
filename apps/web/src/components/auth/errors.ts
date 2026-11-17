import { Code, ConnectError } from '@connectrpc/connect';

export const UNREACHABLE = "LlamaTrade couldn't be reached. Check your connection and try again.";

const TRANSIENT: ReadonlySet<Code> = new Set([
  Code.Unavailable,
  Code.Unknown,
  Code.DeadlineExceeded,
  Code.Internal,
  Code.Canceled,
  Code.Aborted,
]);

/** A failure of the network or the service rather than an answer about the request. */
export function isUnreachable(err: unknown): boolean {
  if (err instanceof ConnectError) return TRANSIENT.has(err.code);
  return err instanceof TypeError;
}

/** The message to show for a failed auth request: the server's own words when it gave a reason. */
export function authErrorMessage(err: unknown, fallback: string): string {
  if (isUnreachable(err)) return UNREACHABLE;
  if (err instanceof ConnectError) return err.rawMessage || fallback;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

const WRONG_PASSWORD = "That email and password don't match. Check both, or reset your password.";

/** Wrong credentials belong under the password field; anything else is a note over the form. */
export function signInError(err: unknown): { field: string; form: string } {
  if (err instanceof ConnectError && err.code === Code.Unauthenticated) {
    return { field: WRONG_PASSWORD, form: '' };
  }
  return {
    field: '',
    form: authErrorMessage(
      err,
      "You couldn't be signed in. Please check your details and try again."
    ),
  };
}

export type RegisterField = 'inviteCode' | 'email' | 'password';

const sentence = (s: string) => {
  const t = s.trim();
  if (!t) return t;
  const cap = t.charAt(0).toUpperCase() + t.slice(1);
  return /[.!?]$/.test(cap) ? cap : `${cap}.`;
};

/** Which field a failed sign-up belongs under, with the words to show there. */
export function registerError(err: unknown): { field: RegisterField | null; message: string } {
  const fallback = "The account couldn't be created. Please try again.";
  if (isUnreachable(err)) return { field: null, message: UNREACHABLE };
  const raw =
    err instanceof ConnectError ? err.rawMessage : err instanceof Error ? err.message : '';
  if (/invite code/i.test(raw)) return { field: 'inviteCode', message: sentence(raw) };
  if (err instanceof ConnectError && err.code === Code.AlreadyExists) {
    return {
      field: 'email',
      message: 'An account already uses this email address. Sign in, or reset your password.',
    };
  }
  if (/^password/i.test(raw)) return { field: 'password', message: sentence(raw) };
  return { field: null, message: raw ? sentence(raw) : fallback };
}
