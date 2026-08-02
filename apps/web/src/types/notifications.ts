/** Display helpers for notification categories, severities, and channels. */

import { NotificationCategory, NotificationSeverity } from '@llamatrade/core/proto/events_pb';
import { AlertConditionType, ChannelType } from '@llamatrade/core/proto/notification_pb';

export const CATEGORY_GROUPS: ReadonlyArray<{
  label: string;
  categories: ReadonlyArray<NotificationCategory>;
}> = [
  {
    label: 'Money',
    categories: [
      NotificationCategory.SLEEVE_FROZEN,
      NotificationCategory.FILL_QUARANTINED,
      NotificationCategory.EXTERNAL_TRADE_ADOPTED,
      NotificationCategory.CORPORATE_ACTION_PROPOSED,
      NotificationCategory.CORPORATE_ACTION_APPLIED,
    ],
  },
  {
    label: 'Trading',
    categories: [
      NotificationCategory.ORDER_FILLED,
      NotificationCategory.ORDER_REJECTED,
      NotificationCategory.POSITION_OPENED,
      NotificationCategory.POSITION_CLOSED,
      NotificationCategory.POSITION_DRIFT,
      NotificationCategory.RISK_BREACH,
      NotificationCategory.EVALUATION_STALLED,
      NotificationCategory.SYMBOL_NOT_TRADABLE,
      NotificationCategory.CONNECTION_LOST,
      NotificationCategory.STRATEGY_ERROR,
      NotificationCategory.SESSION_STARTED,
      NotificationCategory.SESSION_STOPPED,
      NotificationCategory.SESSION_ERROR,
      NotificationCategory.CIRCUIT_BREAKER_TRIGGERED,
      NotificationCategory.CIRCUIT_BREAKER_RESET,
      NotificationCategory.STOP_LOSS_HIT,
      NotificationCategory.TAKE_PROFIT_HIT,
      NotificationCategory.RECONCILIATION_DRIFT,
    ],
  },
  {
    label: 'Strategies',
    categories: [
      NotificationCategory.EXECUTION_STARTED,
      NotificationCategory.EXECUTION_STOPPED,
      NotificationCategory.FUNDING_FAILED,
      NotificationCategory.SLEEVE_RELEASE_DEFERRED,
      NotificationCategory.EXECUTION_CANCELLED,
      NotificationCategory.PLAN_LIMIT_REACHED,
      NotificationCategory.BACKTEST_COMPLETED,
      NotificationCategory.BACKTEST_FAILED,
    ],
  },
  {
    label: 'Billing & account',
    categories: [
      NotificationCategory.PAYMENT_SUCCEEDED,
      NotificationCategory.PAYMENT_FAILED,
      NotificationCategory.TRIAL_ENDING,
      NotificationCategory.SUBSCRIPTION_UPDATED,
      NotificationCategory.SUBSCRIPTION_CANCELED,
      NotificationCategory.CONFIRMATION_PENDING,
      NotificationCategory.PRICE_ALERT_TRIGGERED,
      NotificationCategory.WEBHOOK_DISABLED,
    ],
  },
];

