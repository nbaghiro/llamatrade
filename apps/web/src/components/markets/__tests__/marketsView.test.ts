import { describe, expect, it } from 'vitest';

import {
  cashLine,
  cleanSymbol,
  dayMoves,
  heldRows,
  mapTiles,
  lastSessionOnly,
  rangeBars,
  rangeStart,
  rangeStats,
} from '../marketsView';

const sleeve = (over: Record<string, unknown>) => ({
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

describe('heldRows', () => {
  it('lists each symbol once, largest first, with live holders before paper', () => {
    const rows = heldRows([
      sleeve({
        executionId: 'p',
        holdings: [h('GLD', 54, 500), h('TLT', 205, 400)],
        targets: { GLD: 0.4 },
      }),
      sleeve({
        executionId: 'l',
        name: 'All-Weather Portfolio',
        live: true,
        value: 2000,
        holdings: [h('GLD', 26, 300), h('ZERO', 0, 0)],
      }),
    ]);
    expect(rows.map((r) => r.symbol)).toEqual(['GLD', 'TLT']);
    expect(rows[0].holders.map((x) => [x.initials, x.live, x.weight, x.target])).toEqual([
      ['AW', true, 0.15, undefined],
      ['RR', false, 0.5, 0.4],
    ]);
  });
});

describe('ranges', () => {
  const now = new Date('2026-11-17T15:00:00Z');
  it('starts from the first sleeve for "since start" and a year without one', () => {
    const first = new Date('2026-06-02T00:00:00Z');
    expect(rangeStart('start', now, first)).toBe(first);
    expect(now.getTime() - rangeStart('start', now, null).getTime()).toBe(366 * 86_400_000);
    expect(now.getTime() - rangeStart('1M', now, null).getTime()).toBe(31 * 86_400_000);
    expect(rangeBars('1D')).toBe('intraday5');
    expect(rangeBars('1W')).toBe('hourly');
    expect(rangeBars('3M')).toBe('daily');
  });

  it('keeps only the last session for intraday', () => {
    const c = (time: number) => ({ time, open: 1, high: 1, low: 1, close: 1, volume: 1 });
    const out = lastSessionOnly([c(1), c(2), c(3)], (t) => (t < 2 ? 'a' : 'b'));
    expect(out.map((x) => x.time)).toEqual([2, 3]);
    expect(lastSessionOnly([], () => '')).toEqual([]);
  });
});

describe('rangeStats', () => {
  const candles = [
    { time: 1, open: 100, high: 105, low: 99, close: 104, volume: 10 },
    { time: 2, open: 104, high: 112, low: 103, close: 110, volume: 20 },
  ];
  it('reads the day from the daily bar and the change from the first open', () => {
    const s = rangeStats(candles, {
      time: 3,
      open: 109,
      high: 111,
      low: 108,
      close: 110,
      volume: 99,
    });
    expect(s).toEqual({
      open: 109,
      dayLow: 108,
      dayHigh: 111,
      change: expect.closeTo(0.1, 9),
      high: 112,
      volume: 99,
    });
    expect(rangeStats(candles)?.open).toBe(104);
    expect(rangeStats([])).toBeNull();
  });
});

describe('cleanSymbol', () => {
  it('upper-cases a plausible ticker and rejects the rest', () => {
    expect(cleanSymbol(' brk.b ')).toBe('BRK.B');
    expect(cleanSymbol('spy')).toBe('SPY');
    expect(cleanSymbol('')).toBeNull();
    expect(cleanSymbol('1ABC')).toBeNull();
    expect(cleanSymbol('TOO-LONG-SYMBOL')).toBeNull();
  });
});

describe('mapTiles and dayMoves', () => {
  const rows = heldRows([
    sleeve({
      executionId: 'a',
      holdings: [h('TLT', 200, 18000), h('SMH', 30, 7800), h('XLI', 40, 5500)],
    }),
    sleeve({ executionId: 'b', name: 'All-Weather', live: true, holdings: [h('TLT', 212, 19500)] }),
  ]);
  const quotes = {
    TLT: { change: -0.2, changePercent: -0.22 },
    SMH: { change: 3.38, changePercent: 1.32 },
    XLI: null,
  };

  it('sums dollars and shares per symbol and applies the move to the shares held', () => {
    const tiles = mapTiles(rows, quotes, 100000);
    const tlt = tiles.find((t) => t.symbol === 'TLT');
    expect(tlt?.value).toBe(37500);
    expect(tlt?.qty).toBe(412);
    expect(tlt?.share).toBeCloseTo(0.375, 9);
    expect(tlt?.pct).toBe(-0.22);
    expect(tlt?.dayMove).toBeCloseTo(-82.4, 9);
    expect(tiles.find((t) => t.symbol === 'XLI')).toMatchObject({ pct: null, dayMove: null });
    expect(mapTiles(rows, quotes, 0)[0].share).toBeNull();
  });

  it('totals the known moves and lists the largest from best to worst', () => {
    const d = dayMoves(mapTiles(rows, quotes, 100000));
    expect(d.total).toBeCloseTo(101.4 - 82.4, 9);
    expect(d.held).toBe(50800);
    expect(d.movers.map((m) => m.symbol)).toEqual(['SMH', 'TLT']);
    expect(d.missing).toEqual(['XLI']);
    expect(dayMoves(mapTiles(rows, quotes, 1), 1).movers.map((m) => m.symbol)).toEqual(['SMH']);
    expect(dayMoves([])).toEqual({ total: 0, held: 0, movers: [], missing: [] });
  });
});

describe('cashLine', () => {
  it('adds sleeve cash to unallocated and names where most of it is', () => {
    expect(
      cashLine(
        [
          { name: 'Tech Momentum', cash: 20000 },
          { name: 'All-Weather', cash: 300 },
          { name: 'Unknown', cash: null },
        ],
        6000
      )
    ).toEqual({
      total: 26300,
      most: { sleeve: { name: 'Tech Momentum', cash: 20000 }, amount: 20000 },
    });
    expect(cashLine([{ name: 'A', cash: 100 }], 900)).toEqual({
      total: 1000,
      most: { sleeve: null, amount: 900 },
    });
  });

  it('names nobody when the cash is spread out or in one place only', () => {
    expect(
      cashLine(
        [
          { name: 'A', cash: 50 },
          { name: 'B', cash: 50 },
        ],
        null
      )?.most
    ).toBeNull();
    expect(cashLine([{ name: 'A', cash: 50 }], null)).toEqual({ total: 50, most: null });
    expect(cashLine([], 0)).toEqual({ total: 0, most: null });
  });

  it('is unknown when the ledger gave no figures', () => {
    expect(cashLine([{ name: 'A', cash: null }], null)).toBeNull();
  });
});
