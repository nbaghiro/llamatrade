import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { toDecimal, toTimestamp } from '@llamatrade/core/stores/backtest';

import { symbolsOf } from '../../components/home/templates';
import { backtestClient, strategyClient } from '../../services/grpc-client';
import { getTenantContext } from '../../store/auth';

export const FIRST_BACKTEST_CAPITAL = 25_000;
export const FIRST_BACKTEST_YEARS = 2;

/** The window for a first backtest: the two years up to the start of today, in UTC. */
export function firstBacktestRange(now: Date): { start: Date; end: Date } {
  const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const start = new Date(end);
  start.setUTCFullYear(end.getUTCFullYear() - FIRST_BACKTEST_YEARS);
  return { start, end };
}

/** Saves the template as a strategy, starts its backtest and returns the run id. */
export async function startTemplateBacktest(
  template: Pick<StrategyTemplate, 'id' | 'name' | 'description' | 'configSexpr'>,
  benchmark: string,
  now = new Date()
): Promise<{ runId: string; strategyId: string }> {
  const context = getTenantContext();
  if (!context) throw new Error('Your session has ended. Please sign in again.');

  const created = await strategyClient.createStrategy({
    context,
    name: template.name,
    description: template.description,
    dslCode: template.configSexpr,
    templateId: template.id,
    symbols: symbolsOf(template.configSexpr),
    templateParams: {},
  });
  const strategy = created.strategy;
  if (!strategy) throw new Error("The strategy couldn't be saved.");

  const { start, end } = firstBacktestRange(now);
  const res = await backtestClient.runBacktest({
    context,
    config: {
      strategyId: strategy.id,
      strategyVersion: strategy.version,
      startDate: toTimestamp(start),
      endDate: toTimestamp(end),
      initialCapital: toDecimal(FIRST_BACKTEST_CAPITAL),
      symbols: strategy.symbols,
      commission: toDecimal(0.001),
      slippagePercent: toDecimal(0.001),
      timeframe: '1D',
      allowShorting: false,
      useAdjustedPrices: true,
      parameters: {},
      benchmarkSymbol: benchmark,
      includeBenchmark: benchmark !== '',
    },
  });
  if (!res.backtest) throw new Error("The backtest couldn't be started.");
  return { runId: res.backtest.id, strategyId: strategy.id };
}