const CATEGORY_LABELS: Partial<Record<NotificationCategory, string>> = {
  [NotificationCategory.SLEEVE_FROZEN]: 'Sleeve frozen',
  [NotificationCategory.FILL_QUARANTINED]: 'Fill quarantined',
  [NotificationCategory.EXTERNAL_TRADE_ADOPTED]: 'External trade detected',
  [NotificationCategory.CORPORATE_ACTION_PROPOSED]: 'Corporate action pending',
  [NotificationCategory.CORPORATE_ACTION_APPLIED]: 'Corporate action applied',
  [NotificationCategory.ORDER_FILLED]: 'Order filled',
  [NotificationCategory.ORDER_REJECTED]: 'Order rejected',
  [NotificationCategory.POSITION_OPENED]: 'Position opened',
  [NotificationCategory.POSITION_CLOSED]: 'Position closed',
  [NotificationCategory.POSITION_DRIFT]: 'Position drift',
  [NotificationCategory.RISK_BREACH]: 'Risk gate block',
  [NotificationCategory.EVALUATION_STALLED]: 'Evaluation stalled',
  [NotificationCategory.SYMBOL_NOT_TRADABLE]: 'Symbol not tradable',
  [NotificationCategory.CONNECTION_LOST]: 'Connection lost',
  [NotificationCategory.STRATEGY_ERROR]: 'Strategy error',
  [NotificationCategory.SESSION_STARTED]: 'Session started',
  [NotificationCategory.SESSION_STOPPED]: 'Session stopped',
  [NotificationCategory.SESSION_ERROR]: 'Session failed',
  [NotificationCategory.CIRCUIT_BREAKER_TRIGGERED]: 'Circuit breaker',
  [NotificationCategory.CIRCUIT_BREAKER_RESET]: 'Circuit breaker reset',
  [NotificationCategory.STOP_LOSS_HIT]: 'Stop loss hit',
  [NotificationCategory.TAKE_PROFIT_HIT]: 'Take profit hit',
  [NotificationCategory.RECONCILIATION_DRIFT]: 'Reconciliation drift',
  [NotificationCategory.EXECUTION_STARTED]: 'Strategy deployed',
  [NotificationCategory.EXECUTION_STOPPED]: 'Strategy stopped',
  [NotificationCategory.FUNDING_FAILED]: 'Funding failed',
  [NotificationCategory.SLEEVE_RELEASE_DEFERRED]: 'Capital release delayed',
  [NotificationCategory.EXECUTION_CANCELLED]: 'Execution cancelled',
  [NotificationCategory.PLAN_LIMIT_REACHED]: 'Plan limit reached',
  [NotificationCategory.BACKTEST_COMPLETED]: 'Backtest completed',
  [NotificationCategory.BACKTEST_FAILED]: 'Backtest failed',
  [NotificationCategory.PAYMENT_SUCCEEDED]: 'Payment received',
  [NotificationCategory.PAYMENT_FAILED]: 'Payment failed',
  [NotificationCategory.TRIAL_ENDING]: 'Trial ending',
  [NotificationCategory.SUBSCRIPTION_UPDATED]: 'Subscription updated',
  [NotificationCategory.SUBSCRIPTION_CANCELED]: 'Subscription canceled',
  [NotificationCategory.WELCOME]: 'Welcome',
  [NotificationCategory.PASSWORD_CHANGED]: 'Password changed',
  [NotificationCategory.ACCOUNT_LOCKED]: 'Sign-in attempts blocked',
  [NotificationCategory.EMAIL_VERIFICATION]: 'Email verification',
  [NotificationCategory.PASSWORD_RESET]: 'Password reset',
  [NotificationCategory.CONFIRMATION_PENDING]: 'Copilot approval pending',
  [NotificationCategory.PRICE_ALERT_TRIGGERED]: 'Price alert',
  [NotificationCategory.WEBHOOK_DISABLED]: 'Webhook disabled',
};

export function categoryLabel(category: NotificationCategory): string {
  return CATEGORY_LABELS[category] ?? 'Notification';
}

/** Severity → Badge variant, mirroring the email severity colors: actionable
 * = orange (primary), critical = red (danger), security = blue (accent). */
export function severityBadge(
  severity: NotificationSeverity,
): 'primary' | 'danger' | 'accent' | 'gray' {
  switch (severity) {
    case NotificationSeverity.CRITICAL:
      return 'danger';
    case NotificationSeverity.SECURITY:
      return 'accent';
    case NotificationSeverity.ACTIONABLE:
      return 'primary';
    default:
      return 'gray';
  }
}

export const CHANNEL_LABELS: Partial<Record<ChannelType, string>> = {
  [ChannelType.EMAIL]: 'Email',
  [ChannelType.WEBHOOK]: 'Webhook',
};

export const CONDITION_TYPE_LABELS: Partial<Record<AlertConditionType, string>> = {
  [AlertConditionType.PRICE_ABOVE]: 'Price above',
  [AlertConditionType.PRICE_BELOW]: 'Price below',
  [AlertConditionType.PRICE_CHANGE_PERCENT]: 'Price move %',
  [AlertConditionType.VOLUME_ABOVE]: 'Volume above',
  [AlertConditionType.RSI_ABOVE]: 'RSI above',
  [AlertConditionType.RSI_BELOW]: 'RSI below',
  [AlertConditionType.ORDER_FILLED]: 'Order filled',
  [AlertConditionType.RECONCILIATION_DRIFT]: 'Reconciliation drift',
  [AlertConditionType.SLEEVE_FROZEN]: 'Sleeve frozen',
};
