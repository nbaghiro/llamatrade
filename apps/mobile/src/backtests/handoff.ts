import { num, toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { DEFAULT_BACKTEST_COSTS, useBacktestStore } from '@llamatrade/core/stores/backtest';

import { loadRunsFor } from './data';
import { isoDay } from './model';

/** The strategy's newest completed run, whose settings a new run can copy. */
export async function lastSettings(strategyId: string): Promise<BacktestRun | null> {
  const runs = await loadRunsFor(strategyId, true);
  const done = runs
    .filter((r) => r.status === BacktestStatus.COMPLETED && r.config)
    .sort((a, b) => Number(b.createdAt?.seconds ?? 0) - Number(a.createdAt?.seconds ?? 0));
  return done[0] ?? null;
}

/**
 * Starts a run of `version` with the same range, capital, costs and benchmark as the last
 * completed run (builder/handoff2 A). Null when there's no earlier run to copy or the start fails.
 */
export async function backtestLikeLast(strategyId: string, version: number): Promise<string | null> {
  const last = await lastSettings(strategyId);
  const cfg = last?.config;
  const start = toDate(cfg?.startDate);
  const end = toDate(cfg?.endDate);
  if (!cfg || !start || !end) return null;
  const store = useBacktestStore.getState();
  store.setConfig({
    strategyId,
    strategyVersion: version,
    startDate: isoDay(start.getTime()),
    endDate: isoDay(end.getTime()),
    initialCapital: num(cfg.initialCapital) || 25000,
    symbols: [],
    commission: cfg.commission?.value ? num(cfg.commission) : DEFAULT_BACKTEST_COSTS.commission,
    slippage: cfg.slippagePercent?.value ? num(cfg.slippagePercent) : DEFAULT_BACKTEST_COSTS.slippage,
    timeframe: cfg.timeframe || '1D',
    benchmarkSymbol: cfg.benchmarkSymbol ?? 'SPY',
  });
  return store.runBacktest();
}
