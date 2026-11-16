import { NotificationCategory, NotificationSeverity } from '@llamatrade/core/proto/events_pb';
import {
  NotificationPriority,
  NotificationType,
  type Notification,
} from '@llamatrade/core/proto/notification_pb';

/** Kinds that mean something is frozen, rejected or failed and needs a look. */
const ATTENTION_CATEGORIES: ReadonlySet<NotificationCategory> = new Set([
  NotificationCategory.SLEEVE_FROZEN,
  NotificationCategory.FILL_QUARANTINED,
  NotificationCategory.ORDER_REJECTED,
  NotificationCategory.RISK_BREACH,
  NotificationCategory.RECONCILIATION_DRIFT,
  NotificationCategory.EVALUATION_STALLED,
  NotificationCategory.SYMBOL_NOT_TRADABLE,
  NotificationCategory.CONNECTION_LOST,
  NotificationCategory.STRATEGY_ERROR,
  NotificationCategory.SESSION_ERROR,
  NotificationCategory.CIRCUIT_BREAKER_TRIGGERED,
  NotificationCategory.FUNDING_FAILED,
  NotificationCategory.BACKTEST_FAILED,
  NotificationCategory.PAYMENT_FAILED,
  NotificationCategory.WEBHOOK_DISABLED,
  NotificationCategory.ACCOUNT_LOCKED,
]);

type NotificationLike = Pick<Notification, 'type' | 'metadata'>;

function metaInt(n: NotificationLike, key: string): number | null {
  const raw = n.metadata[key];
  if (raw === undefined || raw.trim() === '') return null;
  const v = Number(raw);
  return Number.isInteger(v) ? v : null;
}

/** True when a notification is shown in amber: high priority, critical, or a frozen/rejected/failed kind. */
export function needsAttention(n: NotificationLike): boolean {
  const priority = metaInt(n, 'priority');
  if (priority === NotificationPriority.HIGH || priority === NotificationPriority.CRITICAL) {
    return true;
  }
  if (metaInt(n, 'severity') === NotificationSeverity.CRITICAL) return true;
  const category = metaInt(n, 'category');
  if (category !== null && ATTENTION_CATEGORIES.has(category as NotificationCategory)) return true;
  return n.type === NotificationType.ERROR || n.type === NotificationType.ALERT;
}

/** "10:15" for today, "Nov 12" before that, in the viewer's time zone. */
export function noticeTime(created: Date | null, now: Date): string {
  if (!created) return '';
  const sameDay = created.toDateString() === now.toDateString();
  return sameDay
    ? created.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: false })
    : created.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
