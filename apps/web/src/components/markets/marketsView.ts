import type { Candle } from '@llamatrade/core/stores/markets';

import { formatNumber } from '../../lib/format';
import { sleeveInitials } from '../portfolio/history';

import type { CostLine } from './PriceChart';

export interface Holder {
  sleeveId: string | null;
  executionId: string;
  name: string;
  initials: string;
  index: number;
  live: boolean;
  qty: number;
  avgCost: number;
  marketValue: number;
  unrealized: number;
  /** Share of the sleeve's value, 0 to 1. */
  weight: number;
  target?: number;
  rebalance: string;
  running: boolean;
}

export interface WatchRow {
  symbol: string;
  holders: Holder[];
}

interface SleeveLike {
  sleeveId: string | null;
  executionId: string;
  name: string;
  live: boolean;
  value: number;
  rebalance: string;
  running: boolean;
  targets: Readonly<Record<string, number>>;
  holdings: readonly {
    symbol: string;
    qty: number;
    avgEntryPrice: number;
    marketValue: number;
    unrealizedPnl: number;
  }[];
}

/** Every symbol the sleeves hold, largest combined value first, with who holds how much. */
export function heldRows(sleeves: readonly SleeveLike[]): WatchRow[] {
  const bySymbol = new Map<string, Holder[]>();
  sleeves.forEach((s, index) => {
    for (const h of s.holdings) {
      if (!h.symbol || h.qty === 0) continue;
      const list = bySymbol.get(h.symbol) ?? [];
      list.push({
        sleeveId: s.sleeveId,
        executionId: s.executionId,
        name: s.name,
        initials: sleeveInitials(s.name),
        index,
        live: s.live,
        qty: h.qty,
        avgCost: h.avgEntryPrice,
        marketValue: h.marketValue,
        unrealized: h.unrealizedPnl,
        weight: s.value > 0 ? h.marketValue / s.value : 0,
        target: s.targets[h.symbol],
        rebalance: s.rebalance,
        running: s.running,
      });
      bySymbol.set(h.symbol, list);
    }
  });
  const total = (list: Holder[]) => list.reduce((sum, h) => sum + h.marketValue, 0);
  return [...bySymbol.entries()]
    .map(([symbol, holders]) => ({
      symbol,
      // Live first, so real money is never listed under simulated money.
      holders: holders.sort(
        (a, b) => Number(b.live) - Number(a.live) || b.marketValue - a.marketValue
      ),
    }))
    .sort((a, b) => total(b.holders) - total(a.holders) || a.symbol.localeCompare(b.symbol));
}

export type PriceRange = '1D' | '1W' | '1M' | '3M' | 'start' | '1Y';

const DAY = 86_400_000;
const RANGE_DAYS: Record<Exclude<PriceRange, 'start'>, number> = {
  '1D': 4,
  '1W': 7,
  '1M': 31,
  '3M': 92,
  '1Y': 366,
};

/** Where a range begins. "start" is the first sleeve's start, or a year when there is none. */
export function rangeStart(range: PriceRange, now: Date, firstStart: Date | null): Date {
  if (range === 'start') return firstStart ?? new Date(now.getTime() - RANGE_DAYS['1Y'] * DAY);
  return new Date(now.getTime() - RANGE_DAYS[range] * DAY);
}

/** Intraday bars for the short ranges, daily bars otherwise. */
export function rangeBars(range: PriceRange): 'intraday5' | 'hourly' | 'daily' {
  if (range === '1D') return 'intraday5';
  if (range === '1W') return 'hourly';
  return 'daily';
}

/** For 1D, only the latest trading day's bars. */
export function lastSessionOnly(
  candles: readonly Candle[],
  dayOf: (sec: number) => string
): Candle[] {
  if (candles.length === 0) return [];
  const last = dayOf(candles[candles.length - 1].time);
  return candles.filter((c) => dayOf(c.time) === last);
}

export interface RangeStats {
  open: number;
  dayLow: number;
  dayHigh: number;
  /** Change over the range as a fraction of its first close. */
  change: number;
  high: number;
  volume: number;
}

/** The figures under the chart, from the range's bars and the latest daily bar. */
export function rangeStats(candles: readonly Candle[], daily?: Candle | null): RangeStats | null {
  if (candles.length === 0) return null;
  const first = candles[0];
  const last = candles[candles.length - 1];
  const day = daily ?? last;
  const base = first.open || first.close;
  return {
    open: day.open,
    dayLow: day.low,
    dayHigh: day.high,
    change: base > 0 ? last.close / base - 1 : 0,
    high: candles.reduce((m, c) => Math.max(m, c.high), -Infinity),
    volume: day.volume,
  };
}

const KEY = 'llamatrade-watchlist';
export const DEFAULT_WATCH = ['SPY', 'QQQ'];

/** The symbols this viewer watches, kept in this browser only. */
export function readWatchlist(): string[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed) && parsed.every((s) => typeof s === 'string')) return parsed;
  } catch {
    // Storage can be blocked; the defaults stand in.
  }
  return DEFAULT_WATCH;
}

export function saveWatchlist(symbols: readonly string[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(symbols));
  } catch {
    // Not saved; the list still works for this visit.
  }
}

