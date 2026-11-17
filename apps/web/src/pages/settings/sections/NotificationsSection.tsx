import { create } from '@bufbuild/protobuf';
import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import { ChannelPreferenceSchema, ChannelType } from '@llamatrade/core/proto/notification_pb';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { AlertTriangle, Check, Lock, Send } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { LogoMark } from '../../../components/common/Logo';
import {
  AlertManager,
  WebhookManager,
} from '../../../components/notifications/NotificationSettings';
import { PanelError, SkeletonRows, Tabs } from '../../../components/ui';
import { useAuthStore } from '../../../store/auth';
import {
  CATEGORY_GROUPS,
  CHANNEL_LABELS,
  PREFERENCE_CHANNELS,
  canReach,
  categoryLabel,
  cellState,
  toggledPreferences,
  type CellState,
  type PreferenceChannel,
} from '../../../types/notifications';
import { emailPreview } from '../emailPreview';

type Tab = 'delivery' | 'webhooks' | 'alerts';
type LoadState = 'loading' | 'ready' | 'error';

const FOLDED = 6;

function Cell({
  state,
  label,
  disabled,
  onToggle,
}: {
  state: CellState;
  label: string;
  disabled: boolean;
  onToggle: () => void;
}) {
  if (state === 'unavailable') {
    return (
      <span title="Not sent on this channel" className="inline-block w-4 text-center text-fg-3">
        ·
      </span>
    );
  }
  const on = state !== 'off';
  const locked = state === 'locked';
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={on}
      aria-label={locked ? `${label}, always on` : label}
      title={locked ? 'This kind of notice always emails' : undefined}
      disabled={locked || disabled}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      className={`inline-grid h-4 w-4 place-items-center rounded-[4px] align-middle transition-colors ${
        on
          ? 'bg-accent-fill text-accent-ink'
          : 'border-[1.5px] border-line-strong hover:border-fg-3'
      } ${locked ? 'cursor-not-allowed opacity-50' : 'disabled:cursor-wait'}`}
    >
      {on &&
        (locked ? (
          <Lock className="h-2.5 w-2.5" strokeWidth={3} />
        ) : (
          <Check className="h-[11px] w-[11px]" strokeWidth={3} />
        ))}
    </button>
  );
}

function EmailPanel({ category, emailOn }: { category: NotificationCategory; emailOn: boolean }) {
  const email = useAuthStore((s) => s.user?.email ?? '');
  const preview = emailPreview(category);
  const label = categoryLabel(category);
  const reachable = canReach(ChannelType.EMAIL, category);
  return (
    <div className="grid content-start gap-2.5">
      <section aria-label="The email this notice sends" className="panel overflow-hidden">
        <header className="grid gap-0.5 border-b border-line bg-sunk px-4 py-2.5">
          <span className="truncate text-[11.5px] text-fg-3">
            From LlamaTrade{email ? ` · to ${email}` : ''}
          </span>
          <b className="text-[13.5px] font-semibold">{preview.subject}</b>
        </header>
        <div className="grid gap-3 px-4 py-4 text-[13px] text-fg-2">
          <LogoMark size={26} />
          <p className="m-0">{preview.body}</p>
          <p className="m-0 text-[11.5px] text-fg-3">
            {!reachable
              ? `${label} only appears in the app, so no email is sent.`
              : emailOn
                ? `You get this because ${label} is on for email. Change it in Notifications.`
                : `${label} is off for email, so this only appears in the app.`}
          </p>
        </div>
      </section>
      <div className="flex flex-wrap items-center gap-2.5">
        <button type="button" className="btn btn-secondary btn-sm" disabled>
          <Send aria-hidden="true" className="h-3.5 w-3.5" />
          Send a test
        </button>
        <span className="text-[11.5px] text-fg-3">
          Test emails aren&apos;t available yet. Words in brackets are filled in by the real notice.
        </span>
      </div>
    </div>
  );
}

