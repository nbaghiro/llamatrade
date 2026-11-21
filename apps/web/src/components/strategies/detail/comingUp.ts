import { marketDay } from '../../../lib/marketHolidays';
import { nextRebalanceDate } from '../../../lib/sessionState';

export interface ComingUp {
  at: Date;
  kind: 'rebalance' | 'closed' | 'early';
  text: string;
}

const DAY_MS = 86_400_000;

/**
 * What happens next for a running session over the coming `days`: its next scheduled
 * rebalance, and NYSE closures and early closes. `today` is the New York date at UTC midnight.
 */
export function comingUp(rebalance: string, today: Date, days = 21): ComingUp[] {
  const out: ComingUp[] = [];
  const next = nextRebalanceDate(rebalance, today);
  const daily = rebalance.trim().toLowerCase() === 'daily';
  if (next && next.getTime() - today.getTime() <= days * DAY_MS) {
    out.push({ at: next, kind: 'rebalance', text: 'Rebalance' });
  }
  for (let i = daily ? 0 : 1; i <= days; i++) {
    const d = new Date(today.getTime() + i * DAY_MS);
    const m = marketDay(d);
    if (m.name && m.closed) out.push({ at: d, kind: 'closed', text: 'Market closed' });
    else if (m.earlyClose) out.push({ at: d, kind: 'early', text: 'Closes at 13:00' });
  }
  return out.sort((a, b) => a.at.getTime() - b.at.getTime());
}
