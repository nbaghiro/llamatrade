/**
 * Backtest view-model types for UI surfaces (gallery cards, history).
 *
 * These are lightweight, display-oriented projections of the proto
 * `BacktestRun`/`BacktestResults` messages. They exist so components can render
 * without depending on proto wire types directly.
 */

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
