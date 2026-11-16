/**
 * Notification state management with Zustand.
 *
 * Serves the bell + notification center (list, unread count, mark read), the
 * per-channel preference matrix, webhook endpoint management, and price
 * alerts. All calls thread the real tenant context.
 */

import { create, type StoreApi } from "zustand";

import type {
  Alert,
  AlertCondition,
  ChannelPreference,
  Notification,
  TestWebhookResponse,
  Webhook,
} from "@llamatrade/core/proto/notification_pb";
import { ChannelType } from "@llamatrade/core/proto/notification_pb";
import type { NotificationCategory } from "@llamatrade/core/proto/events_pb";

import { getTenantContext, notificationClient } from "../net";

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

export const HISTORY_PAGE_SIZE = 30;

export interface NotificationHistory {
  items: Notification[];
  unreadOnly: boolean;
  /** Last page loaded; 0 before the first load. */
  page: number;
  hasMore: boolean;
  total: number;
  loading: boolean;
  error: string | null;
}

const EMPTY_HISTORY: NotificationHistory = {
  items: [],
  unreadOnly: false,
  page: 0,
  hasMore: false,
  total: 0,
  loading: false,
  error: null,
};

interface NotificationsState {
  notifications: Notification[];
  unreadCount: number;
  /** The full list page, paged separately so the bell's polling never resets it. */
  history: NotificationHistory;
  webhooks: Webhook[];
  preferences: ChannelPreference[];
  alerts: Alert[];
  loading: boolean;
  error: string | null;

  fetchNotifications: (unreadOnly?: boolean) => Promise<void>;
  /** Loads page 1 for the given filter, replacing the list. */
  fetchHistory: (unreadOnly: boolean) => Promise<void>;
  /** Appends the next page of the current filter. */
  fetchMoreHistory: () => Promise<void>;
  markAsRead: (notificationId: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;

  fetchWebhooks: () => Promise<void>;
  createWebhook: (
    input: CreateWebhookInput,
  ) => Promise<{ webhook: Webhook; secret: string }>;
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

const markRead = (list: Notification[], id: string | null): Notification[] =>
  list.map((n) => (id === null || n.id === id ? { ...n, isRead: true } : n));

/** Drops ids already shown, since new arrivals shift later pages. */
function appendUnique(
  list: Notification[],
  next: Notification[],
): Notification[] {
  const seen = new Set(list.map((n) => n.id));
  return [...list, ...next.filter((n) => !seen.has(n.id))];
}

type NotificationsApi = Pick<
  StoreApi<NotificationsState>,
  "setState" | "getState"
>;

let historyRequest = 0;

async function loadHistoryPage(
  { setState: set, getState: get }: NotificationsApi,
  page: number,
  unreadOnly: boolean,
): Promise<void> {
  const request = historyRequest;
  try {
    const response = await notificationClient.listNotifications({
      context: getTenantContext(),
      unreadOnly,
      pagination: { page, pageSize: HISTORY_PAGE_SIZE },
    });
    if (request !== historyRequest) return;
    const current = get().history;
    const items =
      page === 1
        ? response.notifications
        : appendUnique(current.items, response.notifications);
    set({
      unreadCount: response.unreadCount,
      history: {
        ...current,
        items,
        page,
        total: response.pagination?.totalItems ?? items.length,
        hasMore:
          response.pagination?.hasNext ??
          response.notifications.length === HISTORY_PAGE_SIZE,
        loading: false,
        error: null,
      },
    });
  } catch (error) {
    if (request !== historyRequest) return;
    set({
      history: {
        ...get().history,
        loading: false,
        error: message(error, "Failed to load notifications"),
      },
    });
  }
}

export const useNotificationsStore = create<NotificationsState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  history: EMPTY_HISTORY,
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
      set({
        error: message(error, "Failed to fetch notifications"),
        loading: false,
      });
    }
  },

  fetchHistory: async (unreadOnly) => {
    historyRequest += 1;
    set({ history: { ...EMPTY_HISTORY, unreadOnly, loading: true } });
    await loadHistoryPage({ setState: set, getState: get }, 1, unreadOnly);
  },

  fetchMoreHistory: async () => {
    const { history } = get();
    if (history.loading || !history.hasMore) return;
    set({ history: { ...history, loading: true, error: null } });
    await loadHistoryPage(
      { setState: set, getState: get },
      history.page + 1,
      history.unreadOnly,
    );
  },

  markAsRead: async (notificationId) => {
    try {
      await notificationClient.markAsRead({
        context: getTenantContext(),
        notificationId,
      });
      const { notifications, history, unreadCount } = get();
      const wasUnread = [...notifications, ...history.items].some(
        (n) => n.id === notificationId && !n.isRead,
      );
      set({
        notifications: markRead(notifications, notificationId),
        history: { ...history, items: markRead(history.items, notificationId) },
        unreadCount: wasUnread ? Math.max(0, unreadCount - 1) : unreadCount,
      });
    } catch (error) {
      set({ error: message(error, "Failed to mark as read") });
    }
  },

  markAllAsRead: async () => {
    try {
      await notificationClient.markAsRead({
        context: getTenantContext(),
        markAll: true,
      });
      const { notifications, history } = get();
      set({
        notifications: markRead(notifications, null),
        history: { ...history, items: markRead(history.items, null) },
        unreadCount: 0,
      });
    } catch (error) {
      set({ error: message(error, "Failed to mark all as read") });
    }
  },

  fetchWebhooks: async () => {
    set({ loading: true, error: null });
    try {
      const response = await notificationClient.listWebhooks({
        context: getTenantContext(),
      });
      set({ webhooks: response.webhooks, loading: false });
    } catch (error) {
      set({
        error: message(error, "Failed to fetch webhooks"),
        loading: false,
      });
    }
  },

  createWebhook: async ({ name, url, events }) => {
    const response = await notificationClient.createWebhook({
      context: getTenantContext(),
      name,
      url,
      events,
    });
    if (!response.webhook)
      throw new Error("Webhook creation returned no webhook");
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
      set({
        webhooks: get().webhooks.map((w) =>
          w.id === updated.id ? updated : w,
        ),
      });
    }
  },

  deleteWebhook: async (webhookId) => {
    await notificationClient.deleteWebhook({
      context: getTenantContext(),
      webhookId,
    });
    set({ webhooks: get().webhooks.filter((w) => w.id !== webhookId) });
  },

  testWebhook: async (webhookId) =>
    notificationClient.testWebhook({ context: getTenantContext(), webhookId }),

  fetchPreferences: async () => {
    try {
      const response = await notificationClient.getPreferences({
        context: getTenantContext(),
      });
      set({ preferences: response.preferences });
    } catch (error) {
      set({ error: message(error, "Failed to fetch preferences") });
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
      set({ error: message(error, "Failed to fetch alerts") });
    }
  },

  createAlert: async ({
    name,
    description,
    condition,
    channels,
    cooldownMinutes,
  }) => {
    const response = await notificationClient.createAlert({
      context: getTenantContext(),
      name,
      description,
      condition,
      channels,
      cooldownMinutes,
    });
    if (!response.alert) throw new Error("Alert creation returned no alert");
    set({ alerts: [response.alert, ...get().alerts] });
    return response.alert;
  },

  deleteAlert: async (alertId) => {
    await notificationClient.deleteAlert({
      context: getTenantContext(),
      alertId,
    });
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
      set({
        alerts: get().alerts.map((a) => (a.id === updated.id ? updated : a)),
      });
    }
  },
}));
