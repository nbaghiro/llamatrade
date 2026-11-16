import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { useMemo } from 'react';

import { aggregateAttention, type AttentionEntry } from './attention';

/** Frozen sleeves, recent rejected orders and unread high-priority notices, from what has loaded. */
export function useAttentionEntries(): AttentionEntry[] {
  const frozenSleeves = useDashboardStore((s) => s.frozenSleeves);
  const rejectedOrders = useDashboardStore((s) => s.rejectedOrders);
  const notifications = useNotificationsStore((s) => s.notifications);
  return useMemo(
    () => aggregateAttention({ frozenSleeves, rejectedOrders, notifications, now: new Date() }),
    [frozenSleeves, rejectedOrders, notifications]
  );
}
