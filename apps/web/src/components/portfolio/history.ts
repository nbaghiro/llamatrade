import { num } from '@llamatrade/core/format';
import { OrderSide, type Order, type TradingSession } from '@llamatrade/core/proto/trading_pb';

import { etParts } from '../../lib/marketClock';

/** A dated value on a sleeve or account curve, in milliseconds since the epoch. */
export interface TimedValue {
  t: number;
  v: number;
}

/** A signed cash movement at a time. */
export interface CashStep {
  t: number;
  amount: number;
}

/** One fill the ledger booked to a sleeve, read from the order that made it. */
export interface SleeveFill {
  id: string;
  at: Date;
  sleeveId: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  price: number;
}

const tsMs = (ts: { seconds: bigint } | undefined): number =>
  ts?.seconds ? Number(ts.seconds) * 1000 : 0;

/** Every filled order whose session belongs to a sleeve, newest first. */
export function sleeveFills(
  orders: readonly Order[],
  sessions: readonly Pick<TradingSession, 'id' | 'sleeveId'>[]
): SleeveFill[] {
  const sleeveOf = new Map(sessions.filter((s) => s.sleeveId).map((s) => [s.id, s.sleeveId]));
  const out: SleeveFill[] = [];
  for (const o of orders) {
    const qty = num(o.filledQuantity);
    const sleeveId = sleeveOf.get(o.sessionId);
    const t = tsMs(o.filledAt) || tsMs(o.submittedAt) || tsMs(o.createdAt);
    if (!sleeveId || qty <= 0 || !t) continue;
    out.push({
      id: o.id,
      at: new Date(t),
      sleeveId,
      symbol: o.symbol,
      side: o.side === OrderSide.SELL ? 'sell' : 'buy',
      qty,
      price: num(o.averageFillPrice) || num(o.limitPrice),
    });
  }
  return out.sort((a, b) => b.at.getTime() - a.at.getTime());
}

