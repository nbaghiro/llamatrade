import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useMemo } from 'react';

import { buildSessionRow, type SessionRow } from '../sessions/sessionRows';

/** Every session with its name, state and figures, from what the trading store has loaded. */
export function useSessionRows(): SessionRow[] {
  const sessions = useTradingStore((s) => s.sessions);
  const executions = useTradingStore((s) => s.executions);
  const sleeves = useTradingStore((s) => s.sleeves);
  const performance = useTradingStore((s) => s.performance);
  const orders = useTradingStore((s) => s.orders);
  const strategies = useStrategiesStore((s) => s.strategies);
  return useMemo(
    () =>
      sessions.map((session) =>
        buildSessionRow(session, { executions, sleeves, performance, strategies, orders })
      ),
    [sessions, executions, sleeves, performance, strategies, orders]
  );
}
