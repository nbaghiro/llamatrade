import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import { describeRejection, isRefused, ordersToday } from '../rejection';

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });

const order = (over: Record<string, unknown>) =>
  ({
    id: 'o',
    symbol: 'TLT',
    side: OrderSide.BUY,
    status: OrderStatus.FILLED,
    statusMessage: '',
    quantity: { value: '10' },
    filledQuantity: { value: '10' },
    averageFillPrice: { value: '90' },
    limitPrice: { value: '0' },
    ...over,
  }) as unknown as Order;

const stoppedBuy = order({
  id: 'r',
  quantity: { value: '124' },
  filledQuantity: { value: '0' },
  status: OrderStatus.REJECTED,
  statusMessage: 'Order value $11210.84 exceeds limit $10000.00',
  createdAt: ts('2026-11-17T15:31:02Z'),
});
const gldSale = order({
  id: 'g',
  symbol: 'GLD',
  side: OrderSide.SELL,
  filledQuantity: { value: '9' },
  averageFillPrice: { value: '247.86' },
  filledAt: ts('2026-11-17T15:31:07Z'),
});

describe('describeRejection', () => {
  it('describes a buy stopped by the order value check', () => {
    const r = describeRejection(stoppedBuy, [stoppedBuy, gldSale]);
    expect(r?.title).toBe('Buy 124 TLT not sent');
    expect(r?.reason).toBe("$11,210.84 is over this session's limit of $10,000.00 per order.");
    expect(r?.sent).toBe('Nothing was sent to Alpaca.');
    expect(r?.othersClear).toBe(true);
    expect(r?.price).toBeCloseTo(90.41, 2);
    expect(r?.fits).toBe(110);
    expect(r?.leftBehind).toBe(
      'The GLD sale filled, so $2,230.74 stays in the sleeve as cash until the next rebalance.'
    );
  });

  it('leaves out fills from other days', () => {
    const old = order({ ...gldSale, id: 'old', filledAt: ts('2026-11-16T15:31:07Z') });
    expect(describeRejection(stoppedBuy, [old])?.leftBehind).toBeNull();
  });

  it('says what a refused sale leaves behind', () => {
    const sell = order({
      id: 's',
      side: OrderSide.SELL,
      quantity: { value: '5' },
      status: OrderStatus.REJECTED,
      statusMessage: 'insufficient qty',
      submittedAt: ts('2026-11-17T15:31:02Z'),
    });
    const r = describeRejection(sell, []);
    expect(r?.title).toBe('Sell 5 TLT rejected');
    expect(r?.sent).toBe('Alpaca received it and refused it.');
    expect(r?.reason).toBe('Alpaca refused it: insufficient qty');
    expect(r?.leftBehind).toBe('The 5 TLT shares stay in the sleeve.');
    expect(r?.fits).toBe(0);
    expect(r?.othersClear).toBe(false);
  });

  it('names the checks a stop failed when there is no limit to read', () => {
    const r = describeRejection(
      order({
        ...stoppedBuy,
        statusMessage: 'Market is closed; rate limit reached',
      }),
      []
    );
    expect(r?.reason).toBe('It failed the market is open and order rate check.');
    expect(r?.othersClear).toBe(false);
    expect(r?.fits).toBe(0);
  });

  it('ignores filled orders and orders with no time', () => {
    expect(describeRejection(gldSale, [])).toBeNull();
    expect(describeRejection(order({ ...stoppedBuy, createdAt: undefined }), [])).toBeNull();
  });
});

describe('ordersToday', () => {
  it('counts today’s fills and refusals in New York time', () => {
    const now = new Date('2026-11-17T16:00:00Z');
    const yesterday = order({ id: 'y', filledAt: ts('2026-11-16T20:00:00Z') });
    expect(ordersToday([stoppedBuy, gldSale, yesterday], now)).toEqual({ filled: 1, refused: 1 });
    expect(isRefused(stoppedBuy)).toBe(true);
    expect(isRefused(gldSale)).toBe(false);
  });
});
