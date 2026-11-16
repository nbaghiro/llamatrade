import type { Position, TradingSession } from '@llamatrade/core/proto/trading_pb';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useEffect, useMemo, useState } from 'react';

import { listRunningExecutions } from '../../../services/strategy';

export interface RunningSession {
  session: TradingSession | null;
  /** The exact version the session runs, from its execution; null when unknown. */
  version: number | null;
  positions: Position[];
  loading: boolean;
}

/** The paper session running this strategy, its version and its positions. */
export function useRunningSession(strategyId: string | null): RunningSession {
  const { sessions, positions, loaded, loading, loadBlotter } = useTradingStore();
  const [version, setVersion] = useState<number | null>(null);
  const [execLoading, setExecLoading] = useState(false);

  useEffect(() => {
    if (strategyId && !loaded && !loading) {
      loadBlotter().catch(() => undefined);
    }
  }, [strategyId, loaded, loading, loadBlotter]);

  useEffect(() => {
    if (!strategyId) {
      setVersion(null);
      return;
    }
    let live = true;
    setExecLoading(true);
    listRunningExecutions(strategyId)
      .then((execs) => {
        if (live) setVersion(execs[0]?.version || null);
      })
      .catch(() => {
        if (live) setVersion(null);
      })
      .finally(() => {
        if (live) setExecLoading(false);
      });
    return () => {
      live = false;
    };
  }, [strategyId]);

  return useMemo(() => {
    const session = strategyId
      ? (sessions.find((s) => s.strategyId === strategyId && s.isActive) ?? null)
      : null;
    return {
      session,
      version,
      positions: session ? positions.filter((p) => p.sessionId === session.id) : [],
      loading: (strategyId !== null && !loaded) || execLoading,
    };
  }, [strategyId, sessions, positions, loaded, version, execLoading]);
}
