/**
 * View-model + derivations for a strategy row (Strategies table + detail views).
 *
 * A row blends three real sources: the strategy record (name/status/DSL/symbols),
 * its latest completed backtest (return, sharpe, drawdown, equity curves, final
 * holdings), and its live-deployment figures (allocation, mode). Nothing here is
 * mocked — fields with no source resolve to `null` and render as an em dash.
 *
 * Platform-neutral: pure derivations only. The Tailwind pill class map stays in web.
 */

import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus, type Strategy } from '@llamatrade/core/proto/strategy_pb';
import type { StrategyDeployment } from '../stores/strategies';
import { dateShort, money, moneyShort, num } from '../format';

export type StrategyPill = 'LIVE' | 'PAPER' | 'PAUSED' | 'DRAFT' | 'ARCHIVED';

export type ImplementationType = 'dsl' | 'template';

export interface StrategyRowView {
  strategy: Strategy;
  color: string;
  /** Latest completed backtest (full results), or null if never run. */
  run: BacktestRun | null;
  pill: StrategyPill;
  implementation: ImplementationType;
  meta: string;
  /** Headline return %: realized when deployed, else backtest (`returnIsBacktest`). */
  returnPct: number | null;
  returnIsBacktest: boolean;
  sharpe: number | null;
  maxDrawdownPct: number | null;
  benchmarkReturnPct: number | null;
  /** Deployed capital in dollars, or null when the strategy is not deployed. */
  allocation: number | null;
  deployed: boolean;
  equityCurve: number[];
  benchmarkCurve: number[];
}

export function getImplementationType(strategy: Strategy): ImplementationType {
  // Every stored strategy compiles to a DSL (config_sexpr is the source of
  // truth); template provenance is not persisted, so non-template means DSL.
  return strategy.templateId ? 'template' : 'dsl';
}

function pillFor(strategy: Strategy, deployment: StrategyDeployment | undefined): StrategyPill {
  switch (strategy.status) {
    case StrategyStatus.DRAFT:
      return 'DRAFT';
    case StrategyStatus.PAUSED:
      return 'PAUSED';
    case StrategyStatus.ARCHIVED:
      return 'ARCHIVED';
    case StrategyStatus.ACTIVE:
      // Badge by mode; a deployed strategy is LIVE only when its execution is
      // explicitly live — anything else (paper, or not yet resolved) is PAPER.
      return deployment?.mode === ExecutionMode.LIVE ? 'LIVE' : 'PAPER';
    default:
      return 'DRAFT';
  }
}

export function buildRow(
  strategy: Strategy,
  run: BacktestRun | null,
  deployment: StrategyDeployment | undefined,
  color: string
): StrategyRowView {
  const metrics = run?.results?.metrics;
  const deployed = deployment !== undefined;
  const implementation = getImplementationType(strategy);

  // Metrics are stored as fractions on the wire (0.12 = 12%).
  const backtestReturn = metrics ? num(metrics.totalReturn) * 100 : null;
  const returnPct = deployed ? deployment.returnAll : backtestReturn;

  return {
    strategy,
    color,
    run,
    pill: pillFor(strategy, deployment),
    implementation,
    meta: `${implementation} · ${strategy.timeframe || '1D'} · ${strategy.symbols.length} pos`,
    returnPct,
    returnIsBacktest: !deployed && backtestReturn !== null,
    sharpe: metrics ? num(metrics.sharpeRatio) : null,
    maxDrawdownPct: metrics ? num(metrics.maxDrawdown) * 100 : null,
    benchmarkReturnPct: metrics ? num(metrics.benchmarkReturn) * 100 : null,
    allocation: deployed ? deployment.allocatedCapital : null,
    deployed,
    equityCurve: (run?.results?.equityCurve ?? []).map((p) => num(p.equity)),
    benchmarkCurve: (run?.results?.benchmarkEquityCurve ?? []).map((p) => num(p.equity)),
  };
}

/** Per-asset weights (%) from a backtest's final holdings, largest first. */
export function positionAllocations(run: BacktestRun | null): { symbol: string; weight: number }[] {
  const positions = run?.results?.finalPositions ?? [];
  const valued = positions
    .map((p) => ({
      symbol: p.symbol,
      value: num(p.marketValue) || num(p.quantity) * num(p.currentPrice),
    }))
    .filter((p) => p.value > 0);

  const total = valued.reduce((sum, p) => sum + p.value, 0);
  if (total <= 0) return [];

  return valued
    .map((p) => ({ symbol: p.symbol, weight: (p.value / total) * 100 }))
    .sort((a, b) => b.weight - a.weight);
}

// Formatting

export function formatReturn(pct: number): string {
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

/** Compact dollars: $50k, $1.2k, $0. */
export function formatMoneyShort(value: number): string {
  return moneyShort(value);
}

export function formatMoneyFull(value: number): string {
  return money(value);
}

/** "Just now" / "3h ago" / "2d ago" / "Jul 16" past a week. */
export function formatUpdated(ts: { seconds: bigint } | undefined): string {
  if (!ts?.seconds) return '—';
  const date = new Date(Number(ts.seconds) * 1000);
  const diffHours = Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffHours < 1) return 'Just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return dateShort(date);
}
