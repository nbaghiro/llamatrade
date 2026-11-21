/** The list as running against its backtest (list2 C): open sessions first, then the rest. */

import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';

import type { SessionRow } from '../sessions/sessionRows';

import type { SameDates } from './sameDates';
import { pickSession, type BacktestCell } from './stageModel';
import type { RunFigures } from './strategyView';

export interface RunningItem {
  strategy: Strategy;
  row: SessionRow;
}

export const isLiveRow = (r: SessionRow) => r.session.mode === ExecutionMode.LIVE;

/**
 * One item per open session, live first and then the longest running; every strategy without
 * an open session goes to `notRunning`, stopped ones first, otherwise in the order given.
 */
export function splitByRunning(
  strategies: readonly Strategy[],
  sessions: readonly SessionRow[]
): { running: RunningItem[]; notRunning: Strategy[] } {
  const running: RunningItem[] = [];
  const notRunning: Strategy[] = [];
  for (const strategy of strategies) {
    const open = sessions.filter((s) => s.session.strategyId === strategy.id && s.view.open);
    if (open.length) open.forEach((row) => running.push({ strategy, row }));
    else notRunning.push(strategy);
  }
  const ran = new Set(sessions.map((s) => s.session.strategyId));
  notRunning.sort((a, b) => Number(ran.has(b.id)) - Number(ran.has(a.id)));
  running.sort(
    (a, b) =>
      Number(isLiveRow(b.row)) - Number(isLiveRow(a.row)) ||
      (a.row.startedAt?.getTime() ?? 0) - (b.row.startedAt?.getTime() ?? 0)
  );
  return { running, notRunning };
}

/** "3 running · 4 not running". */
export function listSummary(running: number, notRunning: number): string {
  return `${running} running · ${notRunning} not running`;
}

export type NotRunningState =
  | { kind: 'stopped'; at: Date | null; sessionPct: number | null; live: boolean }
  | { kind: 'neverRun' }
  | { kind: 'draft'; version: number }
  | { kind: 'loading' };

/**
 * Stopped when a session ran it before; Never run when the latest backtest tested this version;
 * otherwise a draft (untested, or tested on an older version).
 */
export function notRunningState(
  strategy: Pick<Strategy, 'id' | 'version'>,
  backtest: BacktestCell,
  sessions: readonly SessionRow[]
): NotRunningState {
  const past = pickSession(sessions.filter((s) => s.session.strategyId === strategy.id));
  if (past) {
    const ended = past.session.endedAt?.seconds
      ? new Date(Number(past.session.endedAt.seconds) * 1000)
      : null;
    return {
      kind: 'stopped',
      at: ended,
      sessionPct: past.figures.totalPct,
      live: isLiveRow(past),
    };
  }
  if (backtest.kind === 'loading') return { kind: 'loading' };
  if (backtest.kind === 'none' || backtest.kind === 'stale') {
    return { kind: 'draft', version: strategy.version || 1 };
  }
  return { kind: 'neverRun' };
}

export type NotRunningAction = { kind: 'backtest'; version: number } | { kind: 'first' } | null;

/** The one next step a not-running card offers. */
export function notRunningAction(
  strategy: Pick<Strategy, 'version'>,
  backtest: BacktestCell
): NotRunningAction {
  if (backtest.kind === 'none') return { kind: 'first' };
  if (backtest.kind === 'stale') return { kind: 'backtest', version: strategy.version };
  return null;
}

export interface SharedRange {
  start: Date;
  end: Date;
  benchmarkSymbol: string;
  benchmarkReturn: number | null;
}

const monthKey = (d: Date | null) => (d ? d.getUTCFullYear() * 12 + d.getUTCMonth() : -1);

/**
 * The range every loaded backtest shares, by month, with the benchmark's return over it; null
 * when none have loaded or they differ, so the header doesn't claim one range for all.
 */
export function sharedRange(figures: readonly (RunFigures | null)[]): SharedRange | null {
  const known = figures.filter((f): f is RunFigures => f !== null && !!f.start && !!f.end);
  if (!known.length) return null;
  const [first] = known;
  const same = known.every(
    (f) =>
      monthKey(f.start) === monthKey(first.start) &&
      monthKey(f.end) === monthKey(first.end) &&
      f.benchmarkSymbol === first.benchmarkSymbol
  );
  if (!same || !first.start || !first.end) return null;
  return {
    start: first.start,
    end: first.end,
    benchmarkSymbol: first.benchmarkSymbol,
    benchmarkReturn: first.benchmarkReturn,
  };
}

export interface RunningFigures {
  /** The session's return: over the shared days when a backtest covers them, else since it started. */
  session: number | null;
  /** The backtest over the same days; null when no run covers them. */
  backtest: number | null;
  /** Session minus backtest, in percentage points. */
  gap: number | null;
}

export function runningFigures(row: SessionRow, same: SameDates | null): RunningFigures {
  if (same && same.paper.length) {
    const i = same.paper.length - 1;
    return { session: same.paper[i], backtest: same.backtest[i], gap: same.gap[i] };
  }
  return { session: row.figures.totalPct, backtest: null, gap: null };
}
