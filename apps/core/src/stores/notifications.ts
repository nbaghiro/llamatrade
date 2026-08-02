/**
 * Notification state management with Zustand.
 *
 * Serves the bell + notification center (list, unread count, mark read), the
 * per-channel preference matrix, webhook endpoint management, and price
 * alerts. All calls thread the real tenant context.
 */

import { create } from 'zustand';

import type {
  Alert,
  AlertCondition,
  ChannelPreference,
  Notification,
  TestWebhookResponse,
  Webhook,
} from '@llamatrade/core/proto/notification_pb';
import { ChannelType } from '@llamatrade/core/proto/notification_pb';
import type { NotificationCategory } from '@llamatrade/core/proto/events_pb';

import { getTenantContext, notificationClient } from '../net';

export interface CreateWebhookInput {
  name: string;
  url: string;
  events: NotificationCategory[];
}

export interface CreateAlertInput {
  name: string;
  description: string;
  condition: AlertCondition;
  channels: ChannelType[];
  cooldownMinutes: number;
}

interface NotificationsState {
  notifications: Notification[];
  unreadCount: number;
  webhooks: Webhook[];
  preferences: ChannelPreference[];
  alerts: Alert[];
  loading: boolean;
  error: string | null;

  fetchNotifications: (unreadOnly?: boolean) => Promise<void>;
  markAsRead: (notificationId: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;

  fetchWebhooks: () => Promise<void>;
  createWebhook: (input: CreateWebhookInput) => Promise<{ webhook: Webhook; secret: string }>;
  updateWebhook: (webhook: Webhook) => Promise<void>;
  deleteWebhook: (webhookId: string) => Promise<void>;
  testWebhook: (webhookId: string) => Promise<TestWebhookResponse>;

  fetchPreferences: () => Promise<void>;
  updatePreferences: (preferences: ChannelPreference[]) => Promise<void>;

  fetchAlerts: (activeOnly?: boolean) => Promise<void>;
  createAlert: (input: CreateAlertInput) => Promise<Alert>;
  deleteAlert: (alertId: string) => Promise<void>;
  toggleAlert: (alertId: string, isActive: boolean) => Promise<void>;
}

const message = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

export const useNotificationsStore = create<NotificationsState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  webhooks: [],
  preferences: [],
  alerts: [],
  loading: false,
  error: null,

  fetchNotifications: async (unreadOnly = false) => {
    set({ loading: true, error: null });
    try {
      const response = await notificationClient.listNotifications({
        context: getTenantContext(),
        unreadOnly,
        pagination: { page: 1, pageSize: 50 },
      });
      set({
        notifications: response.notifications,
        unreadCount: response.unreadCount,
        loading: false,
      });
    } catch (error) {
      set({ error: message(error, 'Failed to fetch notifications'), loading: false });
    }
  },

  markAsRead: async (notificationId) => {
    try {
      await notificationClient.markAsRead({ context: getTenantContext(), notificationId });
      set({
        notifications: get().notifications.map((n) =>
          n.id === notificationId ? { ...n, isRead: true } : n,
        ),
        unreadCount: Math.max(0, get().unreadCount - 1),
      });
    } catch (error) {
      set({ error: message(error, 'Failed to mark as read') });
    }
  },

  markAllAsRead: async () => {
    try {
      await notificationClient.markAsRead({ context: getTenantContext(), markAll: true });
      set({
        notifications: get().notifications.map((n) => ({ ...n, isRead: true })),
        unreadCount: 0,
      });
    } catch (error) {
      set({ error: message(error, 'Failed to mark all as read') });
    }
  },

  fetchWebhooks: async () => {
    set({ loading: true, error: null });
    try {
      const response = await notificationClient.listWebhooks({ context: getTenantContext() });
      set({ webhooks: response.webhooks, loading: false });
    } catch (error) {
      set({ error: message(error, 'Failed to fetch webhooks'), loading: false });
    }
  },

  createWebhook: async ({ name, url, events }) => {
    const response = await notificationClient.createWebhook({
      context: getTenantContext(),
      name,
      url,
      events,
    });
    if (!response.webhook) throw new Error('Webhook creation returned no webhook');
    set({ webhooks: [response.webhook, ...get().webhooks] });
    return { webhook: response.webhook, secret: response.secret };
  },

  updateWebhook: async (webhook) => {
    const response = await notificationClient.updateWebhook({
      context: getTenantContext(),
      webhookId: webhook.id,
      name: webhook.name,
      url: webhook.url,
      events: webhook.events,
      isActive: webhook.isActive,
    });
    if (response.webhook) {
      const updated = response.webhook;
      set({ webhooks: get().webhooks.map((w) => (w.id === updated.id ? updated : w)) });
    }
  },

  deleteWebhook: async (webhookId) => {
    await notificationClient.deleteWebhook({ context: getTenantContext(), webhookId });
    set({ webhooks: get().webhooks.filter((w) => w.id !== webhookId) });
  },

  testWebhook: async (webhookId) =>
    notificationClient.testWebhook({ context: getTenantContext(), webhookId }),

  fetchPreferences: async () => {
    try {
      const response = await notificationClient.getPreferences({ context: getTenantContext() });
      set({ preferences: response.preferences });
    } catch (error) {
      set({ error: message(error, 'Failed to fetch preferences') });
    }
  },

  updatePreferences: async (preferences) => {
    const response = await notificationClient.updatePreferences({
      context: getTenantContext(),
      preferences,
    });
    set({ preferences: response.preferences });
  },

  fetchAlerts: async (activeOnly = false) => {
    try {
      const response = await notificationClient.listAlerts({
        context: getTenantContext(),
        activeOnly,
      });
      set({ alerts: response.alerts });
    } catch (error) {
      set({ error: message(error, 'Failed to fetch alerts') });
    }
  },

  createAlert: async ({ name, description, condition, channels, cooldownMinutes }) => {
    const response = await notificationClient.createAlert({
      context: getTenantContext(),
      name,
      description,
      condition,
      channels,
      cooldownMinutes,
    });
    if (!response.alert) throw new Error('Alert creation returned no alert');
    set({ alerts: [response.alert, ...get().alerts] });
    return response.alert;
  },

  deleteAlert: async (alertId) => {
    await notificationClient.deleteAlert({ context: getTenantContext(), alertId });
    set({ alerts: get().alerts.filter((a) => a.id !== alertId) });
  },

  toggleAlert: async (alertId, isActive) => {
    const response = await notificationClient.toggleAlert({
      context: getTenantContext(),
      alertId,
      isActive,
    });
    if (response.alert) {
      const updated = response.alert;
      set({ alerts: get().alerts.map((a) => (a.id === updated.id ? updated : a)) });
    }
  },
}));
