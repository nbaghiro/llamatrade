import { describe, expect, it } from 'vitest';

import { appHref, readSignedIn, tokenExpired } from '../lib/session';

const NOW = 1_800_000_000_000;
const jwt = (exp: number) => `h.${btoa(JSON.stringify({ exp }))}.s`;
const stored = (isAuthenticated: boolean, accessToken: string | null) =>
  JSON.stringify({ state: { isAuthenticated, accessToken } });

describe('tokenExpired', () => {
  it('treats missing and malformed tokens as expired', () => {
    expect(tokenExpired(null, NOW)).toBe(true);
    expect(tokenExpired('not-a-jwt', NOW)).toBe(true);
    expect(tokenExpired(`h.${btoa('{}')}.s`, NOW)).toBe(true);
  });

  it('compares exp in seconds against now', () => {
    expect(tokenExpired(jwt(NOW / 1000 + 60), NOW)).toBe(false);
    expect(tokenExpired(jwt(NOW / 1000), NOW)).toBe(true);
  });
});

describe('readSignedIn', () => {
  it('needs the authenticated flag and a live token', () => {
    expect(readSignedIn(stored(true, jwt(NOW / 1000 + 60)), NOW)).toBe(true);
    expect(readSignedIn(stored(false, jwt(NOW / 1000 + 60)), NOW)).toBe(false);
    expect(readSignedIn(stored(true, jwt(NOW / 1000 - 60)), NOW)).toBe(false);
  });

  it('is signed out with nothing stored or unreadable storage', () => {
    expect(readSignedIn(null, NOW)).toBe(false);
    expect(readSignedIn('{oops', NOW)).toBe(false);
    expect(readSignedIn(JSON.stringify({}), NOW)).toBe(false);
  });
});

describe('appHref', () => {
  it('keeps relative paths when the app serves the page', () => {
    expect(appHref('/login', { standalone: false })).toBe('/login');
  });

  it('links to the app origin from the standalone build, trimming slashes', () => {
    expect(appHref('/login', { standalone: true, appUrl: 'https://app.example.com/' })).toBe(
      'https://app.example.com/login'
    );
  });

  it('hides app links in the standalone build without an app origin', () => {
    expect(appHref('/login', { standalone: true })).toBeNull();
    expect(appHref('/login', { standalone: true, appUrl: '' })).toBeNull();
  });
});
