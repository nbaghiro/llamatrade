import { OrderSide, type Order } from '@llamatrade/core/proto/trading_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';

import { formatMoney, formatNumber } from '../../lib/format';

import { etDayKey, isFilled, quantitiesBefore, type FillDay } from './timeline';

export type PriceSource = 'fill' | 'close';

export interface HoldingLine {
  symbol: string;
  before: number;
  after: number;
  /** Shares bought and sold in this rebalance. */
  bought: number;
  sold: number;
  /** Average fill price for traded symbols, else that day's close; null when neither is known. */
  price: number | null;
  priceSource: PriceSource | null;
  valueBefore: number | null;
  valueAfter: number | null;
  /** Share of the holdings' value at these prices, cash not counted; null when any holding is unpriced. */
  weightBefore: number | null;
  weightAfter: number | null;
  /** From the strategy's fixed weights, when it has them. */
  target: number | null;
  changed: boolean;
}

export interface RebalanceDiff {
  key: string;
  at: Date;
  /** The previous rebalance that traded; null for the first. */
  previousAt: Date | null;
  lines: HoldingLine[];
  changes: number;
  added: number;
  removed: number;
  orders: Order[];
  ordersFilled: number;
  valueBefore: number | null;
  valueAfter: number | null;
  /** What the sells paid in and the buys spent, at fill prices. */
  cashIn: number;
  cashOut: number;
  cashFromOrders: number;
}

const EPS = 1e-9;

const filledQty = (o: Order) => toNumber(o.filledQuantity) || 0;

/** Average fill price per symbol across one rebalance's orders, skipping fills without a price. */
export function fillPrices(orders: readonly Order[]): Map<string, number> {
  const sums = new Map<string, { qty: number; cost: number }>();
  for (const o of orders) {
    if (!isFilled(o)) continue;
    const q = filledQty(o);
    const p = toNumber(o.averageFillPrice);
    if (!(q > 0) || !(p > 0)) continue;
    const s = sums.get(o.symbol) ?? { qty: 0, cost: 0 };
    s.qty += q;
    s.cost += q * p;
    sums.set(o.symbol, s);
  }
  const out = new Map<string, number>();
  for (const [sym, s] of sums) out.set(sym, s.cost / s.qty);
  return out;
}

/** The symbols held around a rebalance that it didn't trade, so need a close to be valued. */
export function untradedSymbols(orders: readonly Order[], day: FillDay): string[] {
  const before = quantitiesBefore(orders, day.at);
  const traded = fillPrices(day.orders);
  return [...before.entries()]
    .filter(([sym, q]) => Math.abs(q) > EPS && !traded.has(sym))
    .map(([sym]) => sym)
    .sort();
}

/** Each symbol's close on one New York day, from daily bars (time in seconds). */
export function closesOn(
  bars: Readonly<Record<string, readonly { time: number; close: number }[]>>,
  dayKey: string
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [sym, list] of Object.entries(bars)) {
    const bar = list.find((b) => etDayKey(new Date(b.time * 1000)) === dayKey);
    if (bar && bar.close > 0) out[sym] = bar.close;
  }
  return out;
}

