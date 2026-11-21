import { drawdownOf, type TradeInput } from '../../lib/backtestView';

export interface HeldPeriod {
  /** The symbols held, sorted and joined: "GLD · TLT". */
  key: string;
  symbols: string[];
  from: Date;
  to: Date;
}

const DAY = 86_400_000;
const dayStart = (d: Date) => Math.floor(d.getTime() / DAY) * DAY;

/**
 * What the backtest held and when, from its round-trip trades: one period per run of days with
 * the same set of symbols. Days in cash make no period.
 */
export function heldPeriods(trades: readonly TradeInput[], end: Date): HeldPeriod[] {
  const endMs = dayStart(end);
  const legs = trades
    .filter((t): t is TradeInput & { entryTime: Date } => t.entryTime !== null)
    .map((t) => ({
      symbol: t.symbol,
      from: dayStart(t.entryTime),
      to: t.exitTime ? dayStart(t.exitTime) : Infinity,
    }));
  const bounds = [...new Set(legs.flatMap((l) => [l.from, l.to]))]
    .filter((b) => Number.isFinite(b) && b <= endMs)
    .sort((a, b) => a - b);

  const periods: HeldPeriod[] = [];
  bounds.forEach((b, i) => {
    const to = i + 1 < bounds.length ? bounds[i + 1] : endMs;
    if (to <= b) return;
    const symbols = [
      ...new Set(legs.filter((l) => l.from <= b && l.to > b).map((l) => l.symbol)),
    ].sort();
    if (symbols.length === 0) return;
    const key = symbols.join(' · ');
    const last = periods[periods.length - 1];
    if (last && last.key === key && last.to.getTime() === b) {
      last.to = new Date(to);
    } else {
      periods.push({ key, symbols, from: new Date(b), to: new Date(to) });
    }
  });
  return periods;
}

/** The days the holdings changed from one set to another, after the first purchase. */
export function switchesOf(periods: readonly HeldPeriod[]): HeldPeriod[] {
  return periods.slice(1);
}

/** The distinct sets held, most days first. */
export function heldSets(periods: readonly HeldPeriod[]): { key: string; days: number }[] {
  const days = new Map<string, number>();
  for (const p of periods) {
    days.set(p.key, (days.get(p.key) ?? 0) + (p.to.getTime() - p.from.getTime()) / DAY);
  }
  return [...days.entries()]
    .map(([key, d]) => ({ key, days: Math.round(d) }))
    .sort((a, b) => b.days - a.days);
}

/** The stretch from the peak before the deepest drop down to that low, or null without one. */
export function worstDrop(
  dates: readonly Date[],
  values: readonly number[]
): { from: Date; to: Date; depth: number } | null {
  if (dates.length !== values.length || values.length < 2) return null;
  const dd = drawdownOf(values);
  let low = 0;
  dd.forEach((d, i) => {
    if (d < dd[low]) low = i;
  });
  if (dd[low] >= 0) return null;
  let peak = low;
  while (peak > 0 && dd[peak] < 0) peak--;
  return { from: dates[peak], to: dates[low], depth: dd[low] };
}

/** "TLT and GLD", or "BIL, BND, GLD and 4 more" for long sets. */
export function symbolsLabel(symbols: readonly string[], max = 3): string {
  if (symbols.length <= 2) return symbols.join(' and ');
  if (symbols.length <= max)
    return `${symbols.slice(0, -1).join(', ')} and ${symbols[symbols.length - 1]}`;
  return `${symbols.slice(0, max).join(', ')} and ${symbols.length - max} more`;
}

const dropPct = (depth: number) => `${(Math.abs(depth) * 100).toFixed(1)}%`;

/**
 * "SPY's worst drop was 18.8%, against 12.3% for Recession Radar.", from both curves over the
 * same dates, or null when either curve never fell.
 */
export function dropComparison(
  bench: string,
  benchValues: readonly number[] | undefined,
  strategyDepth: number | null,
  name: string
): string | null {
  if (!bench || !benchValues || benchValues.length < 2 || !strategyDepth) return null;
  const benchDepth = Math.min(...drawdownOf(benchValues));
  if (!(benchDepth < 0) || !(strategyDepth < 0)) return null;
  return `${bench}'s worst drop was ${dropPct(benchDepth)}, against ${dropPct(strategyDepth)} for ${name}.`;
}
