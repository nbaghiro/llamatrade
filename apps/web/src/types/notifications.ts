/** Display helpers for notification categories, severities, and channels. */

import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
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
  [NotificationCategory.EXECUTION_STARTED]: 'Session started',
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

/** The label for a category stored as a string in notification metadata, or null when unknown. */
export function metadataCategoryLabel(raw: string | undefined): string | null {
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isInteger(value)) return null;
  return CATEGORY_LABELS[value as NotificationCategory] ?? null;
}

const C = NotificationCategory;
const EMAIL = ChannelType.EMAIL;
const WEBHOOK = ChannelType.WEBHOOK;
const M = [EMAIL] as const;
const W = [WEBHOOK] as const;
const MW = [EMAIL, WEBHOOK] as const;

/**
 * External channels each category can reach, mirroring CATEGORY_SPECS in
 * services/notification/src/preferences.py. Preferences can only narrow these.
 */
export const DEFAULT_CHANNELS: Partial<Record<NotificationCategory, readonly ChannelType[]>> = {
  [C.SLEEVE_FROZEN]: MW,
  [C.FILL_QUARANTINED]: MW,
  [C.EXTERNAL_TRADE_ADOPTED]: W,
  [C.CORPORATE_ACTION_PROPOSED]: M,
  [C.ORDER_FILLED]: W,
  [C.ORDER_REJECTED]: W,
  [C.POSITION_OPENED]: W,
  [C.POSITION_CLOSED]: W,
  [C.POSITION_DRIFT]: MW,
  [C.RISK_BREACH]: W,
  [C.EVALUATION_STALLED]: MW,
  [C.SYMBOL_NOT_TRADABLE]: MW,
  [C.CONNECTION_LOST]: MW,
  [C.STRATEGY_ERROR]: MW,
  [C.SESSION_ERROR]: MW,
  [C.CIRCUIT_BREAKER_TRIGGERED]: MW,
  [C.CIRCUIT_BREAKER_RESET]: W,
  [C.STOP_LOSS_HIT]: W,
  [C.TAKE_PROFIT_HIT]: W,
  [C.RECONCILIATION_DRIFT]: MW,
  [C.FUNDING_FAILED]: M,
  [C.SLEEVE_RELEASE_DEFERRED]: M,
  [C.PAYMENT_SUCCEEDED]: M,
  [C.PAYMENT_FAILED]: M,
  [C.TRIAL_ENDING]: M,
  [C.SUBSCRIPTION_UPDATED]: M,
  [C.SUBSCRIPTION_CANCELED]: M,
  [C.WEBHOOK_DISABLED]: M,
};

/** Critical-severity categories, which always reach email whatever the matrix says. */
export const ALWAYS_EMAIL: ReadonlySet<NotificationCategory> = new Set([
  C.SLEEVE_FROZEN,
  C.FILL_QUARANTINED,
  C.SESSION_ERROR,
  C.CIRCUIT_BREAKER_TRIGGERED,
  C.SLEEVE_RELEASE_DEFERRED,
  C.PAYMENT_FAILED,
]);

export const PREFERENCE_CHANNELS = [EMAIL, WEBHOOK] as const;
export type PreferenceChannel = (typeof PREFERENCE_CHANNELS)[number];

export interface ChannelPrefLike {
  channel: ChannelType;
  enabled: boolean;
  categories: readonly NotificationCategory[];
}

/** locked: always emails; unavailable: the category never goes to this channel. */
export type CellState = 'locked' | 'on' | 'off' | 'unavailable';

export function canReach(channel: ChannelType, category: NotificationCategory): boolean {
  return (DEFAULT_CHANNELS[category] ?? []).includes(channel);
}

function chosen(
  prefs: readonly ChannelPrefLike[],
  channel: ChannelType,
  category: NotificationCategory
): boolean {
  const pref = prefs.find((p) => p.channel === channel);
  if (!pref) return true;
  if (!pref.enabled) return false;
  return pref.categories.length === 0 || pref.categories.includes(category);
}

/** What one box in the matrix shows, resolved the same way the notification service routes. */
export function cellState(
  prefs: readonly ChannelPrefLike[],
  channel: ChannelType,
  category: NotificationCategory
): CellState {
  if (channel === EMAIL && ALWAYS_EMAIL.has(category)) return 'locked';
  if (!canReach(channel, category)) return 'unavailable';
  return chosen(prefs, channel, category) ? 'on' : 'off';
}

/**
 * The preferences to save after flipping one box. An empty category list means "every default",
 * so a channel with everything on saves as empty and one with nothing on saves as disabled.
 */
export function toggledPreferences(
  prefs: readonly ChannelPrefLike[],
  channel: PreferenceChannel,
  category: NotificationCategory
): ChannelPrefLike[] {
  return PREFERENCE_CHANNELS.map((ch) => {
    const existing = prefs.find((p) => p.channel === ch);
    if (ch !== channel) {
      return existing ?? { channel: ch, enabled: true, categories: [] };
    }
    const eligible = (Object.keys(DEFAULT_CHANNELS).map(Number) as NotificationCategory[])
      .filter((c) => canReach(ch, c))
      .sort((a, b) => a - b);
    if (!eligible.includes(category)) {
      return existing ?? { channel: ch, enabled: true, categories: [] };
    }
    const on = new Set(eligible.filter((c) => chosen(prefs, ch, c)));
    if (on.has(category)) on.delete(category);
    else on.add(category);
    if (on.size === 0) return { channel: ch, enabled: false, categories: [] };
    if (on.size === eligible.length) return { channel: ch, enabled: true, categories: [] };
    return { channel: ch, enabled: true, categories: eligible.filter((c) => on.has(c)) };
  });
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

const PRICE_CONDITIONS = new Set([AlertConditionType.PRICE_ABOVE, AlertConditionType.PRICE_BELOW]);

/** "SPY · RSI above 70", "QQQ · Price move −3%", "TLT · Price below $90". */
export function alertConditionText(
  type: AlertConditionType | undefined,
  symbol?: string,
  threshold?: string
): string {
  const kind = type ?? AlertConditionType.UNSPECIFIED;
  const value = threshold?.trim() ?? '';
  const n = Number(value);
  let rule = CONDITION_TYPE_LABELS[kind] ?? 'Condition';
  if (kind === AlertConditionType.PRICE_CHANGE_PERCENT) {
    const signed = n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : `${n}`;
    rule = value ? `Price move ${Number.isFinite(n) ? signed : value}%` : 'Price move';
  } else if (value) {
    rule = `${rule} ${PRICE_CONDITIONS.has(kind) && Number.isFinite(n) ? `$${value}` : value}`;
  }
  return symbol ? `${symbol} · ${rule}` : rule;
}
