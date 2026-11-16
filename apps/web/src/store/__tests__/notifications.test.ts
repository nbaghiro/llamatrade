/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  listNotifications,
  markAsRead,
  listWebhooks,
  createWebhook,
  updateWebhook,
  deleteWebhook,
  testWebhook,
  getPreferences,
  updatePreferences,
  listAlerts,
  createAlert,
  deleteAlert,
  toggleAlert,
} = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  markAsRead: vi.fn(),
  listWebhooks: vi.fn(),
  createWebhook: vi.fn(),
  updateWebhook: vi.fn(),
  deleteWebhook: vi.fn(),
  testWebhook: vi.fn(),
  getPreferences: vi.fn(),
  updatePreferences: vi.fn(),
  listAlerts: vi.fn(),
  createAlert: vi.fn(),
  deleteAlert: vi.fn(),
  toggleAlert: vi.fn(),
}));

vi.mock('@llamatrade/core/net', () => ({
  notificationClient: {
    listNotifications,
    markAsRead,
    listWebhooks,
    createWebhook,
    updateWebhook,
    deleteWebhook,
    testWebhook,
    getPreferences,
    updatePreferences,
    listAlerts,
    createAlert,
    deleteAlert,
    toggleAlert,
  },
  getTenantContext: () => ({ tenantId: 't1', userId: 'u1' }),
}));

import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import {
  AlertConditionType,
  ChannelType,
  type Notification,
  type Webhook,
} from '@llamatrade/core/proto/notification_pb';
import { HISTORY_PAGE_SIZE, useNotificationsStore } from '@llamatrade/core/stores/notifications';

import {
  ALWAYS_EMAIL,
  CATEGORY_GROUPS,
  DEFAULT_CHANNELS,
  alertConditionText,
  cellState,
  metadataCategoryLabel,
  toggledPreferences,
  type ChannelPrefLike,
} from '../../types/notifications';

function fakeNotification(id: string, isRead = false): Notification {
  return { id, isRead, title: 't', message: 'm', metadata: {} } as unknown as Notification;
}

function fakeWebhook(id: string, isActive = true): Webhook {
  return { id, name: 'w', url: 'https://x.test', events: [], isActive } as unknown as Webhook;
}

beforeEach(() => {
  vi.clearAllMocks();
  useNotificationsStore.setState({
    notifications: [],
    unreadCount: 0,
    webhooks: [],
    preferences: [],
    alerts: [],
    loading: false,
    error: null,
    history: {
      items: [],
      unreadOnly: false,
      page: 0,
      hasMore: false,
      total: 0,
      loading: false,
      error: null,
    },
  });
});

describe('notifications list', () => {
  it('hydrates list and unread count', async () => {
    listNotifications.mockResolvedValue({
      notifications: [fakeNotification('n1'), fakeNotification('n2', true)],
      unreadCount: 1,
    });
    await useNotificationsStore.getState().fetchNotifications();
    const state = useNotificationsStore.getState();
    expect(state.notifications).toHaveLength(2);
    expect(state.unreadCount).toBe(1);
  });

  it('markAsRead flips the row and decrements the badge', async () => {
    useNotificationsStore.setState({
      notifications: [fakeNotification('n1')],
      unreadCount: 1,
    });
    markAsRead.mockResolvedValue({ markedCount: 1 });
    await useNotificationsStore.getState().markAsRead('n1');
    const state = useNotificationsStore.getState();
    expect(state.notifications[0].isRead).toBe(true);
    expect(state.unreadCount).toBe(0);
    expect(markAsRead).toHaveBeenCalledWith(expect.objectContaining({ notificationId: 'n1' }));
  });

  it('markAllAsRead clears everything', async () => {
    useNotificationsStore.setState({
      notifications: [fakeNotification('n1'), fakeNotification('n2')],
      unreadCount: 2,
    });
    markAsRead.mockResolvedValue({ markedCount: 2 });
    await useNotificationsStore.getState().markAllAsRead();
    const state = useNotificationsStore.getState();
    expect(state.unreadCount).toBe(0);
    expect(state.notifications.every((n) => n.isRead)).toBe(true);
    expect(markAsRead).toHaveBeenCalledWith(expect.objectContaining({ markAll: true }));
  });

  it('fetch failure lands in error, not a throw', async () => {
    listNotifications.mockRejectedValue(new Error('mesh down'));
    await useNotificationsStore.getState().fetchNotifications();
    expect(useNotificationsStore.getState().error).toBe('mesh down');
  });
});

