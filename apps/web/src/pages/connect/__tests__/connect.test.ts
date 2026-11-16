import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  alpacaLinkErrorMessage,
  safeReturnPath,
  startAlpacaLink,
} from '../../../services/alpacaOAuth';
import { firstBacktestRange } from '../../onboarding/runTemplate';

describe('safeReturnPath', () => {
  it('keeps in-app paths and falls back for anything else', () => {
    expect(safeReturnPath('/welcome/result/r1')).toBe('/welcome/result/r1');
    expect(safeReturnPath(null)).toBe('/dashboard');
    expect(safeReturnPath('')).toBe('/dashboard');
    expect(safeReturnPath('https://evil.example')).toBe('/dashboard');
    expect(safeReturnPath('//evil.example')).toBe('/dashboard');
    expect(safeReturnPath('settings', '/settings')).toBe('/settings');
  });
});

describe('alpacaLinkErrorMessage', () => {
  it('says plainly that a cancelled link connected nothing', () => {
    expect(alpacaLinkErrorMessage('access_denied')).toMatch(/cancelled.*nothing was connected/);
    expect(alpacaLinkErrorMessage('server_error')).toMatch(/nothing was changed/);
  });
});

describe('firstBacktestRange', () => {
  it('covers the two years before the start of today in UTC', () => {
    const { start, end } = firstBacktestRange(new Date('2026-11-13T22:15:00Z'));
    expect(end.toISOString()).toBe('2026-11-13T00:00:00.000Z');
    expect(start.toISOString()).toBe('2024-11-13T00:00:00.000Z');
  });
});

describe('startAlpacaLink', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const stubStart = (body: unknown, ok = true) =>
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok, json: () => Promise.resolve(body) } as Response)
    );

  it('refuses to redirect when the answer has no authorize URL', async () => {
    stubStart({});
    await expect(startAlpacaLink('tok')).rejects.toThrow(/Could not start/);
  });

  it('refuses a non-http authorize URL', async () => {
    stubStart({ authorizeUrl: 'javascript:alert(1)' });
    await expect(startAlpacaLink('tok')).rejects.toThrow(/Could not start/);
  });

  it('throws when the auth service answers with an error', async () => {
    stubStart({ authorizeUrl: 'https://app.alpaca.markets/oauth' }, false);
    await expect(startAlpacaLink('tok')).rejects.toThrow(/Could not start/);
  });
});
