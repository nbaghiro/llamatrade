/**
 * View-model + derivations for the Strategies table + detail drawer.
 *
 * A row blends three real sources: the strategy record (name/status/DSL/symbols),
 * its latest completed backtest (return, sharpe, drawdown, equity curves, final
 * holdings), and its live-deployment figures (allocation, mode). Nothing here is
 * mocked — fields with no source resolve to `null` and render as an em dash.
 */

import type { BacktestRun } from '../../generated/proto/backtest_pb';
import { ExecutionMode } from '../../generated/proto/common_pb';
import { StrategyStatus, type Strategy } from '../../generated/proto/strategy_pb';
import { toNumber } from '../../store/backtest';
import type { StrategyDeployment } from '@llamatrade/core/stores/strategies';

// Categorical swatch palette (Monolith tokens), assigned by table slot; mirrors the portfolio series palette (violet/cyan/grey inline).
export const STRATEGY_COLORS = [
  '#0f7a34', // green
  '#1a1aff', // blue
  '#ff4d1c', // orange
  '#c81e1e', // red
  '#6b2fb3', // violet
  '#0e8ba0', // cyan
];

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
  const backtestReturn = metrics ? toNumber(metrics.totalReturn) * 100 : null;
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
    sharpe: metrics ? toNumber(metrics.sharpeRatio) : null,
    maxDrawdownPct: metrics ? toNumber(metrics.maxDrawdown) * 100 : null,
    benchmarkReturnPct: metrics ? toNumber(metrics.benchmarkReturn) * 100 : null,
    allocation: deployed ? deployment.allocatedCapital : null,
    deployed,
    equityCurve: (run?.results?.equityCurve ?? []).map((p) => toNumber(p.equity)),
    benchmarkCurve: (run?.results?.benchmarkEquityCurve ?? []).map((p) => toNumber(p.equity)),
  };
}

/** Per-asset weights (%) from a backtest's final holdings, largest first. */
export function positionAllocations(run: BacktestRun | null): { symbol: string; weight: number }[] {
  const positions = run?.results?.finalPositions ?? [];
  const valued = positions
    .map((p) => ({
      symbol: p.symbol,
      value: toNumber(p.marketValue) || toNumber(p.quantity) * toNumber(p.currentPrice),
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
  if (value === 0) return '$0';
  if (Math.abs(value) >= 1000) {
    const k = value / 1000;
    return `$${k >= 10 ? Math.round(k) : k.toFixed(1)}k`;
  }
  return `$${Math.round(value)}`;
}

export function formatMoneyFull(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatUpdated(ts: { seconds: bigint } | undefined): string {
  if (!ts?.seconds) return '—';
  const date = new Date(Number(ts.seconds) * 1000);
  const diffMs = Date.now() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffHours < 1) return 'Just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

const PILL_CLASS: Record<StrategyPill, string> = {
  LIVE: 'bg-green-500 text-bone',
  PAPER: 'bg-orange-500 text-ink',
  PAUSED: 'bg-ink text-bone',
  DRAFT: 'bg-bone text-ink',
  ARCHIVED: 'bg-gray-200 text-ink/60',
};

export function pillClass(pill: StrategyPill): string {
  return PILL_CLASS[pill];
}
