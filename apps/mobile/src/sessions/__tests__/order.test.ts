import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { againstLimit, limitFromMessage, sharesUnder } from '../order.ts';

describe('limitFromMessage', () => {
  it('reads a dollar limit the rejection names', () => {
    assert.equal(limitFromMessage('Order value over the $10,000 limit'), 10_000);
    assert.equal(limitFromMessage('exceeds max order value 12000.50'), 12_000.5);
  });
  it('is null when the message names no limit', () => {
    assert.equal(limitFromMessage('insufficient buying power'), null);
    assert.equal(limitFromMessage('symbol $XYZ not tradable'), null);
    assert.equal(limitFromMessage(''), null);
  });
});

describe('sharesUnder', () => {
  it('counts whole shares under the limit', () => {
    assert.equal(sharesUnder(10_000, 90.41), 110);
    assert.equal(sharesUnder(100, 100), 1);
    assert.equal(sharesUnder(0, 10), 0);
    assert.equal(sharesUnder(10, 0), 0);
  });
});

describe('againstLimit', () => {
  it('works out the over amount and what fits', () => {
    const r = againstLimit(124, 90.41, 'over the $10,000 limit');
    assert.ok(Math.abs(r.value - 11_210.84) < 1e-6);
    assert.ok(Math.abs(r.over - 1_210.84) < 1e-6);
    assert.equal(r.fits, 110);
  });
  it('keeps the value without a limit', () => {
    const r = againstLimit(10, 5, 'rejected by broker');
    assert.deepEqual(r, { value: 50, limit: null, over: 0, fits: null });
  });
});
