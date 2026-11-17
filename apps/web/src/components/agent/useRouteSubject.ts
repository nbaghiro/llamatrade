import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useMemo } from 'react';

import { etToday } from '../sessions/sessionRows';
import { useSessionRows } from '../shell/useSessionRows';

import { buildSubjects, findSubject, strategySubject, type CopilotSubject } from './subjects';

/** The subject key a page's path is about: a session, a strategy or a backtest. */
export function routeSubjectKey(pathname: string): string | null {
  const session = pathname.match(/^\/trading\/(?!orders\/)([^/]+)$/);
  if (session) return `session:${session[1]}`;
  const strategy = pathname.match(/^\/strategies\/(?!templates|builder)([^/]+)(?:\/[^/]+)?$/);
  if (strategy && !pathname.endsWith('/edit')) return `strategy:${strategy[1]}`;
  const backtest = pathname.match(/^\/backtest\/([^/]+)$/);
  if (backtest) return `backtest:${backtest[1]}`;
  if (pathname === '/portfolio' || pathname === '/dashboard') return 'account';
  return null;
}

/** The subject of the page being viewed, so a question asked from it starts with that context. */
export function useRouteSubject(pathname: string): CopilotSubject | null {
  const rows = useSessionRows();
  const strategies = useStrategiesStore((s) => s.strategies);
  const runs = useBacktestStore((s) => s.backtests);
  return useMemo(() => {
    const key = routeSubjectKey(pathname);
    if (!key) return null;
    const groups = buildSubjects(rows, strategies, runs, etToday(), Number.POSITIVE_INFINITY);
    const found = findSubject(groups, key);
    if (found || !key.startsWith('strategy:')) return found;
    const s = strategies.find((st) => `strategy:${st.id}` === key);
    return s ? strategySubject(s) : null;
  }, [pathname, rows, strategies, runs]);
}
