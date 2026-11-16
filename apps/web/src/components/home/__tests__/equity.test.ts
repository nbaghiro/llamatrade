import { describe, expect, it } from 'vitest';

import { alignAsOf, equityWindow } from '../equity';

const DAY = 86_400_000;
const T0 = Date.UTC(2026, 0, 1);
const pt = (day: number, value: number) => ({
  timestamp: new Date(T0 + day * DAY).toISOString(),
  value,
});

describe('equityWindow', () => {
  it('needs two points', () => {
    expect(equityWindow([pt(0, 0)], [], '1M')).toBeNull();
  });

  it('rebases the account to the start of the range', () => {
    const curve = [pt(0, 0), pt(50, 10), pt(80, 21)];
    const w = equityWindow(curve, [], '1M');
    expect(w?.dates).toHaveLength(2);
    expect(w?.account[0]).toBeCloseTo(0);
    // 1.21 / 1.10 - 1 = 10%
    expect(w?.account[1]).toBeCloseTo(10);
    expect(w?.accountReturn).toBeCloseTo(0.1);
    expect(w?.bench).toBeNull();
    expect(w?.benchReturn).toBeNull();
  });

  it('uses the whole history for All and when a range holds one point', () => {
    const curve = [pt(0, 0), pt(30, 5), pt(60, 10)];
    expect(equityWindow(curve, [], 'ALL')?.dates).toHaveLength(3);
    expect(equityWindow(curve, [], '1W')?.dates).toHaveLength(3);
  });

  it('aligns the benchmark by date and rebases it too', () => {
    const curve = [pt(0, 0), pt(2, 1), pt(4, 2)];
    const bench = [pt(0, 0), pt(1, 10), pt(3, 21)];
    const w = equityWindow(curve, bench, 'ALL');
    expect(w?.bench?.map((v) => Math.round(v * 100) / 100)).toEqual([0, 10, 21]);
    expect(w?.benchReturn).toBeCloseTo(0.21);
  });
});

describe('alignAsOf', () => {
  it('takes the latest value at or before each date and the first value before the series starts', () => {
    const dates = [-1, 0, 1, 5].map((d) => new Date(T0 + d * DAY));
    const bench = [pt(3, 30), pt(0, 0), pt(1, 10)];
    expect(alignAsOf(dates, bench)).toEqual([0, 0, 10, 30]);
  });

  it('is null without a benchmark', () => {
    expect(alignAsOf([new Date(T0)], [])).toBeNull();
  });
});
