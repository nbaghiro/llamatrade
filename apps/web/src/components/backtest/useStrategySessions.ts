import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useEffect, useMemo } from 'react';

import { strategySessions, type StrategySession } from './strategySessions';

/** Every paper and live session with the version it runs; empty until the blotter loads. */
export function useStrategySessions(): { sessions: StrategySession[]; loaded: boolean } {
  const executions = useTradingStore((s) => s.executions);
  const sessions = useTradingStore((s) => s.sessions);
  const loaded = useTradingStore((s) => s.loaded);
  const loading = useTradingStore((s) => s.loading);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);

  useEffect(() => {
    if (!loaded && !loading) loadBlotter().catch(() => undefined);
  }, [loaded, loading, loadBlotter]);

  return useMemo(
    () => ({ sessions: strategySessions(executions, sessions), loaded }),
    [executions, sessions, loaded]
  );
}
