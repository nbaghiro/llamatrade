/** A session's filled orders, grouped by the New York trading day they filled on. */

import { num, toDate } from '@llamatrade/core/format';
import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';

import { etParts } from '../../../lib/marketClock';

export interface Fill {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  notional: number;
  at: Date;
}

export interface FillDay {
  /** The trading day at UTC midnight. */
  day: Date;
  /** When the first fill of the day happened. */
  at: Date;
  fills: Fill[];
}

/** Filled and partly filled orders as fills; orders without a fill time are left out. */
export function toFills(orders: readonly Order[]): Fill[] {
  const out: Fill[] = [];
  for (const o of orders) {
    if (o.status !== OrderStatus.FILLED && o.status !== OrderStatus.PARTIAL) continue;
    const at = toDate(o.filledAt) ?? toDate(o.submittedAt);
    const quantity = num(o.filledQuantity) || num(o.quantity);
    const price = num(o.averageFillPrice);
    if (!at || quantity <= 0) continue;
    out.push({
      id: o.id,
      symbol: o.symbol,
      side: o.side === OrderSide.SELL ? 'sell' : 'buy',
      quantity,
      price,
      notional: quantity * price,
      at,
    });
  }
  return out.sort((a, b) => a.at.getTime() - b.at.getTime());
}

/** Fills grouped by New York calendar day, oldest first; sells before buys within a day. */
export function fillDays(fills: readonly Fill[]): FillDay[] {
  const byDay = new Map<number, FillDay>();
  for (const f of fills) {
    const p = etParts(f.at);
    const day = new Date(Date.UTC(p.year, p.month, p.day));
    const key = day.getTime();
    const entry = byDay.get(key);
    if (entry) {
      entry.fills.push(f);
      if (f.at < entry.at) entry.at = f.at;
    } else {
      byDay.set(key, { day, at: f.at, fills: [f] });
    }
  }
  const days = [...byDay.values()].sort((a, b) => a.day.getTime() - b.day.getTime());
  for (const d of days) {
    d.fills.sort((a, b) => (a.side === b.side ? 0 : a.side === 'sell' ? -1 : 1));
  }
  return days;
}
