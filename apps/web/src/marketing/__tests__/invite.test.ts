import { describe, expect, it } from 'vitest';

import {
  INVITE_COPY,
  inviteBody,
  inviteEndpoint,
  isValidEmail,
  readInviteResponse,
} from '../lib/invite';

describe('inviteEndpoint', () => {
  it('builds the Loops URL from a form id', () => {
    expect(inviteEndpoint('clx12abc')).toBe('https://app.loops.so/api/newsletter-form/clx12abc');
    expect(inviteEndpoint('  clx12abc ')).toBe('https://app.loops.so/api/newsletter-form/clx12abc');
  });

  it('is closed when the id is unset, blank or the placeholder', () => {
    expect(inviteEndpoint(undefined)).toBeNull();
    expect(inviteEndpoint('')).toBeNull();
    expect(inviteEndpoint('   ')).toBeNull();
    expect(inviteEndpoint('REPLACE_WITH_LOOPS_FORM_ID')).toBeNull();
  });

  it('rejects ids that would change the path', () => {
    expect(inviteEndpoint('../x')).toBeNull();
    expect(inviteEndpoint('a/b')).toBeNull();
    expect(inviteEndpoint('a?b=c')).toBeNull();
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

describe('inviteBody', () => {
  it('sends the trimmed email and the source', () => {
    const body = inviteBody('  you@example.com ');
    expect(body.get('email')).toBe('you@example.com');
    expect(body.get('source')).toBe('landing');
  });
});

describe('readInviteResponse', () => {
  it('accepts success true', () => {
    expect(readInviteResponse(200, { success: true })).toEqual({ ok: true });
  });

  it('accepts a 2xx without a success field', () => {
    expect(readInviteResponse(200, {})).toEqual({ ok: true });
    expect(readInviteResponse(204, null)).toEqual({ ok: true });
  });

  it('passes on the Loops message when it refuses', () => {
    expect(readInviteResponse(400, { success: false, message: 'Email is invalid' })).toEqual({
      ok: false,
      message: 'Email is invalid',
    });
  });

  it('never reports success for an error status, whatever the body', () => {
    expect(readInviteResponse(500, null)).toEqual({ ok: false, message: INVITE_COPY.failed });
    expect(readInviteResponse(429, {})).toEqual({ ok: false, message: INVITE_COPY.failed });
    expect(readInviteResponse(500, 'oops')).toEqual({ ok: false, message: INVITE_COPY.failed });
  });

  it('falls back to the generic message for an empty or odd message', () => {
    expect(readInviteResponse(200, { success: false, message: '  ' })).toEqual({
      ok: false,
      message: INVITE_COPY.failed,
    });
    expect(readInviteResponse(200, { success: false, message: 42 })).toEqual({
      ok: false,
      message: INVITE_COPY.failed,
    });
  });

  it('uses the design copy', () => {
    expect(INVITE_COPY.done).toBe("You're on the list. We'll email you when a place opens.");
    expect(INVITE_COPY.invalid).toBe('Please enter a valid email address.');
    for (const text of Object.values(INVITE_COPY)) expect(text).not.toContain('—');
  });
});
