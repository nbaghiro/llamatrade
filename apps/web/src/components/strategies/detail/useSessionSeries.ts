import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useMemo } from 'react';

import { compareSameDates, dailyCloses, runPoints, type SameDates } from '../sameDates';

import type { StrategySession } from './useStrategySession';

/** The session's daily closes, with the same-dates backtest scaled onto them when it covers every day. */
export function useSessionSeries(ss: StrategySession, sameRun: BacktestRun | null | undefined) {
  return useMemo(() => {
    const points = ss.curve.status === 'ready' ? ss.curve.points : [];
    const daily = dailyCloses(points);
    const same: SameDates | null = sameRun ? compareSameDates(points, runPoints(sameRun)) : null;
    const covers = same !== null && same.dates.length === daily.length;
    return { daily, same, bench: covers ? same.backtestScaled : undefined };
  }, [ss.curve, sameRun]);
}
