/** View-model maths for backtest runs: trades by month, compare ranges, progress and figures. */

import type { MonthReturn } from './illustrative/series';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const TRADING_DAYS = 252;
const DEFAULT_RISK_FREE = 0.02;

/** "YYYY-MM-DD" in UTC. */
export function dayKey(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** "YYYY-MM" in UTC. */
export function monthKey(d: Date): string {
  return d.toISOString().slice(0, 7);
}

/** "Nov 1, 2024" from a date, read in UTC. */
export function longDate(d: Date): string {
  return `${MON[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

/** "Aug 2026" from "2026-08". */
export function monthLabel(month: string): string {
  const [y, m] = month.split('-').map(Number);
  return `${MON[m - 1] ?? ''} ${y}`;
}

export function rangeLabel(start: Date, end: Date): string {
  return `${longDate(start)} to ${longDate(end)}`;
}

/** "#month-2026-08" → "2026-08"; anything else → null. */
export function parseMonthHash(hash: string): string | null {
  const m = /^#?month-(\d{4})-(0[1-9]|1[0-2])$/.exec(hash.trim());
  return m ? `${m[1]}-${m[2]}` : null;
}

/** The MonthlyGrid cell key ("2026-7") for a "2026-08" month. */
export function gridCellKey(month: string): string {
  const [y, m] = month.split('-').map(Number);
  return `${y}-${m - 1}`;
}

/** BacktestResults.monthly_returns ("2024-01" → 0.05) as grid months, oldest first. */
export function monthlyReturnsFromMap(map: Readonly<Record<string, number>>): MonthReturn[] {
  return Object.entries(map)
    .map(([k, r]) => {
      const m = /^(\d{4})-(\d{2})$/.exec(k);
      return m && Number.isFinite(r) ? { y: Number(m[1]), m: Number(m[2]) - 1, r } : null;
    })
    .filter((x): x is MonthReturn => x !== null)
    .sort((a, b) => a.y - b.y || a.m - b.m);
}

export type Side = 'BUY' | 'SELL';

/** A round-trip trade from GetBacktestTrades, already converted from proto. */
export interface TradeInput {
  symbol: string;
  side: Side;
  quantity: number;
  entryPrice: number;
  exitPrice: number;
  entryTime: Date | null;
  exitTime: Date | null;
  pnl: number;
  entryReason: string;
  exitReason: string;
}

/** One simulated order: the entry or the exit of a trade. */
export interface SimOrder {
  date: string;
  side: Side;
  symbol: string;
  quantity: number;
  price: number;
  value: number;
  /** Realised P&L, set on the order that closes a trade. */
  pnl: number | null;
  reason: string;
}

export interface Rebalance {
  date: string;
  month: string;
  /** The reasons the orders give, joined; usually one branch. */
  branch: string;
  orders: SimOrder[];
  realised: number;
}

const opposite = (s: Side): Side => (s === 'BUY' ? 'SELL' : 'BUY');

/** Splits each round trip into its entry and exit orders. */
export function tradesToOrders(trades: readonly TradeInput[]): SimOrder[] {
  const out: SimOrder[] = [];
  for (const t of trades) {
    if (t.entryTime) {
      out.push({
        date: dayKey(t.entryTime),
        side: t.side,
        symbol: t.symbol,
        quantity: t.quantity,
        price: t.entryPrice,
        value: t.quantity * t.entryPrice,
        pnl: null,
        reason: t.entryReason.trim(),
      });
    }
    if (t.exitTime) {
      out.push({
        date: dayKey(t.exitTime),
        side: opposite(t.side),
        symbol: t.symbol,
        quantity: t.quantity,
        price: t.exitPrice,
        value: t.quantity * t.exitPrice,
        pnl: t.pnl,
        reason: t.exitReason.trim() || t.entryReason.trim(),
      });
    }
  }
  return out;
}

/** Orders grouped by trading day, newest day first; sells before buys within a day. */
export function groupRebalances(orders: readonly SimOrder[]): Rebalance[] {
  const byDay = new Map<string, SimOrder[]>();
  for (const o of orders) {
    const list = byDay.get(o.date) ?? [];
    list.push(o);
    byDay.set(o.date, list);
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
    .map(([date, list]) => {
      const sorted = [...list].sort((a, b) =>
        a.side === b.side ? a.symbol.localeCompare(b.symbol) : a.side === 'SELL' ? -1 : 1
      );
      const reasons = [...new Set(sorted.map((o) => o.reason).filter(Boolean))];
      return {
        date,
        month: date.slice(0, 7),
        branch: reasons.join(' · '),
        orders: sorted,
        realised: sorted.reduce((s, o) => s + (o.pnl ?? 0), 0),
      };
    });
}

export function rebalancesInMonth(rebalances: readonly Rebalance[], month: string): Rebalance[] {
  return rebalances.filter((r) => r.month === month);
}

/** The newest month that had a rebalance, or null. */
export function latestTradedMonth(rebalances: readonly Rebalance[]): string | null {
  return rebalances[0]?.month ?? null;
}

export interface Curve {
  dates: readonly Date[];
  values: readonly number[];
}

export interface CommonRange {
  start: Date;
  end: Date;
  dates: Date[];
  /** Each curve rebased to growth of 1 at the shared start, on the shared dates. */
  series: number[][];
}

/**
 * Cuts curves to the dates every one of them has, then rebases each to 1 at the
 * first shared date. Null when fewer than two shared dates remain.
 */
export function commonRange(curves: readonly Curve[]): CommonRange | null {
  if (curves.length === 0) return null;
  const maps = curves.map((c) => {
    const m = new Map<string, number>();
    c.dates.forEach((d, i) => {
      const v = c.values[i];
      if (Number.isFinite(v) && v > 0) m.set(dayKey(d), v);
    });
    return m;
  });
  const keys = [...maps[0].keys()].filter((k) => maps.every((m) => m.has(k))).sort();
  if (keys.length < 2) return null;
  const series = maps.map((m) => {
    const first = m.get(keys[0]) as number;
    return keys.map((k) => (m.get(k) as number) / first);
  });
  const dates = keys.map((k) => new Date(`${k}T00:00:00Z`));
  return { start: dates[0], end: dates[dates.length - 1], dates, series };
}

/** Fractional drawdown from the running peak: 0 at a peak, negative below it. */
export function drawdownOf(values: readonly number[]): number[] {
  let peak = -Infinity;
  return values.map((v) => {
    peak = Math.max(peak, v);
    return peak > 0 ? v / peak - 1 : 0;
  });
}

export interface PerfFigures {
  totalReturn: number;
  cagr: number;
  sharpe: number;
  sortino: number;
  /** Negative fraction, e.g. −0.12. */
  maxDrawdown: number;
  volatility: number;
}

const mean = (xs: readonly number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;

/** Figures from daily closes, with the engine's conventions: 252 days, 2% risk-free, population std. */
export function figuresFromCurve(
  values: readonly number[],
  riskFree = DEFAULT_RISK_FREE
): PerfFigures | null {
  if (values.length < 2 || values[0] <= 0) return null;
  const rets: number[] = [];
  for (let i = 1; i < values.length; i++) rets.push(values[i] / values[i - 1] - 1);
  const total = values[values.length - 1] / values[0] - 1;
  const m = mean(rets);
  const std = Math.sqrt(mean(rets.map((r) => (r - m) ** 2)));
  const dailyRf = riskFree / TRADING_DAYS;
  const excess = rets.map((r) => r - dailyRf);
  const downside = Math.sqrt(mean(excess.map((e) => Math.min(e, 0) ** 2)));
  return {
    totalReturn: total,
    cagr: (1 + total) ** (TRADING_DAYS / rets.length) - 1,
    sharpe: std === 0 ? 0 : (Math.sqrt(TRADING_DAYS) * mean(excess)) / std,
    sortino: downside === 0 ? 0 : (Math.sqrt(TRADING_DAYS) * mean(excess)) / downside,
    maxDrawdown: Math.min(0, ...drawdownOf(values)),
    volatility: std * Math.sqrt(TRADING_DAYS),
  };
}

/** Trading days from the deepest low back to the previous peak; null if it never got back. */
export function recoveryDays(values: readonly number[]): number | null {
  const dd = drawdownOf(values);
  let low = 0;
  dd.forEach((d, i) => {
    if (d < dd[low]) low = i;
  });
  if (dd[low] === 0) return 0;
  for (let i = low + 1; i < values.length; i++) if (dd[i] >= 0) return i - low;
  return null;
}

/** Decimal strings from StreamBacktestProgress.partial_metrics; empty when the field is unset. */
export interface PartialMetricsInput {
  totalReturn?: string;
  maxDrawdown?: string;
  benchmarkReturn?: string;
}

export interface PartialFigures {
  totalReturn: number | null;
  /** Negative fraction. */
  maxDrawdown: number | null;
  benchmarkReturn: number | null;
}

const parseDecimal = (s: string | undefined): number | null => {
  if (s === undefined || s.trim() === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};

/** The figures a run can show before it ends. Missing values stay null and render as dots. */
export function partialFigures(m: PartialMetricsInput | null): PartialFigures {
  if (!m) return { totalReturn: null, maxDrawdown: null, benchmarkReturn: null };
  const dd = parseDecimal(m.maxDrawdown);
  return {
    totalReturn: parseDecimal(m.totalReturn),
    maxDrawdown: dd === null ? null : -Math.abs(dd),
    benchmarkReturn: parseDecimal(m.benchmarkReturn),
  };
}

export type RunPhase = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface ProgressEvent {
  phase: RunPhase;
  percent: number;
  /** "YYYY-MM-DD" the engine has replayed through, or empty. */
  currentDate: string;
  message: string;
  /** Client receive time in ms. */
  atMs: number;
}

export type LogTone = 'ok' | 'now' | 'bad' | 'note';

export interface LogLine {
  /** Seconds since the run was submitted. */
  at: number;
  text: string;
  tone: LogTone;
}

const isTerminal = (p: RunPhase) => p === 'completed' || p === 'failed' || p === 'cancelled';

/**
 * Log lines built from progress events alone: queued, replaying through the latest date,
 * and how it ended. The stream carries no engine log text, so nothing else is claimed.
 */
export function runLog(events: readonly ProgressEvent[], startMs: number): LogLine[] {
  const at = (ms: number) => Math.max(0, (ms - startMs) / 1000);
  const lines: LogLine[] = [{ at: 0, text: 'queued', tone: 'ok' }];
  const started = events.find((e) => e.phase !== 'pending');
  if (!started) return lines;
  const end = events.find((e) => isTerminal(e.phase));
  const dated = events.filter((e) => e.currentDate && (!end || e.atMs <= end.atMs));
  const latest = dated[dated.length - 1];

  if (started.phase === 'running' || dated.length > 0) {
    lines.push({ at: at(started.atMs), text: 'started on a worker', tone: 'ok' });
  }
  if (!end) {
    lines.push({
      at: at(latest?.atMs ?? started.atMs),
      text: latest ? `replaying through ${latest.currentDate}` : 'preparing data',
      tone: 'now',
    });
    return lines;
  }
  if (latest) {
    lines.push({ at: at(latest.atMs), text: `replayed through ${latest.currentDate}`, tone: 'ok' });
  }
  if (end.phase === 'completed') lines.push({ at: at(end.atMs), text: 'completed', tone: 'ok' });
  if (end.phase === 'cancelled') lines.push({ at: at(end.atMs), text: 'cancelled', tone: 'note' });
  if (end.phase === 'failed') {
    const msg = end.message.trim();
    lines.push({ at: at(end.atMs), text: msg ? `failed: ${msg}` : 'failed', tone: 'bad' });
  }
  return lines;
}

export type RebalanceFrequency = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annually';

const FREQS: readonly RebalanceFrequency[] = [
  'daily',
  'weekly',
  'monthly',
  'quarterly',
  'annually',
];

export function asFrequency(s: string | undefined): RebalanceFrequency | null {
  const v = (s ?? '').trim().toLowerCase();
  return (FREQS as readonly string[]).includes(v) ? (v as RebalanceFrequency) : null;
}

const MONTHS_PER: Partial<Record<RebalanceFrequency, number>> = {
  monthly: 1,
  quarterly: 3,
  annually: 12,
};

/**
 * Scheduled rebalance count over a range, and how many fall on or before `through`.
 * Only for monthly, quarterly and annual schedules; null otherwise.
 */
export function scheduledRebalances(
  start: Date,
  end: Date,
  freq: RebalanceFrequency | null,
  through?: Date | null
): { total: number; done: number } | null {
  const step = freq ? MONTHS_PER[freq] : undefined;
  if (!step || end < start) return null;
  const idx = (d: Date) => d.getUTCFullYear() * 12 + d.getUTCMonth();
  const months = idx(end) - idx(start) + 1;
  const total = Math.ceil(months / step);
  if (!through) return { total, done: 0 };
  const elapsed = Math.min(months, Math.max(0, idx(through) - idx(start) + 1));
  return { total, done: Math.min(total, Math.ceil(elapsed / step)) };
}

/** Indicator and metric names a DSL source calls, in vocabulary order. */
export function namesUsed(dsl: string, vocabulary: readonly string[]): string[] {
  const called = new Set<string>();
  const re = /\(\s*([a-z][a-z0-9-]*)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(dsl)) !== null) called.add(m[1]);
  return vocabulary.filter((v) => called.has(v));
}

/** Runs past this count make the compare chart hard to read. */
export const COMPARE_SOFT_LIMIT = 4;

/** Parses "?runs=a,b,c" into unique non-empty ids, in order. */
export function parseRunIds(param: string | null): string[] {
  if (!param) return [];
  return [
    ...new Set(
      param
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    ),
  ];
}

/** A curve's values on another curve's dates, carrying the last known value forward. */
export function alignTo(dates: readonly Date[], curve: Curve): (number | null)[] {
  const byDay = new Map<string, number>();
  curve.dates.forEach((d, i) => byDay.set(dayKey(d), curve.values[i]));
  let last: number | null = null;
  return dates.map((d) => {
    const v = byDay.get(dayKey(d));
    if (v !== undefined && Number.isFinite(v)) last = v;
    return last;
  });
}
