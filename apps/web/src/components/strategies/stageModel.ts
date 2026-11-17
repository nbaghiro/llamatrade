/** The stage track (list2 A): where each strategy sits between draft, backtested, paper and live. */

import { toDate } from '@llamatrade/core/format';
import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';

import { nextRebalanceDate } from '../../lib/sessionState';
import type { SessionRow } from '../sessions/sessionRows';

import { runFigures, type RunFigures } from './strategyView';

export type Stage = 'draft' | 'backtested' | 'paper' | 'live';

export const STAGES: readonly Stage[] = ['draft', 'backtested', 'paper', 'live'];

export type BacktestCell =
  | { kind: 'loading' }
  | { kind: 'none' }
  /** The latest completed run tested this version. */
  | { kind: 'current'; figures: RunFigures; version: number }
  /** The latest completed run tested an older version; the rules changed since. */
  | { kind: 'stale'; figures: RunFigures; version: number };

export type NextStep =
  | { kind: 'rebalance'; at: Date }
  | { kind: 'schedule'; label: string }
  | { kind: 'restart'; mode: 'paper' | 'live' }
  | { kind: 'start' }
  | { kind: 'backtest'; version: number }
  | { kind: 'firstBacktest' }
  | { kind: 'none' };

export interface StageRow {
  stage: Stage;
  backtest: BacktestCell;
  paper: SessionRow | null;
  live: SessionRow | null;
  next: NextStep;
}

const isLive = (row: SessionRow) => row.session.mode === ExecutionMode.LIVE;

/** The session shown for one mode: an open one first, then the most recently started. */
export function pickSession(rows: readonly SessionRow[]): SessionRow | null {
  let best: SessionRow | null = null;
  for (const r of rows) {
    if (!best) {
      best = r;
      continue;
    }
    if (r.view.open !== best.view.open) {
      if (r.view.open) best = r;
      continue;
    }
    if ((r.startedAt?.getTime() ?? 0) > (best.startedAt?.getTime() ?? 0)) best = r;
  }
  return best;
}

export function backtestCell(
  strategy: Pick<Strategy, 'version'>,
  run: BacktestRun | null | undefined
): BacktestCell {
  if (run === undefined) return { kind: 'loading' };
  const figures = runFigures(run);
  if (!run || !figures) return { kind: 'none' };
  const version = run.strategyVersion || strategy.version;
  return version < strategy.version
    ? { kind: 'stale', figures, version }
    : { kind: 'current', figures, version };
}

function sessionNext(row: SessionRow, today: Date): NextStep {
  if (!row.view.open) return { kind: 'restart', mode: isLive(row) ? 'live' : 'paper' };
  if (row.state === 'running') {
    const at = nextRebalanceDate(row.rebalance, today);
    if (at) return { kind: 'rebalance', at };
    return { kind: 'schedule', label: row.rebalance === 'Daily' ? 'Each trading day' : '' };
  }
  return { kind: 'none' };
}

/** One strategy's place on the track. `today` is the New York calendar date at UTC midnight. */
export function stageRow(
  strategy: Pick<Strategy, 'id' | 'version'>,
  run: BacktestRun | null | undefined,
  sessions: readonly SessionRow[],
  today: Date
): StageRow {
  const own = sessions.filter((s) => s.session.strategyId === strategy.id);
  const live = pickSession(own.filter(isLive));
  const paper = pickSession(own.filter((s) => !isLive(s)));
  const backtest = backtestCell(strategy, run);

  if (live) return { stage: 'live', backtest, paper, live, next: sessionNext(live, today) };
  if (paper) return { stage: 'paper', backtest, paper, live, next: sessionNext(paper, today) };
  if (backtest.kind === 'current') {
    return { stage: 'backtested', backtest, paper, live, next: { kind: 'start' } };
  }
  const next: NextStep =
    backtest.kind === 'stale'
      ? { kind: 'backtest', version: strategy.version }
      : backtest.kind === 'none'
        ? { kind: 'firstBacktest' }
        : { kind: 'none' };
  return { stage: 'draft', backtest, paper, live, next };
}

/** The stage a row's dashed segment leads to, or null when nothing comes next. */
export function nextStage(row: StageRow): Stage | null {
  switch (row.next.kind) {
    case 'firstBacktest':
    case 'backtest':
      return 'backtested';
    case 'start':
      return 'paper';
    default:
      return null;
  }
}

/** "7 strategies · 1 live, 2 in paper, 1 stopped, 3 not run yet". */
export function trackSummary(rows: readonly StageRow[]): string {
  const n = rows.length;
  const head = `${n} ${n === 1 ? 'strategy' : 'strategies'}`;
  if (n === 0) return head;
  let live = 0;
  let paper = 0;
  let stopped = 0;
  let notRun = 0;
  for (const r of rows) {
    const s = r.live ?? r.paper;
    if (!s) notRun++;
    else if (!s.view.open) stopped++;
    else if (r.live) live++;
    else paper++;
  }
  const parts: string[] = [];
  if (live) parts.push(`${live} live`);
  if (paper) parts.push(`${paper} in paper`);
  if (stopped) parts.push(`${stopped} stopped`);
  if (notRun) parts.push(`${notRun} not run yet`);
  return `${head} · ${parts.join(', ')}`;
}

/** When a strategy's own definition last changed. */
export function editedAt(strategy: Pick<Strategy, 'updatedAt' | 'createdAt'>): Date | null {
  return toDate(strategy.updatedAt) ?? toDate(strategy.createdAt);
}

export const STAGE_HEAD: Record<Stage, { title: string; sub: string }> = {
  draft: { title: 'Draft', sub: 'Rules you can edit' },
  backtested: { title: 'Backtested', sub: 'Latest completed run' },
  paper: { title: 'Paper', sub: 'Simulated money on Alpaca' },
  live: { title: 'Live', sub: 'Real money on Alpaca' },
};

export const TRACK_COLS =
  'grid-cols-[minmax(180px,1.15fr)_repeat(4,minmax(0,1fr))_minmax(130px,0.75fr)]';

/** "Quarterly · VTI VGLT IEF GLD DBC". */
export function strategySub(strategy: Pick<Strategy, 'rebalance' | 'symbols'>): string {
  const r = strategy.rebalance.trim();
  const word = r ? `${r[0].toUpperCase()}${r.slice(1).toLowerCase()}` : '';
  const syms = strategy.symbols;
  const shown =
    syms.length > 4 ? `${syms.slice(0, 3).join(' ')} +${syms.length - 3}` : syms.join(' ');
  return [word, shown].filter(Boolean).join(' · ');
}
