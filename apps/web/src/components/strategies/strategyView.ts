/** Pure view-model for the strategies list, overview and detail page. */

import { num, toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus, type Strategy } from '@llamatrade/core/proto/strategy_pb';
import type { StrategyDeployment } from '@llamatrade/core/stores/strategies';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';

import { buildOutline, lineText, rebalanceWord } from '../../lib/outline';
import type { RunState } from '../ui';

export type ListFilter = 'all' | 'running' | 'draft' | 'stopped';

export const LIST_FILTERS: ReadonlyArray<{ key: ListFilter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'running', label: 'Running' },
  { key: 'draft', label: 'Drafts' },
  { key: 'stopped', label: 'Stopped' },
];

/** The state mark for a strategy: its paper session's state when deployed, else its own status. */
export function runState(strategy: Strategy, deployment: StrategyDeployment | undefined): RunState {
  if (deployment) {
    switch (deployment.status) {
      case ExecutionStatus.RUNNING:
        return 'running';
      case ExecutionStatus.PENDING:
        return 'waiting';
      case ExecutionStatus.PAUSED:
        return 'paused';
      case ExecutionStatus.ERROR:
        return 'error';
      case ExecutionStatus.STOPPED:
        return 'stopped';
      default:
        break;
    }
  }
  switch (strategy.status) {
    case StrategyStatus.DRAFT:
      return 'draft';
    case StrategyStatus.PAUSED:
      return 'paused';
    default:
      return 'stopped';
  }
}

/** A clearer word for a strategy that has never run than "Stopped". */
export function stateLabel(state: RunState, deployed: boolean): string | undefined {
  if (state === 'stopped' && !deployed) return 'Not running';
  return undefined;
}

export function matchesFilter(state: RunState, filter: ListFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'running') {
    return state === 'running' || state === 'waiting' || state === 'paused' || state === 'error';
  }
  if (filter === 'draft') return state === 'draft';
  return state === 'stopped';
}

export interface RunFigures {
  totalReturn: number;
  cagr: number;
  maxDrawdown: number;
  sharpe: number;
  benchmarkReturn: number | null;
  benchmarkSymbol: string;
  start: Date | null;
  end: Date | null;
  dates: Date[];
  equity: number[];
  bench: number[];
}

/** Figures from a completed backtest. Fractions stay fractions; drawdown is always negative. */
export function runFigures(run: BacktestRun | null | undefined): RunFigures | null {
  const m = run?.results?.metrics;
  if (!run || run.status !== BacktestStatus.COMPLETED || !m) return null;
  const curve = run.results?.equityCurve ?? [];
  const benchCurve = run.results?.benchmarkEquityCurve ?? [];
  const dates: Date[] = [];
  const equity: number[] = [];
  const bench: number[] = [];
  const sameLength = benchCurve.length === curve.length;
  curve.forEach((p, i) => {
    const d = toDate(p.timestamp);
    if (!d) return;
    dates.push(d);
    equity.push(num(p.equity));
    if (sameLength) bench.push(num(benchCurve[i].equity));
  });
  const benchSymbol = run.results?.benchmarkSymbol ?? '';
  return {
    totalReturn: num(m.totalReturn),
    cagr: num(m.annualizedReturn),
    maxDrawdown: -Math.abs(num(m.maxDrawdown)),
    sharpe: num(m.sharpeRatio),
    benchmarkReturn: benchSymbol && m.benchmarkReturn?.value ? num(m.benchmarkReturn) : null,
    benchmarkSymbol: benchSymbol,
    start: toDate(run.config?.startDate) ?? dates[0] ?? null,
    end: toDate(run.config?.endDate) ?? dates[dates.length - 1] ?? null,
    dates,
    equity,
    bench,
  };
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const monthYear = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
export const dayMonthYear = (d: Date) =>
  `${MON[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;

/** "Nov 2024 to Oct 2026" for a run's range. */
export function rangeLabel(f: Pick<RunFigures, 'start' | 'end'>): string {
  if (!f.start || !f.end) return '';
  return `${monthYear(f.start)} to ${monthYear(f.end)}`;
}

/** A one-line summary: the description when there is one, otherwise the first rules in words. */
export function summaryLine(strategy: Pick<Strategy, 'description' | 'dslCode'>): string {
  if (strategy.description.trim()) return strategy.description.trim();
  const parsed = strategy.dslCode ? fromDSLString(strategy.dslCode) : null;
  if (!parsed) return '';
  const lines = buildOutline(parsed.tree);
  const rules = lines.filter((l) => l.kind !== 'asset' && l.number !== null);
  if (!rules.length) return '';
  const symbols = [...new Set(lines.filter((l) => l.kind === 'asset').map((l) => l.symbol ?? ''))];
  const text = rules.slice(0, 2).map(lineText).join(', then ');
  const tail = symbols.length
    ? ` across ${symbols.slice(0, 5).join(', ')}${symbols.length > 5 ? ' and more' : ''}`
    : '';
  return `${text[0].toUpperCase()}${text.slice(1)}${tail}.`;
}

/** "Version 3 · monthly · benchmark SPY · $25,000 allocated". */
export function metaLine(
  strategy: Pick<Strategy, 'version' | 'rebalance' | 'dslCode'>,
  allocation: number | null
): string {
  const parsed = strategy.dslCode ? fromDSLString(strategy.dslCode) : null;
  const rebalance = parsed?.metadata.timeframe
    ? rebalanceWord(parsed.metadata.timeframe)
    : strategy.rebalance || '';
  const bench = parsed?.metadata.benchmark;
  const parts = [`Version ${strategy.version || 1}`];
  if (rebalance) parts.push(rebalance);
  if (bench) parts.push(`benchmark ${bench}`);
  if (allocation !== null && allocation > 0) {
    parts.push(`$${Math.round(allocation).toLocaleString('en-US')} allocated`);
  }
  return parts.join(' · ');
}

const runTime = (b: BacktestRun) => Number(b.completedAt?.seconds ?? b.createdAt?.seconds ?? 0);

/** Runs newest first. */
export function newestFirst(runs: readonly BacktestRun[]): BacktestRun[] {
  return [...runs].sort((a, b) => runTime(b) - runTime(a));
}

/** The newest completed run for each saved version of a strategy. */
export function latestRunPerVersion(runs: readonly BacktestRun[]): Map<number, BacktestRun> {
  const out = new Map<number, BacktestRun>();
  for (const r of newestFirst(runs)) {
    if (r.status !== BacktestStatus.COMPLETED) continue;
    if (!out.has(r.strategyVersion)) out.set(r.strategyVersion, r);
  }
  return out;
}
