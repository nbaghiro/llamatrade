import { Code, ConnectError } from '@connectrpc/connect';
import { describe, expect, it } from 'vitest';

import { UNREACHABLE, authErrorMessage, isUnreachable } from '../errors';

describe('authErrorMessage', () => {
  it('replaces network failures with a plain unreachable message', () => {
    expect(authErrorMessage(new ConnectError('Failed to fetch', Code.Unknown), 'x')).toBe(
      UNREACHABLE
    );
    expect(authErrorMessage(new ConnectError('upstream', Code.Unavailable), 'x')).toBe(UNREACHABLE);
    expect(authErrorMessage(new TypeError('Failed to fetch'), 'x')).toBe(UNREACHABLE);
  });

  it("keeps the server's reason for a rejected request", () => {
    const err = new ConnectError('Invalid email or password', Code.Unauthenticated);
    expect(authErrorMessage(err, 'x')).toBe('Invalid email or password');
  });

  it('falls back when the server gave no reason', () => {
    expect(authErrorMessage(new ConnectError('', Code.InvalidArgument), 'Fallback')).toBe(
      'Fallback'
    );
    expect(authErrorMessage('nope', 'Fallback')).toBe('Fallback');
  });

  it('keeps messages thrown by the OAuth helpers', () => {
    expect(authErrorMessage(new Error('Could not complete sign up.'), 'x')).toBe(
      'Could not complete sign up.'
    );
  });
});

describe('isUnreachable', () => {
  it('treats a used or expired token as an answer, not an outage', () => {
    expect(isUnreachable(new ConnectError('expired', Code.InvalidArgument))).toBe(false);
    expect(isUnreachable(new ConnectError('down', Code.Unavailable))).toBe(true);
  });
});
