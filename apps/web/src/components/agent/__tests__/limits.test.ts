import { describe, expect, it } from 'vitest';

import { copilotLimit, isRateLimited, limitCopy } from '../limits';

describe('copilotLimit', () => {
  it('tells an outage from a rate limit and from an ordinary error', () => {
    expect(copilotLimit({ serviceUnavailable: true, error: null })).toBe('outage');
    expect(
      copilotLimit({
        serviceUnavailable: false,
        error: '[resource_exhausted] Too many requests; slow down and retry shortly.',
      })
    ).toBe('rate');
    expect(
      copilotLimit({ serviceUnavailable: false, error: 'Failed to create session' })
    ).toBeNull();
    expect(copilotLimit({ serviceUnavailable: false, error: null })).toBeNull();
  });

  it('reads the limiter message without its code prefix', () => {
    expect(isRateLimited('Too many requests; slow down and retry shortly.')).toBe(true);
    expect(isRateLimited(undefined)).toBe(false);
  });
});

describe('limitCopy', () => {
  const since = new Date('2026-11-18T15:38:00Z');

  it('says since when and that a kept question waits for the person', () => {
    const copy = limitCopy('outage', since, true);
    expect(copy.title).toBe('Copilot can’t reach its model');
    expect(copy.body).toMatch(/^Since 10:38 ET\. Your question is kept/);
  });

  it('says what still works when nothing was kept, and omits an unknown start', () => {
    expect(limitCopy('outage', null, false).body).toMatch(/^You can read every conversation/);
    expect(limitCopy('rate', since, true).body).toContain('about a minute');
    expect(limitCopy('rate', since, false).body).not.toContain('kept');
  });
});
