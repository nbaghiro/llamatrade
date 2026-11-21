/**
 * Home and Portfolio as plain data: session rows, the paper and live split, the blended curve,
 * lanes, the next rebalance per session, the one timeline and what needs attention. Pure, so it
 * runs under `node --test`; `data.ts` maps the stores onto these shapes.
 */

export type Mode = 'live' | 'paper';
export type RowState = 'running' | 'waiting' | 'paused' | 'frozen' | 'stopped' | 'error';
export type Cadence = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annually';

export interface Point {
  /** Epoch ms. */
  t: number;
  v: number;
}

export interface SessionIn {
  /** The execution id, as the portfolio service keys performance. */
  id: string;
  strategyId: string;
  /** The trading session id, when the blotter has one for this execution. */
  sessionId: string | null;
  /** The ledger sleeve id, when known. */
  sleeveId: string | null;
  name: string;
  mode: Mode;
  state: RowState;
  value: number | null;
  /** Percent, as the portfolio service reports it (0.62 is 0.62%). */
  dayReturnPct: number | null;
  allocated: number;
  equity: readonly Point[];
  startedAt: number | null;
  endedAt: number | null;
  /** The strategy's rebalance setting, as stored ("monthly"); empty when unknown. */
  rebalance: string;
}

export interface FillIn {
  id: string;
  t: number;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  price: number;
  strategyId: string;
  sessionId: string;
}

const DAY = 86_400_000;

/** "Recession Radar (paper)" as "Recession Radar"; the mode is shown beside it. */
export function displayName(name: string): string {
  return name.replace(/\s*\((paper|live)\)\s*$/i, '').trim() || name;
}

/** The dollar move behind a one-day percent return on today's value. */
export function todayMove(value: number | null, pct: number | null): number | null {
  if (value === null || pct === null || !Number.isFinite(value) || !Number.isFinite(pct)) return null;
  const denom = 1 + pct / 100;
  if (denom <= 0) return null;
  return value - value / denom;
}

/** A move small enough (under 0.25%) to stay in ink rather than gain or loss. */
export function isQuiet(pct: number | null): boolean {
  return pct === null || !Number.isFinite(pct) || Math.abs(pct) < 0.25;
}

export function cadenceOf(rebalance: string): Cadence | null {
  const r = rebalance.trim().toLowerCase();
  if (r === 'daily' || r === 'weekly' || r === 'monthly' || r === 'quarterly') return r;
  if (r === 'annually' || r === 'yearly' || r === 'annual') return 'annually';
  return null;
}

/* ------------------------------------------------------------ sessions -- */

export interface SessionRow extends SessionIn {
  title: string;
  today: number | null;
  spark: number[];
}

const STATE_ORDER: Record<RowState, number> = { frozen: 0, error: 0, running: 1, waiting: 1, paused: 2, stopped: 3 };

/** Rows for a list: attention first, then running by value, stopped last. */
export function sessionRows(sessions: readonly SessionIn[], sparkPoints = 40): SessionRow[] {
  return sessions
    .map((s) => ({
      ...s,
      title: displayName(s.name),
      today: s.state === 'stopped' ? null : todayMove(s.value, s.dayReturnPct),
      spark: s.equity.slice(-sparkPoints).map((p) => p.v),
    }))
    .sort((a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state] || (b.value ?? 0) - (a.value ?? 0));
}

export interface AccountSplit {
  live: number;
  paper: number;
  /** Live sessions and live cash are known; false means the live figure is incomplete. */
  liveKnown: boolean;
  total: number;
}

/**
 * Live and paper money: each account's session values plus its unallocated cash. A null cash
 * figure means it couldn't be read; the sessions still count.
 */
export function accountSplit(sessions: readonly SessionIn[], paperCash: number | null, liveCash: number | null): AccountSplit {
  let live = 0;
  let paper = 0;
  let hasLive = false;
  for (const s of sessions) {
    if (s.state === 'stopped' && (s.value ?? 0) === 0) continue;
    const v = s.value ?? 0;
    if (s.mode === 'live') {
      live += v;
      hasLive = true;
    } else paper += v;
  }
  if (paperCash !== null && Number.isFinite(paperCash)) paper += paperCash;
  if (liveCash !== null && Number.isFinite(liveCash)) {
    live += liveCash;
    hasLive = true;
  }
  return { live, paper, liveKnown: !hasLive || liveCash !== null, total: live + paper };
}

