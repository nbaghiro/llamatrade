import { num, toDate } from '@llamatrade/core/format';
import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useMemo } from 'react';

import {
  compareSameDates,
  dailyCloses,
  runPoints,
  type DatedValue,
  type SameDates,
} from '../sameDates';

import type { StrategySession } from './useStrategySession';

const dayKey = (d: Date) => d.toISOString().slice(0, 10);

/** The run's benchmark curve as dated values. */
export function benchmarkPoints(run: BacktestRun | null | undefined): DatedValue[] {
  const out: DatedValue[] = [];
  for (const p of run?.results?.benchmarkEquityCurve ?? []) {
    const at = toDate(p.timestamp);
    const value = num(p.equity);
    if (at && value > 0) out.push({ at, value });
  }
  return out;
}

/** A same-dates series placed on the session's days; days it doesn't cover are NaN. */
export function alignToDays(
  daily: readonly DatedValue[],
  same: SameDates | null
): number[] | undefined {
  if (!same) return undefined;
  const byDay = new Map(same.dates.map((d, i) => [dayKey(d), same.backtestScaled[i]]));
  return daily.map((d) => byDay.get(dayKey(d.at)) ?? NaN);
}

/**
 * The session's daily closes, with the same-dates backtest scaled onto them over the days it
 * covers, and the benchmark's return over the same dates.
 */
export function useSessionSeries(ss: StrategySession, sameRun: BacktestRun | null | undefined) {
  return useMemo(() => {
    const points = ss.curve.status === 'ready' ? ss.curve.points : [];
    const daily = dailyCloses(points);
    const same: SameDates | null = sameRun ? compareSameDates(points, runPoints(sameRun)) : null;
    const benchSame: SameDates | null = sameRun
      ? compareSameDates(points, benchmarkPoints(sameRun))
      : null;
    return {
      daily,
      same,
      bench: alignToDays(daily, same),
      benchSame,
      benchSymbol: sameRun?.results?.benchmarkSymbol ?? '',
    };
  }, [ss.curve, sameRun]);
}
