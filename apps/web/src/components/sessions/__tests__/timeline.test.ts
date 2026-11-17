import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import {
  asOf,
  curveStats,
  fillDays,
  largestThatFits,
  nextRebalances,
  niceTicks,
  parseLimitBreach,
  quantitiesBefore,
  rangeStart,
  sharesFor,
  symbolLanes,
  toSeries,
  windowed,
} from '../timeline';

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });

const order = (over: Record<string, unknown>) =>
  ({
    id: 'o',
    symbol: 'TLT',
    side: OrderSide.BUY,
    status: OrderStatus.FILLED,
    filledQuantity: { value: '10' },
    quantity: { value: '10' },
    ...over,
  }) as unknown as Order;

describe('rangeStart', () => {
  const now = new Date('2026-11-16T15:00:00Z');
  it('goes back a month or three', () => {
    expect(rangeStart('1M', now, null).toISOString().slice(0, 10)).toBe('2026-10-16');
    expect(rangeStart('3M', now, null).toISOString().slice(0, 10)).toBe('2026-08-16');
  });
  it('starts All at the earliest start, but never less than a week back', () => {
    const early = new Date('2026-01-15T00:00:00Z');
    expect(rangeStart('all', now, early)).toEqual(early);
    expect(rangeStart('all', now, new Date('2026-11-15T00:00:00Z')).toISOString()).toBe(
      '2026-11-09T15:00:00.000Z'
    );
  });
});

describe('fillDays', () => {
  it('groups filled orders by New York day and skips the rest', () => {
    const days = fillDays([
      order({ id: 'a', filledAt: ts('2026-11-10T15:31:00Z') }),
      order({ id: 'b', filledAt: ts('2026-11-10T15:30:00Z') }),
      order({ id: 'c', filledAt: ts('2026-11-03T15:30:00Z') }),
      order({ id: 'd', status: OrderStatus.REJECTED, createdAt: ts('2026-11-12T15:30:00Z') }),
      // 01:00 UTC on the 11th is still the 10th in New York.
      order({ id: 'e', filledAt: ts('2026-11-11T01:00:00Z') }),
    ]);
    expect(days.map((d) => d.key)).toEqual(['2026-11-03', '2026-11-10']);
    expect(days[1].orders.map((o) => o.id)).toEqual(['a', 'b', 'e']);
    expect(days[1].at.toISOString()).toBe('2026-11-10T15:30:00.000Z');
  });
});

describe('series helpers', () => {
  const points = [
    { timestamp: ts('2026-11-02T00:00:00Z'), equity: { value: '110' } },
    { timestamp: ts('2026-11-01T00:00:00Z'), equity: { value: '100' } },
    { timestamp: ts('2026-11-03T00:00:00Z'), equity: { value: '0' } },
    { timestamp: ts('2026-11-04T00:00:00Z'), equity: { value: '88' } },
  ];
  it('sorts and drops empty points', () => {
    const s = toSeries(points as unknown as Parameters<typeof toSeries>[0]);
    expect(s.values).toEqual([100, 110, 88]);
  });
  it('finds high, low and the largest drawdown', () => {
    expect(curveStats([100, 110, 88, 120])).toEqual({
      high: 120,
      low: 88,
      maxDrawdown: 88 / 110 - 1,
      first: 100,
      last: 120,
    });
    expect(curveStats([])).toBeNull();
  });
});

describe('holdings from fills', () => {
  const orders = [
    order({ symbol: 'TLT', filledAt: ts('2026-11-01T15:00:00Z') }),
    order({
      symbol: 'TLT',
      side: OrderSide.SELL,
      filledQuantity: { value: '4' },
      filledAt: ts('2026-11-05T15:00:00Z'),
    }),
    order({ symbol: 'GLD', filledAt: ts('2026-11-05T15:00:00Z') }),
  ];
  it('counts shares before a moment', () => {
    const q = quantitiesBefore(orders, new Date('2026-11-05T00:00:00Z'));
    expect(Object.fromEntries(q)).toEqual({ TLT: 10 });
    expect(Object.fromEntries(quantitiesBefore(orders, new Date('2026-12-01T00:00:00Z')))).toEqual({
      TLT: 6,
      GLD: 10,
    });
  });
  it('builds a lane per symbol, preferred symbols first', () => {
    const lanes = symbolLanes(orders, ['GLD', 'SPY']);
    expect(lanes.map((l) => l.symbol)).toEqual(['GLD', 'SPY', 'TLT']);
    expect(lanes[2].fills.map((f) => f.side)).toEqual(['buy', 'sell']);
  });
});

