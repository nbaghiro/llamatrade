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
