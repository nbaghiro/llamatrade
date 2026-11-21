import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import {
  buildRebalanceDiff,
  closesOn,
  fillPrices,
  lineNote,
  netText,
  tradeText,
  untradedSymbols,
} from '../rebalanceDiff';
import { fillDays } from '../timeline';

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });

let n = 0;
const fill = (
  symbol: string,
  side: 'buy' | 'sell',
  qty: number,
  price: number,
  at: string,
  status: OrderStatus = OrderStatus.FILLED
) =>
  ({
    id: `o${++n}`,
    symbol,
    side: side === 'buy' ? OrderSide.BUY : OrderSide.SELL,
    status,
    filledQuantity: { value: String(qty) },
    quantity: { value: String(qty) },
    averageFillPrice: { value: String(price) },
    filledAt: ts(at),
  }) as unknown as Order;

const NOV10 = '2026-11-10T20:50:00Z';
const NOV17 = '2026-11-17T15:31:00Z';

const history = [
  fill('TLT', 'buy', 163, 92, NOV10),
  fill('GLD', 'buy', 63, 240, NOV10),
  fill('TLT', 'buy', 42, 90.41, NOV17),
  fill('GLD', 'sell', 9, 247.86, NOV17),
];

describe('fillPrices', () => {
  it('averages a symbol over its fills, weighted by shares', () => {
    const prices = fillPrices([
      fill('TLT', 'buy', 10, 90, NOV17),
      fill('TLT', 'buy', 30, 94, NOV17),
    ]);
    expect(prices.get('TLT')).toBeCloseTo(93);
  });
  it('skips zero prices and unfilled orders', () => {
    const prices = fillPrices([
      fill('TLT', 'buy', 10, 0, NOV17),
      fill('GLD', 'buy', 5, 200, NOV17, OrderStatus.REJECTED),
    ]);
    expect(prices.size).toBe(0);
  });
});

