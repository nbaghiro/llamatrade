import { num, toDate } from '@llamatrade/core/format';
import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus, type Sleeve } from '@llamatrade/core/proto/ledger_pb';
import type { StrategyPerformanceSummary } from '@llamatrade/core/proto/portfolio_pb';
import type { StrategyExecution } from '@llamatrade/core/proto/strategy_pb';
import { OrderSide, OrderStatus, type Order, type TradingSession } from '@llamatrade/core/proto/trading_pb';
import { executionFor, sleeveFor, useTradingStore } from '@llamatrade/core/stores/trading';
import { useMemo } from 'react';
import { useShallow } from 'zustand/react/shallow';

import { needsYou, toRow, type ExecState, type FillInput, type NeedsItem, type RejectedInput, type SessionRow } from './model';

const EXEC: Partial<Record<ExecutionStatus, ExecState>> = {
  [ExecutionStatus.PENDING]: 'pending',
  [ExecutionStatus.RUNNING]: 'running',
  [ExecutionStatus.PAUSED]: 'paused',
  [ExecutionStatus.STOPPED]: 'stopped',
  [ExecutionStatus.ERROR]: 'error',
};

function ms(d: Date | null): number | null {
  return d ? d.getTime() : null;
}

function optionalNum(d: { value: string } | undefined): number | null {
  return d?.value ? num(d) : null;
}

/** One session with its execution, sleeve and performance, as a row. */
export function sessionRow(
  session: TradingSession,
  executions: readonly StrategyExecution[],
  sleeves: readonly Sleeve[],
  performance: readonly StrategyPerformanceSummary[],
): SessionRow {
  const execution = executionFor(session, executions);
  const sleeve = sleeveFor(session, sleeves);
  const perf = execution ? performance.find((p) => p.executionId === execution.id) : undefined;
  return toRow({
    id: session.id,
    name: session.name,
    mode: session.mode === ExecutionMode.LIVE ? 'live' : 'paper',
    active: session.isActive,
    startedAt: ms(toDate(session.startedAt)),
    endedAt: ms(toDate(session.endedAt)),
    sleeveId: session.sleeveId,
    strategyId: session.strategyId,
    executionId: execution?.id ?? null,
    execution: execution ? EXEC[execution.status] ?? null : null,
    sleeveFrozen: sleeve?.status === SleeveStatus.FROZEN,
    value: optionalNum(perf?.currentValue) ?? optionalNum(session.currentEquity),
    return1dPct: optionalNum(perf?.returns?.return1d),
    returnAllPct: optionalNum(perf?.returns?.returnAll),
    version: execution?.version ?? null,
  });
}

/** Every loaded session as a row. */
export function useSessionRows(): SessionRow[] {
  const { sessions, executions, sleeves, performance } = useTradingStore(
    useShallow((s) => ({ sessions: s.sessions, executions: s.executions, sleeves: s.sleeves, performance: s.performance })),
  );
  return useMemo(
    () => sessions.map((s) => sessionRow(s, executions, sleeves, performance)),
    [sessions, executions, sleeves, performance],
  );
}

export function rejectedOf(orders: readonly Order[]): RejectedInput[] {
  return orders
    .filter((o) => o.status === OrderStatus.REJECTED)
    .map((o) => ({
      id: o.id,
      side: o.side === OrderSide.SELL ? 'sell' : 'buy',
      symbol: o.symbol,
      quantity: num(o.quantity),
      message: o.statusMessage,
      at: ms(toDate(o.submittedAt) ?? toDate(o.createdAt)),
      sessionId: o.sessionId,
    }));
}

export function useNeedsYou(rows: readonly SessionRow[]): NeedsItem[] {
  const orders = useTradingStore((s) => s.orders);
  return useMemo(() => needsYou(rows, rejectedOf(orders), clock), [rows, orders]);
}

/** Filled orders as fills, at their average fill price. */
export function fillsOf(orders: readonly Order[]): FillInput[] {
  return orders
    .filter((o) => o.status === OrderStatus.FILLED || (o.status === OrderStatus.PARTIAL && num(o.filledQuantity) > 0))
    .map((o) => ({
      id: o.id,
      symbol: o.symbol,
      side: o.side === OrderSide.SELL ? ('sell' as const) : ('buy' as const),
      quantity: num(o.filledQuantity) || num(o.quantity),
      price: num(o.averageFillPrice),
      at: ms(toDate(o.filledAt) ?? toDate(o.submittedAt) ?? toDate(o.createdAt)) ?? 0,
    }))
    .filter((f) => f.at > 0 && f.quantity > 0);
}

/** Fills keyed by the session that placed them. */
export function fillsBySession(orders: readonly Order[]): Map<string, FillInput[]> {
  const sessionOf = new Map(orders.map((o) => [o.id, o.sessionId]));
  const map = new Map<string, FillInput[]>();
  for (const f of fillsOf(orders)) {
    const id = sessionOf.get(f.id) ?? '';
    const list = map.get(id);
    if (list) list.push(f);
    else map.set(id, [f]);
  }
  return map;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "10:31" in the device's time. */
export function clock(t: number): string {
  const d = new Date(t);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** "Nov 12". */
export function day(t: number | null): string {
  if (t === null) return '';
  const d = new Date(t);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

/** "Today" for today, else "Nov 12". */
export function dayOrToday(t: number): string {
  const d = new Date(t);
  const now = new Date();
  return d.toDateString() === now.toDateString() ? 'Today' : day(t);
}
