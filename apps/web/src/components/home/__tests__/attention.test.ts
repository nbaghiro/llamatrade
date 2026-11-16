import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import { NotificationPriority } from '@llamatrade/core/proto/notification_pb';
import { OrderSide } from '@llamatrade/core/proto/trading_pb';
import type { FrozenSleeve, RejectedOrder } from '@llamatrade/core/stores/dashboard';
import { describe, expect, it } from 'vitest';

import {
  REJECTED_WINDOW_HOURS,
  aggregateAttention,
  internalLink,
  sessionsSummary,
  type AttentionSources,
} from '../attention';

const NOW = new Date('2026-11-13T15:42:00Z');
const hoursAgo = (h: number) => new Date(NOW.getTime() - h * 3_600_000);

const sleeve = (over: Partial<FrozenSleeve> = {}): FrozenSleeve => ({
  id: 's1',
  name: 'Recession Radar',
  executionId: 'e1',
  ...over,
});

const order = (over: Partial<RejectedOrder> = {}): RejectedOrder => ({
  id: 'o1',
  symbol: 'TLT',
  side: OrderSide.BUY,
  quantity: 47,
  message: 'insufficient buying power',
  at: hoursAgo(2),
  strategyId: 'st1',
  sessionId: 'se1',
  ...over,
});

const notice = (
  over: { id?: string; isRead?: boolean; metadata?: Record<string, string> } = {}
) => ({
  id: over.id ?? 'n1',
  title: 'Session error',
  message: 'The session stopped evaluating',
  isRead: over.isRead ?? false,
  metadata: over.metadata ?? { priority: String(NotificationPriority.HIGH) },
});

const sources = (over: Partial<AttentionSources> = {}): AttentionSources => ({
  frozenSleeves: [],
  rejectedOrders: [],
  notifications: [],
  now: NOW,
  ...over,
});

describe('aggregateAttention', () => {
  it('is empty when nothing needs attention', () => {
    expect(aggregateAttention(sources())).toEqual([]);
  });

  it('shows nothing when none of the sources loaded', () => {
    expect(aggregateAttention(sources({ frozenSleeves: null, rejectedOrders: null }))).toEqual([]);
  });

  it('names a frozen sleeve and sends Review to the portfolio', () => {
    const [entry] = aggregateAttention(sources({ frozenSleeves: [sleeve()] }));
    expect(entry).toMatchObject({
      id: 'frozen-s1',
      kind: 'frozen',
      title: 'Recession Radar is frozen.',
      href: '/portfolio',
    });
    expect(entry.detail).toContain('wait');
  });

  it('describes a rejected order with Alpaca’s reason as a sentence', () => {
    const [entry] = aggregateAttention(sources({ rejectedOrders: [order()] }));
    expect(entry.title).toBe('A buy of 47 TLT was rejected.');
    expect(entry.detail).toBe('insufficient buying power.');
    expect(entry.href).toBe('/trading');
  });

  it('falls back to a plain reason and keeps fractional quantities', () => {
    const [entry] = aggregateAttention(
      sources({ rejectedOrders: [order({ message: '  ', quantity: 1.5, side: OrderSide.SELL })] })
    );
    expect(entry.title).toBe('A sell of 1.50 TLT was rejected.');
    expect(entry.detail).toBe('Alpaca did not accept the order.');
  });

  it('drops rejections outside the window and ones without a time', () => {
    const entries = aggregateAttention(
      sources({
        rejectedOrders: [
          order({ id: 'old', at: hoursAgo(REJECTED_WINDOW_HOURS + 1) }),
          order({ id: 'edge', at: hoursAgo(REJECTED_WINDOW_HOURS) }),
          order({ id: 'undated', at: null }),
        ],
      })
    );
    expect(entries.map((e) => e.id)).toEqual(['rejected-edge']);
  });

  it('orders frozen sleeves first, then rejections newest first, then notices', () => {
    const entries = aggregateAttention(
      sources({
        frozenSleeves: [sleeve()],
        rejectedOrders: [order({ id: 'a', at: hoursAgo(5) }), order({ id: 'b', at: hoursAgo(1) })],
        notifications: [notice()],
      })
    );
    expect(entries.map((e) => e.id)).toEqual([
      'frozen-s1',
      'rejected-b',
      'rejected-a',
      'notice-n1',
    ]);
  });

  it('includes only unread high or critical priority notices', () => {
    const entries = aggregateAttention(
      sources({
        notifications: [
          notice({ id: 'high' }),
          notice({ id: 'crit', metadata: { priority: String(NotificationPriority.CRITICAL) } }),
          notice({ id: 'normal', metadata: { priority: String(NotificationPriority.MEDIUM) } }),
          notice({ id: 'read', isRead: true }),
          notice({ id: 'none', metadata: {} }),
        ],
      })
    );
    expect(entries.map((e) => e.id)).toEqual(['notice-high', 'notice-crit']);
  });

  it('skips notices that repeat a source that loaded, and keeps them when it did not', () => {
    const frozenNotice = notice({
      id: 'fz',
      metadata: {
        priority: String(NotificationPriority.HIGH),
        category: String(NotificationCategory.SLEEVE_FROZEN),
      },
    });
    const rejectedNotice = notice({
      id: 'rj',
      metadata: {
        priority: String(NotificationPriority.HIGH),
        category: String(NotificationCategory.ORDER_REJECTED),
      },
    });
    const loaded = aggregateAttention(sources({ notifications: [frozenNotice, rejectedNotice] }));
    expect(loaded).toEqual([]);

    const failed = aggregateAttention(
      sources({
        frozenSleeves: null,
        rejectedOrders: null,
        notifications: [frozenNotice, rejectedNotice],
      })
    );
    expect(failed.map((e) => e.id)).toEqual(['notice-fz', 'notice-rj']);
  });

  it('links a notice only to an in-app path', () => {
    const [inApp, external] = aggregateAttention(
      sources({
        notifications: [
          notice({
            id: 'a',
            metadata: { priority: String(NotificationPriority.HIGH), link: '/trading?session=1' },
          }),
          notice({
            id: 'b',
            metadata: { priority: String(NotificationPriority.HIGH), link: 'https://example.com' },
          }),
        ],
      })
    );
    expect(inApp.href).toBe('/trading?session=1');
    expect(external.href).toBe('/settings/notifications');
  });
});

describe('internalLink', () => {
  it('accepts app paths and rejects anything that could leave the app', () => {
    expect(internalLink('/portfolio')).toBe('/portfolio');
    expect(internalLink('//evil.example')).toBeNull();
    expect(internalLink('javascript:alert(1)')).toBeNull();
    expect(internalLink(undefined)).toBeNull();
  });
});

describe('sessionsSummary', () => {
  it('counts sessions and attention with the right plurals', () => {
    expect(sessionsSummary(3, 1)).toBe('3 paper sessions, 1 needs attention');
    expect(sessionsSummary(1, 0)).toBe('1 paper session');
    expect(sessionsSummary(0, 2)).toBe('0 paper sessions, 2 need attention');
  });
});