describe('buildRebalanceDiff', () => {
  const days = fillDays(history);

  it('compares with the holdings left by the previous rebalance that traded', () => {
    const d = buildRebalanceDiff(history, days, 1);
    expect(d).not.toBeNull();
    if (!d) return;
    expect(d.previousAt?.toISOString()).toBe('2026-11-10T20:50:00.000Z');
    expect(d.at.toISOString()).toBe('2026-11-17T15:31:00.000Z');
    const tlt = d.lines.find((l) => l.symbol === 'TLT');
    const gld = d.lines.find((l) => l.symbol === 'GLD');
    expect(tlt).toMatchObject({ before: 163, after: 205, bought: 42, sold: 0 });
    expect(gld).toMatchObject({ before: 63, after: 54, bought: 0, sold: 9 });
    expect(d.changes).toBe(2);
    expect(d.added).toBe(1);
    expect(d.removed).toBe(1);
    expect(d.ordersFilled).toBe(2);
  });

  it('values both sides at the fill prices and weights them against the holdings', () => {
    const d = buildRebalanceDiff(history, days, 1);
    if (!d) throw new Error('no diff');
    const tlt = d.lines.find((l) => l.symbol === 'TLT');
    expect(tlt?.priceSource).toBe('fill');
    expect(tlt?.valueBefore).toBeCloseTo(163 * 90.41);
    expect(tlt?.valueAfter).toBeCloseTo(205 * 90.41);
    const total = 205 * 90.41 + 54 * 247.86;
    expect(d.valueAfter).toBeCloseTo(total);
    expect(tlt?.weightAfter).toBeCloseTo((205 * 90.41) / total);
    const weights = d.lines.reduce((s, l) => s + (l.weightAfter ?? 0), 0);
    expect(weights).toBeCloseTo(1);
  });

  it('nets the cash the fills paid in and spent', () => {
    const d = buildRebalanceDiff(history, days, 1);
    expect(d?.cashFromOrders).toBeCloseTo(9 * 247.86 - 42 * 90.41);
  });

  it('treats the first rebalance as starting from nothing', () => {
    const d = buildRebalanceDiff(history, days, 0);
    if (!d) throw new Error('no diff');
    expect(d.previousAt).toBeNull();
    expect(d.lines.every((l) => l.before === 0)).toBe(true);
    expect(d.valueBefore).toBe(0);
    expect(d.lines.map((l) => lineNote(l))).toEqual([
      'GLD is new in the sleeve.',
      'TLT is new in the sleeve.',
    ]);
  });

  it('returns null for an index with no rebalance', () => {
    expect(buildRebalanceDiff(history, days, 5)).toBeNull();
    expect(buildRebalanceDiff([], [], 0)).toBeNull();
  });

  it('keeps a symbol sold in full, ending at zero shares', () => {
    const orders = [
      fill('SMH', 'buy', 12, 250, NOV10),
      fill('XLK', 'buy', 10, 230, NOV10),
      fill('SMH', 'sell', 12, 263.3, NOV17),
    ];
    const d = buildRebalanceDiff(orders, fillDays(orders), 1, { XLK: 236.4 });
    const smh = d?.lines.find((l) => l.symbol === 'SMH');
    expect(smh).toMatchObject({ before: 12, after: 0, changed: true, weightAfter: 0 });
    expect(smh && lineNote(smh)).toBe('Sold all 12 SMH.');
  });

  it('prices held symbols the rebalance did not trade from that day’s close', () => {
    const orders = [
      fill('VTI', 'buy', 10, 290, NOV10),
      fill('BND', 'buy', 20, 72, NOV10),
      fill('BND', 'buy', 5, 72.9, NOV17),
    ];
    const ds = fillDays(orders);
    expect(untradedSymbols(orders, ds[1])).toEqual(['VTI']);
    const d = buildRebalanceDiff(orders, ds, 1, { VTI: 298.4 });
    const vti = d?.lines.find((l) => l.symbol === 'VTI');
    expect(vti).toMatchObject({ priceSource: 'close', price: 298.4, changed: false });
    expect(d?.changes).toBe(1);
  });

  it('leaves values and weights unknown when an untraded holding has no price', () => {
    const orders = [
      fill('VTI', 'buy', 10, 290, NOV10),
      fill('BND', 'buy', 20, 72, NOV10),
      fill('BND', 'buy', 5, 72.9, NOV17),
    ];
    const d = buildRebalanceDiff(orders, fillDays(orders), 1);
    const vti = d?.lines.find((l) => l.symbol === 'VTI');
    const bnd = d?.lines.find((l) => l.symbol === 'BND');
    expect(vti?.price).toBeNull();
    expect(vti?.valueAfter).toBeNull();
    expect(bnd?.valueAfter).toBeCloseTo(25 * 72.9);
    expect(bnd?.weightAfter).toBeNull();
    expect(d?.valueAfter).toBeNull();
  });

  it('counts partial fills at their filled quantity', () => {
    const orders = [
      fill('TLT', 'buy', 100, 90, NOV10),
      fill('TLT', 'buy', 7, 91, NOV17, OrderStatus.PARTIAL),
    ];
    const d = buildRebalanceDiff(orders, fillDays(orders), 1);
    expect(d?.lines[0]).toMatchObject({ before: 100, after: 107, bought: 7 });
  });

  it('treats a zero fill price as unknown and falls back to the close', () => {
    const orders = [fill('TLT', 'buy', 100, 90, NOV10), fill('TLT', 'buy', 5, 0, NOV17)];
    const ds = fillDays(orders);
    const none = buildRebalanceDiff(orders, ds, 1);
    expect(none?.lines[0].price).toBeNull();
    expect(none?.cashFromOrders).toBe(0);
    const closed = buildRebalanceDiff(orders, ds, 1, { TLT: 91 });
    expect(closed?.lines[0]).toMatchObject({ price: 91, priceSource: 'close' });
  });

  it('notes the gap to a fixed target', () => {
    const d = buildRebalanceDiff(history, days, 1, {}, { TLT: 0.6, GLD: 0.4 });
    const tlt = d?.lines.find((l) => l.symbol === 'TLT');
    expect(tlt?.target).toBe(0.6);
    expect(tlt && lineNote(tlt)).toMatch(
      /^TLT ended at 58\.1% of holdings, 1\.9 points under its 60\.0% target\.$/
    );
  });

  it('puts changed lines first, then larger holdings', () => {
    const orders = [
      fill('VTI', 'buy', 100, 300, NOV10),
      fill('BND', 'buy', 10, 72, NOV10),
      fill('BND', 'buy', 1, 73, NOV17),
    ];
    const d = buildRebalanceDiff(orders, fillDays(orders), 1, { VTI: 300 });
    expect(d?.lines.map((l) => l.symbol)).toEqual(['BND', 'VTI']);
  });
});

describe('wording', () => {
  const days = fillDays(history);
  const d = buildRebalanceDiff(history, days, 1);
  const tlt = d?.lines.find((l) => l.symbol === 'TLT');
  const gld = d?.lines.find((l) => l.symbol === 'GLD');

  it('says what was traded and at what price', () => {
    expect(tlt && tradeText(tlt)).toBe('bought 42 at $90.41');
    expect(gld && tradeText(gld)).toBe('sold 9 at $247.86');
  });
  it('gives the net change for the unified view', () => {
    expect(tlt && netText(tlt)).toBe('+42');
    expect(gld && netText(gld)).toBe('−9');
  });
  it('has no note for a change without a target', () => {
    expect(tlt && lineNote(tlt)).toBeNull();
  });
});

describe('closesOn', () => {
  it('picks the bar for the New York day and ignores missing or zero closes', () => {
    const t = (iso: string) => Date.parse(iso) / 1000;
    const out = closesOn(
      {
        VTI: [
          { time: t('2026-11-16T05:00:00Z'), close: 296 },
          { time: t('2026-11-17T05:00:00Z'), close: 298.4 },
        ],
        BND: [{ time: t('2026-11-17T05:00:00Z'), close: 0 }],
        IWM: [],
      },
      '2026-11-17'
    );
    expect(out).toEqual({ VTI: 298.4 });
  });
});
