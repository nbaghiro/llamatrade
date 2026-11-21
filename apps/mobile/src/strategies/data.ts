import { num, toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { StrategyEquityPoint } from '@llamatrade/core/proto/portfolio_pb';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useEffect, useMemo, useState } from 'react';

import { loadRun, loadRunsFor, pointsOf } from '../backtests/data';
import { useSessionRows } from '../sessions/data';
import type { SessionRow } from '../sessions/model';
import { compareSameDates, pickSameDatesRun, type DatedValue, type RunMeta, type SameDates, type SessionFact } from './model';

export function runMeta(r: BacktestRun): RunMeta {
  return {
    id: r.id,
    completed: r.status === BacktestStatus.COMPLETED,
    start: toDate(r.config?.startDate)?.getTime() ?? null,
    end: toDate(r.config?.endDate)?.getTime() ?? null,
    version: r.strategyVersion,
    createdAt: toDate(r.createdAt)?.getTime() ?? 0,
  };
}

export function equityPoints(points: readonly StrategyEquityPoint[] | undefined): DatedValue[] {
  const out: DatedValue[] = [];
  for (const p of points ?? []) {
    const at = toDate(p.timestamp)?.getTime();
    const value = num(p.equity);
    if (at !== undefined && value > 0) out.push({ at, value });
  }
  return out;
}

/** Sessions as the stage logic reads them. */
export function sessionFacts(rows: readonly SessionRow[]): SessionFact[] {
  return rows.map((r) => ({ strategyId: r.strategyId, state: r.state, mode: r.mode, startedAt: r.startedAt, endedAt: r.endedAt }));
}

/** Every session row, with the equity curves loaded once. */
export function useSessionsWithCurves(): { rows: SessionRow[]; curves: Record<string, DatedValue[]>; loaded: boolean } {
  const rows = useSessionRows();
  const loaded = useTradingStore((s) => s.loaded);
  const curvesLoaded = useTradingStore((s) => s.curvesLoaded);
  const raw = useTradingStore((s) => s.curves);
  const executions = useTradingStore((s) => s.executions);
  useEffect(() => {
    const st = useTradingStore.getState();
    if (!st.loaded && !st.loading) st.loadBlotter().then(() => useTradingStore.getState().loadCurves()).catch(() => undefined);
    else if (st.loaded && !st.curvesLoaded) st.loadCurves().catch(() => undefined);
  }, [loaded, executions.length]);
  const curves = useMemo(() => {
    const out: Record<string, DatedValue[]> = {};
    for (const [id, c] of Object.entries(raw)) out[id] = equityPoints(c.points);
    return out;
  }, [raw]);
  return { rows, curves, loaded: loaded && curvesLoaded };
}

export type SameDatesState =
  | { status: 'loading' }
  | { status: 'none' }
  | { status: 'error' }
  | { status: 'ready'; same: SameDates; run: BacktestRun };

/** A session's curve against the completed backtest that best covers the same dates. */
export function useSameDates(strategyId: string, points: readonly DatedValue[], startedAt: number | null, version: number | null): SameDatesState {
  const [state, setState] = useState<SameDatesState>({ status: 'loading' });
  const lastAt = points.length ? points[points.length - 1].at : 0;
  useEffect(() => {
    let live = true;
    if (!startedAt || points.length < 2) {
      setState({ status: 'none' });
      return;
    }
    loadRunsFor(strategyId)
      .then(async (runs) => {
        const pick = pickSameDatesRun(runs.map(runMeta), startedAt, lastAt || Date.now(), version);
        if (!pick) return live && setState({ status: 'none' });
        const run = await loadRun(pick.id);
        const same = run ? compareSameDates(points, pointsOf(run.results?.equityCurve)) : null;
        if (!live) return;
        setState(run && same ? { status: 'ready', same, run } : { status: 'none' });
      })
      .catch(() => live && setState({ status: 'error' }));
    return () => {
      live = false;
    };
    // Points are identified by their count and last date.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyId, startedAt, version, points.length, lastAt]);
  return state;
}
