import { OrderSide, type Order } from '@llamatrade/core/proto/trading_pb';
import { toDate } from '@llamatrade/core/stores/backtest';

import { orderOutcome, type OrderOutcome } from '../../lib/sessionState';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Nov 4 09:31:07" in New York time. */
export function placedAt(order: Order): string {
  const d = toDate(order.submittedAt) ?? toDate(order.createdAt);
  if (!d) return '·';
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(d);
  const get = (t: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === t)?.value ?? '';
  return `${MON[Number(get('month')) - 1]} ${get('day')} ${get('hour')}:${get('minute')}:${get('second')}`;
}

export const sideWord = (s: OrderSide) => (s === OrderSide.SELL ? 'SELL' : 'BUY');

export const outcomeOf = (o: Order): OrderOutcome =>
  orderOutcome(o.status, Boolean(o.submittedAt?.seconds));
