/**
 * The Markets tab and a symbol's page as plain data: which sessions hold a symbol, the rows
 * for each segment, today's move and its tone, and where fills sit on a candle chart.
 * No imports, so it runs under `node --test`.
 */

export type Segment = 'held' | 'indexes' | 'watch';
export type Range = '1D' | '1M' | '6M' | '1Y';

export const INDEXES: readonly string[] = ['SPY', 'QQQ', 'DIA', 'IWM'];
export const WATCH: readonly string[] = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD'];

export interface HoldingInput {
  symbol: string;
  sessionId: string;
  shares: number;
  avgPrice: number;
  value: number;
}

export interface HolderSession {
  id: string;
  title: string;
  mode: 'live' | 'paper';
  frozen: boolean;
  stopped: boolean;
}

export interface Holder {
  sessionId: string;
  title: string;
  mode: 'live' | 'paper';
  frozen: boolean;
  shares: number;
  avgPrice: number;
  value: number;
  /** Share of the session's holdings, 0..1; null when its total is unknown. */
  weight: number | null;
}

/**
 * Who holds each symbol, from open positions of sessions that still run. A symbol's holders are
 * ordered by value; the map is ordered by total value held.
 */
export function holdersBySymbol(positions: readonly HoldingInput[], sessions: readonly HolderSession[]): Map<string, Holder[]> {
  const byId = new Map(sessions.filter((s) => !s.stopped).map((s) => [s.id, s]));
  const open = positions.filter((p) => p.shares !== 0 && byId.has(p.sessionId));
  const totals = new Map<string, number>();
  for (const p of open) totals.set(p.sessionId, (totals.get(p.sessionId) ?? 0) + p.value);
  const map = new Map<string, Holder[]>();
  for (const p of open) {
    const s = byId.get(p.sessionId);
    if (!s) continue;
    const total = totals.get(p.sessionId) ?? 0;
    const holder: Holder = {
      sessionId: s.id,
      title: s.title,
      mode: s.mode,
      frozen: s.frozen,
      shares: p.shares,
      avgPrice: p.avgPrice,
      value: p.value,
      weight: total > 0 ? p.value / total : null,
    };
    const list = map.get(p.symbol);
    if (list) list.push(holder);
    else map.set(p.symbol, [holder]);
  }
  for (const list of map.values()) list.sort((a, b) => b.value - a.value);
  const sum = (l: readonly Holder[]) => l.reduce((a, h) => a + h.value, 0);
  return new Map([...map.entries()].sort((a, b) => sum(b[1]) - sum(a[1])));
}

/** The line under a held symbol: who holds it, "live" when only live sessions do. */
export function holderLine(holders: readonly Holder[]): string {
  if (holders.length === 0) return '';
  const names = holders.map((h) => h.title).join(', ');
  return holders.every((h) => h.mode === 'live') ? `${names} · live` : names;
}

export function symbolsFor(segment: Segment, held: readonly string[]): string[] {
  if (segment === 'held') return [...held];
  if (segment === 'indexes') return [...INDEXES];
  return WATCH.filter((s) => !held.includes(s));
}

export interface Move {
  price: number;
  changePct: number;
}

/** Rows sorted by today's move, largest gain first; symbols without a quote go last. */
export function sortByMove(symbols: readonly string[], moves: Readonly<Record<string, Move | undefined>>): string[] {
  return [...symbols].sort((a, b) => {
    const ma = moves[a];
    const mb = moves[b];
    if (!ma && !mb) return 0;
    if (!ma) return 1;
    if (!mb) return -1;
    return mb.changePct - ma.changePct;
  });
}

export type MoveTone = 'gain' | 'loss' | 'fg';

/** Moves under 0.25% stay ink; larger ones take the gain or loss tone. */
export function moveTone(changePct: number): MoveTone {
  if (!Number.isFinite(changePct) || Math.abs(changePct) < 0.25) return 'fg';
  return changePct > 0 ? 'gain' : 'loss';
}

/** +1.32% / −0.22% from a percent. */
export function signedPct(p: number, digits = 2): string {
  if (!Number.isFinite(p)) return '';
  const sign = p > 0 ? '+' : p < 0 ? '−' : '';
  return `${sign}${Math.abs(p).toFixed(digits)}%`;
}

/** 261.47; four decimals under $1. */
export function price(p: number): string {
  if (!Number.isFinite(p)) return '';
  return p.toFixed(Math.abs(p) < 1 ? 4 : 2);
}

/** Trailing window for each range; 1D asks for five-minute bars, the rest daily. */
export const RANGE_DAYS: Record<Range, number> = { '1D': 1, '1M': 31, '6M': 183, '1Y': 366 };

export interface CandleLike {
  /** Epoch seconds. */
  time: number;
  high: number;
  low: number;
}

export interface FillMark {
  side: 'buy' | 'sell';
  price: number;
  /** Epoch ms. */
  at: number;
  sessionId: string;
}

export interface PlacedMark extends FillMark {
  /** Index of the candle the fill falls in. */
  index: number;
}

/**
 * Fills placed on the candle they fall in; fills before the first candle or after the last
 * are left off, since the chart can't show them.
 */
export function placeFills(fills: readonly FillMark[], candles: readonly CandleLike[]): PlacedMark[] {
  if (candles.length === 0) return [];
  const first = candles[0].time * 1000;
  const step = candles.length > 1 ? (candles[candles.length - 1].time - candles[0].time) * 1000 / (candles.length - 1) : 86_400_000;
  const lastEnd = candles[candles.length - 1].time * 1000 + step;
  const out: PlacedMark[] = [];
  for (const f of fills) {
    if (f.at < first || f.at >= lastEnd) continue;
    let index = 0;
    for (let i = 0; i < candles.length; i++) if (candles[i].time * 1000 <= f.at) index = i;
    out.push({ ...f, index });
  }
  return out;
}

/** Low and high across candles and any extra prices (fills, average costs), with a little room. */
export function priceRange(candles: readonly CandleLike[], extra: readonly number[] = []): { min: number; max: number } | null {
  let min = Infinity;
  let max = -Infinity;
  for (const c of candles) {
    if (c.low < min) min = c.low;
    if (c.high > max) max = c.high;
  }
  for (const v of extra) {
    if (!Number.isFinite(v)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (!(min <= max)) return null;
  const pad = (max - min || max * 0.01 || 1) * 0.06;
  return { min: min - pad, max: max + pad };
}
