import {
  BacktestStatus,
  type BacktestMetrics,
  type BacktestRun,
  type BacktestTrade,
  type EquityPoint,
} from '@llamatrade/core/proto/backtest_pb';
import { OrderSide } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber, type RunProgressEvent } from '@llamatrade/core/stores/backtest';

import type {
  Curve,
  PartialMetricsInput,
  ProgressEvent,
  RunPhase,
  TradeInput,
} from '../../lib/backtestView';

export function phaseOf(status: BacktestStatus | undefined): RunPhase {
  switch (status) {
    case BacktestStatus.RUNNING:
      return 'running';
    case BacktestStatus.COMPLETED:
      return 'completed';
    case BacktestStatus.FAILED:
      return 'failed';
    case BacktestStatus.CANCELLED:
      return 'cancelled';
    default:
      return 'pending';
  }
}

export function toProgressEvents(events: readonly RunProgressEvent[]): ProgressEvent[] {
  return events.map((e) => ({
    phase: phaseOf(e.status),
    percent: e.percent,
    currentDate: e.currentDate,
    message: e.message,
    atMs: e.atMs,
  }));
}

export function toPartialInput(m: BacktestMetrics | null): PartialMetricsInput | null {
  if (!m) return null;
  return {
    totalReturn: m.totalReturn?.value,
    maxDrawdown: m.maxDrawdown?.value,
    benchmarkReturn: m.benchmarkReturn?.value,
  };
}

export function toCurve(points: readonly EquityPoint[] | undefined): Curve {
  const dates: Date[] = [];
  const values: number[] = [];
  for (const p of points ?? []) {
    const d = toDate(p.timestamp);
    if (!d) continue;
    dates.push(d);
    values.push(toNumber(p.equity));
  }
  return { dates, values };
}

export function toTradeInputs(trades: readonly BacktestTrade[]): TradeInput[] {
  return trades.map((t) => ({
    symbol: t.symbol,
    side: t.side === OrderSide.SELL ? 'SELL' : 'BUY',
    quantity: toNumber(t.quantity),
    entryPrice: toNumber(t.entryPrice),
    exitPrice: toNumber(t.exitPrice),
    entryTime: toDate(t.entryTime),
    exitTime: toDate(t.exitTime),
    pnl: toNumber(t.pnl),
    entryReason: t.entryReason,
    exitReason: t.exitReason,
  }));
}

export interface RunMeta {
  start: Date | null;
  end: Date | null;
  capital: number;
  benchmark: string;
}

export function runMeta(run: BacktestRun | null): RunMeta {
  const cfg = run?.config;
  return {
    start: toDate(cfg?.startDate),
    end: toDate(cfg?.endDate),
    capital: toNumber(cfg?.initialCapital),
    benchmark: run?.results?.benchmarkSymbol || cfg?.benchmarkSymbol || '',
  };
}

/** Seconds from start to completion, when both are known. */
export function runSeconds(run: BacktestRun | null): number | null {
  const a = toDate(run?.startedAt) ?? toDate(run?.createdAt);
  const b = toDate(run?.completedAt);
  return a && b ? Math.max(0, (b.getTime() - a.getTime()) / 1000) : null;
}

export function isFinished(status: BacktestStatus | undefined): boolean {
  return (
    status === BacktestStatus.COMPLETED ||
    status === BacktestStatus.FAILED ||
    status === BacktestStatus.CANCELLED
  );
}

/** Progress events reconstructed from a stored run's timestamps, for a run we didn't watch. */
export function eventsFromRun(run: BacktestRun): { events: ProgressEvent[]; startMs: number } {
  const created = toDate(run.createdAt)?.getTime() ?? 0;
  const started = toDate(run.startedAt)?.getTime() ?? created;
  const done = toDate(run.completedAt)?.getTime() ?? started;
  const phase = phaseOf(run.status);
  const end = toDate(run.config?.endDate);
  const events: ProgressEvent[] = [];
  if (phase !== 'pending' && run.startedAt) {
    events.push({ phase: 'running', percent: 0, currentDate: '', message: '', atMs: started });
  }
  if (phase === 'completed' || phase === 'failed' || phase === 'cancelled') {
    events.push({
      phase,
      percent: 100,
      currentDate: phase === 'completed' && end ? end.toISOString().slice(0, 10) : '',
      message: run.statusMessage,
      atMs: done,
    });
  }
  return { events, startMs: created };
}