/** A typed symbol, upper-cased; null when it can't be one. */
export function cleanSymbol(input: string): string | null {
  const s = input.trim().toUpperCase();
  return /^[A-Z][A-Z0-9.]{0,9}$/.test(s) ? s : null;
}

export interface DayQuote {
  change: number;
  changePercent: number;
}

export interface MapTile {
  symbol: string;
  /** Dollars across every sleeve that holds the symbol. */
  value: number;
  qty: number;
  /** Share of total equity, 0 to 1; null without an equity figure. */
  share: number | null;
  /** Today's move in percent; null when there is no quote. */
  pct: number | null;
  /** Today's dollar move on the shares held now; null when there is no quote. */
  dayMove: number | null;
  holders: Holder[];
}

/** One map tile per held symbol, with today's move applied to the shares held now. */
export function mapTiles(
  rows: readonly WatchRow[],
  quotes: Readonly<Record<string, DayQuote | null | undefined>>,
  equity: number
): MapTile[] {
  return rows.map((r) => {
    const value = r.holders.reduce((s, h) => s + h.marketValue, 0);
    const qty = r.holders.reduce((s, h) => s + h.qty, 0);
    const q = quotes[r.symbol] ?? null;
    return {
      symbol: r.symbol,
      value,
      qty,
      share: equity > 0 ? value / equity : null,
      pct: q ? q.changePercent : null,
      dayMove: q ? q.change * qty : null,
      holders: r.holders,
    };
  });
}

export interface DayMoves {
  /** Sum of the known moves. */
  total: number;
  /** Dollars held across every tile. */
  held: number;
  /** The largest moves by size, listed from best to worst. */
  movers: { symbol: string; move: number }[];
  /** Symbols without a quote, so not in the total. */
  missing: string[];
}

export function dayMoves(tiles: readonly MapTile[], limit = 4): DayMoves {
  const known = tiles.filter(
    (t): t is MapTile & { dayMove: number } => t.dayMove !== null && Number.isFinite(t.dayMove)
  );
  const movers = [...known]
    .sort((a, b) => Math.abs(b.dayMove) - Math.abs(a.dayMove) || a.symbol.localeCompare(b.symbol))
    .slice(0, limit)
    .filter((t) => Math.abs(t.dayMove) >= 0.005)
    .sort((a, b) => b.dayMove - a.dayMove)
    .map((t) => ({ symbol: t.symbol, move: t.dayMove }));
  return {
    total: known.reduce((s, t) => s + t.dayMove, 0),
    held: tiles.reduce((s, t) => s + t.value, 0),
    movers,
    missing: tiles
      .filter((t) => t.dayMove === null || !Number.isFinite(t.dayMove))
      .map((t) => t.symbol),
  };
}

export interface CashSource {
  name: string;
  cash: number | null;
}

export interface CashLine<T extends CashSource> {
  total: number;
  /** Where most of it sits, when one place holds more than half: a sleeve, or null for unallocated. */
  most: { sleeve: T | null; amount: number } | null;
}

/** Cash in sleeves and unallocated; null when the ledger gave no cash figure at all. */
export function cashLine<T extends CashSource>(
  sleeves: readonly T[],
  unallocated: number | null
): CashLine<T> | null {
  const parts: { sleeve: T | null; amount: number }[] = [];
  for (const s of sleeves) if (s.cash !== null) parts.push({ sleeve: s, amount: s.cash });
  if (unallocated !== null) parts.push({ sleeve: null, amount: unallocated });
  if (parts.length === 0) return null;
  const total = parts.reduce((sum, p) => sum + p.amount, 0);
  if (total <= 0) return { total: Math.max(0, total), most: null };
  const top = [...parts].sort((a, b) => b.amount - a.amount)[0];
  return { total, most: top.amount > total / 2 && parts.length > 1 ? top : null };
}

/** "+1.32%" from a percent figure. */
export function pctText(pct: number): string {
  return `${formatNumber(pct, { signed: true })}%`;
}

/** The text class for a day move on the map: the tile gain and loss colours, or plain. */
export function moveClass(v: number): string {
  if (Math.abs(v) < 0.005) return 'text-fg-2';
  return v > 0 ? 'tile-gain-text' : 'tile-loss-text';
}

/** A share count, with decimals only for fractional shares. */
export const shares = (q: number) => formatNumber(q, { dp: q % 1 ? 2 : 0 });

/** One average-cost line per price and account, naming every sleeve that shares it. */
export function costLines(holders: readonly Holder[]): CostLine[] {
  const out = new Map<string, { price: number; live: boolean; names: string[] }>();
  for (const h of holders) {
    const key = `${h.avgCost.toFixed(2)}:${h.live}`;
    const line = out.get(key) ?? { price: h.avgCost, live: h.live, names: [] };
    line.names.push(h.name);
    out.set(key, line);
  }
  return [...out.values()].map((l) => ({
    price: l.price,
    live: l.live,
    label: `${l.names.join(' and ')} avg cost ${l.price.toFixed(2)} · ${l.live ? 'live' : 'paper'}`,
  }));
}