/**
 * Sum of session equity curves on every timestamp any of them has, each carrying its last
 * value forward. Before its first point a series counts its baseline (e.g. the capital it was
 * given), so a session starting doesn't read as a jump in performance; without one it counts 0.
 */
export function blendEquity(series: ReadonlyArray<readonly Point[]>, baselines?: readonly number[]): Point[] {
  const sorted = series.map((s) => s.filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v)).sort((a, b) => a.t - b.t));
  const times = [...new Set(sorted.flatMap((s) => s.map((p) => p.t)))].sort((a, b) => a - b);
  const idx = sorted.map(() => -1);
  return times.map((t) => {
    let sum = 0;
    sorted.forEach((s, i) => {
      while (idx[i] + 1 < s.length && s[idx[i] + 1].t <= t) idx[i]++;
      if (idx[i] >= 0) sum += s[idx[i]].v;
      else if (s.length) sum += baselines?.[i] ?? 0;
    });
    return { t, v: sum };
  });
}

export type Period = '1M' | '3M' | '1Y' | 'All';
export const PERIODS: readonly Period[] = ['1M', '3M', '1Y', 'All'];

/** Start of a period ending at `now`; null for All. */
export function periodStart(period: Period, now: number): number | null {
  switch (period) {
    case '1M':
      return now - 31 * DAY;
    case '3M':
      return now - 92 * DAY;
    case '1Y':
      return now - 366 * DAY;
    default:
      return null;
  }
}

/* ------------------------------------------------------------ schedule -- */

function dayStart(t: number): Date {
  const d = new Date(t);
  d.setHours(0, 0, 0, 0);
  return d;
}

function isWeekday(d: Date): boolean {
  const w = d.getDay();
  return w !== 0 && w !== 6;
}

