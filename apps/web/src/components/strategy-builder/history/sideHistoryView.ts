import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import type { StrategyTree } from '@llamatrade/core/strategy/types';

import { alignTo } from '../../../lib/backtestView';
import { toCurve, toTradeInputs } from '../../backtest/runData';
import type { RebalanceEvery } from '../blocks/conditionHistory';

import {
  conditionSides,
  scheduledDates,
  sideCounts,
  sideSpans,
  sidesAtDates,
  sidesAtRebalances,
  type ConditionSides,
  type SideCounts,
  type SideSpan,
} from './sides';

export interface SideHistoryView {
  dates: readonly Date[];
  values: readonly number[];
  benchmark: number[] | undefined;
  start: Date;
  end: Date;
  sides: ConditionSides | null;
  spans: SideSpan[];
  /** Scheduled rebalances, or days with orders when the schedule is daily. */
  rebalanceDates: Date[];
  /** True when the dates are the schedule's, false when they are days with orders. */
  scheduled: boolean;
  counts: SideCounts;
  totalReturn: number | null;
  benchReturn: number | null;
  maxDrawdown: number | null;
  sharpe: number | null;
  benchSymbol: string;
}

/** The last backtest read against the saved rules: curve, side per rebalance and its figures. */
export function sideHistoryView(
  run: BacktestRun,
  tree: StrategyTree,
  every: RebalanceEvery
): SideHistoryView | null {
  const curve = toCurve(run.results?.equityCurve);
  if (curve.dates.length < 2) return null;
  const benchCurve = toCurve(run.results?.benchmarkEquityCurve);
  const aligned = benchCurve.dates.length ? alignTo(curve.dates, benchCurve) : [];
  const firstBench = aligned.find((v): v is number => v !== null);
  const benchmark =
    firstBench !== undefined
      ? aligned.map((v) => ((v ?? firstBench) / firstBench) * curve.values[0])
      : undefined;
  const start = curve.dates[0];
  const end = curve.dates[curve.dates.length - 1];
  const trades = toTradeInputs(run.results?.trades ?? []);
  const sides = conditionSides(tree);
  const schedule = scheduledDates(curve.dates, every);
  const points = sides
    ? schedule
      ? sidesAtDates(trades, schedule, sides)
      : sidesAtRebalances(trades, sides)
    : [];
  const orderDays = [
    ...new Set(
      trades.flatMap((t) => [t.entryTime, t.exitTime]).flatMap((d) => (d ? [d.getTime()] : []))
    ),
  ]
    .sort((a, b) => a - b)
    .map((t) => new Date(t));
  const rebalanceDates = schedule ?? (sides ? points.map((p) => p.date) : orderDays);
  const m = run.results?.metrics;
  return {
    dates: curve.dates,
    values: curve.values,
    benchmark,
    start,
    end,
    sides,
    spans: sides ? sideSpans(points, end) : [],
    rebalanceDates,
    scheduled: schedule !== null,
    counts: sideCounts(points),
    totalReturn: m ? toNumber(m.totalReturn) : null,
    benchReturn: m ? toNumber(m.benchmarkReturn) : null,
    maxDrawdown: m ? -Math.abs(toNumber(m.maxDrawdown)) : null,
    sharpe: m ? toNumber(m.sharpeRatio) : null,
    benchSymbol: run.results?.benchmarkSymbol || run.config?.benchmarkSymbol || 'Benchmark',
  };
}

/** "RSI above 70" from "the 14-day RSI of SPY is above 70", for a narrow lane label. */
export function shortCondition(condition: string): string {
  const m = /^(?:the )?(?:\d+-day )?(.+?) of [A-Z.]+ (is )?(.+)$/.exec(condition);
  return m ? `${m[1]} ${m[3]}` : condition;
}
