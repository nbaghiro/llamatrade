import { describe, expect, it } from 'vitest';

import type { SleeveFill } from '../../portfolio/history';
import { heldRows } from '../marketsView';
import {
  fillPhrase,
  fillsOnDay,
  heldByText,
  nextSort,
  quoteRows,
  rangePosition,
  sortRows,
  yearRange,
  type QuoteRow,
} from '../quoteRows';

const sleeve = (over: Partial<Parameters<typeof heldRows>[0][number]>) => ({
  sleeveId: 's',
  executionId: 'e',
  name: 'Recession Radar',
  live: false,
  value: 1000,
  rebalance: 'monthly',
  running: true,
  targets: {},
  holdings: [],
  ...over,
});
const h = (symbol: string, qty: number, marketValue: number) => ({
  symbol,
  qty,
  avgEntryPrice: 1,
  marketValue,
  unrealizedPnl: 0,
});

const held = heldRows([
  sleeve({ executionId: 'a', name: 'All-Weather', holdings: [h('GLD', 26, 6400)] }),
  sleeve({ executionId: 'b', holdings: [h('GLD', 54, 13300), h('TLT', 205, 18573)] }),
]);

describe('quoteRows', () => {
  const rows = quoteRows({
    held,
    watchOnly: ['SPY', 'TLT'],
    quotes: {
      GLD: { price: 246.87, changePercent: -0.38, volume: 212480 },
      SPY: { price: 590.12, changePercent: 0.21, volume: 0 },
    },
    names: { GLD: 'SPDR Gold Shares' },
    intraday: { GLD: [1, 2, 3] },
    years: { GLD: { low: 200, high: 260 } },
  });

  it('lists held symbols first, then watched ones not already held', () => {
    expect(rows.map((r) => r.symbol)).toEqual(['GLD', 'TLT', 'SPY']);
    expect(rows.map((r) => r.held)).toEqual([true, true, false]);
  });

  it('leaves missing figures empty rather than zero', () => {
    const tlt = rows[1];
    expect(tlt).toMatchObject({ last: null, changePct: null, volume: null, year: null, name: '' });
    expect(rows[2].volume).toBeNull();
    expect(rows[0]).toMatchObject({ last: 246.87, changePct: -0.38, volume: 212480 });
    expect(rows[0].intraday).toEqual([1, 2, 3]);
  });

  it('writes who holds a symbol with initials and shares', () => {
    expect(heldByText(rows[0].holders)).toBe('RR 54 · AW 26');
    expect(heldByText([])).toBe('');
  });
});

const row = (
  symbol: string,
  last: number | null,
  changePct: number | null,
  volume: number | null
) =>
  ({ symbol, last, changePct, volume }) as Pick<
    QuoteRow,
    'symbol' | 'last' | 'changePct' | 'volume'
  >;

describe('sortRows', () => {
  const rows = [
    row('TLT', 90.6, 0.42, 1820340),
    row('GLD', 246.87, -0.38, null),
    row('SPY', null, null, null),
    row('BND', 72.9, 0.42, 377600),
  ].map((r) => ({ ...r, name: '', held: true, holders: [], intraday: [], year: null }));

  it('keeps the given order by default', () => {
    expect(sortRows(rows, 'default', 'asc').map((r) => r.symbol)).toEqual([
      'TLT',
      'GLD',
      'SPY',
      'BND',
    ]);
  });

  it('sorts by symbol either way', () => {
    expect(sortRows(rows, 'symbol', 'asc').map((r) => r.symbol)).toEqual([
      'BND',
      'GLD',
      'SPY',
      'TLT',
    ]);
    expect(sortRows(rows, 'symbol', 'desc')[0].symbol).toBe('TLT');
  });

  it('puts rows without a figure last in both directions and keeps ties stable', () => {
    expect(sortRows(rows, 'change', 'desc').map((r) => r.symbol)).toEqual([
      'TLT',
      'BND',
      'GLD',
      'SPY',
    ]);
    expect(sortRows(rows, 'change', 'asc').map((r) => r.symbol)).toEqual([
      'GLD',
      'TLT',
      'BND',
      'SPY',
    ]);
    expect(sortRows(rows, 'volume', 'asc').map((r) => r.symbol)).toEqual([
      'BND',
      'TLT',
      'GLD',
      'SPY',
    ]);
    expect(sortRows(rows, 'last', 'desc').map((r) => r.symbol)).toEqual([
      'GLD',
      'TLT',
      'BND',
      'SPY',
    ]);
  });

  it('starts a new column in its natural direction and flips the same one', () => {
    expect(nextSort({ key: 'default', dir: 'asc' }, 'change')).toEqual({
      key: 'change',
      dir: 'desc',
    });
    expect(nextSort({ key: 'change', dir: 'desc' }, 'change')).toEqual({
      key: 'change',
      dir: 'asc',
    });
    expect(nextSort({ key: 'change', dir: 'asc' }, 'symbol')).toEqual({
      key: 'symbol',
      dir: 'asc',
    });
  });
});

describe('52-week range', () => {
  const c = (low: number, high: number) => ({
    time: 0,
    open: low,
    high,
    low,
    close: high,
    volume: 0,
  });

  it('takes the low and high of the bars', () => {
    expect(yearRange([c(90, 95), c(85, 100), c(88, 92)])).toEqual({ low: 85, high: 100 });
    expect(yearRange([c(90, 95)])).toBeNull();
    expect(yearRange([c(0, 0), c(0, 0)])).toBeNull();
  });

  it('places the last price, stretching the range when today breaks it', () => {
    expect(rangePosition({ low: 80, high: 100 }, 90)).toBe(0.5);
    expect(rangePosition({ low: 80, high: 100 }, 110)).toBe(1);
    expect(rangePosition({ low: 80, high: 100 }, 70)).toBe(0);
    expect(rangePosition({ low: 90, high: 90 }, 90)).toBe(0.5);
    expect(rangePosition(null, 90)).toBeNull();
    expect(rangePosition({ low: 80, high: 100 }, null)).toBeNull();
  });
});

describe('fills on a day', () => {
  const f = (id: string, sleeveId: string, symbol: string, iso: string): SleeveFill => ({
    id,
    sleeveId,
    symbol,
    side: 'buy',
    qty: 42,
    price: 90.41,
    at: new Date(iso),
  });
  const day = (d: Date) => d.toISOString().slice(0, 10);

  it("keeps one sleeve's fills of one symbol on that day, oldest first", () => {
    const fills = [
      f('3', 's1', 'TLT', '2026-11-17T15:50:00Z'),
      f('1', 's1', 'TLT', '2026-11-17T14:31:00Z'),
      f('2', 's2', 'TLT', '2026-11-17T14:31:00Z'),
      f('4', 's1', 'GLD', '2026-11-17T14:31:00Z'),
      f('5', 's1', 'TLT', '2026-11-16T14:31:00Z'),
    ];
    expect(fillsOnDay(fills, 's1', 'TLT', '2026-11-17', day).map((x) => x.id)).toEqual(['1', '3']);
  });

  it('says what each fill did', () => {
    expect(fillPhrase({ side: 'buy', qty: 42, price: 90.41 })).toBe('Bought 42 at 90.41');
    expect(fillPhrase({ side: 'sell', qty: 1.5, price: 10 })).toBe('Sold 1.50 at 10.00');
  });
});