describe('order limit', () => {
  it('reads the value and limit from the stored message', () => {
    expect(parseLimitBreach('Order value $11210.84 exceeds limit $10000.00')).toEqual({
      value: 11210.84,
      limit: 10000,
    });
    expect(parseLimitBreach('Order value $5,200 exceeds the limit of $5,000; rate limit')).toEqual({
      value: 5200,
      limit: 5000,
    });
    expect(parseLimitBreach('Market is closed')).toBeNull();
  });
  it('works out the largest whole order that fits', () => {
    expect(largestThatFits(10000, 90.41)).toBe(110);
    expect(largestThatFits(100, 25)).toBe(4);
    expect(largestThatFits(100, 0)).toBe(0);
  });
  it('picks round axis steps', () => {
    expect(niceTicks(12000)).toEqual([0, 3000, 6000, 9000, 12000]);
    expect(niceTicks(0)).toEqual([0]);
  });
});

describe('windowed', () => {
  const d = (s: string) => new Date(s);
  const series = {
    dates: [d('2026-01-01'), d('2026-05-01'), d('2026-10-01')],
    values: [100, 120, 130],
  };
  it('opens with the value in force and closes at the current value', () => {
    const w = windowed(series, d('2026-08-01'), d('2026-11-16'), 135);
    expect(w.values).toEqual([120, 120, 130, 130, 135]);
    expect(w.dates[1].getTime()).toBe(d('2026-10-01').getTime() - 1);
    expect(w.dates[4]).toEqual(d('2026-11-16'));
  });
  it('draws a flat line when nothing changed inside the window', () => {
    const w = windowed(series, d('2026-10-15'), d('2026-11-16'), null);
    expect(w.values).toEqual([130, 130]);
  });
  it('stays empty for a session that started after the window', () => {
    expect(windowed(series, d('2025-01-01'), d('2025-06-01'), 1).dates).toEqual([]);
  });
});

describe('asOf', () => {
  it('carries the last value forward and is NaN before the first', () => {
    const d = (s: string) => new Date(s);
    const out = asOf({ dates: [d('2026-01-02'), d('2026-01-05')], values: [1, 2] }, [
      d('2026-01-01'),
      d('2026-01-03'),
      d('2026-01-05'),
    ]);
    expect(Number.isNaN(out[0])).toBe(true);
    expect(out.slice(1)).toEqual([1, 2]);
  });
});

describe('planning a live session', () => {
  it('lists the next monthly rebalances', () => {
    const out = nextRebalances('Monthly', new Date(Date.UTC(2026, 10, 16)), 3);
    expect(out.map((d) => d.toISOString().slice(0, 10))).toEqual([
      '2026-12-01',
      '2027-01-04',
      '2027-02-01',
    ]);
    expect(nextRebalances('Daily', new Date(Date.UTC(2026, 10, 16)), 3)).toEqual([]);
  });
  it('splits capital by the current weights at the last prices', () => {
    const out = sharesFor(10000, [
      { symbol: 'TLT', value: 600, price: 90.41 },
      { symbol: 'GLD', value: 400, price: 247.86 },
    ]);
    expect(out.buys).toEqual([
      { symbol: 'TLT', shares: 66 },
      { symbol: 'GLD', shares: 16 },
    ]);
    expect(out.cash).toBeCloseTo(10000 - 66 * 90.41 - 16 * 247.86, 6);
    expect(sharesFor(0, [])).toEqual({ buys: [], cash: 0 });
  });
});