describe('webhooks', () => {
  it('create prepends and returns the one-time secret', async () => {
    createWebhook.mockResolvedValue({ webhook: fakeWebhook('w1'), secret: 's3cret' });
    const { secret } = await useNotificationsStore
      .getState()
      .createWebhook({ name: 'w', url: 'https://x.test', events: [] });
    expect(secret).toBe('s3cret');
    expect(useNotificationsStore.getState().webhooks).toHaveLength(1);
  });

  it('update replaces the row in place', async () => {
    useNotificationsStore.setState({ webhooks: [fakeWebhook('w1', true)] });
    updateWebhook.mockResolvedValue({ webhook: fakeWebhook('w1', false) });
    await useNotificationsStore.getState().updateWebhook(fakeWebhook('w1', false));
    expect(useNotificationsStore.getState().webhooks[0].isActive).toBe(false);
  });

  it('delete removes the row', async () => {
    useNotificationsStore.setState({ webhooks: [fakeWebhook('w1')] });
    deleteWebhook.mockResolvedValue({ success: true });
    await useNotificationsStore.getState().deleteWebhook('w1');
    expect(useNotificationsStore.getState().webhooks).toHaveLength(0);
  });

  it('test returns the raw response', async () => {
    testWebhook.mockResolvedValue({ success: true, statusCode: 204, message: 'delivered' });
    const result = await useNotificationsStore.getState().testWebhook('w1');
    expect(result.statusCode).toBe(204);
  });
});

describe('alerts and preferences', () => {
  it('toggle swaps the alert row', async () => {
    useNotificationsStore.setState({
      alerts: [{ id: 'a1', isActive: true } as never],
    });
    toggleAlert.mockResolvedValue({ alert: { id: 'a1', isActive: false } });
    await useNotificationsStore.getState().toggleAlert('a1', false);
    expect(useNotificationsStore.getState().alerts[0].isActive).toBe(false);
  });

  it('delete removes the alert', async () => {
    useNotificationsStore.setState({ alerts: [{ id: 'a1' } as never] });
    deleteAlert.mockResolvedValue({ success: true });
    await useNotificationsStore.getState().deleteAlert('a1');
    expect(useNotificationsStore.getState().alerts).toHaveLength(0);
  });

  it('preferences round-trip through the client', async () => {
    updatePreferences.mockResolvedValue({ preferences: [{ channel: 1, enabled: false }] });
    await useNotificationsStore.getState().updatePreferences([]);
    expect(useNotificationsStore.getState().preferences).toHaveLength(1);
  });
});

describe('mark as read keeps the bell and the full list in step', () => {
  it('flips the row in both lists and counts it once', async () => {
    useNotificationsStore.setState({
      notifications: [fakeNotification('n1')],
      unreadCount: 3,
      history: { ...useNotificationsStore.getState().history, items: [fakeNotification('n1')] },
    });
    markAsRead.mockResolvedValue({ markedCount: 1 });

    await useNotificationsStore.getState().markAsRead('n1');

    const state = useNotificationsStore.getState();
    expect(state.notifications[0].isRead).toBe(true);
    expect(state.history.items[0].isRead).toBe(true);
    expect(state.unreadCount).toBe(2);
  });

  it('leaves the badge alone when the row was already read', async () => {
    useNotificationsStore.setState({
      notifications: [fakeNotification('n1', true)],
      unreadCount: 2,
    });
    markAsRead.mockResolvedValue({ markedCount: 0 });

    await useNotificationsStore.getState().markAsRead('n1');

    expect(useNotificationsStore.getState().unreadCount).toBe(2);
  });

  it('mark all reads every history row too', async () => {
    useNotificationsStore.setState({
      unreadCount: 2,
      history: {
        ...useNotificationsStore.getState().history,
        items: [fakeNotification('a'), fakeNotification('b')],
      },
    });
    markAsRead.mockResolvedValue({ markedCount: 2 });

    await useNotificationsStore.getState().markAllAsRead();

    expect(useNotificationsStore.getState().history.items.every((n) => n.isRead)).toBe(true);
  });
});

