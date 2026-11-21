import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useMemo } from 'react';

import { sessionsAttention, type SessionsAttention } from './attentionModel';

/** The Sessions tab's mark from whatever has loaded: Home's read and the trading store's. */
export function useSessionsAttention(): SessionsAttention {
  const dashboardFrozen = useDashboardStore((s) => s.frozenSleeves);
  const rejected = useDashboardStore((s) => s.rejectedOrders);
  const sleeves = useTradingStore((s) => s.sleeves);
  return useMemo(
    () =>
      sessionsAttention(
        dashboardFrozen,
        sleeves.filter((s) => s.status === SleeveStatus.FROZEN).map((s) => ({ id: s.id, name: s.name })),
        rejected ? rejected.map((r) => ({ id: r.id, name: r.symbol })) : null,
      ),
    [dashboardFrozen, sleeves, rejected],
  );
}
