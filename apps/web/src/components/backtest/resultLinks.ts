import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';

import {
  coversRange,
  curatedRanges,
  startsAtFloor,
  type CuratedRange,
} from '../../lib/backtestRanges';
import { longDate } from '../../lib/backtestView';
import { formatMoney, formatNumber } from '../../lib/format';

import { runMeta } from './runData';
import { runWhen } from './runLabels';

/** The latest completed run of the newest earlier version, to compare a result against. */
export function previousVersionRun(
  runs: readonly BacktestRun[],
  run: BacktestRun
): BacktestRun | null {
  const earlier = runs.filter(
    (r) =>
      r.strategyId === run.strategyId &&
      r.strategyVersion < run.strategyVersion &&
      r.status === BacktestStatus.COMPLETED
  );
  if (!earlier.length) return null;
  const top = Math.max(...earlier.map((r) => r.strategyVersion));
  const latest = (r: BacktestRun) => Number(r.completedAt?.seconds ?? r.createdAt?.seconds ?? 0n);
  return earlier.filter((r) => r.strategyVersion === top).sort((a, b) => latest(b) - latest(a))[0];
}

/** The first curated range this version hasn't run on, the run itself included; null if none. */
export function untestedRange(
  runs: readonly BacktestRun[],
  run: BacktestRun,
  today: Date
): CuratedRange | null {
  const mine = [run, ...runs].filter(
    (r) =>
      r.strategyId === run.strategyId &&
      r.strategyVersion === run.strategyVersion &&
      r.status === BacktestStatus.COMPLETED
  );
  const tested = (range: CuratedRange) =>
    mine.some((r) => {
      const { start, end } = runMeta(r);
      return start !== null && end !== null && coversRange(start, end, range);
    });
  return curatedRanges(today).find((range) => !tested(range)) ?? null;
}

/** "$1.00 per fill, 0.05% slippage" from the run's settings; empty when the run doesn't say. */
export function costsLabel(run: BacktestRun): string {
  const cfg = run.config;
  const parts: string[] = [];
  if (cfg?.commission) parts.push(`${formatMoney(toNumber(cfg.commission))} per fill`);
  if (cfg?.slippagePercent) {
    parts.push(`${formatNumber(toNumber(cfg.slippagePercent) * 100, { dp: 2 })}% slippage`);
  }
  return parts.join(', ');
}

/** "Jan 4, 2021 → Oct 30, 2026 · $25,000 · against SPY · finished Nov 16, 4:18 pm". */
export function resultMetaLine(run: BacktestRun, finished: boolean): string {
  const meta = runMeta(run);
  const range =
    meta.start && meta.end
      ? `${longDate(meta.start)} → ${longDate(meta.end)}${startsAtFloor(meta.start) ? ', the earliest Alpaca history' : ''}`
      : null;
  const costs = costsLabel(run);
  return [
    range,
    formatMoney(meta.capital, { dp: 0 }),
    meta.benchmark ? `against ${meta.benchmark}` : null,
    costs || null,
    finished && run.completedAt ? `finished ${runWhen(run)}` : null,
  ]
    .filter((x): x is string => Boolean(x))
    .join(' · ');
}
