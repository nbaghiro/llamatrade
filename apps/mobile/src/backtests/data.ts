import { num, toDate } from '@llamatrade/core/format';
import { getTenantContext } from '@llamatrade/core/net';
import { BacktestStatus, type BacktestRun, type BacktestTrade, type EquityPoint } from '@llamatrade/core/proto/backtest_pb';
import { useEffect, useState } from 'react';

import { backtestClient } from '../net/clients';
import type { HeldSpan, Point, RunListItem } from './model';

export function pointsOf(curve: readonly EquityPoint[] | undefined): Point[] {
  const out: Point[] = [];
  for (const p of curve ?? []) {
    const at = toDate(p.timestamp)?.getTime();
    const value = num(p.equity);
    if (at !== undefined && value > 0) out.push({ at, value });
  }
  return out;
}

export function stateOf(status: BacktestStatus): RunListItem['state'] {
  switch (status) {
    case BacktestStatus.COMPLETED:
      return 'completed';
    case BacktestStatus.RUNNING:
      return 'running';
    case BacktestStatus.FAILED:
      return 'failed';
    case BacktestStatus.CANCELLED:
      return 'cancelled';
    default:
      return 'pending';
  }
}

/** A run as a history row; the strategy's name comes from the caller. */
export function listItem(run: BacktestRun, name: string, metrics?: { totalReturn?: { value: string }; sharpeRatio?: { value: string } }): RunListItem {
  const m = metrics ?? run.results?.metrics;
  return {
    id: run.id,
    strategyId: run.strategyId,
    name,
    version: run.strategyVersion,
    at: (toDate(run.completedAt) ?? toDate(run.createdAt))?.getTime() ?? 0,
    ret: m?.totalReturn?.value ? num(m.totalReturn) : null,
    sharpe: m?.sharpeRatio?.value ? num(m.sharpeRatio) : null,
    state: stateOf(run.status),
  };
}

/** What a run held and when, from its round-trip trades; an open trade runs to the end. */
export function heldSpans(trades: readonly BacktestTrade[], end: number): HeldSpan[] {
  const out: HeldSpan[] = [];
  for (const t of trades) {
    const from = toDate(t.entryTime)?.getTime();
    if (from === undefined) continue;
    out.push({ symbol: t.symbol, from, to: toDate(t.exitTime)?.getTime() ?? end });
  }
  return out;
}

const runCache = new Map<string, Promise<BacktestRun | null>>();
const listCache = new Map<string, Promise<BacktestRun[]>>();

/** One run with results, cached for the app's lifetime once completed. */
export function loadRun(id: string, fresh = false): Promise<BacktestRun | null> {
  let p = fresh ? undefined : runCache.get(id);
  if (!p) {
    p = backtestClient
      .getBacktest({ context: getTenantContext(), backtestId: id })
      .then((r) => r.backtest ?? null);
    const cached = p;
    p.then((run) => {
      if (!run || run.status !== BacktestStatus.COMPLETED) runCache.delete(id);
    }).catch(() => runCache.delete(id));
    runCache.set(id, cached);
  }
  return p;
}

/** A strategy's runs without results, newest first by the service's order. */
export function loadRunsFor(strategyId: string, fresh = false): Promise<BacktestRun[]> {
  let p = fresh ? undefined : listCache.get(strategyId);
  if (!p) {
    p = backtestClient
      .listBacktests({ context: getTenantContext(), strategyId, pagination: { page: 1, pageSize: 50 } })
      .then((r) => r.backtests);
    p.catch(() => listCache.delete(strategyId));
    listCache.set(strategyId, p);
  }
  return p;
}

export type Load<T> = { status: 'loading' } | { status: 'error' } | { status: 'ready'; value: T };

/** A promise-returning read as state, re-run when the key changes or `retry` is called. */
export function useLoad<T>(key: string | null, read: () => Promise<T>): Load<T> & { retry: () => void } {
  const [state, setState] = useState<Load<T>>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (key === null) return;
    let live = true;
    setState({ status: 'loading' });
    read()
      .then((value) => live && setState({ status: 'ready', value }))
      .catch(() => live && setState({ status: 'error' }));
    return () => {
      live = false;
    };
    // `read` is keyed by `key`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);
  return { ...state, retry: () => setAttempt((a) => a + 1) };
}
