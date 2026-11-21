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
  /** The order's client id, from which the ledger derives the fill's event id. */
  clientOrderId?: string;
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
      clientOrderId: o.clientOrderId || undefined,
    });
  }
  return out.sort((a, b) => b.at.getTime() - a.at.getTime());
}

const MONTH_MS = 30 * 86_400_000;

/** The last 30 days of a curve, closing on the value now. */
export function lastMonth(points: readonly TimedValue[], value: number, now: Date): number[] {
  const from = now.getTime() - MONTH_MS;
  return [...points.filter((p) => p.t >= from && p.t <= now.getTime()).map((p) => p.v), value];
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

/**
 * The ledger's event id for a fill: the first 16 bytes of SHA-256 over the order's client id, as
 * a UUID (`deterministic_event_id` in the portfolio service). ListTransactions returns it as the
 * transaction id, so a fill row can be tied to its order exactly.
 */
export async function ledgerFillId(clientOrderId: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(clientOrderId));
  const hex = [...new Uint8Array(digest).slice(0, 16)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** Each fill keyed by its ledger event id; fills without a client order id are left out. */
export async function fillsByLedgerId(
  fills: readonly SleeveFill[]
): Promise<Map<string, SleeveFill>> {
  const keyed = await Promise.all(
    fills
      .filter((f): f is SleeveFill & { clientOrderId: string } => Boolean(f.clientOrderId))
      .map(async (f) => [await ledgerFillId(f.clientOrderId), f] as const)
  );
  return new Map(keyed);
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

/** Allocations into one sleeve: the ledger names the receiving sleeve on each allocation row. */
export function allocationSteps(rows: readonly CashRow[], sleeveName: string): CashStep[] {
  return rows
    .filter((r) => r.kind === 'allocation' && r.sublabel === sleeveName)
    .map((r) => ({ t: r.at.getTime(), amount: Math.abs(r.amount) }));
}
