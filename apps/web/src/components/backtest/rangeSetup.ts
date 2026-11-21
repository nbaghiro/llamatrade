import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate } from '@llamatrade/core/stores/backtest';

import { coversRange, type CuratedRange } from '../../lib/backtestRanges';

import { runMeta } from './runData';

const DAY_MS = 86_400_000;

/**
 * Seconds a run over `days` calendar days should take, from the median pace of past completed
 * runs; null without at least one timed run.
 */
export function estimateSeconds(runs: readonly BacktestRun[], days: number): number | null {
  const paces = runs
    .filter((r) => r.status === BacktestStatus.COMPLETED)
    .map((r) => {
      const a = toDate(r.startedAt);
      const b = toDate(r.completedAt);
      const { start, end } = runMeta(r);
      if (!a || !b || !start || !end) return null;
      const span = (end.getTime() - start.getTime()) / DAY_MS;
      const secs = (b.getTime() - a.getTime()) / 1000;
      return span > 0 && secs > 0 ? secs / span : null;
    })
    .filter((x): x is number => x !== null)
    .sort((x, y) => x - y);
  if (!paces.length) return null;
  const mid = Math.floor(paces.length / 2);
  const pace = paces.length % 2 ? paces[mid] : (paces[mid - 1] + paces[mid]) / 2;
  return pace * Math.max(0, days);
}

/** "About 20 seconds", "About 3 minutes". */
export function durationLabel(seconds: number): string {
  if (seconds < 90) return `About ${Math.max(5, Math.round(seconds / 5) * 5)} seconds`;
  return `About ${Math.round(seconds / 60)} minutes`;
}

/** The newest completed run of the strategy's latest tested version over each curated range. */
export function testedOn(
  runs: readonly BacktestRun[],
  strategyId: string,
  ranges: readonly CuratedRange[]
): { range: CuratedRange; run: BacktestRun | null }[] {
  const mine = runs
    .filter((r) => r.strategyId === strategyId && r.status === BacktestStatus.COMPLETED)
    .sort(
      (a, b) =>
        b.strategyVersion - a.strategyVersion ||
        Number(b.completedAt?.seconds ?? 0n) - Number(a.completedAt?.seconds ?? 0n)
    );
  return ranges.map((range) => ({
    range,
    run:
      mine.find((r) => {
        const { start, end } = runMeta(r);
        return start !== null && end !== null && coversRange(start, end, range);
      }) ?? null,
  }));
}
