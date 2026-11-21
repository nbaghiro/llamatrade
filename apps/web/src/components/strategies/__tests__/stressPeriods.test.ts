import { describe, expect, it } from 'vitest';

import {
  andList,
  findStressPeriods,
  heldGoingIn,
  periodName,
  rebase,
} from '../detail/stressPeriods';

const day = (iso: string) => new Date(`${iso}T00:00:00Z`);
const days = (n: number, from = '2020-01-01') =>
  Array.from({ length: n }, (_, i) => new Date(day(from).getTime() + i * 86_400_000 * 30));

describe('findStressPeriods', () => {
  it('finds a fall of more than 10% and when the benchmark got back', () => {
    const dates = days(8);
    const bench = [100, 110, 95, 90, 100, 112, 115, 116];
    const strat = [100, 105, 100, 98, 104, 106, 107, 108];
    const [p, ...rest] = findStressPeriods(dates, bench, strat);
    expect(rest).toHaveLength(0);
    expect(p.n).toBe(1);
    expect(p.start).toEqual(dates[1]);
    expect(p.trough).toEqual(dates[3]);
    expect(p.recovered).toEqual(dates[5]);
    expect(p.benchDrop).toBeCloseTo(90 / 110 - 1);
    expect(p.strategyDrop).toBeCloseTo(98 / 105 - 1);
    expect(p.strategyBack).toEqual(dates[5]);
    expect(p.monthsBack).toBe(2);
  });

  it('ignores falls of 10% or less', () => {
    const dates = days(4);
    expect(findStressPeriods(dates, [100, 91, 95, 101], [1, 1, 1, 1])).toEqual([]);
  });

  it('keeps a fall that has not recovered by the end', () => {
    const dates = days(4);
    const [p] = findStressPeriods(dates, [100, 80, 70, 75], [100, 90, 85, 88]);
    expect(p.recovered).toBeNull();
    expect(p.trough).toEqual(dates[2]);
    expect(p.strategyBack).toBeNull();
    expect(p.monthsBack).toBeNull();
  });

  it('numbers several stretches in order', () => {
    const dates = days(9);
    const bench = [100, 85, 101, 102, 80, 103, 104, 90, 92];
    const ps = findStressPeriods(dates, bench, bench);
    expect(ps.map((p) => p.n)).toEqual([1, 2, 3]);
    expect(ps[2].recovered).toBeNull();
  });

  it('reports no drop when the strategy only rose', () => {
    const dates = days(4);
    const [p] = findStressPeriods(dates, [100, 80, 85, 101], [100, 101, 102, 103]);
    expect(p.strategyDrop).toBe(0);
  });

  it('skips non-finite and zero benchmark values', () => {
    const dates = days(5);
    const ps = findStressPeriods(dates, [100, NaN, 0, 80, 101], [1, 1, 1, 1, 1]);
    expect(ps).toHaveLength(1);
    expect(ps[0].trough).toEqual(dates[3]);
  });

  it('handles empty input', () => {
    expect(findStressPeriods([], [], [])).toEqual([]);
  });
});

describe('heldGoingIn', () => {
  const start = day('2020-02-19');
  const trough = day('2020-03-23');

  it('is unknown when the run recorded no trades', () => {
    expect(heldGoingIn([], start, trough)).toEqual({ kind: 'unknown' });
    expect(heldGoingIn(null, start, trough)).toEqual({ kind: 'unknown' });
  });

  it('groups what was open at the start, then what it bought before the low', () => {
    const r = heldGoingIn(
      [
        { symbol: 'TLT', entry: day('2020-02-03'), exit: day('2020-03-02') },
        { symbol: 'GLD', entry: day('2020-02-03'), exit: day('2020-03-02') },
        { symbol: 'QQQ', entry: day('2020-03-02'), exit: null },
        { symbol: 'VTI', entry: day('2020-03-02'), exit: null },
        { symbol: 'SPY', entry: day('2019-01-02'), exit: day('2020-01-02') },
        { symbol: 'IWM', entry: day('2020-04-01'), exit: null },
      ],
      start,
      trough
    );
    expect(r).toEqual({
      kind: 'held',
      groups: [{ symbols: ['TLT', 'GLD'], from: day('2020-02-03') }],
      then: { symbols: ['QQQ', 'VTI'], from: day('2020-03-02') },
      more: 0,
    });
  });

  it('is cash when trades exist but none were open', () => {
    expect(
      heldGoingIn(
        [{ symbol: 'SPY', entry: day('2019-01-02'), exit: day('2019-06-01') }],
        start,
        trough
      )
    ).toEqual({ kind: 'cash', then: null, more: 0 });
  });
});

describe('heldGoingIn counts', () => {
  it('counts further buying days before the low', () => {
    const r = heldGoingIn(
      [
        { symbol: 'SPY', entry: day('2020-01-02'), exit: null },
        { symbol: 'TLT', entry: day('2020-02-25'), exit: null },
        { symbol: 'GLD', entry: day('2020-03-02'), exit: null },
        { symbol: 'IEF', entry: day('2020-03-09'), exit: null },
      ],
      day('2020-02-19'),
      day('2020-03-23')
    );
    expect(r.kind === 'held' && r.then?.symbols).toEqual(['TLT']);
    expect(r.kind === 'held' && r.more).toBe(2);
  });
});

describe('helpers', () => {
  it('names known falls by start date', () => {
    expect(periodName(day('2020-02-19'))).toBe('Covid sell-off');
    expect(periodName(day('2022-01-03'))).toBe('Rate rises');
    expect(periodName(day('2017-05-01'))).toBeNull();
  });

  it('joins lists', () => {
    expect(andList([])).toBe('');
    expect(andList(['TLT'])).toBe('TLT');
    expect(andList(['TLT', 'GLD'])).toBe('TLT and GLD');
    expect(andList(['QQQ', 'VTI', 'IWM'])).toBe('QQQ, VTI and IWM');
  });

  it('rebases to a start value', () => {
    expect(rebase([NaN, 50, 100], 10)).toEqual([NaN, 10, 20]);
    expect(rebase([0, NaN], 10).every(Number.isNaN)).toBe(true);
  });
});
