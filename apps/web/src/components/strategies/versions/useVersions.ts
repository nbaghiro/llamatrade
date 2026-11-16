import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { StrategyVersion } from '@llamatrade/core/proto/strategy_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { backtestClient } from '../../../services/grpc-client';
import { listStrategyVersions } from '../../../services/strategy';
import { getTenantContext } from '../../../store/auth';
import { latestRunPerVersion } from '../strategyView';

type Loaded =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; versions: StrategyVersion[] };

/** A strategy's saved versions, newest first, with the latest completed backtest of each. */
export function useVersions(strategyId: string) {
  const [state, setState] = useState<Loaded>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const backtests = useBacktestStore((s) => s.backtests);
  const listBacktests = useBacktestStore((s) => s.listBacktests);

  useEffect(() => {
    let live = true;
    setState({ status: 'loading' });
    listStrategyVersions(strategyId)
      .then((r) => {
        if (live)
          setState({
            status: 'ready',
            versions: [...r.versions].sort((a, b) => b.version - a.version),
          });
      })
      .catch(() => live && setState({ status: 'error' }));
    listBacktests(strategyId).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [strategyId, attempt, listBacktests]);

  const runs = useMemo(
    () => latestRunPerVersion(backtests.filter((b) => b.strategyId === strategyId)),
    [backtests, strategyId]
  );
  const reload = useCallback(() => setAttempt((a) => a + 1), []);
  return { state, runs, reload };
}

/** The full results of up to two runs, fetched only when both exist. */
export function useRunPair(a: BacktestRun | undefined, b: BacktestRun | undefined) {
  const [pair, setPair] = useState<[BacktestRun, BacktestRun] | null>(null);
  const aId = a?.id;
  const bId = b?.id;
  useEffect(() => {
    setPair(null);
    if (!aId || !bId) return;
    let live = true;
    const context = getTenantContext();
    Promise.all([
      backtestClient.getBacktest({ context, backtestId: aId }),
      backtestClient.getBacktest({ context, backtestId: bId }),
    ])
      .then(([ra, rb]) => {
        if (!live || !ra.backtest || !rb.backtest) return;
        if (
          ra.backtest.status !== BacktestStatus.COMPLETED ||
          rb.backtest.status !== BacktestStatus.COMPLETED
        )
          return;
        setPair([ra.backtest, rb.backtest]);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [aId, bId]);
  return pair;
}
