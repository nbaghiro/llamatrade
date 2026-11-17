import {
  compares,
  conditionStats,
  ema,
  indicatorFromCloses,
  isDrawableIndicator,
  momentum,
  monthStarts,
  rsi,
  sma,
  stddev,
  warmupBars,
} from '@llamatrade/core/strategy/indicators';
import { describe, expect, it } from 'vitest';

describe('sma and ema', () => {
  it('averages a trailing window and leaves warm-up empty', () => {
    const out = sma([1, 2, 3, 4, 5], 3);
    expect(out.slice(0, 2).every(Number.isNaN)).toBe(true);
    expect(out.slice(2)).toEqual([2, 3, 4]);
  });

  it('seeds the ema with the simple mean, then smooths', () => {
    const out = ema([1, 2, 3, 4], 3);
    expect(out[2]).toBe(2);
    expect(out[3]).toBeCloseTo(4 * 0.5 + 2 * 0.5);
  });

  it('returns all NaN for too little history', () => {
    expect(sma([1, 2], 3).every(Number.isNaN)).toBe(true);
    expect(ema([1, 2], 3).every(Number.isNaN)).toBe(true);
  });
});

describe('rsi', () => {
  it('matches a hand-computed Wilder series', () => {
    // changes: +1, -1, +2, +1  → period 2 seed: gain 0.5, loss 0.5
    const out = rsi([10, 11, 10, 12, 13], 2);
    expect(out.slice(0, 2).every(Number.isNaN)).toBe(true);
    expect(out[2]).toBeCloseTo(50);
    // gain (0.5 + 2) / 2 = 1.25, loss (0.5 + 0) / 2 = 0.25 → 100 - 100/6
    expect(out[3]).toBeCloseTo(100 - 100 / 6);
    // gain (1.25 + 1) / 2 = 1.125, loss 0.125 → rs 9
    expect(out[4]).toBeCloseTo(90);
  });

  it('reads 100 when there are no losses', () => {
    expect(rsi([1, 2, 3, 4], 2)[3]).toBe(100);
  });
});

describe('momentum and stddev', () => {
  it('computes differences and population deviation', () => {
    expect(momentum([1, 3, 6], 1).slice(1)).toEqual([2, 3]);
    expect(stddev([2, 4, 4, 4, 5, 5, 7, 9], 8)[7]).toBeCloseTo(2);
  });
});

describe('drawable indicators', () => {
  it('lists only the close-based ones', () => {
    expect(isDrawableIndicator('rsi')).toBe(true);
    expect(isDrawableIndicator('macd_line')).toBe(false);
    expect(indicatorFromCloses('sma', [1, 2, 3], 2)[2]).toBe(2.5);
    expect(warmupBars('rsi', 14)).toBe(15);
    expect(warmupBars('sma', 20)).toBe(20);
  });
});

describe('conditionStats', () => {
  it('counts days, stretches and rebalance hits', () => {
    const values = [NaN, 71, 72, 69, 75, 76, 60];
    const stats = conditionStats(values, 'gt', 70, [0, 2, 3, 5]);
    expect(stats.days).toBe(4);
    expect(stats.stretches).toEqual([
      { from: 1, to: 2 },
      { from: 4, to: 5 },
    ]);
    expect(stats.rebalancesHeld).toEqual([2, 5]);
  });

  it('closes a stretch that runs to the end', () => {
    expect(conditionStats([1, 5, 6], 'gte', 5).stretches).toEqual([{ from: 1, to: 2 }]);
  });

  it('compares with every comparator', () => {
    expect(compares(1, 'lt', 2)).toBe(true);
    expect(compares(2, 'lte', 2)).toBe(true);
    expect(compares(2, 'eq', 2)).toBe(true);
    expect(compares(2, 'neq', 2)).toBe(false);
    expect(compares(3, 'cross_above', 2)).toBe(true);
    expect(compares(1, 'cross_below', 2)).toBe(true);
  });
});

describe('monthStarts', () => {
  it('marks the first trading day of each month', () => {
    const dates = ['2025-01-02', '2025-01-03', '2025-02-03', '2025-02-04', '2025-03-03'].map(
      (d) => new Date(`${d}T00:00:00Z`)
    );
    expect(monthStarts(dates)).toEqual([0, 2, 4]);
  });
});
