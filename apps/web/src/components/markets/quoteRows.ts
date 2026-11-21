import type { Candle } from '@llamatrade/core/stores/markets';

import type { SleeveFill } from '../portfolio/history';

import { shares, type Holder, type WatchRow } from './marketsView';

export interface YearRange {
  low: number;
  high: number;
}

export interface QuoteRow {
  symbol: string;
  name: string;
  held: boolean;
  holders: Holder[];
  last: number | null;
  /** Today's move in percent; null without a quote. */
  changePct: number | null;
  /** IEX volume for today; null when the feed reported none. */
  volume: number | null;
  intraday: number[];
  year: YearRange | null;
}

interface QuoteLike {
  price: number;
  changePercent: number;
  volume: number;
}

export interface QuoteInputs {
  held: readonly WatchRow[];
  watchOnly: readonly string[];
  quotes: Readonly<Record<string, QuoteLike | null | undefined>>;
  names: Readonly<Record<string, string>>;
  intraday: Readonly<Record<string, readonly number[]>>;
  years: Readonly<Record<string, YearRange | null | undefined>>;
}

/** One row per held symbol, then one per watched symbol, in that order. */
export function quoteRows(inputs: QuoteInputs): QuoteRow[] {
  const row = (symbol: string, holders: Holder[]): QuoteRow => {
    const q = inputs.quotes[symbol] ?? null;
    return {
      symbol,
      name: inputs.names[symbol] ?? '',
      held: holders.length > 0,
      holders,
      last: q ? q.price : null,
      changePct: q ? q.changePercent : null,
      volume: q && q.volume > 0 ? q.volume : null,
      intraday: [...(inputs.intraday[symbol] ?? [])],
      year: inputs.years[symbol] ?? null,
    };
  };
  const heldSymbols = new Set(inputs.held.map((r) => r.symbol));
  return [
    ...inputs.held.map((r) => row(r.symbol, r.holders)),
    ...inputs.watchOnly.filter((s) => !heldSymbols.has(s)).map((s) => row(s, [])),
  ];
}

/** "AW 26 · RR 54": each holding sleeve's initials and shares. */
export function heldByText(holders: readonly Holder[]): string {
  return holders.map((h) => `${h.initials} ${shares(h.qty)}`).join(' · ');
}

export type SortKey = 'default' | 'symbol' | 'last' | 'change' | 'volume';
export type SortDir = 'asc' | 'desc';

const VALUE: Record<Exclude<SortKey, 'default' | 'symbol'>, (r: QuoteRow) => number | null> = {
  last: (r) => r.last,
  change: (r) => r.changePct,
  volume: (r) => r.volume,
};

/** Rows sorted by a column; rows without a figure always go last, and ties keep their order. */
export function sortRows(rows: readonly QuoteRow[], key: SortKey, dir: SortDir): QuoteRow[] {
  if (key === 'default') return [...rows];
  const sign = dir === 'asc' ? 1 : -1;
  const indexed = rows.map((r, i) => ({ r, i }));
  if (key === 'symbol') {
    return indexed
      .sort((a, b) => sign * a.r.symbol.localeCompare(b.r.symbol) || a.i - b.i)
      .map((x) => x.r);
  }
  const get = VALUE[key];
  return indexed
    .sort((a, b) => {
      const va = get(a.r);
      const vb = get(b.r);
      if (va === null && vb === null) return a.i - b.i;
      if (va === null) return 1;
      if (vb === null) return -1;
      return sign * (va - vb) || a.i - b.i;
    })
    .map((x) => x.r);
}

/** The next sort after a header click: a new column starts in its natural direction, the same column flips. */
export function nextSort(
  current: { key: SortKey; dir: SortDir },
  key: Exclude<SortKey, 'default'>
): { key: SortKey; dir: SortDir } {
  if (current.key === key) return { key, dir: current.dir === 'asc' ? 'desc' : 'asc' };
  return { key, dir: key === 'symbol' ? 'asc' : 'desc' };
}

/** The low and high of a year of daily bars; null with fewer than two bars. */
export function yearRange(candles: readonly Candle[]): YearRange | null {
  if (candles.length < 2) return null;
  let low = Infinity;
  let high = -Infinity;
  for (const c of candles) {
    if (c.low > 0) low = Math.min(low, c.low);
    high = Math.max(high, c.high);
  }
  return Number.isFinite(low) && high >= low ? { low, high } : null;
}

/** Where the last price sits in the year's range, 0 to 1, with today's price stretching it. */
export function rangePosition(range: YearRange | null, last: number | null): number | null {
  if (!range || last === null || !Number.isFinite(last)) return null;
  const low = Math.min(range.low, last);
  const high = Math.max(range.high, last);
  if (high - low <= 0) return 0.5;
  return (last - low) / (high - low);
}

/** A sleeve's fills of one symbol on the given ET day, oldest first. */
export function fillsOnDay(
  fills: readonly SleeveFill[],
  sleeveId: string | null,
  symbol: string,
  dayKey: string,
  dayOf: (d: Date) => string
): SleeveFill[] {
  return fills
    .filter((f) => f.sleeveId === sleeveId && f.symbol === symbol && dayOf(f.at) === dayKey)
    .sort((a, b) => a.at.getTime() - b.at.getTime());
}

/** "Bought 42 at 90.41", one phrase per fill. */
export function fillPhrase(f: Pick<SleeveFill, 'side' | 'qty' | 'price'>): string {
  return `${f.side === 'buy' ? 'Bought' : 'Sold'} ${shares(f.qty)} at ${f.price.toFixed(2)}`;
}
