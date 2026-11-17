import { OrderSide, type Order } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import {
  accountHistory,
  allocationSteps,
  byDay,
  estimateRebalance,
  etDayKey,
  fillFor,
  freeCashSteps,
  maxDrawdown,
  sleeveFills,
  sleeveInitials,
  valueAt,
  windowFrom,
  type SleeveFill,
} from '../history';

const T = (iso: string) => Date.parse(iso);
const ts = (iso: string) => ({ seconds: BigInt(Math.floor(T(iso) / 1000)), nanos: 0 });

function order(over: Partial<Record<string, unknown>> & { id: string; sessionId: string }): Order {
  return {
    symbol: 'TLT',
    side: OrderSide.BUY,
    filledQuantity: { value: '10' },
    averageFillPrice: { value: '90.5' },
    filledAt: ts('2026-11-17T15:31:00Z'),
    ...over,
  } as unknown as Order;
}

describe('sleeveFills', () => {
  const sessions = [
    { id: 's1', sleeveId: 'sl1' },
    { id: 's2', sleeveId: '' },
  ];

  it('keeps filled orders whose session has a sleeve, newest first', () => {
    const fills = sleeveFills(
      [
        order({ id: 'a', sessionId: 's1', filledAt: ts('2026-11-10T15:00:00Z') }),
        order({ id: 'b', sessionId: 's1', side: OrderSide.SELL }),
        order({ id: 'c', sessionId: 's2' }),
        order({ id: 'd', sessionId: 's1', filledQuantity: { value: '0' } }),
        order({ id: 'e', sessionId: 'missing' }),
      ],
      sessions
    );
    expect(fills.map((f) => f.id)).toEqual(['b', 'a']);
    expect(fills[0]).toMatchObject({ sleeveId: 'sl1', side: 'sell', qty: 10, price: 90.5 });
  });

  it('falls back to the limit price when there is no average fill price', () => {
    const [f] = sleeveFills(
      [
        order({
          id: 'a',
          sessionId: 's1',
          averageFillPrice: undefined,
          limitPrice: { value: '88' },
        }),
      ],
      sessions
    );
    expect(f.price).toBe(88);
  });
});

describe('byDay and etDayKey', () => {
  it('groups by the New York day, not the UTC day', () => {
    expect(etDayKey(new Date('2026-11-18T03:00:00Z'))).toBe('2026-11-17');
    const groups = byDay([
      { at: new Date('2026-11-17T15:00:00Z') },
      { at: new Date('2026-11-18T03:00:00Z') },
      { at: new Date('2026-11-16T15:00:00Z') },
    ]);
    expect(groups.map((g) => [g.key, g.items.length])).toEqual([
      ['2026-11-16', 1],
      ['2026-11-17', 2],
    ]);
    expect(groups[1].at.toISOString()).toBe('2026-11-17T15:00:00.000Z');
  });
});

describe('valueAt', () => {
  const pts = [
    { t: 10, v: 1 },
    { t: 20, v: 2 },
  ];
  it('forward-fills and is null before the first point', () => {
    expect(valueAt(pts, 5)).toBeNull();
    expect(valueAt(pts, 10)).toBe(1);
    expect(valueAt(pts, 15)).toBe(1);
    expect(valueAt(pts, 99)).toBe(2);
  });
});

describe('accountHistory', () => {
  const deposit = T('2026-01-06T15:00:00Z');
  const alloc = T('2026-01-15T14:01:00Z');
  const now = T('2026-11-17T15:00:00Z');
  const sleeve = {
    points: [
      { t: T('2026-01-15T16:00:00Z'), v: 35_000 },
      { t: T('2026-06-01T16:00:00Z'), v: 36_000 },
    ],
    allocations: [{ t: alloc, amount: 35_000 }],
  };
  const cash = [
    { t: deposit, amount: 100_000 },
    { t: alloc, amount: -35_000 },
  ];

  it('adds sleeves and free cash, with the allocation standing in before the curve starts', () => {
    const h = accountHistory([sleeve], cash, now);
    const at = (iso: string) => h.dates.findIndex((d) => d.getTime() === T(iso));
    expect(h.equity[at('2026-01-15T14:01:00Z')]).toBe(100_000);
    expect(h.equity[at('2026-06-01T16:00:00Z')]).toBe(101_000);
    expect(h.added[h.added.length - 1]).toBe(100_000);
    expect(h.dates[h.dates.length - 1].getTime()).toBe(now);
  });

  it('starts at the first money and draws risers just before each step', () => {
    const h = accountHistory([sleeve], cash, now);
    expect(h.dates[0].getTime()).toBe(deposit);
    expect(h.dates.some((d) => d.getTime() === alloc - 60_000)).toBe(true);
  });

  it('ignores anything after now', () => {
    const h = accountHistory([sleeve], [...cash, { t: now + 1, amount: 5 }], now);
    expect(h.equity[h.equity.length - 1]).toBe(101_000);
  });

  it('windows from a start, opening with the value there', () => {
    const h = accountHistory([sleeve], cash, now);
    const start = new Date('2026-03-01T00:00:00Z');
    const w = windowFrom(h, start);
    expect(w.dates[0]).toBe(start);
    expect(w.equity[0]).toBe(100_000);
    expect(windowFrom(h, new Date(0))).toBe(h);
  });
});

