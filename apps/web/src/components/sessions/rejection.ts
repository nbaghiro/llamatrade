import { OrderSide, type Order } from '@llamatrade/core/proto/trading_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';

import { formatMoney, formatNumber } from '../../lib/format';
import { RISK_CHECKS, stoppingChecks } from '../../lib/sessionState';

import { outcomeOf } from './orderLabels';
import { etDayKey, isFilled, largestThatFits, orderTime, parseLimitBreach } from './timeline';

const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/** A rejected or not-sent order: a stop before Alpaca, or a refusal by Alpaca. */
export const isRefused = (o: Order) => {
  const out = outcomeOf(o);
  return out === 'stopped' || out === 'rejected';
};

export interface Rejection {
  order: Order;
  at: Date;
  /** "Buy 124 TLT rejected". */
  title: string;
  /** What stopped it, in a sentence. */
  reason: string;
  /** Whether anything reached Alpaca. */
  sent: string;
  /** Only one check stopped it, so the others passed. */
  othersClear: boolean;
  /** What the rejection left in the sleeve, from the day's fills; null when nothing filled. */
  leftBehind: string | null;
  /** The price the order was valued at, when known. */
  price: number;
  /** Whole shares that fit under the breached limit; 0 when there is no limit to fit under. */
  fits: number;
}

/** The price an order was valued at: from its stored limit breach, else its limit price. */
function priceOf(o: Order): number {
  const quantity = toNumber(o.quantity);
  const breach = parseLimitBreach(o.statusMessage);
  if (breach && quantity > 0) return breach.value / quantity;
  return toNumber(o.limitPrice);
}

/** Everything the card on a rejected order's marker says, from the order and the day's fills. */
export function describeRejection(order: Order, sameDay: readonly Order[]): Rejection | null {
  const at = orderTime(order);
  if (!at || !isRefused(order)) return null;
  const stopped = outcomeOf(order) === 'stopped';
  const buy = order.side !== OrderSide.SELL;
  const quantity = toNumber(order.quantity);
  const breach = parseLimitBreach(order.statusMessage);
  const price = priceOf(order);

  let reason: string;
  if (breach) {
    reason = `${formatMoney(breach.value)} is over this session's limit of ${formatMoney(breach.limit)} per order.`;
  } else if (stopped) {
    const names = stoppingChecks(order.statusMessage).map((i) => RISK_CHECKS[i]?.toLowerCase());
    reason = names.length
      ? `It failed the ${names.join(' and ')} check.`
      : order.statusMessage || 'A risk check stopped it.';
  } else {
    reason = order.statusMessage
      ? `Alpaca refused it: ${order.statusMessage}`
      : 'Alpaca refused it without a reason.';
  }
  const othersClear = stopped && stoppingChecks(order.statusMessage).length === 1;

  const key = etDayKey(at);
  const filled = sameDay.filter((o) => {
    const t = orderTime(o);
    return o.id !== order.id && isFilled(o) && t !== null && etDayKey(t) === key;
  });
  const opposite = filled.filter((o) => (o.side === OrderSide.SELL) === buy);
  const proceeds = opposite.reduce(
    (s, o) => s + toNumber(o.filledQuantity) * toNumber(o.averageFillPrice),
    0
  );
  let leftBehind: string | null = null;
  if (buy && opposite.length > 0 && proceeds > 0) {
    const symbols = [...new Set(opposite.map((o) => o.symbol))].join(' and ');
    leftBehind = `The ${symbols} ${opposite.length === 1 ? 'sale' : 'sales'} filled, so ${formatMoney(proceeds)} stays in the sleeve as cash until the next rebalance.`;
  } else if (!buy) {
    leftBehind = `The ${qty(quantity)} ${order.symbol} shares stay in the sleeve.`;
  }

  return {
    order,
    at,
    title: `${buy ? 'Buy' : 'Sell'} ${qty(quantity)} ${order.symbol} ${stopped ? 'not sent' : 'rejected'}`,
    reason,
    othersClear,
    sent: stopped ? 'Nothing was sent to Alpaca.' : 'Alpaca received it and refused it.',
    leftBehind,
    price,
    fits: breach && price > 0 ? largestThatFits(breach.limit, price) : 0,
  };
}

export interface OrdersToday {
  filled: number;
  refused: number;
}

/** Today's orders by outcome, New York day. */
export function ordersToday(orders: readonly Order[], now: Date): OrdersToday {
  const key = etDayKey(now);
  const today = orders.filter((o) => {
    const t = orderTime(o);
    return t !== null && etDayKey(t) === key;
  });
  return {
    filled: today.filter(isFilled).length,
    refused: today.filter(isRefused).length,
  };
}