function Delivery() {
  const preferences = useNotificationsStore((s) => s.preferences);
  const fetchPreferences = useNotificationsStore((s) => s.fetchPreferences);
  const updatePreferences = useNotificationsStore((s) => s.updatePreferences);
  const email = useAuthStore((s) => s.user?.email ?? '');
  const [load, setLoad] = useState<LoadState>('loading');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [selected, setSelected] = useState<NotificationCategory>(
    () =>
      CATEGORY_GROUPS.flatMap((g) => g.categories).find((c) => canReach(ChannelType.EMAIL, c)) ??
      NotificationCategory.SLEEVE_FROZEN
  );
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());

  const reload = useCallback(() => {
    setLoad('loading');
    useNotificationsStore.setState({ error: null });
    fetchPreferences()
      .then(() => setLoad(useNotificationsStore.getState().error ? 'error' : 'ready'))
      .catch(() => setLoad('error'));
  }, [fetchPreferences]);

  useEffect(reload, [reload]);

  const toggle = (channel: PreferenceChannel, category: NotificationCategory) => {
    setSaving(true);
    setSaveError(null);
    const next = toggledPreferences(preferences, channel, category).map((p) =>
      create(ChannelPreferenceSchema, { ...p, categories: [...p.categories] })
    );
    updatePreferences(next)
      .catch((e: unknown) =>
        setSaveError(e instanceof Error ? e.message : "That change couldn't be saved.")
      )
      .finally(() => setSaving(false));
  };

  if (load === 'loading') {
    return (
      <div className="panel">
        <SkeletonRows rows={8} cols={3} />
      </div>
    );
  }
  if (load === 'error') {
    return (
      <div className="panel">
        <PanelError
          title="Delivery settings couldn't be loaded"
          unaffected="Notifications still arrive in the app."
          onRetry={reload}
        />
      </div>
    );
  }

  const emailOn = cellState(preferences, ChannelType.EMAIL, selected) !== 'off';

  return (
    <div className="grid gap-3">
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
        <div className="panel overflow-hidden">
          {saveError && (
            <p role="alert" className="m-0 flex items-center gap-2 px-4 py-2 text-xs text-risk">
              <AlertTriangle className="h-3.5 w-3.5 flex-none" />
              {saveError}
            </p>
          )}
          <table className="w-full text-[12.5px]">
            <thead>
              <tr>
                <th className="border-b border-line px-4 py-2 text-left text-[11px] font-medium text-fg-3">
                  Kind of notice
                </th>
                {PREFERENCE_CHANNELS.map((ch) => (
                  <th
                    key={ch}
                    className="w-[72px] border-b border-line px-3 py-2 text-center text-[11px] font-medium text-fg-3"
                  >
                    {CHANNEL_LABELS[ch]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CATEGORY_GROUPS.map((group) => {
                const expanded = open.has(group.label) || group.categories.length <= FOLDED + 1;
                const shown = expanded ? group.categories : group.categories.slice(0, FOLDED);
                const hidden = group.categories.length - shown.length;
                return (
                  <GroupRows
                    key={group.label}
                    label={group.label.replace('&', 'and')}
                    categories={shown}
                    selected={selected}
                    onSelect={setSelected}
                    preferences={preferences}
                    saving={saving}
                    onToggle={toggle}
                    hidden={hidden}
                    onShowAll={() => setOpen((s) => new Set([...s, group.label]))}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
        <EmailPanel category={selected} emailOn={emailOn} />
      </div>
      <p className="m-0 text-[12px] text-fg-3">
        A dot means that kind of notice isn&apos;t sent on that channel. A lock means it always
        emails.{email ? ` Emails go to ${email}.` : ''}
      </p>
    </div>
  );
}

function GroupRows({
  label,
  categories,
  selected,
  onSelect,
  preferences,
  saving,
  onToggle,
  hidden,
  onShowAll,
}: {
  label: string;
  categories: readonly NotificationCategory[];
  selected: NotificationCategory;
  onSelect: (c: NotificationCategory) => void;
  preferences: Parameters<typeof cellState>[0];
  saving: boolean;
  onToggle: (channel: PreferenceChannel, category: NotificationCategory) => void;
  hidden: number;
  onShowAll: () => void;
}) {
  return (
    <>
      <tr>
        <td colSpan={3} className="bg-sunk px-4 py-[5px] text-[11px] text-fg-3">
          {label}
        </td>
      </tr>
      {categories.map((category) => {
        const on = category === selected;
        const pinned = cellState([], ChannelType.EMAIL, category) === 'locked';
        const inAppOnly = !PREFERENCE_CHANNELS.some((ch) => canReach(ch, category));
        return (
          <tr
            key={category}
            onClick={() => onSelect(category)}
            className={`cursor-pointer ${on ? 'bg-accent-soft' : 'hover:bg-sunk'}`}
          >
            <td className="border-b border-line px-4 py-2 text-fg">
              <button
                type="button"
                aria-pressed={on}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(category);
                }}
                className={`text-left ${on ? 'font-semibold' : ''}`}
              >
                {categoryLabel(category)}
              </button>
              {(pinned || inAppOnly) && (
                <span className="text-[11px] text-fg-3">
                  {' '}
                  · {pinned ? 'always emails' : 'in the app only'}
                </span>
              )}
            </td>
            {PREFERENCE_CHANNELS.map((ch) => (
              <td key={ch} className="border-b border-line px-3 py-2 text-center">
                <Cell
                  state={cellState(preferences, ch, category)}
                  label={`${categoryLabel(category)} by ${CHANNEL_LABELS[ch]}`}
                  disabled={saving}
                  onToggle={() => onToggle(ch, category)}
                />
              </td>
            ))}
          </tr>
        );
      })}
      {hidden > 0 && (
        <tr>
          <td className="border-b border-line px-4 py-2 text-fg-3">
            {hidden} more in {label}
          </td>
          <td colSpan={2} className="border-b border-line px-3 py-2 text-center">
            <button
              type="button"
              className="text-[12px] text-accent hover:underline"
              onClick={onShowAll}
            >
              Show all
            </button>
          </td>
        </tr>
      )}
    </>
  );
}

/** The delivery grid with the email each kind sends beside it; webhooks and alerts on tabs. */
export function NotificationsSection() {
  const webhooks = useNotificationsStore((s) => s.webhooks);
  const alerts = useNotificationsStore((s) => s.alerts);
  const fetchWebhooks = useNotificationsStore((s) => s.fetchWebhooks);
  const fetchAlerts = useNotificationsStore((s) => s.fetchAlerts);
  const [tab, setTab] = useState<Tab>('delivery');

  useEffect(() => {
    fetchWebhooks().catch(() => undefined);
    fetchAlerts().catch(() => undefined);
  }, [fetchWebhooks, fetchAlerts]);

  const count = (n: number) =>
    n > 0 ? <span className="num ml-1 text-[11px] text-fg-3">{n}</span> : null;

  return (
    <div className="grid gap-4">
      <Tabs
        label="Notification settings"
        value={tab}
        onChange={setTab}
        options={[
          { key: 'delivery', label: 'Delivery' },
          { key: 'webhooks', label: <>Webhooks{count(webhooks.length)}</> },
          { key: 'alerts', label: <>Price alerts{count(alerts.length)}</> },
        ]}
      />
      {tab === 'delivery' && <Delivery />}
      {tab === 'webhooks' && <WebhookManager />}
      {tab === 'alerts' && <AlertManager />}
    </div>
  );
}