describe('cash steps from activity rows', () => {
  const rows = [
    { kind: 'deposit', sublabel: 'Paper credit', amount: 100, signed: 100, at: new Date(1) },
    { kind: 'allocation', sublabel: 'Risk Parity', amount: 30, signed: -30, at: new Date(2) },
    { kind: 'allocation', sublabel: 'Other', amount: 5, signed: -5, at: new Date(3) },
    { kind: 'buy', sublabel: '1 at 2', amount: 2, signed: 0, at: new Date(4) },
  ];
  it('reads free-cash movements and per-sleeve allocations', () => {
    expect(freeCashSteps(rows)).toEqual([
      { t: 1, amount: 100 },
      { t: 2, amount: -30 },
      { t: 3, amount: -5 },
    ]);
    expect(allocationSteps(rows, 'Risk Parity')).toEqual([{ t: 2, amount: 30 }]);
  });
});

describe('maxDrawdown', () => {
  it('is the largest fall from a running peak', () => {
    expect(maxDrawdown([100, 120, 90, 130, 117])).toBeCloseTo(-0.25);
    expect(maxDrawdown([1, 2, 3])).toBe(0);
    expect(maxDrawdown([])).toBe(0);
  });
});

describe('estimateRebalance', () => {
  it('trades whole shares toward fixed targets and skips what is on target', () => {
    const orders = estimateRebalance(
      [
        { symbol: 'TLT', qty: 205, price: 90.6, marketValue: 18_573 },
        { symbol: 'GLD', qty: 54, price: 246.87, marketValue: 13_330.98 },
        { symbol: 'XLK', qty: 1, price: 0, marketValue: 0 },
      ],
      { TLT: 0.6, GLD: 0.4, XLK: 0.1 },
      31_904.2
    );
    expect(orders).toEqual([
      { symbol: 'TLT', side: 'buy', qty: 6, amount: 6 * 90.6 },
      { symbol: 'GLD', side: 'sell', qty: 2, amount: 2 * 246.87 },
    ]);
  });

  it('leaves out holdings without a target', () => {
    expect(estimateRebalance([{ symbol: 'A', qty: 1, price: 1, marketValue: 1 }], {}, 10)).toEqual(
      []
    );
  });
});

describe('fillFor', () => {
  const fill = (over: Partial<SleeveFill>): SleeveFill => ({
    id: 'f',
    at: new Date('2026-11-17T15:31:00Z'),
    sleeveId: 'sl1',
    symbol: 'TLT',
    side: 'buy',
    qty: 42,
    price: 90.41,
    ...over,
  });

  it('matches symbol, side and size within five minutes, closest first', () => {
    const row = { kind: 'buy', symbol: 'TLT', qty: 42, at: new Date('2026-11-17T15:31:30Z') };
    const near = fill({ id: 'near' });
    const far = fill({ id: 'far', at: new Date('2026-11-17T15:34:00Z') });
    expect(fillFor(row, [far, near])?.id).toBe('near');
    expect(fillFor({ ...row, qty: 41 }, [near])).toBeNull();
    expect(fillFor({ ...row, kind: 'sell' }, [near])).toBeNull();
    expect(fillFor({ ...row, at: new Date('2026-11-17T16:00:00Z') }, [near])).toBeNull();
    expect(fillFor({ ...row, kind: 'deposit' }, [near])).toBeNull();
  });
});

describe('sleeveInitials', () => {
  it('takes the first letters of the first two words', () => {
    expect(sleeveInitials('All-Weather Portfolio')).toBe('AW');
    expect(sleeveInitials('Recession Radar')).toBe('RR');
    expect(sleeveInitials('Momentum')).toBe('M');
  });
});
