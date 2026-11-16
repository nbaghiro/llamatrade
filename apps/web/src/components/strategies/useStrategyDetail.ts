import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useEffect, useMemo, useState } from 'react';

import { getStrategy } from '../../services/strategy';
import { useRunningSession } from '../strategy-builder/hooks/useRunningSession';

import { metaLine, runState, stateLabel } from './strategyView';

type Loaded =
  | { status: 'loading' }
  | { status: 'missing' }
  | { status: 'error' }
  | { status: 'ready'; strategy: Strategy };

/** One strategy with its latest completed run, deployment and running session. */
export function useStrategyDetail(id: string | null) {
  const details = useStrategiesStore((s) => s.details);
  const listed = useStrategiesStore((s) => s.strategies);
  const runs = useStrategiesStore((s) => s.runs);
  const deployments = useStrategiesStore((s) => s.deployments);
  const fetchStrategyRun = useStrategiesStore((s) => s.fetchStrategyRun);
  const fetchDeployments = useStrategiesStore((s) => s.fetchDeployments);
  const [loaded, setLoaded] = useState<Loaded>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!id) return;
    let live = true;
    const cached = useStrategiesStore.getState().details[id];
    setLoaded(cached ? { status: 'ready', strategy: cached } : { status: 'loading' });
    getStrategy(id)
      .then((r) => {
        if (!live) return;
        const strategy = r.strategy;
        if (!strategy) {
          setLoaded({ status: 'missing' });
          return;
        }
        useStrategiesStore.setState((s) => ({ details: { ...s.details, [id]: strategy } }));
        setLoaded({ status: 'ready', strategy });
      })
      .catch((e: unknown) => {
        if (!live) return;
        const msg = e instanceof Error ? e.message : '';
        setLoaded(/not.?found/i.test(msg) ? { status: 'missing' } : { status: 'error' });
      });
    fetchStrategyRun(id).catch(() => undefined);
    if (Object.keys(useStrategiesStore.getState().deployments).length === 0) {
      fetchDeployments().catch(() => undefined);
    }
    return () => {
      live = false;
    };
  }, [id, attempt, fetchStrategyRun, fetchDeployments]);

  const session = useRunningSession(id);
  const summary = id ? (details[id] ?? listed.find((s) => s.id === id)) : undefined;
  const strategy = loaded.status === 'ready' ? loaded.strategy : summary;
  const deployment = id ? deployments[id] : undefined;
  const run = id ? runs[id] : undefined;

  return useMemo(() => {
    const state = strategy ? runState(strategy, deployment) : 'draft';
    return {
      status: strategy ? ('ready' as const) : loaded.status,
      strategy,
      run,
      deployment,
      session,
      state,
      stateLabel: stateLabel(state, deployment !== undefined),
      meta: strategy ? metaLine(strategy, deployment?.allocatedCapital ?? null) : '',
      retry: () => setAttempt((a) => a + 1),
    };
  }, [strategy, run, deployment, session, loaded.status]);
}
