import type { CurvePoint } from '@llamatrade/core/chart';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';
import type { DashboardStrategy } from '@llamatrade/core/stores/dashboard';

import { formatMoney, formatNumber, formatPct, pnlTone } from '../../lib/format';
import { etParts, etToDate } from '../../lib/marketClock';
import { isTradingDay, marketDay, tradingDaysBetween } from '../../lib/marketHolidays';
import type { SessionState, SessionStateView } from '../../lib/sessionState';
import type { SessionRow } from '../sessions/sessionRows';
import type { AccountMode } from '../ui/ModeBadge';

import { alignAsOf } from './equity';

const DAY = 86_400_000;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/** "Nov 23", from a calendar date at UTC midnight. */
export const dayLabel = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCDate()}`;
/** "Mon Nov 23", from a calendar date at UTC midnight. */
export const weekdayLabel = (d: Date) => `${WEEKDAY[d.getUTCDay()]} ${dayLabel(d)}`;

/** The New York calendar date of an instant, at UTC midnight. */
export function etDay(at: Date): Date {
  const p = etParts(at);
  return new Date(Date.UTC(p.year, p.month, p.day));
}

const addDays = (d: Date, n: number) => new Date(d.getTime() + n * DAY);

export interface HomeSession {
  id: string;
  name: string;
  mode: AccountMode;
  state: SessionState;
  view: SessionStateView;
  /** "Monthly", "Weekly", "Daily" or "". */
  rebalance: string;
  value: number | null;
  /** Today's change in dollars and as a fraction. */
  today: number | null;
  todayPct: number | null;
  startedAt: Date | null;
  stoppedAt: Date | null;
  /** When the sleeve last changed while frozen, standing in for when it froze. */
  frozenAt: Date | null;
  /** Absolute equity snapshots. */
  equity: readonly CurvePoint[];
  /** Cumulative return in percent, for a sparkline. */
  curve: readonly number[];
  allocated: number | null;
  href: string;
}

/** One entry per session, with figures from the dashboard's performance read where it has them. */
export function homeSessions(
  rows: readonly SessionRow[],
  strategies: readonly DashboardStrategy[]
): HomeSession[] {
  return rows.map((row) => {
    const strategy = row.execution ? strategies.find((s) => s.id === row.execution?.id) : undefined;
    const value =
      strategy?.currentValue ??
      row.figures.equity ??
      (row.session.currentEquity ? toNumber(row.session.currentEquity) : null);
    const dayReturn = strategy ? strategy.dayReturn : null;
    const today =
      value !== null && dayReturn !== null && dayReturn > -1
        ? value - value / (1 + dayReturn)
        : null;
    return {
      id: row.session.id,
      name: row.name,
      mode: row.session.mode === ExecutionMode.LIVE ? 'live' : 'paper',
      state: row.state,
      view: row.view,
      rebalance: row.rebalance,
      value,
      today,
      todayPct: today === null ? null : dayReturn,
      startedAt: row.startedAt ?? strategy?.startedAt ?? null,
      stoppedAt:
        toDate(row.session.endedAt) ??
        (row.state === 'stopped' ? toDate(row.execution?.stoppedAt) : null),
      frozenAt: row.state === 'frozen' ? toDate(row.sleeve?.updatedAt) : null,
      equity: strategy?.equity ?? [],
      curve: strategy?.curve.map((p) => p.value) ?? [],
      allocated: strategy?.allocatedCapital ?? null,
      href: `/trading/${row.session.id}`,
    };
  });
}

/** Open sessions first by value, then stopped ones, so the largest money leads. */
export function bySize(sessions: readonly HomeSession[]): HomeSession[] {
  const open = (s: HomeSession) => (s.state === 'stopped' || s.state === 'error' ? 1 : 0);
  return [...sessions].sort(
    (a, b) => open(a) - open(b) || (b.value ?? 0) - (a.value ?? 0) || a.name.localeCompare(b.name)
  );
}

export const FOLD_ABOVE = 8;
export const FOLD_KEEP = 5;

/** Past eight sessions, the five largest keep a lane and the rest fold into one row. */
export function foldSessions(sessions: readonly HomeSession[]): {
  shown: HomeSession[];
  rest: HomeSession[];
} {
  const sorted = bySize(sessions);
  if (sorted.length <= FOLD_ABOVE) return { shown: sorted, rest: [] };
  // A frozen session always keeps its own lane, so the amber is never folded away.
  const keep = sorted.slice(0, FOLD_KEEP);
  const frozen = sorted.slice(FOLD_KEEP).filter((s) => s.state === 'frozen');
  const shown = [...keep, ...frozen];
  return { shown, rest: sorted.filter((s) => !shown.includes(s)) };
}

export interface Fill {
  id: string;
  sessionId: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  amount: number;
  at: Date;
}

/** Filled and partly filled orders, newest first. */
export function fillsOf(orders: readonly Order[]): Fill[] {
  const out: Fill[] = [];
  for (const o of orders) {
    if (o.status !== OrderStatus.FILLED && o.status !== OrderStatus.PARTIAL) continue;
    const at = toDate(o.filledAt);
    const quantity = toNumber(o.filledQuantity) || toNumber(o.quantity);
    const price = toNumber(o.averageFillPrice);
    if (!at || quantity <= 0) continue;
    out.push({
      id: o.id,
      sessionId: o.sessionId,
      symbol: o.symbol,
      side: o.side === OrderSide.SELL ? 'sell' : 'buy',
      quantity,
      price,
      amount: quantity * price,
      at,
    });
  }
  return out.sort((a, b) => b.at.getTime() - a.at.getTime());
}

export interface FillDay {
  day: Date;
  count: number;
}

const qty = (n: number) => formatNumber(n, { dp: n % 1 === 0 ? 0 : 2 });

/** "42 TLT at $90.41". */
export const fillTitle = (f: Fill) => `${qty(f.quantity)} ${f.symbol} at ${formatMoney(f.price)}`;

/** Fills grouped by New York trading day, oldest first. */
export function fillDays(fills: readonly Fill[]): FillDay[] {
  const byDay = new Map<number, number>();
  for (const f of fills) {
    const t = etDay(f.at).getTime();
    byDay.set(t, (byDay.get(t) ?? 0) + 1);
  }
  return [...byDay.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([t, count]) => ({ day: new Date(t), count }));
}

export interface EquitySeries {
  dates: Date[];
  values: number[];
}

/**
 * Sessions' equity added up on every snapshot date. Before its first snapshot a session counts
 * at its allocated capital, as the dashboard's account line does; after its last, at its last value.
 */
export function blendEquity(sessions: readonly HomeSession[]): EquitySeries {
  const legs = sessions
    .map((s) => ({
      points: s.equity
        .map((p) => ({ t: new Date(p.timestamp).getTime(), v: p.value }))
        .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v))
        .sort((a, b) => a.t - b.t),
      baseline: s.allocated,
    }))
    .filter((l) => l.points.length > 0);
  if (legs.length === 0) return { dates: [], values: [] };
  const times = [...new Set(legs.flatMap((l) => l.points.map((p) => p.t)))].sort((a, b) => a - b);
  const cursor = legs.map(() => -1);
  const values = times.map((t) =>
    legs.reduce((sum, leg, i) => {
      while (cursor[i] + 1 < leg.points.length && leg.points[cursor[i] + 1].t <= t) cursor[i] += 1;
      const v = cursor[i] >= 0 ? leg.points[cursor[i]].v : (leg.baseline ?? leg.points[0].v);
      return sum + v;
    }, 0)
  );
  return { dates: times.map((t) => new Date(t)), values };
}

export type HomeRange = '1W' | '1M' | '3M' | '1Y' | 'ALL';
export const HOME_RANGES: HomeRange[] = ['1W', '1M', '3M', '1Y', 'ALL'];
const RANGE_DAYS: Record<HomeRange, number | null> = {
  '1W': 8,
  '1M': 31,
  '3M': 92,
  '1Y': 366,
  ALL: null,
};

/** After the close Home opens on the last week; there is no intraday equity for a 1D view yet. */
export const defaultRange = (phase: Pick<MarketPhase, 'open'>): HomeRange =>
  phase.open ? '3M' : '1W';

/**
 * SPY's move on `day` (an ET date) as a fraction, from the benchmark's percent curve; null when
 * the curve has no point on that day or none before it.
 */
export function benchDayMove(benchmark: readonly CurvePoint[], day: Date): number | null {
  let last = -1;
  for (let i = 0; i < benchmark.length; i++) {
    const t = new Date(benchmark[i].timestamp);
    if (Number.isNaN(t.getTime())) continue;
    const d = etDay(t).getTime();
    if (d === day.getTime()) last = i;
    else if (d > day.getTime()) break;
  }
  if (last < 1) return null;
  const today = new Date(benchmark[last].timestamp);
  let prev = last - 1;
  while (
    prev >= 0 &&
    etDay(new Date(benchmark[prev].timestamp)).getTime() === etDay(today).getTime()
  )
    prev -= 1;
  if (prev < 0) return null;
  const base = 1 + benchmark[prev].value / 100;
  return base > 0 ? (1 + benchmark[last].value / 100) / base - 1 : null;
}

export interface DailyBars {
  /** When the latest daily bar opened. */
  at: Date;
  close: number;
  previousClose: number;
}

/** A symbol's move on `day` from its latest daily bar, when that bar is from that day. */
export function snapshotDayMove(bars: DailyBars | null, day: Date): number | null {
  if (!bars || bars.previousClose <= 0 || bars.close <= 0) return null;
  if (etDay(bars.at).getTime() !== day.getTime()) return null;
  return bars.close / bars.previousClose - 1;
}

export interface CurveWindow extends EquitySeries {
  start: Date;
  /** SPY on the same dates, scaled to start at the account's first value; null without data. */
  bench: number[] | null;
  accountReturn: number | null;
  benchReturn: number | null;
  high: number | null;
  low: number | null;
  /** Worst fall from a high, as a negative fraction. */
  maxDrawdown: number | null;
}

/** The part of the equity series inside a range, ending at `end`. */
export function curveWindow(
  series: EquitySeries,
  benchmark: readonly CurvePoint[],
  range: HomeRange,
  end: Date
): CurveWindow {
  const days = RANGE_DAYS[range];
  const from = days === null ? -Infinity : end.getTime() - days * DAY;
  let idx = series.dates.map((_, i) => i).filter((i) => series.dates[i].getTime() >= from);
  // A range with under two snapshots reaches back to the one before it, so there is a line.
  if (idx.length < 2 && series.dates.length >= 2) {
    const first = idx.length ? idx[0] : series.dates.length;
    idx = series.dates.map((_, i) => i).slice(Math.max(0, first - (2 - idx.length)));
  }
  const dates = idx.map((i) => series.dates[i]);
  const values = idx.map((i) => series.values[i]);
  const start =
    days === null || (dates.length && dates[0].getTime() < from)
      ? (dates[0] ?? new Date(end.getTime() - 30 * DAY))
      : new Date(from);
  const aligned = dates.length ? alignAsOf(dates, benchmark) : null;
  const bench =
    aligned && values.length
      ? aligned.map((v) => values[0] * ((1 + v / 100) / (1 + aligned[0] / 100)))
      : null;
  let peak = -Infinity;
  let worst = 0;
  for (const v of values) {
    peak = Math.max(peak, v);
    if (peak > 0) worst = Math.min(worst, v / peak - 1);
  }
  const first = values[0];
  const last = values[values.length - 1];
  return {
    dates,
    values,
    start,
    bench,
    accountReturn: values.length > 1 && first > 0 ? last / first - 1 : null,
    benchReturn:
      bench && bench.length > 1 && bench[0] > 0 ? bench[bench.length - 1] / bench[0] - 1 : null,
    high: values.length ? Math.max(...values) : null,
    low: values.length ? Math.min(...values) : null,
    maxDrawdown: values.length > 1 ? worst : null,
  };
}

function previousTradingDay(d: Date): Date {
  let p = addDays(d, -1);
  while (!isTradingDay(p)) p = addDays(p, -1);
  return p;
}

const mondayOf = (d: Date) => addDays(d, -((d.getUTCDay() + 6) % 7));

/** Whether a schedule rebalances on a date: the first trading day of a new week, month and so on. */
export function rebalancesOn(rebalance: string, day: Date): boolean {
  if (!isTradingDay(day)) return false;
  const freq = rebalance.trim().toLowerCase();
  if (freq === 'daily') return true;
  const prev = previousTradingDay(day);
  if (freq === 'weekly') return prev.getTime() < mondayOf(day).getTime();
  if (freq === 'monthly') return prev.getUTCMonth() !== day.getUTCMonth();
  if (freq === 'quarterly')
    return Math.floor(prev.getUTCMonth() / 3) !== Math.floor(day.getUTCMonth() / 3);
  if (freq === 'annually') return prev.getUTCFullYear() !== day.getUTCFullYear();
  return false;
}

/** The first scheduled rebalance after `today`, looking up to a year ahead. */
export function nextRebalance(rebalance: string, today: Date): Date | null {
  if (!rebalance) return null;
  for (let i = 1; i <= 370; i++) {
    const d = addDays(today, i);
    if (rebalancesOn(rebalance, d)) return d;
  }
  return null;
}

/** Sessions whose schedule still runs: running, starting or waiting on a frozen sleeve. */
export const schedules = (s: HomeSession) =>
  s.state === 'running' || s.state === 'starting' || s.state === 'frozen';

export type ScheduleKind = 'rebalance' | 'closed' | 'early';

export interface ScheduleRow {
  day: Date;
  kind: ScheduleKind;
  sessions: HomeSession[];
  /** Holiday name for closed and early-close days. */
  name: string | null;
}

/** Rebalances and market closures after `today` and up to `days` ahead. Daily schedules are left out. */
export function upcoming(sessions: readonly HomeSession[], today: Date, days = 14): ScheduleRow[] {
  const active = sessions.filter(
    (s) => schedules(s) && s.rebalance.toLowerCase() !== 'daily' && s.rebalance !== ''
  );
  const out: ScheduleRow[] = [];
  for (let i = 1; i <= days; i++) {
    const day = addDays(today, i);
    const md = marketDay(day);
    if (md.closed && md.name) out.push({ day, kind: 'closed', sessions: [], name: md.name });
    if (md.closed) continue;
    if (md.earlyClose) out.push({ day, kind: 'early', sessions: [], name: md.name });
    const due = active.filter((s) => rebalancesOn(s.rebalance, day));
    if (due.length) out.push({ day, kind: 'rebalance', sessions: due, name: null });
  }
  // With nothing due inside the window, the first rebalance after it is still worth listing.
  if (active.length && !out.some((r) => r.kind === 'rebalance')) {
    for (let i = days + 1; i <= 370; i++) {
      const day = addDays(today, i);
      const due = active.filter((s) => rebalancesOn(s.rebalance, day));
      if (due.length) {
        out.push({ day, kind: 'rebalance', sessions: due, name: null });
        break;
      }
    }
  }
  return out;
}

/** Sessions that rebalance on `today` itself. */
export function rebalancingToday(sessions: readonly HomeSession[], today: Date): HomeSession[] {
  return sessions.filter((s) => schedules(s) && rebalancesOn(s.rebalance, today));
}

export type HomeStage = 'firstVisit' | 'firstSession' | 'ordinary';

/** About a week of daily history before Home switches from the spotlight to the curve. */
export const SPOTLIGHT_DAYS = 5;

export function homeStage(sessions: readonly HomeSession[], today: Date): HomeStage {
  if (sessions.length === 0) return 'firstVisit';
  if (sessions.length === 1) {
    const [s] = sessions;
    const open = s.state !== 'stopped' && s.state !== 'error';
    const started = s.startedAt ? etDay(s.startedAt) : today;
    if (open && tradingDaysBetween(started, today) < SPOTLIGHT_DAYS) return 'firstSession';
  }
  return 'ordinary';
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "3 sessions running, 1 stopped". */
export function sessionsLine(sessions: readonly HomeSession[]): string {
  const count = (states: SessionState[]) => sessions.filter((s) => states.includes(s.state)).length;
  const running = count(['running', 'starting']);
  const parts: string[] = [];
  const rest: [number, string][] = [
    [count(['frozen']), 'frozen'],
    [count(['paused']), 'paused'],
    [count(['stopped', 'error']), 'stopped'],
  ];
  if (running) parts.push(`${plural(running, 'session')} running`);
  for (const [n, word] of rest) {
    if (!n) continue;
    parts.push(parts.length ? `${n} ${word}` : `${plural(n, 'session')} ${word}`);
  }
  return parts.join(', ') || 'No sessions';
}

/** "1 rebalance today", "no rebalances today", or null when the market is closed today. */
export function todayLine(sessions: readonly HomeSession[], today: Date): string | null {
  if (!isTradingDay(today)) return null;
  const n = rebalancingToday(sessions, today).length;
  return n ? `${plural(n, 'rebalance')} today` : 'no rebalances today';
}

/** The Live and Paper parts of a set of sessions. */
export function splitByMode(sessions: readonly HomeSession[]): { live: number; paper: number } {
  let live = 0;
  let paper = 0;
  for (const s of sessions) {
    if (s.value === null) continue;
    if (s.mode === 'live') live += s.value;
    else paper += s.value;
  }
  return { live, paper };
}

const OPEN_MIN = 9 * 60 + 30;
const closeMinutes = (day: Date) => (marketDay(day).earlyClose ? 13 * 60 : 16 * 60);
const instantOf = (day: Date, minutes: number) =>
  etToDate(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), minutes);

export interface MarketPhase {
  open: boolean;
  /** Today's close while open, else the most recent one. */
  close: Date;
  /** The next open when closed. */
  nextOpen: Date | null;
  /** "16:00" or "13:00". */
  closeClock: string;
}

/** Whether the regular session is open by the calendar, with the close and next open around it. */
export function marketPhase(now: Date): MarketPhase {
  const today = etDay(now);
  const minutes = etParts(now).minutes;
  const clockOf = (day: Date) => (marketDay(day).earlyClose ? '13:00' : '16:00');
  if (isTradingDay(today) && minutes >= OPEN_MIN && minutes < closeMinutes(today)) {
    return {
      open: true,
      close: instantOf(today, closeMinutes(today)),
      nextOpen: null,
      closeClock: clockOf(today),
    };
  }
  let last = today;
  if (!isTradingDay(last) || minutes < closeMinutes(last)) last = previousTradingDay(last);
  let next = today;
  if (!isTradingDay(next) || minutes >= OPEN_MIN) next = addDays(next, 1);
  while (!isTradingDay(next)) next = addDays(next, 1);
  return {
    open: false,
    close: instantOf(last, closeMinutes(last)),
    nextOpen: instantOf(next, OPEN_MIN),
    closeClock: clockOf(last),
  };
}

/** "tomorrow at 09:30 ET", "Monday at 09:30 ET" or "at 09:30 ET" for later today. */
export function opensWords(nextOpen: Date, now: Date): string {
  const gap = Math.round((etDay(nextOpen).getTime() - etDay(now).getTime()) / DAY);
  const when =
    gap === 0
      ? ''
      : gap === 1
        ? 'tomorrow '
        : `${new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: 'UTC' }).format(etDay(nextOpen))} `;
  return `${when}at 09:30 ET`;
}

/** A return given in percent, signed, e.g. "+2.30%". */
export const signedPct = (pct: number, dp = 2) => formatPct(pct / 100, { signed: true, dp });

/** Gain or loss text tone for a value in percent or dollars. */
export const toneText = (v: number | null | undefined) =>
  v === null || v === undefined
    ? 'text-fg-3'
    : pnlTone(v) === 'gain'
      ? 'text-gain'
      : pnlTone(v) === 'loss'
        ? 'text-loss'
        : 'text-fg-2';

/** The same tone as `toneText`, for SVG text. */
export const toneFill = (v: number | null | undefined) =>
  v === null || v === undefined
    ? 'fill-fg-3'
    : pnlTone(v) === 'gain'
      ? 'fill-gain'
      : pnlTone(v) === 'loss'
        ? 'fill-loss'
        : 'fill-fg-2';
