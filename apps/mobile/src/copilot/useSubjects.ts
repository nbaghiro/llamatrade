import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { useDashboardStore, type DashboardStrategy } from '@llamatrade/core/stores/dashboard';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useEffect, useMemo } from 'react';

import { runStateOfExecution } from '../ui/status';
import { useCopilotUi } from './store';
import { buildSubjects, subjectFor, type CopilotSubject, type SessionState } from './subjects';

function sessionState(s: DashboardStrategy, frozen: ReadonlySet<string>): SessionState {
  if (frozen.has(s.id)) return 'frozen';
  const state = runStateOfExecution(s.status);
  return state === 'draft' || state === 'archived' ? 'stopped' : state;
}

/** Account, sessions and strategies as Copilot subjects, loading what's missing once. */
export function useSubjects(): { subjects: CopilotSubject[]; sessions: DashboardStrategy[] } {
  const sessions = useDashboardStore((s) => s.strategies);
  const frozenSleeves = useDashboardStore((s) => s.frozenSleeves);
  const dashboardLoaded = useDashboardStore((s) => s.loaded);
  const strategies = useStrategiesStore((s) => s.strategies);
  const backtestReturns = useStrategiesStore((s) => s.backtestReturns);

  useEffect(() => {
    if (!dashboardLoaded) useDashboardStore.getState().fetchDashboard().catch(() => undefined);
    const st = useStrategiesStore.getState();
    if (!st.strategies.length) {
      st.fetchStrategies()
        .then(() => useStrategiesStore.getState().fetchBacktestReturns())
        .catch(() => undefined);
    }
  }, [dashboardLoaded]);

  const subjects = useMemo(() => {
    const frozen = new Set((frozenSleeves ?? []).map((f) => f.executionId));
    const versions = new Map(strategies.map((s) => [s.id, s.version] as const));
    return buildSubjects(
      sessions.map((s) => ({
        id: s.id,
        strategyId: s.strategyId,
        name: s.name,
        live: s.mode === ExecutionMode.LIVE,
        state: sessionState(s, frozen),
        version: versions.get(s.strategyId) || undefined,
      })),
      strategies
        .filter((s) => s.status !== StrategyStatus.ARCHIVED)
        .map((s) => ({
          id: s.id,
          name: s.name,
          draft: s.status === StrategyStatus.DRAFT,
          version: s.version || undefined,
          backtested: backtestReturns[s.id] !== undefined,
        })),
    );
  }, [sessions, frozenSleeves, strategies, backtestReturns]);

  return { subjects, sessions };
}

/** The subject the current Copilot context names. */
export function useCurrentSubject(): { subject: CopilotSubject; subjects: CopilotSubject[]; sessions: DashboardStrategy[] } {
  const context = useCopilotUi((s) => s.context);
  const { subjects, sessions } = useSubjects();
  const subject = useMemo(() => subjectFor(context, subjects), [context, subjects]);
  return { subject, subjects, sessions };
}
