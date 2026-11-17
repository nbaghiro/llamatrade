import { describe, expect, it } from 'vitest';

import {
  changeSentence,
  drawableOf,
  fmt,
  rebalanceEvery,
  rebalanceIndexes,
} from '../conditionHistory';

const days = (...s: string[]) => s.map((d) => new Date(`${d}T00:00:00Z`));

describe('rebalanceIndexes', () => {
  const dates = days('2025-03-28', '2025-03-31', '2025-04-01', '2025-04-07', '2025-07-01');

  it('marks the first trading day of each period', () => {
    expect(rebalanceIndexes(dates, 'monthly')).toEqual([0, 2, 4]);
    expect(rebalanceIndexes(dates, 'weekly')).toEqual([0, 1, 3, 4]);
    expect(rebalanceIndexes(dates, 'quarterly')).toEqual([0, 2, 4]);
    expect(rebalanceIndexes(dates, 'annually')).toEqual([0]);
    expect(rebalanceIndexes(dates, 'daily')).toEqual([0, 1, 2, 3, 4]);
  });

  it('reads the store timeframe, monthly when unknown', () => {
    expect(rebalanceEvery('1W')).toBe('weekly');
    expect(rebalanceEvery('nope')).toBe('monthly');
  });
});

describe('drawableOf', () => {
  it('takes an indicator or price against a number', () => {
    expect(
      drawableOf({
        left: { type: 'indicator', indicator: 'rsi', period: 14, symbol: 'SPY' },
        comparator: 'gt',
        right: { type: 'number', value: 70 },
      })
    ).toEqual({ kind: 'indicator', symbol: 'SPY', indicator: 'rsi', period: 14, threshold: 70 });
    expect(
      drawableOf({
        left: { type: 'price', symbol: 'SPY', field: 'close' },
        comparator: 'lt',
        right: { type: 'number', value: 400 },
      })
    ).toEqual({ kind: 'price', symbol: 'SPY', field: 'close', threshold: 400 });
  });

  it('refuses two series', () => {
    expect(
      drawableOf({
        left: { type: 'price', symbol: 'SPY', field: 'close' },
        comparator: 'gt',
        right: { type: 'indicator', indicator: 'sma', period: 200, symbol: 'SPY' },
      })
    ).toBeNull();
  });
});

describe('changeSentence', () => {
  it('compares with the saved threshold when the counts differ', () => {
    expect(
      changeSentence({
        threshold: '72',
        days: 36,
        rebalances: 6,
        total: 24,
        every: 'monthly',
        saved: { days: 50, rebalances: 8 },
      })
    ).toBe(
      'At 72 it would have held on 36 trading days instead of 50, and at 6 of 24 monthly rebalances instead of 8.'
    );
  });

  it('reads plainly without a saved comparison', () => {
    expect(
      changeSentence({
        threshold: '70',
        days: 1,
        rebalances: 0,
        total: 24,
        every: 'daily',
        saved: null,
      })
    ).toBe('At 70 it would have held on 1 trading day in this window.');
  });

  it('formats figures', () => {
    expect(fmt(71.234)).toBe('71.23');
    expect(fmt(12345.6)).toBe('12,346');
  });
});
