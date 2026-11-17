import { describe, expect, it } from 'vitest';

import {
  INVITE_COPY,
  inviteMailto,
  isValidEmail,
  readInviteResponse,
  waitlistBody,
  waitlistEndpoint,
} from '../lib/invite';

describe('waitlistEndpoint', () => {
  it('appends the JoinWaitlist route to the auth base URL', () => {
    expect(waitlistEndpoint('http://localhost:8810')).toBe(
      'http://localhost:8810/llamatrade.AuthService/JoinWaitlist'
    );
    expect(waitlistEndpoint(' https://auth.example.com/ ')).toBe(
      'https://auth.example.com/llamatrade.AuthService/JoinWaitlist'
    );
  });

  it('keeps a path prefix on the base URL', () => {
    expect(waitlistEndpoint('https://example.com/api/auth//')).toBe(
      'https://example.com/api/auth/llamatrade.AuthService/JoinWaitlist'
    );
  });

  it('is closed when the base URL is unset or blank', () => {
    expect(waitlistEndpoint(undefined)).toBeNull();
    expect(waitlistEndpoint('')).toBeNull();
    expect(waitlistEndpoint('   ')).toBeNull();
  });

  it('rejects values that are not a plain http(s) base URL', () => {
    expect(waitlistEndpoint('localhost:8810')).toBeNull();
    expect(waitlistEndpoint('/auth')).toBeNull();
    expect(waitlistEndpoint('javascript:alert(1)')).toBeNull();
    expect(waitlistEndpoint('ftp://example.com')).toBeNull();
    expect(waitlistEndpoint('https://example.com/?x=1')).toBeNull();
    expect(waitlistEndpoint('https://example.com/#x')).toBeNull();
  });
});

describe('isValidEmail', () => {
  it.each(['you@example.com', ' a@b.co ', 'first.last+tag@sub.example.org'])('accepts %s', (v) =>
    expect(isValidEmail(v)).toBe(true)
  );
  it.each(['', 'you', 'you@', '@example.com', 'you@example', 'a b@c.d', 'a@b c.d'])(
    'rejects %s',
    (v) => expect(isValidEmail(v)).toBe(false)
  );
});

describe('waitlistBody', () => {
  it('sends the trimmed email, the source and the honeypot as JSON', () => {
    expect(JSON.parse(waitlistBody('  you@example.com ', 'join', ''))).toEqual({
      email: 'you@example.com',
      source: 'join',
      company: '',
    });
  });

  it('passes a filled honeypot through for the server to discard', () => {
    expect(JSON.parse(waitlistBody('bot@example.com', 'landing', 'Acme')).company).toBe('Acme');
  });
});

describe('readInviteResponse', () => {
  it('accepts a 2xx with success true or no body', () => {
    expect(readInviteResponse(200, { success: true, message: 'ok' })).toEqual({ ok: true });
    expect(readInviteResponse(200, {})).toEqual({ ok: true });
    expect(readInviteResponse(204, null)).toEqual({ ok: true });
  });

  it('treats an explicit success false as a failure', () => {
    expect(readInviteResponse(200, { success: false })).toEqual({
      ok: false,
      message: INVITE_COPY.failed,
    });
  });

  it('shows the rate-limit copy for resource_exhausted or a 429', () => {
    const limited = { ok: false, message: INVITE_COPY.rateLimited };
    expect(readInviteResponse(429, { code: 'resource_exhausted', message: 'x' })).toEqual(limited);
    expect(readInviteResponse(429, null)).toEqual(limited);
    expect(readInviteResponse(400, { code: 'resource_exhausted' })).toEqual(limited);
  });

  it('shows the invalid copy when the server rejects the email', () => {
    expect(readInviteResponse(400, { code: 'invalid_argument', message: 'bad' })).toEqual({
      ok: false,
      message: INVITE_COPY.invalid,
    });
  });

  it('never reports success for any other error, whatever the body', () => {
    const failed = { ok: false, message: INVITE_COPY.failed };
    expect(readInviteResponse(500, null)).toEqual(failed);
    expect(readInviteResponse(503, { code: 'unavailable' })).toEqual(failed);
    expect(readInviteResponse(500, 'oops')).toEqual(failed);
    expect(readInviteResponse(500, { success: true })).toEqual(failed);
    expect(readInviteResponse(400, { code: 42 })).toEqual(failed);
  });

  it('uses the design copy, without em dashes', () => {
    expect(INVITE_COPY.done).toBe("You're on the list. We'll email you when a place opens.");
    expect(INVITE_COPY.invalid).toBe('Please enter a valid email address.');
    for (const text of Object.values(INVITE_COPY)) expect(text).not.toContain('—');
  });
});

describe('inviteMailto', () => {
  it('builds a mailto with a subject for a valid address', () => {
    expect(inviteMailto(' invites@llamatrade.ai ')).toBe(
      'mailto:invites@llamatrade.ai?subject=LlamaTrade%20invite'
    );
  });

  it("asks for the visitor's address in the body when given one", () => {
    expect(inviteMailto('hello@llamatrade.ai', 'me@example.com')).toBe(
      'mailto:hello@llamatrade.ai?subject=LlamaTrade%20invite&body=Please%20add%20me%40example.com%20to%20the%20LlamaTrade%20waitlist.'
    );
  });

  it('gives null for a missing or malformed address', () => {
    expect(inviteMailto(undefined)).toBeNull();
    expect(inviteMailto('')).toBeNull();
    expect(inviteMailto('not-an-address')).toBeNull();
  });
});
