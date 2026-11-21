import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useMemo } from 'react';

import {
  alignTo,
  dayKey,
  longDate,
  monthLabel,
  type Rebalance,
  type SimOrder,
  type TradeInput,
} from '../../lib/backtestView';

import { rebalanceMarks } from './annotations';
import { toCurve } from './runData';

export type RebalanceKind = 'switch' | 'resize';

/** A net change in one symbol's shares on a rebalance or across a month. */
export interface ShareChange {
  symbol: string;
  /** Shares bought minus shares sold. */
  shares: number;
}

/** One month of a year's rebalances, for the row of cards and the phone list. */
export interface MonthGroup {
  month: string;
  /** Oldest first. */
  rebalances: Rebalance[];
  /** switch when any rebalance in the month changed the symbols held; null with no orders. */
  kind: RebalanceKind | null;
  changes: ShareChange[];
  orders: number;
  realised: number;
}

/** "2022-01" … "2022-12". */
export function yearMonths(year: string): string[] {
  return Array.from({ length: 12 }, (_, i) => `${year}-${String(i + 1).padStart(2, '0')}`);
}

/**
 * Return from the last close before `from` (or the first close inside when there is none) to the
 * last close on or before `to`. Null when the window holds no closes.
 */
export function periodReturn(
  dates: readonly Date[],
  values: readonly (number | null)[],
  from: Date,
  to: Date
): number | null {
  let base: number | null = null;
  let last: number | null = null;
  let seen = false;
  for (let i = 0; i < dates.length; i++) {
    const v = values[i];
    if (v === null || v === undefined || !(v > 0)) continue;
    const t = dates[i].getTime();
    if (t < from.getTime()) base = v;
    else if (t <= to.getTime()) {
      if (!seen && base === null) base = v;
      seen = true;
      last = v;
    }
  }
  return seen && base !== null && last !== null ? last / base - 1 : null;
}

export function monthBounds(month: string): { from: Date; to: Date } {
  const [y, m] = month.split('-').map(Number);
  return { from: new Date(Date.UTC(y, m - 1, 1)), to: new Date(Date.UTC(y, m, 0)) };
}

export function yearBounds(year: string): { from: Date; to: Date } {
  const y = Number(year);
  return { from: new Date(Date.UTC(y, 0, 1)), to: new Date(Date.UTC(y, 11, 31)) };
}

/** Net shares per symbol, sold first then bought, each by symbol. */
export function shareChanges(orders: readonly SimOrder[]): ShareChange[] {
  const net = new Map<string, number>();
  for (const o of orders) {
    net.set(o.symbol, (net.get(o.symbol) ?? 0) + (o.side === 'BUY' ? o.quantity : -o.quantity));
  }
  return [...net.entries()]
    .filter(([, shares]) => Math.abs(shares) > 1e-9)
    .map(([symbol, shares]) => ({ symbol, shares }))
    .sort((a, b) => Math.sign(a.shares) - Math.sign(b.shares) || a.symbol.localeCompare(b.symbol));
}

/** Days whose orders changed the set of symbols held. */
export function switchDays(trades: readonly TradeInput[]): Set<string> {
  return new Set(
    rebalanceMarks(trades)
      .filter((m) => m.switched)
      .map((m) => dayKey(m.at))
  );
}

export function kindOf(r: Rebalance, switches: ReadonlySet<string>): RebalanceKind {
  return switches.has(r.date) ? 'switch' : 'resize';
}

/** Twelve groups for the year, one per month, including months without orders. */
export function monthGroups(
  rebalances: readonly Rebalance[],
  year: string,
  switches: ReadonlySet<string>
): MonthGroup[] {
  return yearMonths(year).map((month) => {
    const list = rebalances
      .filter((r) => r.month === month)
      .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    const orders = list.flatMap((r) => r.orders);
    return {
      month,
      rebalances: list,
      kind: list.length ? (list.some((r) => switches.has(r.date)) ? 'switch' : 'resize') : null,
      changes: shareChanges(orders),
      orders: orders.length,
      realised: list.reduce((s, r) => s + r.realised, 0),
    };
  });
}

const WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine'];

/** "Three", "12"; lower-case unless it opens the sentence. */
function count(n: number, first: boolean): string {
  const w = n < WORDS.length ? WORDS[n] : String(n);
  return first ? w : w.toLowerCase();
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** "Three switches and nine resizes, 48 orders." or "No orders this year." */
export function yearCounts(switches: number, resizes: number, orders: number): string {
  if (orders === 0) return 'No orders this year.';
  const parts: string[] = [];
  if (switches) parts.push(`${count(switches, true)} ${plural(switches, 'switch', 'switches')}`);
  if (resizes) {
    parts.push(`${count(resizes, parts.length === 0)} ${plural(resizes, 'resize', 'resizes')}`);
  }
  return `${parts.join(' and ')}, ${orders} ${plural(orders, 'order', 'orders')}.`;
}

/** "Sell 2 TLT · buy 2 GLD", for the phone list. */
export function changesLine(changes: readonly ShareChange[], max = 3): string {
  const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));
  const shown = changes
    .slice(0, max)
    .map((c) => `${c.shares < 0 ? 'sell' : 'buy'} ${fmt(Math.abs(c.shares))} ${c.symbol}`);
  const more = changes.length - max;
  const line = [...shown, ...(more > 0 ? [`${more} more`] : [])].join(' · ');
  return line ? line[0].toUpperCase() + line.slice(1) : '';
}

/** The distinct reasons the month's orders give, in order. */
export function reasonsOf(rebalances: readonly Rebalance[]): string[] {
  return [...new Set(rebalances.flatMap((r) => r.orders.map((o) => o.reason)).filter(Boolean))];
}

export interface YearSlice {
  dates: Date[];
  values: number[];
  bench: number[] | null;
}

/** The run's curve with its benchmark aligned to the same dates. */
export function useFullCurve(run: BacktestRun): YearSlice {
  return useMemo(() => {
    const eq = toCurve(run.results?.equityCurve);
    const bench = alignTo(eq.dates, toCurve(run.results?.benchmarkEquityCurve));
    return {
      dates: [...eq.dates],
      values: [...eq.values],
      bench: bench.every((v): v is number => v !== null) ? bench : null,
    };
  }, [run]);
}

/** The full curve cut to one calendar year; null with fewer than two points in it. */
export function sliceYear(full: YearSlice, year: string): YearSlice | null {
  const idx = full.dates.flatMap((d, i) => (String(d.getUTCFullYear()) === year ? [i] : []));
  if (idx.length < 2) return null;
  const a = idx[0];
  const b = idx[idx.length - 1] + 1;
  return {
    dates: full.dates.slice(a, b),
    values: full.values.slice(a, b),
    bench: full.bench ? full.bench.slice(a, b) : null,
  };
}

/** "Mar 1, 2022" for one rebalance, "March 2022 · 6 rebalance days" for several. */
export function monthDetailTitle(group: MonthGroup): string {
  if (group.rebalances.length === 1) {
    return longDate(new Date(`${group.rebalances[0].date}T00:00:00Z`));
  }
  const n = group.rebalances.length;
  return `${monthLabel(group.month)}${n ? ` · ${n} rebalance days` : ''}`;
}
