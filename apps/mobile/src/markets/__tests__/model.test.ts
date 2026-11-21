import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  holderLine,
  holdersBySymbol,
  moveTone,
  placeFills,
  price,
  priceRange,
  signedPct,
  sortByMove,
  symbolsFor,
  type HolderSession,
} from '../model.ts';

const sessions: HolderSession[] = [
  { id: 'rr', title: 'Recession Radar', mode: 'paper', frozen: false, stopped: false },
  { id: 'aw', title: 'All-Weather Portfolio', mode: 'live', frozen: false, stopped: false },
  { id: 'ms', title: 'Momentum Sectors', mode: 'paper', frozen: true, stopped: false },
  { id: 'tm', title: 'Tech Momentum Rotation', mode: 'paper', frozen: false, stopped: true },
];

const positions = [
  { symbol: 'TLT', sessionId: 'rr', shares: 239, avgPrice: 89.74, value: 21641.45 },
  { symbol: 'GLD', sessionId: 'rr', shares: 39, avgPrice: 243.2, value: 9687.6 },
  { symbol: 'GLD', sessionId: 'aw', shares: 13, avgPrice: 203, value: 3229.2 },
  { symbol: 'VTI', sessionId: 'aw', shares: 44, avgPrice: 279, value: 13288 },
  { symbol: 'SMH', sessionId: 'ms', shares: 31, avgPrice: 250, value: 8105.57 },
  { symbol: 'QQQ', sessionId: 'tm', shares: 25, avgPrice: 500, value: 12_500 },
];

describe('holdersBySymbol', () => {
  const map = holdersBySymbol(positions, sessions);
  it('leaves out stopped sessions', () => {
    assert.equal(map.has('QQQ'), false);
  });
  it('orders symbols by value held and holders by value', () => {
    assert.deepEqual([...map.keys()], ['TLT', 'VTI', 'GLD', 'SMH']);
    assert.deepEqual(map.get('GLD')?.map((h) => h.sessionId), ['rr', 'aw']);
  });
  it('gives each holding its share of the session', () => {
    const w = map.get('TLT')?.[0].weight ?? 0;
    assert.ok(Math.abs(w - 21641.45 / (21641.45 + 9687.6)) < 1e-9);
    assert.equal(map.get('SMH')?.[0].frozen, true);
  });
});

describe('holderLine', () => {
  const map = holdersBySymbol(positions, sessions);
  it('names the holders and marks a symbol held only by live sessions', () => {
    assert.equal(holderLine(map.get('VTI') ?? []), 'All-Weather Portfolio · live');
    assert.equal(holderLine(map.get('GLD') ?? []), 'Recession Radar, All-Weather Portfolio');
    assert.equal(holderLine([]), '');
  });
});

describe('segments and sorting', () => {
  it('keeps held symbols out of Watch', () => {
    assert.equal(symbolsFor('watch', ['AAPL']).includes('AAPL'), false);
    assert.deepEqual(symbolsFor('indexes', []), ['SPY', 'QQQ', 'DIA', 'IWM']);
  });
  it('sorts by today’s move with unquoted symbols last', () => {
    const order = sortByMove(['TLT', 'SMH', 'X', 'GLD'], {
      TLT: { price: 90, changePct: -0.22 },
      SMH: { price: 261, changePct: 1.32 },
      GLD: { price: 247, changePct: 0.18 },
    });
    assert.deepEqual(order, ['SMH', 'GLD', 'TLT', 'X']);
  });
});

describe('moveTone and formats', () => {
  it('keeps small moves in ink', () => {
    assert.equal(moveTone(0.18), 'fg');
    assert.equal(moveTone(-0.22), 'fg');
    assert.equal(moveTone(1.32), 'gain');
    assert.equal(moveTone(-0.38), 'loss');
    assert.equal(moveTone(Number.NaN), 'fg');
  });
  it('formats signed percents and prices', () => {
    assert.equal(signedPct(1.316), '+1.32%');
    assert.equal(signedPct(-0.2), '−0.20%');
    assert.equal(signedPct(0), '0.00%');
    assert.equal(price(90.41), '90.41');
    assert.equal(price(0.5), '0.5000');
  });
});

describe('placeFills', () => {
  const day = 86_400;
  const candles = [0, 1, 2, 3].map((i) => ({ time: 1_000_000 + i * day, high: 10 + i, low: 5 + i }));
  it('places each fill on its candle and drops ones outside the chart', () => {
    const placed = placeFills(
      [
        { side: 'buy', price: 6, at: (1_000_000 + day + 3600) * 1000, sessionId: 'a' },
        { side: 'sell', price: 9, at: (1_000_000 - day) * 1000, sessionId: 'a' },
        { side: 'sell', price: 9, at: (1_000_000 + 3 * day + 100) * 1000, sessionId: 'a' },
      ],
      candles,
    );
    assert.deepEqual(placed.map((p) => p.index), [1, 3]);
    assert.deepEqual(placeFills([], []), []);
  });
  it('widens the price range to fit average costs', () => {
    const r = priceRange(candles, [2]);
    assert.ok(r !== null && r.min < 2 && r.max > 13);
    assert.equal(priceRange([]), null);
  });
});
