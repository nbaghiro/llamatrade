import { Code, ConnectError } from '@connectrpc/connect';
import { describe, expect, it } from 'vitest';

import {
  UNREACHABLE,
  authErrorMessage,
  isUnreachable,
  registerError,
  signInError,
} from '../errors';

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

describe('registerError', () => {
  it('puts invite code problems under the invite field, in the server words', () => {
    const err = new ConnectError('That invite code has already been used.', Code.InvalidArgument);
    expect(registerError(err)).toEqual({
      field: 'inviteCode',
      message: 'That invite code has already been used.',
    });
  });

  it('puts a taken email under the email field', () => {
    const err = new ConnectError('Email already registered', Code.AlreadyExists);
    expect(registerError(err).field).toBe('email');
  });

  it('puts the password policy under the password field as a sentence', () => {
    const err = new ConnectError('password must be at least 8 characters', Code.InvalidArgument);
    expect(registerError(err)).toEqual({
      field: 'password',
      message: 'Password must be at least 8 characters.',
    });
  });

  it('falls back to a form note for anything else', () => {
    expect(registerError(new ConnectError('upstream', Code.Unavailable))).toEqual({
      field: null,
      message: UNREACHABLE,
    });
    expect(registerError(null).field).toBeNull();
  });
});

describe('signInError', () => {
  it('puts wrong credentials under the password field', () => {
    const err = new ConnectError('Invalid email or password', Code.Unauthenticated);
    expect(signInError(err).field).toContain("don't match");
    expect(signInError(err).form).toBe('');
  });
});
