/**
 * Backtest view-model types and display labels for UI surfaces.
 *
 * `BacktestRunView` is a display projection of the proto `BacktestRun` used by the
 * strategy gallery; the label maps turn proto enums into UI words.
 */

import { BacktestStatus } from '@llamatrade/core/proto/backtest_pb';

export interface BacktestRunView {
  /** Backtest run id */
  id: string;
  /** Owning strategy id */
  strategyId: string;
  /** Resolved strategy name (from the strategies list) */
  strategyName: string;
  /** Total return as a percentage, e.g. 12.4 = +12.4% */
  returnPct: number;
  /** Sharpe ratio (unitless) */
  sharpeRatio: number;
  /** Max drawdown as a percentage, e.g. -8.2 = -8.2% */
  maxDrawdown: number;
  /** When the run completed (falls back to created time) */
  runDate: Date;
  /** Absolute equity values over time, for the sparkline */
  equityCurve: number[];
  /** Absolute benchmark equity values over time, for the sparkline */
  benchmarkCurve: number[];
}

export const BACKTEST_STATUS_LABEL: Record<BacktestStatus, string> = {
  [BacktestStatus.UNSPECIFIED]: 'Unknown',
  [BacktestStatus.PENDING]: 'Queued',
  [BacktestStatus.RUNNING]: 'Running',
  [BacktestStatus.COMPLETED]: 'Completed',
  [BacktestStatus.FAILED]: 'Failed',
  [BacktestStatus.CANCELLED]: 'Cancelled',
};

/** Rebalance frequency as written in a sentence, from Strategy.rebalance. */
export function rebalanceWord(rebalance: string | undefined): string {
  const v = (rebalance ?? '').trim().toLowerCase();
  return v ? v : 'on its schedule';
}

/** "Monthly" from "monthly"; empty input stays empty. */
export function rebalanceLabel(rebalance: string | undefined): string {
  const v = (rebalance ?? '').trim();
  return v ? v[0].toUpperCase() + v.slice(1).toLowerCase() : '';
}
