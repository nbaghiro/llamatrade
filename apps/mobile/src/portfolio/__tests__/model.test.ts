import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { dayCounts, estimateOrders, groupByDay, ordersSentence, parseAmount, statementTag, type StatementIn } from '../model.ts';

describe('estimateOrders', () => {
  it('moves each symbol to its target share in whole shares', () => {
    const orders = estimateOrders(
      [
        { symbol: 'TLT', qty: 205, price: 90.6, marketValue: 18573 },
        { symbol: 'GLD', qty: 54, price: 246.87, marketValue: 13330.98 },
      ],
      { TLT: 0.6, GLD: 0.4 },
      0,
    );
    assert.deepEqual(orders, [
      { symbol: 'GLD', side: 'sell', shares: 2 },
      { symbol: 'TLT', side: 'buy', shares: 6 },
    ]);
    assert.equal(ordersSentence(orders), 'sell 2 GLD and buy 6 TLT');
  });

  it('sells a symbol that is no longer targeted and skips unknown prices', () => {
    const orders = estimateOrders(
      [
        { symbol: 'SPY', qty: 10, price: 100, marketValue: 1000 },
        { symbol: 'QQQ', qty: 0, price: 0, marketValue: 0 },
      ],
      { QQQ: 1 },
      0,
    );
    assert.deepEqual(orders, [{ symbol: 'SPY', side: 'sell', shares: 10 }]);
  });

  it('returns nothing without targets or value', () => {
    assert.deepEqual(estimateOrders([], {}, 100), []);
    assert.deepEqual(estimateOrders([], { SPY: 1 }, 0), []);
  });
});

describe('ordersSentence', () => {
  it('joins three orders', () => {
    assert.equal(
      ordersSentence([
        { symbol: 'A', side: 'buy', shares: 1 },
        { symbol: 'B', side: 'sell', shares: 2 },
        { symbol: 'C', side: 'buy', shares: 3 },
      ]),
      'buy 1 A, sell 2 B and buy 3 C',
    );
    assert.equal(ordersSentence([]), '');
  });
});

function row(over: Partial<StatementIn>): StatementIn {
  return { id: 'r', kind: 'buy', label: '', sublabel: '', signed: 0, amount: 0, t: 0, account: 'paper', sleeveId: 's1', ...over };
}

describe('statement', () => {
  it('groups by day, newest first', () => {
    const a = new Date(2026, 10, 17, 10).getTime();
    const b = new Date(2026, 10, 17, 11).getTime();
    const c = new Date(2026, 10, 13, 9).getTime();
    const days = groupByDay([row({ id: 'a', t: a }), row({ id: 'c', t: c }), row({ id: 'b', t: b })]);
    assert.deepEqual(
      days.map((d) => d.rows.map((r) => r.id)),
      [['b', 'a'], ['c']],
    );
  });

  it('counts rows per sleeve per day', () => {
    const t = new Date(2026, 10, 17, 10).getTime();
    const counts = dayCounts([row({ t }), row({ t: t + 1000 }), row({ t, sleeveId: '' })]);
    assert.equal(counts.get('s1')?.[0].count, 2);
    assert.equal(counts.get('cash')?.[0].count, 1);
  });

  it('tags kinds', () => {
    assert.equal(statementTag('deposit'), 'IN');
    assert.equal(statementTag('mystery'), 'TXN');
  });
});

describe('parseAmount', () => {
  it('reads typed amounts', () => {
    assert.equal(parseAmount('10,000'), 10000);
    assert.equal(parseAmount('$2500.50'), 2500.5);
    assert.equal(parseAmount('0'), null);
    assert.equal(parseAmount('12.345'), null);
    assert.equal(parseAmount('abc'), null);
  });
});
