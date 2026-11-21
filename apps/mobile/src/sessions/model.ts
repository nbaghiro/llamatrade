/**
 * Sessions as the Sessions tab and a session's page read them: state, grouping by account,
 * what needs a decision, and the lanes drawn from fills. Plain data in and out, so it runs
 * under `node --test`; `data.ts` maps the protos onto these shapes.
 */

export type Mode = 'live' | 'paper';
export type SessionState = 'running' | 'waiting' | 'paused' | 'frozen' | 'stopped' | 'error';
export type ExecState = 'pending' | 'running' | 'paused' | 'stopped' | 'error' | null;

export interface SessionInput {
  id: string;
  name: string;
  mode: Mode;
  active: boolean;
  /** Epoch ms. */
  startedAt: number | null;
  endedAt: number | null;
  sleeveId: string;
  strategyId: string;
  executionId: string | null;
  execution: ExecState;
  sleeveFrozen: boolean;
  /** Value now from the performance summary; null when the service has none. */
  value: number | null;
  /** Percent, as the portfolio service returns it (0.6 is 0.6%). */
  return1dPct: number | null;
  returnAllPct: number | null;
  version: number | null;
}

export interface SessionRow extends SessionInput {
  title: string;
  state: SessionState;
  /** Dollar change today; null when there's no value or no one-day return. */
  today: number | null;
}

/** "Recession Radar (paper)" as "Recession Radar"; the mode is shown beside it. */
export function displayName(name: string): string {
  return name.replace(/\s*\((paper|live)\)\s*$/i, '').trim() || name;
}

export function sessionState(s: SessionInput): SessionState {
  if (!s.active || s.endedAt !== null || s.execution === 'stopped') return 'stopped';
  if (s.sleeveFrozen) return 'frozen';
  if (s.execution === 'error') return 'error';
  if (s.execution === 'paused') return 'paused';
  if (s.execution === 'pending') return 'waiting';
  return 'running';
}

/** The dollar move behind a one-day percent return on today's value. */
export function todayChange(value: number | null, return1dPct: number | null): number | null {
  if (value === null || return1dPct === null || !Number.isFinite(value) || !Number.isFinite(return1dPct)) return null;
  const denom = 1 + return1dPct / 100;
  if (denom <= 0) return null;
  return value - value / denom;
}

export function toRow(s: SessionInput): SessionRow {
  const state = sessionState(s);
  return { ...s, title: displayName(s.name), state, today: state === 'stopped' ? null : todayChange(s.value, s.return1dPct) };
}

export interface SessionGroup {
  mode: Mode;
  rows: SessionRow[];
  /** Sum of the values of sessions that still hold money (not stopped). */
  total: number;
  /** How many sessions the total adds up. */
  counted: number;
}

const STATE_ORDER: Record<SessionState, number> = { frozen: 0, error: 1, running: 2, waiting: 3, paused: 4, stopped: 5 };

/** Live above paper, each running first and by value, stopped last. Empty groups are left out. */
export function groupByAccount(rows: readonly SessionRow[]): SessionGroup[] {
  const groups: SessionGroup[] = [];
  for (const mode of ['live', 'paper'] as const) {
    const mine = rows
      .filter((r) => r.mode === mode)
      .sort((a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state] || (b.value ?? 0) - (a.value ?? 0));
    if (mine.length === 0) continue;
    const holding = mine.filter((r) => r.state !== 'stopped' && r.value !== null);
    groups.push({ mode, rows: mine, total: holding.reduce((sum, r) => sum + (r.value ?? 0), 0), counted: holding.length });
  }
  return groups;
}

/** "3 running, 1 stopped" for the subtitle. */
export function countLine(rows: readonly SessionRow[]): string {
  const running = rows.filter((r) => r.state !== 'stopped').length;
  const stopped = rows.length - running;
  const parts: string[] = [];
  if (running) parts.push(`${running} running`);
  if (stopped) parts.push(`${stopped} stopped`);
  return parts.join(', ');
}

/* ------------------------------------------------------------- needs you ---- */

export interface RejectedInput {
  id: string;
  side: 'buy' | 'sell';
  symbol: string;
  quantity: number;
  message: string;
  at: number | null;
  sessionId: string;
}

export interface NeedsItem {
  kind: 'frozen' | 'rejected';
  id: string;
  /** Session to open for a frozen sleeve, order for a rejection. */
  target: string;
  title: string;
  detail: string;
}

/** One list of what needs a decision: frozen sessions first, then rejected orders, newest first. */
export function needsYou(rows: readonly SessionRow[], rejected: readonly RejectedInput[], clock: (ms: number) => string): NeedsItem[] {
  const frozen = rows
    .filter((r) => r.state === 'frozen')
    .map<NeedsItem>((r) => ({
      kind: 'frozen',
      id: `frozen-${r.id}`,
      target: r.id,
      title: `${r.title} is frozen`,
      detail: 'Trading is on hold until it is resolved',
    }));
  const byId = new Map(rows.map((r) => [r.id, r.title]));
  const orders = [...rejected]
    .sort((a, b) => (b.at ?? 0) - (a.at ?? 0))
    .map<NeedsItem>((o) => ({
      kind: 'rejected',
      id: `order-${o.id}`,
      target: o.id,
      title: `${o.side === 'buy' ? 'Buy' : 'Sell'} ${formatQty(o.quantity)} ${o.symbol} rejected`,
      detail: [byId.get(o.sessionId), o.message.trim(), o.at ? clock(o.at) : ''].filter(Boolean).join(' · '),
    }));
  return [...frozen, ...orders];
}

