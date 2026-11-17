import type { StrategyEquityPoint } from '@llamatrade/core/proto/portfolio_pb';
import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';

import { etParts } from '../../lib/marketClock';
import { nextRebalanceDate } from '../../lib/sessionState';

const DAY_MS = 86_400_000;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export type TimeRange = '1M' | '3M' | 'all';

export const RANGE_OPTIONS: readonly { key: TimeRange; label: string }[] = [
  { key: '1M', label: '1M' },
  { key: '3M', label: '3M' },
  { key: 'all', label: 'All' },
];

/** The first day a range shows: a month or three back, or the earliest start for All. */
export function rangeStart(range: TimeRange, now: Date, earliest: Date | null): Date {
  if (range === 'all') {
    const from = earliest ?? new Date(now.getTime() - 90 * DAY_MS);
    return from.getTime() < now.getTime() - 7 * DAY_MS
      ? from
      : new Date(now.getTime() - 7 * DAY_MS);
  }
  const days = range === '1M' ? 31 : 92;
  return new Date(now.getTime() - days * DAY_MS);
}

/** "2026-11-16" for the New York calendar day `d` falls on. */
export function etDayKey(d: Date): string {
  const p = etParts(d);
  return `${p.year}-${String(p.month + 1).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
}

/** "Nov 16" in New York. */
export function etDayLabel(d: Date): string {
  const p = etParts(d);
  return `${MON[p.month]} ${p.day}`;
}

/** "10:31" in New York. */
export function etHm(d: Date): string {
  return d.toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/** When an order last happened: filled, else sent, else created. */
export function orderTime(o: Order): Date | null {
  return toDate(o.filledAt) ?? toDate(o.submittedAt) ?? toDate(o.createdAt);
}

export const isFilled = (o: Order) =>
  o.status === OrderStatus.FILLED || o.status === OrderStatus.PARTIAL;

export interface FillDay {
  key: string;
  /** The first fill of the day. */
  at: Date;
  orders: Order[];
}

/** Filled orders grouped by New York day, oldest first: one group per rebalance that traded. */
export function fillDays(orders: readonly Order[]): FillDay[] {
  const byDay = new Map<string, FillDay>();
  for (const o of orders) {
    if (!isFilled(o)) continue;
    const at = orderTime(o);
    if (!at) continue;
    const key = etDayKey(at);
    const day = byDay.get(key);
    if (!day) byDay.set(key, { key, at, orders: [o] });
    else {
      day.orders.push(o);
      if (at < day.at) day.at = at;
    }
  }
  return [...byDay.values()].sort((a, b) => a.at.getTime() - b.at.getTime());
}

export interface Series {
  dates: Date[];
  values: number[];
}

/** Equity points as parallel dates and values, dropping anything unreadable. */
export function toSeries(points: readonly StrategyEquityPoint[]): Series {
  const rows = points
    .map((p) => ({ d: toDate(p.timestamp), v: toNumber(p.equity) }))
    .filter((x): x is { d: Date; v: number } => x.d !== null && Number.isFinite(x.v) && x.v > 0)
    .sort((a, b) => a.d.getTime() - b.d.getTime());
  return { dates: rows.map((r) => r.d), values: rows.map((r) => r.v) };
}

export interface CurveStats {
  high: number;
  low: number;
  /** The largest fall from a high, as a negative fraction. */
  maxDrawdown: number;
  first: number;
  last: number;
}

export function curveStats(values: readonly number[]): CurveStats | null {
  const xs = values.filter((v) => Number.isFinite(v));
  if (xs.length === 0) return null;
  let peak = xs[0];
  let dd = 0;
  for (const v of xs) {
    peak = Math.max(peak, v);
    if (peak > 0) dd = Math.min(dd, v / peak - 1);
  }
  return {
    high: Math.max(...xs),
    low: Math.min(...xs),
    maxDrawdown: dd,
    first: xs[0],
    last: xs[xs.length - 1],
  };
}

const signedQty = (o: Order) =>
  (o.side === OrderSide.SELL ? -1 : 1) * (toNumber(o.filledQuantity) || 0);

/** Shares per symbol from fills before `at` (exclusive). */
export function quantitiesBefore(orders: readonly Order[], at: Date): Map<string, number> {
  const out = new Map<string, number>();
  for (const o of orders) {
    if (!isFilled(o)) continue;
    const t = orderTime(o);
    if (!t || t.getTime() >= at.getTime()) continue;
    out.set(o.symbol, (out.get(o.symbol) ?? 0) + signedQty(o));
  }
  return out;
}

export interface SymbolLane {
  symbol: string;
  fills: { at: Date; side: 'buy' | 'sell'; order: Order }[];
}

/** One lane per traded symbol, ordered by `prefer` (largest holding first), then by name. */
export function symbolLanes(
  orders: readonly Order[],
  prefer: readonly string[] = []
): SymbolLane[] {
  const lanes = new Map<string, SymbolLane>();
  for (const o of orders) {
    if (!isFilled(o)) continue;
    const at = orderTime(o);
    if (!at) continue;
    const lane = lanes.get(o.symbol) ?? { symbol: o.symbol, fills: [] };
    lane.fills.push({ at, side: o.side === OrderSide.SELL ? 'sell' : 'buy', order: o });
    lanes.set(o.symbol, lane);
  }
  for (const s of prefer) if (!lanes.has(s)) lanes.set(s, { symbol: s, fills: [] });
  const rank = (s: string) => {
    const i = prefer.indexOf(s);
    return i === -1 ? prefer.length : i;
  };
  return [...lanes.values()].sort(
    (a, b) => rank(a.symbol) - rank(b.symbol) || a.symbol.localeCompare(b.symbol)
  );
}

export interface LimitBreach {
  value: number;
  limit: number;
}

/** The order value and limit from a stored rejection, e.g. "Order value $11210.84 exceeds limit $10000.00". */
export function parseLimitBreach(message: string): LimitBreach | null {
  const m =
    /order value\s+\$?([\d,]+(?:\.\d+)?)\s+exceeds(?:\s+the)?\s+limit(?:\s+of)?\s+\$?([\d,]+(?:\.\d+)?)/i.exec(
      message
    );
  if (!m) return null;
  const value = Number(m[1].replace(/,/g, ''));
  const limit = Number(m[2].replace(/,/g, ''));
  return Number.isFinite(value) && Number.isFinite(limit) && limit > 0 ? { value, limit } : null;
}

/** Whole shares at `price` that stay at or under `limit`. */
export function largestThatFits(limit: number, price: number): number {
  if (!(price > 0) || !(limit > 0)) return 0;
  return Math.floor(limit / price + 1e-9);
}

/** Round axis steps for a bar from 0 to `max`, about four of them. */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 3, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

/**
 * The series clipped to [start, end] as a step from the last known value: the value in force at
 * `start` opens it, and `current` (or the last value) closes it at `end`.
 */
export function windowed(series: Series, start: Date, end: Date, current: number | null): Series {
  const dates: Date[] = [];
  const values: number[] = [];
  let before: number | null = null;
  series.dates.forEach((d, i) => {
    if (d.getTime() < start.getTime()) before = series.values[i];
    else if (d.getTime() <= end.getTime()) {
      dates.push(d);
      values.push(series.values[i]);
    }
  });
  if (before !== null && (dates.length === 0 || dates[0].getTime() > start.getTime())) {
    dates.unshift(start);
    values.unshift(before);
  }
  const last = current ?? values[values.length - 1];
  if (
    last !== undefined &&
    Number.isFinite(last) &&
    dates.length > 0 &&
    dates[dates.length - 1].getTime() < end.getTime()
  ) {
    dates.push(end);
    values.push(last);
  }
  return stepped({ dates, values });
}

/** Holds each value until the next point, so a series marked only when it changes reads as steps. */
export function stepped(series: Series): Series {
  const dates: Date[] = [];
  const values: number[] = [];
  series.dates.forEach((d, i) => {
    if (i > 0 && values[values.length - 1] !== series.values[i]) {
      dates.push(new Date(d.getTime() - 1));
      values.push(series.values[i - 1]);
    }
    dates.push(d);
    values.push(series.values[i]);
  });
  return { dates, values };
}

/** The value of `series` in force at each date (its last point at or before it); NaN before it starts. */
export function asOf(series: Series, dates: readonly Date[]): number[] {
  let j = -1;
  return dates.map((d) => {
    while (j + 1 < series.dates.length && series.dates[j + 1].getTime() <= d.getTime()) j++;
    return j >= 0 ? series.values[j] : Number.NaN;
  });
}

/** The next `count` scheduled rebalances after `today` (UTC-midnight dates); empty for daily or unknown schedules. */
export function nextRebalances(rebalance: string, today: Date, count: number): Date[] {
  const out: Date[] = [];
  let from = today;
  for (let i = 0; i < count; i++) {
    const next = nextRebalanceDate(rebalance, from);
    if (!next) break;
    out.push(next);
    from = next;
  }
  return out;
}

/** Whole shares each holding's weight buys with `capital` at its last price, and the cash left. */
export function sharesFor(
  capital: number,
  holdings: readonly { symbol: string; value: number; price: number }[]
): { buys: { symbol: string; shares: number }[]; cash: number } {
  const total = holdings.reduce((n, h) => n + Math.max(0, h.value), 0);
  if (!(capital > 0) || total <= 0) return { buys: [], cash: Math.max(0, capital) };
  let spent = 0;
  const buys = holdings
    .filter((h) => h.value > 0 && h.price > 0)
    .map((h) => {
      const shares = Math.floor((capital * (h.value / total)) / h.price + 1e-9);
      spent += shares * h.price;
      return { symbol: h.symbol, shares };
    })
    .filter((b) => b.shares > 0);
  return { buys, cash: capital - spent };
}

/** "Now 10:42" in New York time. */
export const nowLabel = (now: Date) => `Now ${etHm(now)}`;
