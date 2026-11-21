import { num, toDate } from '@llamatrade/core/format';
import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useEffect, useMemo, useState } from 'react';

import { backtestClient, portfolioClient } from '../../services/grpc-client';
import { getTenantContext } from '../../store/auth';
import type { SessionRow } from '../sessions/sessionRows';

import { useFullRun } from './detail/useRuns';
import {
  compareSameDates,
  dailyCloses,
  pickSameDatesRun,
  runPoints,
  type DatedValue,
  type SameDates,
} from './sameDates';

const SAMPLE_MINUTES = 60;
const RUNS_PAGE = 50;

const runsCache = new Map<string, Promise<BacktestRun[]>>();

/** A strategy's backtests without results, cached for the page's lifetime. */
function listRuns(strategyId: string): Promise<BacktestRun[]> {
  let p = runsCache.get(strategyId);
  if (!p) {
    const context = getTenantContext();
    p = backtestClient
      .listBacktests({ context, strategyId, pagination: { page: 1, pageSize: RUNS_PAGE } })
      .then((r) => r.backtests);
    p.catch(() => runsCache.delete(strategyId));
    runsCache.set(strategyId, p);
  }
  return p;
}

export type Load<T> = { status: 'loading' } | { status: 'error' } | { status: 'ready'; value: T };

export interface RunningCompare {
  curve: Load<DatedValue[]>;
  /** Undefined while the runs load; null when none covers the session's dates. */
  sameRun: BacktestRun | null | undefined;
  same: SameDates | null;
}

/** One open session's equity since it started, and the backtest over the same dates when one exists. */
export function useRunningCompare(row: SessionRow): RunningCompare {
  const executionId = row.execution?.id ?? '';
  const startMs = row.startedAt?.getTime() ?? 0;
  const strategyId = row.session.strategyId;
  const [curve, setCurve] = useState<Load<DatedValue[]>>({ status: 'loading' });
  const [runs, setRuns] = useState<BacktestRun[] | null | undefined>(undefined);

  useEffect(() => {
    const context = getTenantContext();
    if (!executionId || !startMs || !context) {
      setCurve({ status: 'ready', value: [] });
      return;
    }
    let live = true;
    setCurve({ status: 'loading' });
    portfolioClient
      .getStrategyEquityCurve({
        context,
        executionId,
        timeRange: {
          start: { seconds: BigInt(Math.floor(startMs / 1000)), nanos: 0 },
          end: { seconds: BigInt(Math.floor(Date.now() / 1000)), nanos: 0 },
        },
        sampleIntervalMinutes: SAMPLE_MINUTES,
      })
      .then((r) => {
        if (!live) return;
        const points: DatedValue[] = [];
        for (const p of r.equityCurve) {
          const at = toDate(p.timestamp);
          const value = num(p.equity);
          if (at && value > 0) points.push({ at, value });
        }
        setCurve({ status: 'ready', value: dailyCloses(points) });
      })
      .catch(() => live && setCurve({ status: 'error' }));
    return () => {
      live = false;
    };
  }, [executionId, startMs]);

  useEffect(() => {
    let live = true;
    setRuns(undefined);
    listRuns(strategyId)
      .then((r) => live && setRuns(r))
      .catch(() => live && setRuns(null));
    return () => {
      live = false;
    };
  }, [strategyId]);

  const pickedId = useMemo(() => {
    if (runs === undefined) return undefined;
    if (!runs || !row.startedAt) return null;
    return pickSameDatesRun(runs, row.startedAt, new Date(), row.version || null)?.id ?? null;
  }, [runs, row.startedAt, row.version]);

  const full = useFullRun(pickedId);
  const sameRun = pickedId === undefined ? undefined : pickedId === null ? null : full;

  const same = useMemo(
    () =>
      sameRun && curve.status === 'ready'
        ? compareSameDates(curve.value, runPoints(sameRun))
        : null,
    [sameRun, curve]
  );

  return { curve, sameRun, same };
}
