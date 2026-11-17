import type { Order } from '@llamatrade/core/proto/trading_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';

import { formatMoney, formatNumber } from '../../lib/format';

import { outcomeOf, sideWord } from './orderLabels';
import type { SessionRow } from './sessionRows';
import { etDayKey, etHm, orderTime, parseLimitBreach } from './timeline';

export interface NeedItem {
  id: string;
  kind: 'frozen' | 'error' | 'order';
  /** "Momentum Sectors is frozen". */
  title: string;
  /** A longer sentence for the desktop card. */
  detail: string;
  /** The one figure that matters, for a phone row. */
  short: string;
  href: string;
}

const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/** What waits on the person: frozen or failed sessions, then today's orders that weren't sent. */
export function needsYou(
  rows: readonly SessionRow[],
  orders: readonly Order[],
  now: Date = new Date()
): NeedItem[] {
  const names = new Map(rows.map((r) => [r.session.id, r.name]));
  const out: NeedItem[] = [];
  for (const r of rows) {
    if (r.state === 'frozen') {
      out.push({
        id: `frozen-${r.session.id}`,
        kind: 'frozen',
        title: `${r.name} is frozen`,
        detail:
          'The ledger and Alpaca disagree about its holdings. Orders for this sleeve wait until the two agree.',
        short: 'Ledger and Alpaca disagree',
        href: `/trading/${r.session.id}`,
      });
    } else if (r.state === 'error') {
      out.push({
        id: `error-${r.session.id}`,
        kind: 'error',
        title: `${r.name} stopped with an error`,
        detail: r.execution?.errorMessage || 'It places no new orders.',
        short: 'Stopped with an error',
        href: `/trading/${r.session.id}`,
      });
    }
  }
  const today = etDayKey(now);
  for (const o of orders) {
    const at = orderTime(o);
    if (!at || etDayKey(at) !== today) continue;
    const outcome = outcomeOf(o);
    if (outcome !== 'stopped' && outcome !== 'rejected') continue;
    const name = names.get(o.sessionId) ?? 'A session';
    const what = `${sideWord(o.side).toLowerCase()} ${qty(toNumber(o.quantity))} ${o.symbol}`;
    const breach = parseLimitBreach(o.statusMessage);
    out.push({
      id: `order-${o.id}`,
      kind: 'order',
      title: `${name}: ${what} ${outcome === 'stopped' ? 'not sent' : 'rejected'}`,
      detail: breach
        ? `At ${etHm(at)}. ${formatMoney(breach.value)} is over the ${formatMoney(breach.limit, { dp: 0 })} per-order limit. Nothing was sent to Alpaca.`
        : `At ${etHm(at)}. ${o.statusMessage || (outcome === 'stopped' ? 'A risk check stopped it before it reached Alpaca.' : 'Alpaca refused it.')}`,
      short: breach
        ? `${name} · over ${formatMoney(breach.limit, { dp: 0 })} · ${etHm(at)}`
        : `${name} · ${etHm(at)}`,
      href: `/trading/orders/${o.id}`,
    });
  }
  return out;
}
