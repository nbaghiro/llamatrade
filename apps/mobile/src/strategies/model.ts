/**
 * The Strategies tab and a strategy's page (list2 C, overview2 A): where each strategy stands,
 * and a running session against a backtest over the same dates. Plain data, so it runs under
 * `node --test`.
 */

export interface DatedValue {
  /** Epoch ms. */
  at: number;
  value: number;
}

const DAY_MS = 86_400_000;
const dayKey = (t: number) => Math.floor(t / DAY_MS);

/** The parts of a session a strategy's stage depends on. */
export interface SessionFact {
  strategyId: string;
  state: 'running' | 'waiting' | 'paused' | 'frozen' | 'stopped' | 'error';
  mode: 'live' | 'paper';
  startedAt: number | null;
  endedAt: number | null;
}

export type Stage =
  | { kind: 'running' }
  | { kind: 'stopped'; at: number | null; mode: 'live' | 'paper' }
  | { kind: 'neverRun' }
  | { kind: 'draft' };

/**
 * Running while any session is open; Stopped when a session ran it and ended; Never run when a
 * backtest finished but no session ever started; otherwise a draft.
 */
export function stageOf(strategyId: string, sessions: readonly SessionFact[], hasBacktest: boolean): Stage {
  const mine = sessions.filter((s) => s.strategyId === strategyId);
  if (mine.some((s) => s.state !== 'stopped')) return { kind: 'running' };
  if (mine.length) {
    const last = [...mine].sort((a, b) => (b.endedAt ?? b.startedAt ?? 0) - (a.endedAt ?? a.startedAt ?? 0))[0];
    return { kind: 'stopped', at: last.endedAt, mode: last.mode };
  }
  return hasBacktest ? { kind: 'neverRun' } : { kind: 'draft' };
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Nov 12", or "Nov 12, 2025" outside the given year. */
export function shortDate(t: number, thisYear?: number): string {
  const d = new Date(t);
  const base = `${MON[d.getUTCMonth()]} ${d.getUTCDate()}`;
  return thisYear !== undefined && d.getUTCFullYear() !== thisYear ? `${base}, ${d.getUTCFullYear()}` : base;
}

/** The line under a not-running strategy's name. */
export function stageLine(stage: Stage, thisYear?: number): string {
  switch (stage.kind) {
    case 'running':
      return 'Running';
    case 'stopped':
      return stage.at === null ? 'Stopped' : `Stopped ${shortDate(stage.at, thisYear)}`;
    case 'neverRun':
      return 'Never run';
    case 'draft':
      return 'Draft, not backtested';
  }
}

/** "3 running · 4 not running", leaving out a zero side. */
export function listSummary(running: number, notRunning: number): string {
  if (!running && !notRunning) return '';
  if (!running) return `${notRunning} not running`;
  if (!notRunning) return `${running} running`;
  return `${running} running · ${notRunning} not running`;
}

/** Stopped first (they have a record), then never run, then drafts; stable otherwise. */
export function sortNotRunning<T extends { stage: Stage }>(items: readonly T[]): T[] {
  const rank = (s: Stage) => (s.kind === 'stopped' ? 0 : s.kind === 'neverRun' ? 1 : 2);
  return [...items].sort((a, b) => rank(a.stage) - rank(b.stage));
}

/** The last value of each UTC day, in date order. */
export function dailyCloses(points: readonly DatedValue[]): DatedValue[] {
  const byDay = new Map<number, DatedValue>();
  for (const p of [...points].sort((a, b) => a.at - b.at)) byDay.set(dayKey(p.at), p);
  return [...byDay.values()];
}

/** The series value on or before `at`, or null when the series starts later. */
export function valueAt(series: readonly DatedValue[], at: number): number | null {
  let lo = 0;
  let hi = series.length - 1;
  let found: number | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (series[mid].at <= at) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found === null ? null : series[found].value;
}

const MIN_OVERLAP_DAYS = 5;

export interface SameDates {
  dates: number[];
  /** Cumulative return of each from the first shared day, as fractions. */
  session: number[];
  backtest: number[];
  /** The backtest's equity rebased to the session's first value, for one axis. */
  backtestScaled: number[];
  sessionValues: number[];
}

/** The session's daily closes lined up with the backtest on each day both cover; null under five days. */
export function compareSameDates(sessionPoints: readonly DatedValue[], backtestPoints: readonly DatedValue[]): SameDates | null {
  const days = dailyCloses(sessionPoints).filter((p) => p.value > 0);
  const bt = dailyCloses(backtestPoints).filter((p) => p.value > 0);
  if (!days.length || !bt.length) return null;
  const btEnd = dayKey(bt[bt.length - 1].at);
  const shared = days
    .filter((p) => dayKey(p.at) <= btEnd)
    .map((p) => ({ at: p.at, s: p.value, b: valueAt(bt, p.at) }))
    .filter((p): p is { at: number; s: number; b: number } => p.b !== null);
  if (shared.length < MIN_OVERLAP_DAYS) return null;
  const s0 = shared[0].s;
  const b0 = shared[0].b;
  return {
    dates: shared.map((x) => x.at),
    session: shared.map((x) => x.s / s0 - 1),
    backtest: shared.map((x) => x.b / b0 - 1),
    backtestScaled: shared.map((x) => (x.b / b0) * s0),
    sessionValues: shared.map((x) => x.s),
  };
}

export interface RunMeta {
  id: string;
  completed: boolean;
  start: number | null;
  end: number | null;
  version: number;
  createdAt: number;
}

/**
 * The completed run that best covers a session's dates: the session's version first, then the
 * most days of overlap, then the newest. Null when none overlaps five days.
 */
export function pickSameDatesRun(runs: readonly RunMeta[], from: number, to: number, version: number | null): RunMeta | null {
  const scored = runs
    .filter((r) => r.completed && r.start !== null && r.end !== null)
    .map((r) => ({ r, overlap: (Math.min(r.end ?? 0, to) - Math.max(r.start ?? 0, from)) / DAY_MS }))
    .filter((x) => x.overlap >= MIN_OVERLAP_DAYS);
  scored.sort((a, b) => {
    const av = version !== null && a.r.version === version ? 1 : 0;
    const bv = version !== null && b.r.version === version ? 1 : 0;
    if (av !== bv) return bv - av;
    if (Math.abs(a.overlap - b.overlap) >= 1) return b.overlap - a.overlap;
    return b.r.createdAt - a.r.createdAt;
  });
  return scored[0]?.r ?? null;
}

/** Session minus backtest in percentage points, signed for display: "−0.5 pts". */
export function gapLabel(sessionPct: number, backtestPct: number): string {
  const gap = sessionPct - backtestPct;
  const abs = Math.abs(gap).toFixed(1);
  if (abs === '0.0') return '0.0 pts';
  return `${gap < 0 ? '−' : '+'}${abs} pts`;
}
