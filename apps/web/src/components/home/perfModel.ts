/** The account against SPY over a range: lines in percent, drawdown, rebalance days and session changes. */

import type { CurvePoint } from '@llamatrade/core/chart';

import {
  blendEquity,
  curveWindow,
  etDay,
  type EquitySeries,
  type Fill,
  type HomeRange,
  type HomeSession,
} from './homeModel';

const DAY = 86_400_000;

export type Line = (number | null)[];

export interface RebalanceDot {
  index: number;
  sessionId: string;
  fills: number;
}

export interface SessionChange {
  index: number;
  sessionId: string;
  at: Date;
  label: string;
}

export interface PerfWindow {
  dates: Date[];
  /** Account return in percent from the window's first value. */
  acc: number[];
  /** SPY's return in percent on the same dates; null without benchmark data. */
  spy: number[] | null;
  accDrawdown: number[];
  spyDrawdown: number[] | null;
  /** Index of the account's worst drawdown. */
  worst: number;
  fills: number;
  dots: RebalanceDot[];
  changes: SessionChange[];
  start: Date;
}

/** Each value's fall from the highest value before it, in percent. */
export function drawdownOf(pcts: readonly number[]): number[] {
  let peak = -Infinity;
  return pcts.map((v) => {
    peak = Math.max(peak, v);
    return ((1 + v / 100) / (1 + peak / 100) - 1) * 100;
  });
}

/** Index of the last date on or before `at`'s New York day, or -1 when it falls before the first. */
export function indexOnDay(dates: readonly Date[], at: Date): number {
  const day = etDay(at).getTime();
  let found = -1;
  for (let i = 0; i < dates.length; i++) {
    if (etDay(dates[i]).getTime() <= day) found = i;
    else break;
  }
  return found;
}

const pctFrom = (values: readonly number[]) => {
  const base = values[0];
  return values.map((v) => (base > 0 ? (v / base - 1) * 100 : 0));
};

export function perfWindow(
  series: EquitySeries,
  benchmark: readonly CurvePoint[],
  sessions: readonly HomeSession[],
  fills: readonly Fill[],
  range: HomeRange,
  end: Date
): PerfWindow | null {
  const win = curveWindow(series, benchmark, range, end);
  if (win.dates.length < 2) return null;
  const acc = pctFrom(win.values);
  const spy = win.bench ? pctFrom(win.bench) : null;
  const accDrawdown = drawdownOf(acc);
  let worst = 0;
  accDrawdown.forEach((v, i) => {
    if (v < accDrawdown[worst]) worst = i;
  });
  const first = win.dates[0].getTime();
  const inRange = (at: Date) => at.getTime() >= first - DAY / 2 && at.getTime() <= end.getTime();

  const inWindow = fills.filter((f) => inRange(f.at));
  const byDay = new Map<string, RebalanceDot>();
  for (const f of inWindow) {
    const index = indexOnDay(win.dates, f.at);
    if (index < 0) continue;
    const key = `${f.sessionId}:${index}`;
    const dot = byDay.get(key) ?? { index, sessionId: f.sessionId, fills: 0 };
    dot.fills += 1;
    byDay.set(key, dot);
  }

  const changes: SessionChange[] = [];
  for (const s of sessions) {
    const marks: [Date | null, string][] = [
      [s.startedAt, `${s.name} started`],
      [s.stoppedAt, `${s.name} stopped`],
    ];
    for (const [at, label] of marks) {
      if (!at || !inRange(at)) continue;
      const index = Math.max(0, indexOnDay(win.dates, at));
      changes.push({ index, sessionId: s.id, at, label });
    }
  }
  changes.sort((a, b) => a.at.getTime() - b.at.getTime());

  return {
    dates: win.dates,
    acc,
    spy,
    accDrawdown,
    spyDrawdown: spy ? drawdownOf(spy) : null,
    worst,
    fills: inWindow.length,
    dots: [...byDay.values()].sort((a, b) => a.index - b.index),
    changes,
    start: win.start,
  };
}

/** A set of equity points read on `dates`, in percent from its first value there; null before it starts. */
export function lineAlong(dates: readonly Date[], points: readonly CurvePoint[]): Line {
  const sorted = points
    .map((p) => ({ t: new Date(p.timestamp).getTime(), v: p.value }))
    .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v))
    .sort((a, b) => a.t - b.t);
  let j = -1;
  const raw = dates.map((d) => {
    while (j + 1 < sorted.length && sorted[j + 1].t <= d.getTime()) j++;
    return j >= 0 ? sorted[j].v : null;
  });
  const base = raw.find((v): v is number => v !== null && v > 0);
  return raw.map((v) => (v === null || base === undefined ? null : (v / base - 1) * 100));
}

/** Several sessions' equity added up, as points for `lineAlong`. */
export function blendedPoints(sessions: readonly HomeSession[]): CurvePoint[] {
  const s = blendEquity(sessions);
  return s.dates.map((d, i) => ({ timestamp: d.toISOString(), value: s.values[i] }));
}

export interface MonthLine {
  acc: number[];
  spy: number[] | null;
  /** Return over the month as a percent; null with under two points. */
  ret: number | null;
}

/** The past month of a set of equity points, with SPY on the same dates, for a sparkline. */
export function monthOf(
  points: readonly CurvePoint[],
  benchmark: readonly CurvePoint[],
  end: Date
): MonthLine {
  const values = points.map((p) => p.value);
  const series: EquitySeries = {
    dates: points.map((p) => new Date(p.timestamp)),
    values,
  };
  const win = curveWindow(series, benchmark, '1M', end);
  const stale = win.dates.length > 0 && win.dates[0].getTime() < end.getTime() - 45 * DAY;
  if (win.values.length < 2 || stale) return { acc: [], spy: null, ret: null };
  const acc = pctFrom(win.values);
  return {
    acc,
    spy: win.bench ? pctFrom(win.bench) : null,
    ret: acc[acc.length - 1],
  };
}
