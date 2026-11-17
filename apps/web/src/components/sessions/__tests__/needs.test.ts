import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import { needsYou } from '../needs';
import type { SessionRow } from '../sessionRows';

const ts = (iso: string) => ({ seconds: BigInt(Math.floor(Date.parse(iso) / 1000)), nanos: 0 });
const row = (id: string, name: string, state: SessionRow['state']) =>
  ({ session: { id }, name, state, execution: null }) as unknown as SessionRow;
const order = (over: Record<string, unknown>) =>
  ({
    id: 'o1',
    sessionId: 's1',
    symbol: 'TLT',
    side: OrderSide.BUY,
    quantity: { value: '124' },
    status: OrderStatus.REJECTED,
    statusMessage: 'Order value $11210.84 exceeds limit $10000.00',
    createdAt: ts('2026-11-16T15:31:00Z'),
    ...over,
  }) as unknown as Order;

describe('needsYou', () => {
  const now = new Date('2026-11-16T16:00:00Z');
  it('lists frozen sessions, then orders not sent today', () => {
    const items = needsYou(
      [row('s1', 'Recession Radar', 'running'), row('s2', 'Momentum Sectors', 'frozen')],
      [order({}), order({ id: 'old', createdAt: ts('2026-11-10T15:31:00Z') })],
      now
    );
    expect(items.map((i) => i.kind)).toEqual(['frozen', 'order']);
    expect(items[1].title).toBe('Recession Radar: buy 124 TLT not sent');
    expect(items[1].detail).toBe(
      'At 10:31. $11,210.84 is over the $10,000 per-order limit. Nothing was sent to Alpaca.'
    );
    expect(items[1].href).toBe('/trading/orders/o1');
  });
  it('is empty on a quiet day', () => {
    expect(
      needsYou([row('s1', 'A', 'running')], [order({ status: OrderStatus.FILLED })], now)
    ).toEqual([]);
  });
  it('names an order Alpaca refused after it was sent', () => {
    const [item] = needsYou(
      [row('s1', 'A', 'running')],
      [
        order({
          submittedAt: ts('2026-11-16T15:31:00Z'),
          statusMessage: 'insufficient buying power',
        }),
      ],
      now
    );
    expect(item.title).toBe('A: buy 124 TLT rejected');
    expect(item.detail).toBe('At 10:31. insufficient buying power');
  });
});
