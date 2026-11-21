import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { amountProblem, parseAmount, suggestAmount } from '../amount.ts';

describe('parseAmount', () => {
  it('accepts grouped and dollar-signed amounts', () => {
    assert.equal(parseAmount('15,000.50'), 15000.5);
    assert.equal(parseAmount('$ 15000'), 15000);
  });
  it('rejects zero, negatives, extra decimals and text', () => {
    assert.equal(parseAmount('0'), null);
    assert.equal(parseAmount('-5'), null);
    assert.equal(parseAmount('1.005'), null);
    assert.equal(parseAmount('abc'), null);
    assert.equal(parseAmount(''), null);
  });
});

describe('amountProblem', () => {
  it('asks for an amount, then checks it against free cash', () => {
    assert.equal(amountProblem(null, 100), 'Enter an amount greater than $0.');
    assert.match(amountProblem(100.01, 100) ?? '', /more than the free cash/);
    assert.equal(amountProblem(100, 100), null);
    assert.equal(amountProblem(5000, null), null);
  });
});

describe('suggestAmount', () => {
  it('suggests half the free cash in round thousands', () => {
    assert.equal(suggestAmount(20179.95), 10000);
    assert.equal(suggestAmount(1500), 1000);
    assert.equal(suggestAmount(640.7), 640);
    assert.equal(suggestAmount(0), 0);
  });
});
