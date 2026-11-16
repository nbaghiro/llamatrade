import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import { NotificationPriority, type Notification } from '@llamatrade/core/proto/notification_pb';
import { OrderSide } from '@llamatrade/core/proto/trading_pb';
import type { FrozenSleeve, RejectedOrder } from '@llamatrade/core/stores/dashboard';

import { formatNumber } from '../../lib/format';

/** Rejections older than this are history rather than something to act on. */
export const REJECTED_WINDOW_HOURS = 72;

export type AttentionKind = 'frozen' | 'rejected' | 'notice';

export interface AttentionEntry {
  id: string;
  kind: AttentionKind;
  title: string;
  detail: string;
  /** Where "Review" goes. */
  href: string;
}

export interface AttentionSources {
  /** null when the ledger read failed. */
  frozenSleeves: readonly FrozenSleeve[] | null;
  /** null when the trading read failed. */
  rejectedOrders: readonly RejectedOrder[] | null;
  notifications: readonly Pick<Notification, 'id' | 'title' | 'message' | 'isRead' | 'metadata'>[];
  now: Date;
}

function metaInt(n: Pick<Notification, 'metadata'>, key: string): number | null {
  const raw = n.metadata[key];
  if (raw === undefined || raw.trim() === '') return null;
  const v = Number(raw);
  return Number.isInteger(v) ? v : null;
}

function isHighPriority(n: Pick<Notification, 'metadata'>): boolean {
  const p = metaInt(n, 'priority');
  return p === NotificationPriority.HIGH || p === NotificationPriority.CRITICAL;
}

/** Notices that repeat a frozen sleeve or rejected order already read directly. */
const COVERED: Partial<Record<NotificationCategory, keyof AttentionSources>> = {
  [NotificationCategory.SLEEVE_FROZEN]: 'frozenSleeves',
  [NotificationCategory.ORDER_REJECTED]: 'rejectedOrders',
};

function sideWord(side: OrderSide): string {
  if (side === OrderSide.BUY) return 'buy';
  if (side === OrderSide.SELL) return 'sell';
  return 'order';
}

/** An in-app path from notification data; anything else is ignored. */
export function internalLink(link: string | undefined): string | null {
  return link && link.startsWith('/') && !link.startsWith('//') ? link : null;
}

function sentence(text: string): string {
  const t = text.trim();
  if (!t) return '';
  return /[.!?]$/.test(t) ? t : `${t}.`;
}

/**
 * Everything Home should raise, most serious first: frozen sleeves, then recent rejected orders,
 * then unread high-priority notices. A source that failed to load contributes nothing.
 */
export function aggregateAttention({
  frozenSleeves,
  rejectedOrders,
  notifications,
  now,
}: AttentionSources): AttentionEntry[] {
  const out: AttentionEntry[] = [];

  for (const s of frozenSleeves ?? []) {
    out.push({
      id: `frozen-${s.id}`,
      kind: 'frozen',
      title: `${s.name || 'A sleeve'} is frozen.`,
      detail: "Its holdings don't match Alpaca. Orders for this sleeve wait until it's resolved.",
      href: '/portfolio',
    });
  }

  const cutoff = now.getTime() - REJECTED_WINDOW_HOURS * 3_600_000;
  const recent = (rejectedOrders ?? [])
    .filter((o) => o.at !== null && o.at.getTime() >= cutoff)
    .sort((a, b) => (b.at?.getTime() ?? 0) - (a.at?.getTime() ?? 0));
  for (const o of recent) {
    const qty = formatNumber(o.quantity, { dp: o.quantity % 1 === 0 ? 0 : 2 });
    out.push({
      id: `rejected-${o.id}`,
      kind: 'rejected',
      title: `A ${sideWord(o.side)} of ${qty} ${o.symbol} was rejected.`,
      detail: sentence(o.message) || 'Alpaca did not accept the order.',
      href: '/trading',
    });
  }

  for (const n of notifications) {
    if (n.isRead || !isHighPriority(n)) continue;
    const category = metaInt(n, 'category') as NotificationCategory | null;
    const coveredBy = category === null ? undefined : COVERED[category];
    if (coveredBy === 'frozenSleeves' && frozenSleeves !== null) continue;
    if (coveredBy === 'rejectedOrders' && rejectedOrders !== null) continue;
    out.push({
      id: `notice-${n.id}`,
      kind: 'notice',
      title: sentence(n.title) || 'A notice needs your attention.',
      detail: sentence(n.message),
      href: internalLink(n.metadata.link) ?? '/settings/notifications',
    });
  }

  return out;
}

/** "3 paper sessions, 1 needs attention" for the Home header. */
export function sessionsSummary(sessions: number, attention: number): string {
  const s = `${sessions} paper session${sessions === 1 ? '' : 's'}`;
  if (attention === 0) return s;
  return `${s}, ${attention} need${attention === 1 ? 's' : ''} attention`;
}
