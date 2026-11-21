import { create } from '@bufbuild/protobuf';
import type { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import { ChannelPreferenceSchema, type ChannelType } from '@llamatrade/core/proto/notification_pb';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { useCallback, useEffect, useState } from 'react';

import { toggledPreferences } from './notificationModel';
import { ROUTING } from './notifications';

export type LoadState = 'loading' | 'ready' | 'error';

/** The delivery preferences, with a toggle that saves one box at a time. */
export function usePreferences() {
  const preferences = useNotificationsStore((s) => s.preferences);
  const fetchPreferences = useNotificationsStore((s) => s.fetchPreferences);
  const updatePreferences = useNotificationsStore((s) => s.updatePreferences);
  const [load, setLoad] = useState<LoadState>(preferences.length ? 'ready' : 'loading');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const reload = useCallback(() => {
    useNotificationsStore.setState({ error: null });
    fetchPreferences()
      .then(() => setLoad(useNotificationsStore.getState().error ? 'error' : 'ready'))
      .catch(() => setLoad('error'));
  }, [fetchPreferences]);

  useEffect(reload, [reload]);

  const toggle = (channel: number, category: NotificationCategory) => {
    setSaving(true);
    setSaveError(null);
    const next = toggledPreferences(ROUTING, preferences, channel, category).map((p) =>
      create(ChannelPreferenceSchema, {
        channel: p.channel as ChannelType,
        enabled: p.enabled,
        categories: p.categories.map((c) => c as NotificationCategory),
      }),
    );
    updatePreferences(next)
      .catch((e: unknown) => setSaveError(e instanceof Error ? e.message : "That change couldn't be saved."))
      .finally(() => setSaving(false));
  };

  return { preferences, load, saving, saveError, toggle, reload };
}