export function needsLine(count: number): string {
  if (count === 0) return '';
  return count === 1 ? '1 thing needs you' : `${count} things need you`;
}

/* ----------------------------------------------------------------- fills ---- */

export interface FillInput {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  /** Epoch ms of the fill. */
  at: number;
}

export interface RebalanceDay {
  /** Local midnight of the day, epoch ms. */
  day: number;
  /** First fill of the day. */
  at: number;
  fills: FillInput[];
}

function dayStart(ms: number): number {
  const d = new Date(ms);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Fills grouped by the day they filled, oldest first; each day reads as one rebalance. */
export function rebalanceDays(fills: readonly FillInput[]): RebalanceDay[] {
  const map = new Map<number, FillInput[]>();
  for (const f of [...fills].sort((a, b) => a.at - b.at)) {
    const key = dayStart(f.at);
    const list = map.get(key);
    if (list) list.push(f);
    else map.set(key, [f]);
  }
  return [...map.entries()].map(([day, list]) => ({ day, at: list[0].at, fills: list }));
}

export interface LaneMark {
  /** 0..1 across the lane. */
  x: number;
  side: 'buy' | 'sell';
}

export interface SymbolLane {
  symbol: string;
  marks: LaneMark[];
}

/** Where `t` sits between `start` and `end`, clamped to the lane. */
export function laneX(t: number, start: number, end: number): number {
  if (!(end > start)) return 1;
  return Math.min(1, Math.max(0, (t - start) / (end - start)));
}

/** One lane per symbol, held symbols first in the order given, then any others by first fill. */
export function symbolLanes(fills: readonly FillInput[], start: number, end: number, held: readonly string[] = []): SymbolLane[] {
  const order: string[] = [...held];
  for (const f of [...fills].sort((a, b) => a.at - b.at)) if (!order.includes(f.symbol)) order.push(f.symbol);
  return order.map((symbol) => ({
    symbol,
    marks: fills.filter((f) => f.symbol === symbol).map((f) => ({ x: laneX(f.at, start, end), side: f.side })),
  }));
}

/* ---------------------------------------------------------- mix over time ---- */

export interface DailyClose {
  t: number;
  close: number;
}

export interface MixDay {
  t: number;
  /** Weight per symbol, 0..1, in the order of `symbols`. */
  weights: number[];
  cash: number;
  value: number;
}

export interface Mix {
  symbols: string[];
  days: MixDay[];
}

/**
 * Daily weights rebuilt from the fills and each symbol's daily close, with cash as the rest of
 * the allocated capital. Days before the first fill, or with a missing price, are skipped.
 */
export function mixOverTime(allocated: number, fills: readonly FillInput[], closes: Readonly<Record<string, readonly DailyClose[]>>): Mix {
  const sorted = [...fills].sort((a, b) => a.at - b.at);
  const symbols = [...new Set(sorted.map((f) => f.symbol))];
  if (sorted.length === 0 || !(allocated > 0)) return { symbols, days: [] };
  const timeline = [...new Set(symbols.flatMap((s) => (closes[s] ?? []).map((c) => dayStart(c.t))))].sort((a, b) => a - b);
  const priceAt = new Map(symbols.map((s) => [s, new Map((closes[s] ?? []).map((c) => [dayStart(c.t), c.close]))]));
  const shares = new Map<string, number>();
  let cash = allocated;
  let i = 0;
  const days: MixDay[] = [];
  for (const t of timeline) {
    const end = t + 86_400_000;
    while (i < sorted.length && sorted[i].at < end) {
      const f = sorted[i];
      const signed = f.side === 'buy' ? f.quantity : -f.quantity;
      shares.set(f.symbol, (shares.get(f.symbol) ?? 0) + signed);
      cash -= signed * f.price;
      i++;
    }
    if (i === 0) continue;
    const values = symbols.map((s) => (shares.get(s) ?? 0) * (priceAt.get(s)?.get(t) ?? NaN));
    if (values.some((v) => !Number.isFinite(v))) continue;
    const value = values.reduce((a, b) => a + b, 0) + cash;
    if (!(value > 0)) continue;
    days.push({ t, weights: values.map((v) => v / value), cash: cash / value, value });
  }
  return { symbols, days };
}

export interface WeightChange {
  symbol: string;
  before: number;
  after: number;
}

/** Each symbol's weight just before and just after one day's fills, valued at that day's close. */
export function weightChange(mix: Mix, day: number): WeightChange[] {
  const idx = mix.days.findIndex((d) => dayStart(d.t) === dayStart(day));
  if (idx < 0) return [];
  const after = mix.days[idx];
  const before = idx > 0 ? mix.days[idx - 1] : null;
  return mix.symbols.map((symbol, k) => ({ symbol, before: before ? before.weights[k] : 0, after: after.weights[k] }));
}

/* --------------------------------------------------------------- formats ---- */

export function formatQty(n: number): string {
  const r = Math.round(n * 100) / 100;
  return Number.isInteger(r) ? String(r) : r.toFixed(2).replace(/0+$/, '');
}

/** 58.2% from 0.582. */
export function weightPct(w: number, digits = 1): string {
  return `${(w * 100).toFixed(digits)}%`;
}
