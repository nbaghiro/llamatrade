import type { Sleeve } from '@llamatrade/core/proto/ledger_pb';
import type { StrategyPerformanceSummary } from '@llamatrade/core/proto/portfolio_pb';
import type { Strategy, StrategyExecution } from '@llamatrade/core/proto/strategy_pb';
import type { Order, TradingSession } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';
import { executionFor, sleeveFor } from '@llamatrade/core/stores/trading';

import { etParts } from '../../lib/marketClock';
import {
  deriveSessionState,
  nextRebalanceDate,
  sessionFigures,
  sessionSortKey,
  sessionStateView,
  type SessionFigures,
  type SessionState,
  type SessionStateView,
} from '../../lib/sessionState';
import { rebalanceLabel } from '../../types/backtest';

export interface SessionRow {
  session: TradingSession;
  name: string;
  version: number;
  rebalance: string;
  state: SessionState;
  view: SessionStateView;
  figures: SessionFigures;
  execution: StrategyExecution | null;
  sleeve: Sleeve | null;
  orders: number;
  startedAt: Date | null;
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Strips the "(paper)" suffix the deploy flow adds to session names. */
export function sessionName(session: TradingSession, strategy?: Strategy): string {
  return strategy?.name ?? session.name.replace(/\s*\(paper\)\s*$/i, '');
}

export function buildSessionRow(
  session: TradingSession,
  ctx: {
    executions: readonly StrategyExecution[];
    sleeves: readonly Sleeve[];
    performance: readonly StrategyPerformanceSummary[];
    strategies: readonly Strategy[];
    orders: readonly Order[];
  }
): SessionRow {
  const execution = executionFor(session, ctx.executions);
  const sleeve = sleeveFor(session, ctx.sleeves);
  const perf = execution ? ctx.performance.find((p) => p.executionId === execution.id) : undefined;
  const strategy = ctx.strategies.find((s) => s.id === session.strategyId);
  const state = deriveSessionState({
    isActive: session.isActive,
    ended: Boolean(session.endedAt),
    executionStatus: execution?.status,
    sleeveStatus: sleeve?.status,
  });
  const allocated =
    perf?.allocatedCapital ?? execution?.allocatedCapital ?? sleeve?.allocatedCapital;
  return {
    session,
    name: sessionName(session, strategy),
    version: execution?.version || strategy?.version || 0,
    rebalance: rebalanceLabel(strategy?.rebalance),
    state,
    view: sessionStateView(state),
    figures: sessionFigures({
      currentValue: perf?.currentValue ? toNumber(perf.currentValue) : null,
      allocated: allocated ? toNumber(allocated) : null,
      // The portfolio service reports return1d in percent.
      return1d: perf?.returns?.return1d ? toNumber(perf.returns.return1d) / 100 : null,
      cash: sleeve?.cash ? toNumber(sleeve.cash.balance) : null,
    }),
    execution,
    sleeve,
    orders: ctx.orders.filter((o) => o.sessionId === session.id).length,
    startedAt: toDate(session.startedAt),
  };
}

/** Today's date in New York, at UTC midnight. */
export function etToday(now = new Date()): Date {
  const p = etParts(now);
  return new Date(Date.UTC(p.year, p.month, p.day));
}

/** "Dec 1", from a UTC-midnight calendar date. */
export const dayLabel = (d: Date) => `${MON[d.getUTCMonth()]} ${d.getUTCDate()}`;

/** When a running session next rebalances; null when it isn't running or has no fixed schedule. */
export function rowNextRebalance(row: SessionRow, today: Date): Date | null {
  return row.state === 'running' ? nextRebalanceDate(row.rebalance, today) : null;
}

/** Attention first, then open sessions, then stopped; newest first within a state. */
export function sortRows(rows: SessionRow[]): SessionRow[] {
  return [...rows].sort(
    (a, b) =>
      sessionSortKey(a.state) - sessionSortKey(b.state) ||
      (b.startedAt?.getTime() ?? 0) - (a.startedAt?.getTime() ?? 0)
  );
}
