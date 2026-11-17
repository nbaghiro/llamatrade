/** A paper session against a backtest over the same dates (overview2 A, performance2 A). */

import { num, toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';

export interface DatedValue {
  at: Date;
  value: number;
}

const DAY_MS = 86_400_000;
const dayKey = (d: Date) => Math.floor(d.getTime() / DAY_MS);

/** The last value of each UTC day, in date order. */
export function dailyCloses(points: readonly DatedValue[]): DatedValue[] {
  const byDay = new Map<number, DatedValue>();
  for (const p of [...points].sort((a, b) => a.at.getTime() - b.at.getTime())) {
    byDay.set(dayKey(p.at), p);
  }
  return [...byDay.values()];
}

/** The series value on or before `at`, or null when the series starts later. */
export function valueAt(series: readonly DatedValue[], at: Date): number | null {
  let lo = 0;
  let hi = series.length - 1;
  let found: number | null = null;
  const t = at.getTime();
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (series[mid].at.getTime() <= t) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found === null ? null : series[found].value;
}

/** Days with at least one point in each series that two series share. */
const MIN_OVERLAP_DAYS = 5;

export interface SameDates {
  dates: Date[];
  /** Cumulative return of each, as a fraction from the first shared day. */
  paper: number[];
  backtest: number[];
  /** Paper minus backtest, in percentage points. */
  gap: number[];
  /** The backtest's equity rebased to the paper's starting value, for drawing on one axis. */
  backtestScaled: number[];
  start: Date;
  end: Date;
}

/**
 * Lines the paper session's daily closes up with the backtest on each paper day inside the
 * backtest's range. Null when they share fewer than five days.
 */
export function compareSameDates(
  paperPoints: readonly DatedValue[],
  backtestPoints: readonly DatedValue[]
): SameDates | null {
  const paperDays = dailyCloses(paperPoints).filter((p) => p.value > 0);
  const bt = dailyCloses(backtestPoints).filter((p) => p.value > 0);
  if (!paperDays.length || !bt.length) return null;
  const btEnd = dayKey(bt[bt.length - 1].at);
  const shared = paperDays
    .filter((p) => dayKey(p.at) <= btEnd)
    .map((p) => ({ at: p.at, paper: p.value, backtest: valueAt(bt, p.at) }))
    .filter((p): p is { at: Date; paper: number; backtest: number } => p.backtest !== null);
  if (shared.length < MIN_OVERLAP_DAYS) return null;
  const p0 = shared[0].paper;
  const b0 = shared[0].backtest;
  const paper = shared.map((s) => s.paper / p0 - 1);
  const backtest = shared.map((s) => s.backtest / b0 - 1);
  return {
    dates: shared.map((s) => s.at),
    paper,
    backtest,
    gap: paper.map((p, i) => (p - backtest[i]) * 100),
    backtestScaled: shared.map((s) => (s.backtest / b0) * p0),
    start: shared[0].at,
    end: shared[shared.length - 1].at,
  };
}

export interface GapStep {
  at: Date;
  /** Change in the gap over that day, in percentage points. */
  change: number;
}

/**
 * How much the gap moved on each day with fills, and what moved between them. A fill day counts
 * on the first compared day on or after it; fill days outside the compared dates are left out.
 */
export function gapSteps(
  same: Pick<SameDates, 'dates' | 'gap'>,
  fillDays: readonly Date[]
): { steps: GapStep[]; between: number; total: number } {
  const keys = same.dates.map(dayKey);
  const used = new Set<number>();
  const steps: GapStep[] = [];
  for (const d of [...fillDays].sort((a, b) => a.getTime() - b.getTime())) {
    const key = dayKey(d);
    if (!keys.length || key < keys[0]) continue;
    const i = keys.findIndex((k) => k >= key);
    if (i < 0 || used.has(i)) continue;
    used.add(i);
    const before = i === 0 ? 0 : same.gap[i - 1];
    steps.push({ at: same.dates[i], change: same.gap[i] - before });
  }
  const total = same.gap.length ? same.gap[same.gap.length - 1] : 0;
  const stepped = steps.reduce((s, x) => s + x.change, 0);
  return { steps, between: total - stepped, total };
}

/** A run's equity curve as dated values. */
export function runPoints(run: BacktestRun | null | undefined): DatedValue[] {
  const out: DatedValue[] = [];
  for (const p of run?.results?.equityCurve ?? []) {
    const at = toDate(p.timestamp);
    const value = num(p.equity);
    if (at && value > 0) out.push({ at, value });
  }
  return out;
}

const runRange = (r: BacktestRun) => ({
  start: toDate(r.config?.startDate),
  end: toDate(r.config?.endDate),
});

/**
 * The completed run that best covers a session's dates: the version the session runs first,
 * then the most days of overlap, then the newest. Null when none reaches the session's start.
 */
export function pickSameDatesRun(
  runs: readonly BacktestRun[],
  sessionStart: Date,
  sessionEnd: Date,
  version: number | null
): BacktestRun | null {
  const scored = runs
    .filter((r) => r.status === BacktestStatus.COMPLETED)
    .map((r) => {
      const { start, end } = runRange(r);
      if (!start || !end) return null;
      const from = Math.max(start.getTime(), sessionStart.getTime());
      const to = Math.min(end.getTime(), sessionEnd.getTime());
      const overlap = (to - from) / DAY_MS;
      return overlap >= MIN_OVERLAP_DAYS ? { r, overlap } : null;
    })
    .filter((x): x is { r: BacktestRun; overlap: number } => x !== null);
  scored.sort((a, b) => {
    const av = version !== null && a.r.strategyVersion === version ? 1 : 0;
    const bv = version !== null && b.r.strategyVersion === version ? 1 : 0;
    if (av !== bv) return bv - av;
    if (Math.abs(a.overlap - b.overlap) >= 1) return b.overlap - a.overlap;
    return Number(b.r.createdAt?.seconds ?? 0) - Number(a.r.createdAt?.seconds ?? 0);
  });
  return scored[0]?.r ?? null;
}

/** The largest fall from a running peak, as a negative fraction; 0 for a series that never fell. */
export function maxDrawdown(values: readonly number[]): number {
  let peak = -Infinity;
  let worst = 0;
  for (const v of values) {
    if (v > peak) peak = v;
    if (peak > 0) worst = Math.min(worst, v / peak - 1);
  }
  return worst;
}
