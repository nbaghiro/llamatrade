import type { ConditionExpression, PriceField } from '@llamatrade/core/strategy/types';

export type RebalanceEvery = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annually';

const EVERY: Record<string, RebalanceEvery> = {
  '1D': 'daily',
  '1W': 'weekly',
  '1M': 'monthly',
  '3M': 'quarterly',
  '1Y': 'annually',
};

export function rebalanceEvery(timeframe: string): RebalanceEvery {
  return EVERY[timeframe] ?? 'monthly';
}

function periodKey(d: Date, every: RebalanceEvery): string {
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth();
  switch (every) {
    case 'daily':
      return d.toISOString().slice(0, 10);
    case 'weekly': {
      const monday = new Date(Date.UTC(y, m, d.getUTCDate() - ((d.getUTCDay() + 6) % 7)));
      return monday.toISOString().slice(0, 10);
    }
    case 'monthly':
      return `${y}-${m}`;
    case 'quarterly':
      return `${y}-q${Math.floor(m / 3)}`;
    case 'annually':
      return String(y);
  }
}

/** Index of the first trading day in each rebalance period of `dates`. */
export function rebalanceIndexes(dates: readonly Date[], every: RebalanceEvery): number[] {
  const out: number[] = [];
  let last = '';
  dates.forEach((d, i) => {
    const key = periodKey(d, every);
    if (key !== last) {
      out.push(i);
      last = key;
    }
  });
  return out;
}

/** What the threshold line can be drawn against: one series and a number. */
export type Drawable =
  | { kind: 'indicator'; symbol: string; indicator: string; period: number; threshold: number }
  | { kind: 'price'; symbol: string; field: PriceField; threshold: number };

export function drawableOf(condition: ConditionExpression): Drawable | null {
  const { left, right } = condition;
  if (right.type !== 'number') return null;
  if (left.type === 'indicator') {
    return {
      kind: 'indicator',
      symbol: left.symbol,
      indicator: left.indicator,
      period: left.period ?? 14,
      threshold: right.value,
    };
  }
  if (left.type === 'price') {
    return { kind: 'price', symbol: left.symbol, field: left.field, threshold: right.value };
  }
  return null;
}

/** "At 72 it would have held on 36 trading days instead of 50, …", from the counts only. */
export function changeSentence(input: {
  threshold: string;
  days: number;
  rebalances: number;
  total: number;
  every: RebalanceEvery;
  saved: { days: number; rebalances: number } | null;
}): string {
  const { threshold, days, rebalances, total, every, saved } = input;
  const dayWord = (n: number) => `${n} trading ${n === 1 ? 'day' : 'days'}`;
  const head = `At ${threshold} it would have held on ${dayWord(days)}`;
  const daysPart =
    saved && saved.days !== days ? `${head} instead of ${saved.days}` : `${head} in this window`;
  if (every === 'daily') return `${daysPart}.`;
  const reb = `at ${rebalances} of ${total} ${every} rebalances`;
  const rebPart =
    saved && saved.rebalances !== rebalances ? `${reb} instead of ${saved.rebalances}` : reb;
  return `${daysPart}, and ${rebPart}.`;
}

export const fmt = (v: number) =>
  Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('en-US') : String(Math.round(v * 100) / 100);

export const monthYear = (d: Date) =>
  d.toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });

export const shortDay = (d: Date) =>
  d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
