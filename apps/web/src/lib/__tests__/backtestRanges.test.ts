import { describe, expect, it } from 'vitest';

import {
  DATA_FLOOR,
  coversRange,
  curatedRanges,
  daysBackToHigh,
  startsAtFloor,
  stretchFigures,
  stretchesWithin,
  HARD_STRETCHES,
} from '../backtestRanges';

const d = (iso: string) => new Date(`${iso}T00:00:00Z`);

describe('curatedRanges', () => {
  it('runs the open ranges to today and keeps the fixed ones', () => {
    const ranges = curatedRanges(d('2026-10-30'));
    expect(ranges.map((r) => [r.id, r.start, r.end])).toEqual([
      ['five-years', '2021-10-30', '2026-10-30'],
      ['fall-2022', '2021-11-01', '2023-06-30'],
      ['mar-2020', '2020-01-02', '2021-12-31'],
      ['all-data', DATA_FLOOR, '2026-10-30'],
    ]);
  });

  it('never starts five years back before the data floor', () => {
    expect(curatedRanges(d('2019-06-01'))[0].start).toBe(DATA_FLOOR);
  });
});

describe('matching', () => {
  const [five] = curatedRanges(d('2026-10-30'));
  it('matches a run within a week at both ends', () => {
    expect(coversRange(d('2021-11-01'), d('2026-10-29'), five)).toBe(true);
    expect(coversRange(d('2021-12-01'), d('2026-10-29'), five)).toBe(false);
  });
  it('recognises the data floor', () => {
    expect(startsAtFloor(d('2016-01-05'))).toBe(true);
    expect(startsAtFloor(d('2017-01-05'))).toBe(false);
  });
  it('keeps only stretches wholly inside the run', () => {
    expect(stretchesWithin(d('2019-01-01'), d('2026-01-01')).map((s) => s.id)).toEqual([
      'mar-2020',
      '2022',
    ]);
    expect(stretchesWithin(d('2022-06-01'), d('2026-01-01'))).toEqual([]);
  });
});

describe('stretch figures', () => {
  const mar = HARD_STRETCHES[1];
  const dates = [
    '2020-02-18',
    '2020-02-19',
    '2020-03-02',
    '2020-03-23',
    '2020-04-01',
    '2020-05-01',
  ].map(d);
  const run = [100, 100, 90, 95, 99, 101];
  const bench = [200, 200, 150, 140, 170, 205];

  it('takes the deepest fall inside the stretch for both series', () => {
    const [f] = stretchFigures([mar], dates, run, bench);
    expect(f.run).toBeCloseTo(-0.1);
    expect(f.bench).toBeCloseTo(-0.3);
  });

  it('leaves the benchmark out when it has no points', () => {
    expect(stretchFigures([mar], dates, run, null)[0].bench).toBeNull();
  });

  it('counts trading days back to the previous high, or null', () => {
    expect(daysBackToHigh(dates, run, mar)).toBe(2);
    expect(daysBackToHigh(dates, [100, 100, 90, 95, 96, 97], mar)).toBeNull();
  });
});