/** One rebalance as a change set against the holdings left by the previous one that traded. */
export function buildRebalanceDiff(
  orders: readonly Order[],
  days: readonly FillDay[],
  index: number,
  closes: Readonly<Record<string, number>> = {},
  targets: Readonly<Record<string, number>> | null = null
): RebalanceDiff | null {
  const day = days[index];
  if (!day) return null;
  const before = quantitiesBefore(orders, day.at);
  const bought = new Map<string, number>();
  const sold = new Map<string, number>();
  let cashIn = 0;
  let cashOut = 0;
  for (const o of day.orders) {
    if (!isFilled(o)) continue;
    const q = filledQty(o);
    const p = toNumber(o.averageFillPrice);
    const sell = o.side === OrderSide.SELL;
    const book = sell ? sold : bought;
    book.set(o.symbol, (book.get(o.symbol) ?? 0) + q);
    if (p > 0 && sell) cashIn += q * p;
    else if (p > 0) cashOut += q * p;
  }
  const fills = fillPrices(day.orders);
  const symbols = [...new Set([...before.keys(), ...bought.keys(), ...sold.keys()])];

  const raw = symbols
    .map((symbol) => {
      const b = before.get(symbol) ?? 0;
      const buy = bought.get(symbol) ?? 0;
      const sell = sold.get(symbol) ?? 0;
      const after = b + buy - sell;
      const fill = fills.get(symbol);
      const close = closes[symbol];
      const price = fill ?? (close > 0 ? close : null);
      return {
        symbol,
        before: b,
        after: Math.abs(after) < EPS ? 0 : after,
        bought: buy,
        sold: sell,
        price,
        priceSource:
          fill !== undefined ? ('fill' as const) : price !== null ? ('close' as const) : null,
      };
    })
    .filter((l) => Math.abs(l.before) > EPS || Math.abs(l.after) > EPS);

  const allPriced = raw.every((l) => l.price !== null);
  const sum = (key: 'before' | 'after') =>
    allPriced ? raw.reduce((s, l) => s + l[key] * (l.price ?? 0), 0) : null;
  const totalBefore = sum('before');
  const totalAfter = sum('after');
  const weight = (shares: number, price: number | null, total: number | null) =>
    price !== null && total !== null && total > 0 ? (shares * price) / total : null;

  const lines: HoldingLine[] = raw.map((l) => ({
    ...l,
    valueBefore: l.price !== null ? l.before * l.price : null,
    valueAfter: l.price !== null ? l.after * l.price : null,
    weightBefore: weight(l.before, l.price, totalBefore),
    weightAfter: weight(l.after, l.price, totalAfter),
    target: targets?.[l.symbol] ?? null,
    changed: Math.abs(l.after - l.before) > EPS,
  }));
  lines.sort(
    (a, b) =>
      Number(b.changed) - Number(a.changed) ||
      (b.valueAfter ?? 0) - (a.valueAfter ?? 0) ||
      a.symbol.localeCompare(b.symbol)
  );

  return {
    key: day.key,
    at: day.at,
    previousAt: index > 0 ? (days[index - 1]?.at ?? null) : null,
    lines,
    changes: lines.filter((l) => l.changed).length,
    added: lines.filter((l) => l.after > l.before + EPS).length,
    removed: lines.filter((l) => l.after < l.before - EPS).length,
    orders: day.orders,
    ordersFilled: day.orders.filter(isFilled).length,
    valueBefore: totalBefore,
    valueAfter: totalAfter,
    cashIn,
    cashOut,
    cashFromOrders: cashIn - cashOut,
  };
}

const shares = (q: number) => formatNumber(q, { dp: Number.isInteger(q) ? 0 : 2 });
const pct = (w: number) => `${formatNumber(w * 100, { dp: 1 })}%`;

/** What the rebalance did to one holding, in words: "bought 42 at $90.41". */
export function tradeText(line: HoldingLine): string {
  const parts: string[] = [];
  const fill = line.priceSource === 'fill' && line.price !== null ? line.price : null;
  const at = fill !== null ? ` at ${formatMoney(fill)}` : '';
  if (line.bought > 0) parts.push(`bought ${shares(line.bought)}${at}`);
  if (line.sold > 0) parts.push(`sold ${shares(line.sold)}${at}`);
  return parts.join(', ');
}

/** A short note on one changed holding, only from what the fills and fixed targets say. */
export function lineNote(line: HoldingLine): string | null {
  if (!line.changed) return null;
  if (line.before === 0) return `${line.symbol} is new in the sleeve.`;
  if (line.after === 0) return `Sold all ${shares(line.before)} ${line.symbol}.`;
  if (line.target !== null && line.weightAfter !== null) {
    const gap = (line.weightAfter - line.target) * 100;
    const side = Math.abs(gap) < 0.05 ? 'on' : gap < 0 ? 'under' : 'over';
    const by = side === 'on' ? '' : ` ${formatNumber(Math.abs(gap), { dp: 1 })} points`;
    return `${line.symbol} ended at ${pct(line.weightAfter)} of holdings,${by} ${side} its ${pct(line.target)} target.`;
  }
  return null;
}

/** "−9" or "+42" for the unified view. */
export function netText(line: HoldingLine): string {
  const net = line.after - line.before;
  if (Math.abs(net) < EPS) return '';
  return `${net > 0 ? '+' : '−'}${shares(Math.abs(net))}`;
}

export { pct as weightText, shares as sharesText };