function isoWeek(d: Date): string {
  const x = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = x.getUTCDay() || 7;
  x.setUTCDate(x.getUTCDate() + 4 - day);
  const y0 = new Date(Date.UTC(x.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((x.getTime() - y0.getTime()) / DAY + 1) / 7);
  return `${x.getUTCFullYear()}-${week}`;
}

/** The runtime's rule (libs/runtime rebalance.py): does `d` start a new period after `last`? */
export function startsNewPeriod(d: Date, last: Date | null, cadence: Cadence): boolean {
  if (!last) return true;
  if (d.toDateString() === last.toDateString()) return false;
  switch (cadence) {
    case 'daily':
      return d.getTime() > last.getTime();
    case 'weekly':
      return isoWeek(d) !== isoWeek(last);
    case 'monthly':
      return d.getMonth() !== last.getMonth() || d.getFullYear() !== last.getFullYear();
    case 'quarterly':
      return Math.floor(d.getMonth() / 3) !== Math.floor(last.getMonth() / 3) || d.getFullYear() !== last.getFullYear();
    case 'annually':
      return d.getFullYear() !== last.getFullYear();
  }
}

/**
 * The next weekday the runtime would rebalance, starting today, given the last rebalance.
 * Weekends are skipped; market holidays aren't known to the app, so a date can move by a day.
 */
export function nextRebalance(cadence: Cadence, last: number | null, now: number, horizonDays = 400): number | null {
  const lastDay = last === null ? null : dayStart(last);
  const d = dayStart(now);
  for (let i = 0; i < horizonDays; i++) {
    if (isWeekday(d) && startsNewPeriod(d, lastDay, cadence)) return d.getTime();
    d.setDate(d.getDate() + 1);
  }
  return null;
}

/** Last day a session filled an order, standing in for its last rebalance. */
export function lastFillDay(fills: readonly FillIn[], session: Pick<SessionIn, 'strategyId' | 'sessionId'>): number | null {
  let best: number | null = null;
  for (const f of fills) {
    const mine = session.sessionId ? f.sessionId === session.sessionId : f.strategyId === session.strategyId;
    if (mine && (best === null || f.t > best)) best = f.t;
  }
  return best;
}

export interface Planned {
  sessionId: string;
  name: string;
  mode: Mode;
  cadence: Cadence;
  /** Start of the day it is planned for. */
  day: number;
}

/** Planned rebalances for running sessions within `days` of now, soonest first. */
export function plannedRebalances(
  sessions: readonly SessionIn[],
  fills: readonly FillIn[],
  now: number,
  days = 14,
  perSession = 2,
): Planned[] {
  const out: Planned[] = [];
  const limit = dayStart(now).getTime() + days * DAY;
  for (const s of sessions) {
    if (s.state === 'stopped' || s.state === 'paused') continue;
    const cadence = cadenceOf(s.rebalance);
    if (!cadence) continue;
    let last = lastFillDay(fills, s) ?? s.startedAt;
    let from = now;
    for (let k = 0; k < perSession; k++) {
      const day = nextRebalance(cadence, last, from);
      if (day === null || day > limit) break;
      out.push({ sessionId: s.id, name: displayName(s.name), mode: s.mode, cadence, day });
      last = day;
      from = day + DAY;
    }
  }
  return out.sort((a, b) => a.day - b.day || a.name.localeCompare(b.name));
}

/* ------------------------------------------------------------ timeline -- */

export type TimelineEntry =
  | { kind: 'fill'; key: string; t: number; fill: FillIn; session: string; mode: Mode | null }
  | { kind: 'now'; key: 'now'; t: number }
  | { kind: 'planned'; key: string; t: number; planned: Planned };

/** Today's fills, a Now row, then planned rebalances: past and next in one list (activity B). */
export function timeline(
  fills: readonly FillIn[],
  planned: readonly Planned[],
  sessions: readonly SessionIn[],
  now: number,
): TimelineEntry[] {
  const today = dayStart(now).getTime();
  const byStrategy = new Map(sessions.map((s) => [s.strategyId, s]));
  const bySession = new Map(sessions.filter((s) => s.sessionId).map((s) => [s.sessionId ?? '', s]));
  const past: TimelineEntry[] = fills
    .filter((f) => f.t >= today && f.t <= now)
    .sort((a, b) => a.t - b.t)
    .map((f) => {
      const s = bySession.get(f.sessionId) ?? byStrategy.get(f.strategyId);
      return { kind: 'fill', key: f.id, t: f.t, fill: f, session: s ? displayName(s.name) : '', mode: s?.mode ?? null };
    });
  const next: TimelineEntry[] = planned
    .filter((p) => p.day + DAY > now)
    .map((p) => ({ kind: 'planned', key: `${p.sessionId}-${p.day}`, t: p.day, planned: p }));
  return [...past, { kind: 'now', key: 'now', t: now }, ...next];
}

/* --------------------------------------------------------------- lanes -- */

export interface LaneIn {
  key: string;
  name: string;
  mode: Mode;
  state: RowState;
  start: number | undefined;
  end: number | undefined;
  /** Fills grouped by day: start of day and count. */
  fillDays: { day: number; count: number }[];
  planned: number[];
}

/** Fills per session grouped by day, with planned days, for the lanes under the curve. */
export function sessionLanes(sessions: readonly SessionIn[], fills: readonly FillIn[], planned: readonly Planned[]): LaneIn[] {
  return sessionRows(sessions)
    .sort((a, b) => (a.mode === b.mode ? 0 : a.mode === 'live' ? -1 : 1))
    .map((s) => {
      const counts = new Map<number, number>();
      for (const f of fills) {
        const mine = s.sessionId ? f.sessionId === s.sessionId : f.strategyId === s.strategyId;
        if (!mine) continue;
        const day = dayStart(f.t).getTime();
        counts.set(day, (counts.get(day) ?? 0) + 1);
      }
      const lastPoint = s.equity.length ? s.equity[s.equity.length - 1].t : undefined;
      return {
        key: s.id,
        name: s.title,
        mode: s.mode,
        state: s.state,
        start: s.startedAt ?? (s.equity.length ? s.equity[0].t : undefined),
        end: s.state === 'stopped' ? (s.endedAt ?? lastPoint) : undefined,
        fillDays: [...counts.entries()].sort((a, b) => a[0] - b[0]).map(([day, count]) => ({ day, count })),
        planned: planned.filter((p) => p.sessionId === s.id).map((p) => p.day),
      };
    });
}

/** Fills on one day, optionally for one session; newest last. */
export function fillsOn(fills: readonly FillIn[], day: number, session?: Pick<SessionIn, 'strategyId' | 'sessionId'>): FillIn[] {
  const start = dayStart(day).getTime();
  return fills
    .filter((f) => f.t >= start && f.t < start + DAY)
    .filter((f) => !session || (session.sessionId ? f.sessionId === session.sessionId : f.strategyId === session.strategyId))
    .sort((a, b) => a.t - b.t);
}

/* ----------------------------------------------------------- attention -- */

export interface FrozenIn {
  id: string;
  name: string;
  executionId: string;
}

export interface RejectedIn {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  message: string;
  t: number | null;
  sessionId: string;
}

export type Attention =
  | { kind: 'frozen'; key: string; title: string; detail: string; executionId: string; sleeveId: string }
  | { kind: 'rejected'; key: string; title: string; detail: string; orderId: string; t: number | null };

/** What needs a decision, frozen sleeves first, newest rejected order next (attention2 C). */
export function attentionItems(frozen: readonly FrozenIn[] | null, rejected: readonly RejectedIn[] | null): Attention[] {
  const f: Attention[] = (frozen ?? []).map((x) => ({
    kind: 'frozen',
    key: `f-${x.id}`,
    title: `${displayName(x.name)} is frozen.`,
    detail: "Alpaca and the ledger disagree about its holdings, so it won't trade until that's resolved.",
    executionId: x.executionId,
    sleeveId: x.id,
  }));
  const r: Attention[] = [...(rejected ?? [])]
    .sort((a, b) => (b.t ?? 0) - (a.t ?? 0))
    .map((x) => ({
      kind: 'rejected',
      key: `r-${x.id}`,
      title: `Order rejected: ${x.side === 'buy' ? 'buy' : 'sell'} ${formatQty(x.quantity)} ${x.symbol}.`,
      detail: x.message || 'The order was rejected before it reached Alpaca.',
      orderId: x.id,
      t: x.t,
    }));
  return [...f, ...r];
}

function formatQty(q: number): string {
  return Number.isInteger(q) ? String(q) : q.toFixed(2);
}

/* ---------------------------------------------------------- page state -- */

export type HomeMode = 'loading' | 'first' | 'open' | 'closed';

/** First visit when the account has no strategies and no sessions; closed outside market hours. */
export function homeMode(input: {
  loaded: boolean;
  strategyCount: number | null;
  sessionCount: number;
  marketOpen: boolean | null;
}): HomeMode {
  if (!input.loaded) return 'loading';
  if (input.strategyCount === 0 && input.sessionCount === 0) return 'first';
  return input.marketOpen === false ? 'closed' : 'open';
}

/** What each running session added today, largest first, for the after-close recap (quiet A). */
export function closedRecap(sessions: readonly SessionIn[]): { id: string; name: string; mode: Mode; today: number }[] {
  return sessionRows(sessions)
    .filter((s) => s.state !== 'stopped' && s.today !== null)
    .map((s) => ({ id: s.id, name: s.title, mode: s.mode, today: s.today ?? 0 }))
    .sort((a, b) => b.today - a.today);
}

/** Cumulative money added by date from deposits and withdrawals, for the dashed step line. */
export function moneyAdded(rows: readonly { t: number; signed: number }[]): Point[] {
  let sum = 0;
  return [...rows]
    .filter((r) => Number.isFinite(r.t) && Number.isFinite(r.signed) && r.signed !== 0)
    .sort((a, b) => a.t - b.t)
    .map((r) => {
      sum += r.signed;
      return { t: r.t, v: sum };
    });
}
