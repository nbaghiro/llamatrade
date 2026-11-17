import { describe, expect, it } from 'vitest';

import {
  monthTicks,
  nearestDateIndex,
  pctAt,
  pinAlign,
  tickLabel,
  timeArea,
  timeFraction,
  timePath,
} from '../chart/timeScale';

const d = (s: string) => new Date(`${s}T00:00:00Z`);

describe('time scale', () => {
  const start = d('2026-08-01');
  const end = d('2026-08-11');

  it('places dates by time and clamps outside the window', () => {
    expect(timeFraction(d('2026-08-06'), start, end)).toBeCloseTo(0.5);
    expect(timeFraction(d('2026-07-01'), start, end)).toBe(0);
    expect(timeFraction(d('2026-09-01'), start, end)).toBe(1);
    expect(timeFraction(start, start, start)).toBe(1);
    expect(pctAt(d('2026-08-06'), start, end)).toBe('50.000%');
  });

  it('draws a path on dates and breaks at gaps', () => {
    const dates = [d('2026-08-01'), d('2026-08-06'), d('2026-08-11')];
    const path = timePath(dates, [0, 5, 10], start, end, { lo: 0, hi: 10 }, 100, 50);
    expect(path).toBe('M0.00,50.00 L50.00,25.00 L100.00,0.00');
    expect(timeArea(dates, [0, 5, 10], start, end, { lo: 0, hi: 10 }, 100, 50)).toBe(
      'M0.00,50 L0.00,50.00 L50.00,25.00 L100.00,0.00 L100.00,50 Z'
    );
    const broken = timePath(dates, [0, Number.NaN, 10], start, end, { lo: 0, hi: 10 }, 100, 50);
    expect(broken).toBe('M0.00,50.00 M100.00,0.00');
    expect(timeArea(dates, [0, Number.NaN, 10], start, end, { lo: 0, hi: 10 }, 100, 50)).toBe('');
  });

  it('finds the nearest date', () => {
    const dates = [d('2026-08-01'), d('2026-08-06'), d('2026-08-11')];
    expect(nearestDateIndex(dates, d('2026-08-05'))).toBe(1);
    expect(nearestDateIndex([], d('2026-08-05'))).toBe(-1);
  });

  it('ticks on month starts, by year for long spans', () => {
    expect(monthTicks(d('2026-08-17'), d('2026-11-17')).map((t) => tickLabel(t, 92))).toEqual([
      'Sep 1',
      'Oct 1',
      'Nov 1',
    ]);
    const years = monthTicks(d('2021-01-04'), d('2026-10-30'), 10);
    expect(years.map((t) => tickLabel(t, 2125))).toEqual(['2022', '2023', '2024', '2025', '2026']);
    expect(monthTicks(d('2020-01-01'), d('2026-01-01'), 3).length).toBeLessThanOrEqual(3);
    expect(monthTicks(end, start)).toEqual([]);
  });

  it('keeps pins near an edge inside the chart', () => {
    expect(pinAlign(0.02)).toBe('start');
    expect(pinAlign(0.5)).toBe('center');
    expect(pinAlign(0.99)).toBe('end');
  });
});