describe('full notification history', () => {
  const page = (ids: string[], hasNext: boolean, totalItems = 40) => ({
    notifications: ids.map((id) => fakeNotification(id)),
    unreadCount: 5,
    pagination: { totalItems, hasNext },
  });

  it('loads page one with the filter and page size', async () => {
    listNotifications.mockResolvedValue(page(['a', 'b'], true));

    await useNotificationsStore.getState().fetchHistory(true);

    expect(listNotifications).toHaveBeenCalledWith(
      expect.objectContaining({
        unreadOnly: true,
        pagination: { page: 1, pageSize: HISTORY_PAGE_SIZE },
      })
    );
    const h = useNotificationsStore.getState().history;
    expect(h.items.map((n) => n.id)).toEqual(['a', 'b']);
    expect(h).toMatchObject({
      page: 1,
      hasMore: true,
      total: 40,
      unreadOnly: true,
      loading: false,
    });
    expect(useNotificationsStore.getState().unreadCount).toBe(5);
  });

  it('appends the next page and drops rows already shown', async () => {
    listNotifications.mockResolvedValueOnce(page(['a', 'b'], true));
    await useNotificationsStore.getState().fetchHistory(false);
    listNotifications.mockResolvedValueOnce(page(['b', 'c'], false));

    await useNotificationsStore.getState().fetchMoreHistory();

    expect(listNotifications).toHaveBeenLastCalledWith(
      expect.objectContaining({
        unreadOnly: false,
        pagination: { page: 2, pageSize: HISTORY_PAGE_SIZE },
      })
    );
    const h = useNotificationsStore.getState().history;
    expect(h.items.map((n) => n.id)).toEqual(['a', 'b', 'c']);
    expect(h.hasMore).toBe(false);
  });

  it('does nothing more once the last page is in', async () => {
    listNotifications.mockResolvedValue(page(['a'], false));
    await useNotificationsStore.getState().fetchHistory(false);
    listNotifications.mockClear();

    await useNotificationsStore.getState().fetchMoreHistory();

    expect(listNotifications).not.toHaveBeenCalled();
  });

  it('guesses there is more when pagination is missing and the page is full', async () => {
    const ids = Array.from({ length: HISTORY_PAGE_SIZE }, (_, i) => `n${i}`);
    listNotifications.mockResolvedValue({
      notifications: ids.map((id) => fakeNotification(id)),
      unreadCount: 0,
    });

    await useNotificationsStore.getState().fetchHistory(false);

    expect(useNotificationsStore.getState().history.hasMore).toBe(true);
  });

  it('keeps loaded rows and records the error when a later page fails', async () => {
    listNotifications.mockResolvedValueOnce(page(['a'], true));
    await useNotificationsStore.getState().fetchHistory(false);
    listNotifications.mockRejectedValueOnce(new Error('notification service down'));

    await useNotificationsStore.getState().fetchMoreHistory();

    const h = useNotificationsStore.getState().history;
    expect(h.items.map((n) => n.id)).toEqual(['a']);
    expect(h.error).toBe('notification service down');
    expect(h.loading).toBe(false);
    expect(h.hasMore).toBe(true);
  });

  it('ignores a slow answer for a filter the person already left', async () => {
    let resolveSlow: (v: ReturnType<typeof page>) => void = () => undefined;
    listNotifications.mockImplementationOnce(
      () =>
        new Promise((r) => {
          resolveSlow = r;
        })
    );
    const slow = useNotificationsStore.getState().fetchHistory(false);
    listNotifications.mockResolvedValueOnce(page(['u1'], false));
    await useNotificationsStore.getState().fetchHistory(true);

    resolveSlow(page(['old'], false));
    await slow;

    const h = useNotificationsStore.getState().history;
    expect(h.unreadOnly).toBe(true);
    expect(h.items.map((n) => n.id)).toEqual(['u1']);
  });
});

