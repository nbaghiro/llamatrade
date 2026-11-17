import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useEffect, useMemo, useState } from 'react';

import { backtestClient } from '../../../services/grpc-client';
import { getTenantContext } from '../../../store/auth';
import { newestFirst } from '../strategyView';

/** Every backtest of a strategy, newest first, from the backtest store. */
export function useStrategyRuns(strategyId: string) {
  const backtests = useBacktestStore((s) => s.backtests);
  const loading = useBacktestStore((s) => s.loading);
  const listBacktests = useBacktestStore((s) => s.listBacktests);
  useEffect(() => {
    listBacktests(strategyId).catch(() => undefined);
  }, [strategyId, listBacktests]);
  const runs = useMemo(
    () => newestFirst(backtests.filter((b) => b.strategyId === strategyId)),
    [backtests, strategyId]
  );
  return { runs, loading };
}

const cache = new Map<string, Promise<BacktestRun | null>>();

function fetchRun(id: string): Promise<BacktestRun | null> {
  let p = cache.get(id);
  if (!p) {
    const context = getTenantContext();
    p = backtestClient
      .getBacktest({ context, backtestId: id })
      .then((r) => (r.backtest?.status === BacktestStatus.COMPLETED ? r.backtest : null));
    p.catch(() => cache.delete(id));
    cache.set(id, p);
  }
  return p;
}

/** One completed run with its full results; undefined while loading, null when unavailable. */
export function useFullRun(id: string | null | undefined): BacktestRun | null | undefined {
  const [run, setRun] = useState<BacktestRun | null | undefined>(id ? undefined : null);
  useEffect(() => {
    if (!id) {
      setRun(null);
      return;
    }
    let live = true;
    setRun(undefined);
    fetchRun(id)
      .then((r) => live && setRun(r))
      .catch(() => live && setRun(null));
    return () => {
      live = false;
    };
  }, [id]);
  return run;
}