/** "2026-11-17": the New York calendar day a moment falls on. */
export function etDayKey(d: Date): string {
  const p = etParts(d);
  return `${p.year}-${String(p.month + 1).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
}

export interface DayGroup<T extends { at: Date }> {
  key: string;
  /** The earliest moment in the group, where its marker sits. */
  at: Date;
  items: T[];
}

/** Items merged by New York day, oldest day first, so a busy day becomes one counted marker. */
export function byDay<T extends { at: Date }>(items: readonly T[]): DayGroup<T>[] {
  const groups = new Map<string, DayGroup<T>>();
  for (const item of items) {
    const key = etDayKey(item.at);
    const g = groups.get(key);
    if (!g) groups.set(key, { key, at: item.at, items: [item] });
    else {
      g.items.push(item);
      if (item.at < g.at) g.at = item.at;
    }
  }
  return [...groups.values()].sort((a, b) => a.at.getTime() - b.at.getTime());
}

/** The last value at or before `t`, or null before the first point. Points must be sorted. */
export function valueAt(points: readonly TimedValue[], t: number): number | null {
  let out: number | null = null;
  for (const p of points) {
    if (p.t > t) break;
    out = p.v;
  }
  return out;
}

function sumUpTo(steps: readonly CashStep[], t: number): number {
  let s = 0;
  for (const step of steps) if (step.t <= t) s += step.amount;
  return s;
}

export interface SleeveHistory {
  /** The sleeve's equity curve, oldest first. */
  points: readonly TimedValue[];
  /** Money moved into the sleeve (positive) or out of it (negative). */
  allocations: readonly CashStep[];
}

export interface AccountHistory {
  dates: Date[];
  /** Sleeves plus unallocated cash. */
  equity: number[];
  /** Money placed in the sleeves plus unallocated cash: what was added, before any gain. */
  added: number[];
}

/** Just before a step, so a dashed step line draws a riser rather than a ramp. */
const STEP_LEAD = 60_000;

/**
 * The account over time: each sleeve's curve (its allocations stand in before the curve starts)
 * plus unallocated cash, and the money added under it as a step line. The gap between the two
 * is what the sleeves earned.
 */
export function accountHistory(
  sleeves: readonly SleeveHistory[],
  freeCash: readonly CashStep[],
  now: number
): AccountHistory {
  const sorted = sleeves.map((s) => ({
    points: [...s.points].sort((a, b) => a.t - b.t),
    allocations: s.allocations,
  }));
  const stepTimes = [
    ...freeCash.map((c) => c.t),
    ...sorted.flatMap((s) => s.allocations.map((a) => a.t)),
  ];
  const times = new Set<number>([now]);
  for (const t of stepTimes) {
    times.add(t);
    times.add(t - STEP_LEAD);
  }
  for (const s of sorted) for (const p of s.points) times.add(p.t);
  const ordered = [...times].filter((t) => t <= now).sort((a, b) => a - b);

  const out: AccountHistory = { dates: [], equity: [], added: [] };
  for (const t of ordered) {
    const cash = sumUpTo(freeCash, t);
    let equity = cash;
    let added = cash;
    for (const s of sorted) {
      const allocated = sumUpTo(s.allocations, t);
      equity += valueAt(s.points, t) ?? allocated;
      added += allocated;
    }
    if (out.dates.length === 0 && equity === 0 && added === 0) continue;
    out.dates.push(new Date(t));
    out.equity.push(equity);
    out.added.push(added);
  }
  return out;
}

/** The part of a history from `start`, opening with its value at `start`. */
export function windowFrom(history: AccountHistory, start: Date): AccountHistory {
  const s = start.getTime();
  const firstIn = history.dates.findIndex((d) => d.getTime() >= s);
  if (firstIn <= 0) return history;
  const before = firstIn - 1;
  return {
    dates: [start, ...history.dates.slice(firstIn)],
    equity: [history.equity[before], ...history.equity.slice(firstIn)],
    added: [history.added[before], ...history.added.slice(firstIn)],
  };
}

/** The largest fall from a running peak, as a negative fraction (0 when it never fell). */
export function maxDrawdown(values: readonly number[]): number {
  let peak = -Infinity;
  let worst = 0;
  for (const v of values) {
    if (v > peak) peak = v;
    if (peak > 0) worst = Math.min(worst, v / peak - 1);
  }
  return worst;
}

export interface EstimatedOrder {
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  amount: number;
}

/**
 * What a rebalance to fixed targets would trade at today's prices, whole shares only. Symbols
 * the sleeve doesn't hold yet have no price here, so they are left out.
 */
export function estimateRebalance(
  holdings: readonly { symbol: string; qty: number; price: number; marketValue: number }[],
  targets: Readonly<Record<string, number>>,
  sleeveValue: number
): EstimatedOrder[] {
  const out: EstimatedOrder[] = [];
  for (const h of holdings) {
    const target = targets[h.symbol];
    if (target === undefined || h.price <= 0) continue;
    const shares = Math.round((target * sleeveValue - h.marketValue) / h.price);
    if (shares === 0) continue;
    out.push({
      symbol: h.symbol,
      side: shares > 0 ? 'buy' : 'sell',
      qty: Math.abs(shares),
      amount: Math.abs(shares) * h.price,
    });
  }
  return out;
}

/** The sleeve that booked a ledger fill: the order fill with the same symbol, side and size. */
export function fillFor(
  row: { kind: string; symbol: string; qty: number; at: Date },
  fills: readonly SleeveFill[]
): SleeveFill | null {
  if (row.kind !== 'buy' && row.kind !== 'sell') return null;
  const t = row.at.getTime();
  let best: SleeveFill | null = null;
  let bestGap = 5 * 60_000;
  for (const f of fills) {
    if (f.symbol !== row.symbol || f.side !== row.kind || Math.abs(f.qty - row.qty) > 1e-6)
      continue;
    const gap = Math.abs(f.at.getTime() - t);
    if (gap <= bestGap) {
      best = f;
      bestGap = gap;
    }
  }
  return best;
}

/** Initials for a sleeve name in tight places: "All-Weather Portfolio" is "AW". */
export function sleeveInitials(name: string): string {
  const words = name.split(/[\s-]+/).filter((w) => /^[A-Za-z0-9]/.test(w));
  const letters = words.slice(0, 2).map((w) => w[0].toUpperCase());
  return letters.join('') || name.slice(0, 2).toUpperCase();
}

interface CashRow {
  kind: string;
  sublabel: string;
  amount: number;
  signed: number;
  at: Date;
}

/** Changes to unallocated cash, from the activity rows' effect on free cash. */
export function freeCashSteps(rows: readonly CashRow[]): CashStep[] {
  return rows.filter((r) => r.signed !== 0).map((r) => ({ t: r.at.getTime(), amount: r.signed }));
}

/** Allocations into one sleeve: the ledger names the receiving sleeve on each allocation row. */
export function allocationSteps(rows: readonly CashRow[], sleeveName: string): CashStep[] {
  return rows
    .filter((r) => r.kind === 'allocation' && r.sublabel === sleeveName)
    .map((r) => ({ t: r.at.getTime(), amount: Math.abs(r.amount) }));
}
