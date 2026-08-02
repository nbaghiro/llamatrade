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

import type { Notification, Webhook } from '@llamatrade/core/proto/notification_pb';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';

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
    expect(markAsRead).toHaveBeenCalledWith(
      expect.objectContaining({ notificationId: 'n1' }),
    );
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