describe('delivery matrix', () => {
  const E = ChannelType.EMAIL;
  const W = ChannelType.WEBHOOK;
  const C = NotificationCategory;
  const pref = (channel: ChannelType, enabled: boolean, categories: NotificationCategory[] = []) =>
    ({ channel, enabled, categories }) satisfies ChannelPrefLike;

  it('locks email on for critical categories, whatever is saved', () => {
    expect(cellState([pref(E, false)], E, C.SLEEVE_FROZEN)).toBe('locked');
    expect(cellState([pref(E, true, [C.ORDER_FILLED])], E, C.FILL_QUARANTINED)).toBe('locked');
    expect(cellState([], W, C.SLEEVE_FROZEN)).toBe('on');
  });

  it('marks channels a category never reaches as unavailable', () => {
    expect(cellState([], E, C.ORDER_FILLED)).toBe('unavailable');
    expect(cellState([], E, C.BACKTEST_COMPLETED)).toBe('unavailable');
    expect(cellState([], W, C.BACKTEST_COMPLETED)).toBe('unavailable');
  });

  it('reads no row and an empty list as every default, and a list as a narrowing', () => {
    expect(cellState([], W, C.ORDER_FILLED)).toBe('on');
    expect(cellState([pref(W, true)], W, C.ORDER_FILLED)).toBe('on');
    expect(cellState([pref(W, true, [C.ORDER_REJECTED])], W, C.ORDER_FILLED)).toBe('off');
    expect(cellState([pref(W, false)], W, C.ORDER_FILLED)).toBe('off');
  });

  it('turning one box off saves the rest of that channel as an explicit list', () => {
    const next = toggledPreferences([], W, C.ORDER_FILLED);
    const webhook = next.find((p) => p.channel === W);
    expect(webhook?.enabled).toBe(true);
    expect(webhook?.categories).not.toContain(C.ORDER_FILLED);
    expect(webhook?.categories).toContain(C.ORDER_REJECTED);
    expect(next.find((p) => p.channel === E)).toEqual(pref(E, true));
  });

  it('turning the last box back on saves an empty list again', () => {
    const narrowed = toggledPreferences([], W, C.ORDER_FILLED);
    const restored = toggledPreferences(narrowed, W, C.ORDER_FILLED);
    expect(restored.find((p) => p.channel === W)).toEqual(pref(W, true));
  });

  it('switches a channel off when nothing is left, and back on with one category', () => {
    const emailOnly = (Object.keys(DEFAULT_CHANNELS).map(Number) as NotificationCategory[]).filter(
      (c) => DEFAULT_CHANNELS[c]?.includes(E)
    );
    const single = [pref(E, true, [emailOnly[0]])];
    expect(toggledPreferences(single, E, emailOnly[0]).find((p) => p.channel === E)).toEqual(
      pref(E, false)
    );
    expect(
      toggledPreferences([pref(E, false)], E, C.POSITION_DRIFT).find((p) => p.channel === E)
    ).toEqual(pref(E, true, [C.POSITION_DRIFT]));
  });

  it('leaves preferences alone when asked to flip a box that cannot change', () => {
    const before = [pref(E, true, [C.POSITION_DRIFT]), pref(W, false)];
    expect(toggledPreferences(before, E, C.ORDER_FILLED)).toEqual(before);
  });

  it('only pins categories the matrix shows, and every pinned one can reach email', () => {
    const shown = new Set(CATEGORY_GROUPS.flatMap((g) => [...g.categories]));
    for (const c of ALWAYS_EMAIL) {
      expect(shown.has(c)).toBe(true);
      expect(DEFAULT_CHANNELS[c]).toContain(E);
    }
  });
});

describe('alertConditionText', () => {
  it('reads as a short rule with the symbol first', () => {
    expect(alertConditionText(AlertConditionType.RSI_ABOVE, 'SPY', '70')).toBe(
      'SPY · RSI above 70'
    );
    expect(alertConditionText(AlertConditionType.PRICE_BELOW, 'TLT', '90')).toBe(
      'TLT · Price below $90'
    );
  });

  it('signs a price move and puts the percent after the number', () => {
    expect(alertConditionText(AlertConditionType.PRICE_CHANGE_PERCENT, 'QQQ', '-3')).toBe(
      'QQQ · Price move \u22123%'
    );
    expect(alertConditionText(AlertConditionType.PRICE_CHANGE_PERCENT, 'QQQ', '2.5')).toBe(
      'QQQ · Price move +2.5%'
    );
    expect(alertConditionText(AlertConditionType.PRICE_CHANGE_PERCENT, '', '')).toBe('Price move');
  });

  it('falls back for conditions without a threshold or label', () => {
    expect(alertConditionText(AlertConditionType.RECONCILIATION_DRIFT)).toBe(
      'Reconciliation drift'
    );
    expect(alertConditionText(undefined, 'SPY')).toBe('SPY · Condition');
  });
});

describe('metadataCategoryLabel', () => {
  it('labels known categories and ignores anything else', () => {
    expect(metadataCategoryLabel(String(NotificationCategory.SLEEVE_FROZEN))).toBe('Sleeve frozen');
    expect(metadataCategoryLabel('30')).toBeNull();
    expect(metadataCategoryLabel('fill')).toBeNull();
    expect(metadataCategoryLabel(undefined)).toBeNull();
  });
});
