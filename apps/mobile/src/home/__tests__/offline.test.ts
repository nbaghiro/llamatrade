import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { figuresTime, isNetworkError } from '../offline.ts';

describe('isNetworkError', () => {
  it('recognises unreachable servers', () => {
    assert.equal(isNetworkError('TypeError: Network request failed'), true);
    assert.equal(isNetworkError('[unavailable] upstream connect error'), true);
    assert.equal(isNetworkError('The request timed out.'), true);
  });

  it('leaves answers from the server alone', () => {
    assert.equal(isNetworkError('[permission_denied] not allowed'), false);
    assert.equal(isNetworkError(null), false);
    assert.equal(isNetworkError(''), false);
  });
});

describe('figuresTime', () => {
  const now = new Date(2026, 10, 17, 10, 42);

  it('shows the time for today', () => {
    assert.equal(figuresTime(new Date(2026, 10, 17, 10, 38), now), '10:38');
  });

  it('adds the date for another day', () => {
    assert.equal(figuresTime(new Date(2026, 10, 16, 9, 5), now), 'Nov 16, 09:05');
  });

  it('is null without a time', () => {
    assert.equal(figuresTime(null, now), null);
    assert.equal(figuresTime(new Date(NaN), now), null);
  });
});
