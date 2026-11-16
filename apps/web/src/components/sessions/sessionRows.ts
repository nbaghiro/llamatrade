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

/** "Oct 1" or "today, 9:31". */
export function sinceLabel(d: Date | null, now = new Date()): string {
  if (!d) return '·';
  if (d.toDateString() === now.toDateString()) {
    return `today, ${d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }).toLowerCase()}`;
  }
  return `${MON[d.getMonth()]} ${d.getDate()}`;
}

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
      return1d: perf?.returns?.return1d ? toNumber(perf.returns.return1d) : null,
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

/** The Next rebalance cell: a date, the schedule word, or held while frozen; a dot otherwise. */
export function nextRebalanceCell(row: SessionRow, today: Date): string {
  if (row.state === 'frozen') return 'Held';
  if (!row.view.open || row.state === 'paused') return '·';
  if (row.state === 'starting') return 'On its first bar';
  const next = rowNextRebalance(row, today);
  if (next) return dayLabel(next);
  return row.rebalance === 'Daily' ? 'Each trading day' : row.rebalance || 'On schedule';
}

/** Attention first, then open sessions, then stopped; newest first within a state. */
export function sortRows(rows: SessionRow[]): SessionRow[] {
  return [...rows].sort(
    (a, b) =>
      sessionSortKey(a.state) - sessionSortKey(b.state) ||
      (b.startedAt?.getTime() ?? 0) - (a.startedAt?.getTime() ?? 0)
  );
}

export interface RailFacts {
  label: string;
  value: string;
  attention?: boolean;
}

/** The rail's four facts. Data health and reconciliation times have no endpoint, so they aren't claimed. */
export function railFacts(
  /** Null when the sessions couldn't be loaded. */
  known: readonly SessionRow[] | null,
  market: string,
  sleevesKnown: boolean,
  today: Date = etToday()
): RailFacts[] {
  const rows = known ?? [];
  const open = rows.filter((r) => r.view.open);
  const dated = open
    .map((r) => ({ r, at: rowNextRebalance(r, today) }))
    .filter((x): x is { r: SessionRow; at: Date } => x.at !== null)
    .sort((a, b) => a.at.getTime() - b.at.getTime());
  const soonest = dated.filter((x) => x.at.getTime() === dated[0]?.at.getTime());
  const daily = open.some((r) => r.state === 'running' && r.rebalance === 'Daily');
  const frozen = rows.filter((r) => r.state === 'frozen').length;
  const withSleeve = open.filter((r) => r.sleeve).length;
  return [
    {
      label: 'Market',
      value: market.replace(/^Market /, '').replace(/^./, (c) => c.toUpperCase()),
    },
    { label: 'Data', value: 'IEX · daily bars' },
    {
      label: 'Next rebalance',
      value:
        known === null
          ? 'Not available'
          : open.length === 0
            ? 'No open sessions'
            : daily
              ? 'Each trading day'
              : soonest.length
                ? `${dayLabel(soonest[0].at)} · ${
                    soonest.length === 1 ? soonest[0].r.name : `${soonest.length} sessions`
                  }`
                : 'None scheduled',
    },
    {
      label: 'Reconciliation',
      value: frozen
        ? `${frozen} ${frozen === 1 ? 'session' : 'sessions'} frozen`
        : known === null || !sleevesKnown
          ? 'Not available'
          : withSleeve
            ? 'Sleeves active'
            : 'No sleeves yet',
      attention: frozen > 0,
    },
  ];
}

const listWords = (xs: readonly string[]) =>
  xs.length <= 1 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`;

/** One sentence on what the session holds and when it next trades. */
export function statusSentence({
  holdings,
  rebalance,
  open,
  lastOrder,
  next = null,
}: {
  /** Symbol and market value of each position. */
  holdings: readonly { symbol: string; value: number }[];
  rebalance: string;
  open: boolean;
  lastOrder: Date | null;
  /** The next scheduled rebalance, when known. */
  next?: Date | null;
}): string {
  const held = [...holdings].filter((h) => h.value > 0).sort((a, b) => b.value - a.value);
  const parts: string[] = [];
  if (held.length === 0) parts.push(open ? 'Holding cash only.' : 'No positions are held.');
  else if (held.length <= 3) parts.push(`Holding ${listWords(held.map((h) => h.symbol))}.`);
  else parts.push(`Holding ${held.length} positions, the largest ${held[0].symbol}.`);
  if (open) {
    parts.push(
      next
        ? `It rebalances ${rebalance.toLowerCase()}, and nothing trades until the ${dayLabel(next)} rebalance.`
        : rebalance
          ? `It rebalances ${rebalance.toLowerCase()}, and nothing trades in between.`
          : 'It trades only when it rebalances.'
    );
  }
  if (lastOrder) {
    parts.push(
      `The last orders were placed on ${MON[lastOrder.getMonth()]} ${lastOrder.getDate()}.`
    );
  } else if (open) {
    parts.push('No orders have been placed yet.');
  }
  return parts.join(' ');
}
