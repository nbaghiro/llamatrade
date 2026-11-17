import { create } from '@bufbuild/protobuf';
import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import {
  AlertConditionSchema,
  AlertConditionType,
  ChannelPreferenceSchema,
  ChannelType,
} from '@llamatrade/core/proto/notification_pb';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { AlertTriangle, Check, Copy, Lock, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState, type ReactNode } from 'react';

import {
  CATEGORY_GROUPS,
  alertConditionText,
  CHANNEL_LABELS,
  CONDITION_TYPE_LABELS,
  PREFERENCE_CHANNELS,
  canReach,
  categoryLabel,
  cellState,
  toggledPreferences,
  type CellState,
  type PreferenceChannel,
} from '../../types/notifications';
import { PanelError, SkeletonRows } from '../ui';

const CONDITION_OPTIONS = Object.entries(CONDITION_TYPE_LABELS).map(([value, label]) => ({
  value,
  label: label ?? '',
}));

const errorText = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

function SettingsPanel({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="min-w-0 overflow-hidden rounded-panel border border-line bg-panel">
      <header className="flex min-h-[42px] items-center justify-between gap-2.5 border-b border-line px-3.5 py-2.5 text-[12.5px]">
        <b className="font-semibold text-fg">{title}</b>
        {aside && <span className="text-fg-3">{aside}</span>}
      </header>
      {children}
    </section>
  );
}

function InlineError({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="m-0 flex items-center gap-2 px-3.5 py-2 text-xs text-risk">
      <AlertTriangle className="h-3.5 w-3.5 flex-none" />
      {children}
    </p>
  );
}

/** Email and webhook delivery per category, plus webhooks and price alerts. */
export function NotificationSettings() {
  return (
    <div className="grid items-start gap-3 lg:grid-cols-[1.2fr_1fr]">
      <PreferencesMatrix />
      <div className="grid min-w-0 gap-3">
        <WebhookManager />
        <AlertManager />
      </div>
    </div>
  );
}

type LoadState = 'loading' | 'ready' | 'error';

function PreferencesMatrix() {
  const preferences = useNotificationsStore((s) => s.preferences);
  const fetchPreferences = useNotificationsStore((s) => s.fetchPreferences);
  const updatePreferences = useNotificationsStore((s) => s.updatePreferences);
  const [load, setLoad] = useState<LoadState>('loading');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

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
      .catch((e: unknown) => setSaveError(errorText(e, "That change couldn't be saved.")))
      .finally(() => setSaving(false));
  };

  return (
    <SettingsPanel title="Delivery" aside="in-app is always on">
      {load === 'loading' && <SkeletonRows rows={8} cols={3} />}
      {load === 'error' && (
        <PanelError
          title="Delivery settings couldn't be loaded"
          unaffected="Notifications still arrive in the app."
          onRetry={reload}
        />
      )}
      {load === 'ready' && (
        <>
          {saveError && <InlineError>{saveError}</InlineError>}
          <table className="w-full text-[12.5px]">
            <thead>
              <tr>
                <th className="border-b border-line px-3.5 py-2 text-left text-[11px] font-medium text-fg-3">
                  Category
                </th>
                {PREFERENCE_CHANNELS.map((ch) => (
                  <th
                    key={ch}
                    className="w-[76px] border-b border-line px-3.5 py-2 text-right text-[11px] font-medium text-fg-3"
                  >
                    {CHANNEL_LABELS[ch]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CATEGORY_GROUPS.map((group) => (
                <GroupRows key={group.label} label={group.label} categories={group.categories}>
                  {(category) =>
                    PREFERENCE_CHANNELS.map((ch) => (
                      <td key={ch} className="border-b border-line px-3.5 py-2 text-right">
                        <MatrixBox
                          state={cellState(preferences, ch, category)}
                          label={`${categoryLabel(category)} by ${CHANNEL_LABELS[ch]}`}
                          disabled={saving}
                          onToggle={() => toggle(ch, category)}
                        />
                      </td>
                    ))
                  }
                </GroupRows>
              ))}
            </tbody>
          </table>
          <p className="m-0 border-t border-line px-3.5 py-2.5 text-xs text-fg-3">
            Critical notices always email. A dash means that kind of notice only appears in the app
            or on the other channel.
          </p>
        </>
      )}
    </SettingsPanel>
  );
}

function GroupRows({
  label,
  categories,
  children,
}: {
  label: string;
  categories: readonly NotificationCategory[];
  children: (category: NotificationCategory) => ReactNode;
}) {
  return (
    <>
      <tr>
        <td colSpan={3} className="bg-sunk px-3.5 py-[5px] text-[11px] text-fg-3">
          {label}
        </td>
      </tr>
      {categories.map((category) => {
        const inAppOnly = !PREFERENCE_CHANNELS.some((ch) => canReach(ch, category));
        const pinned = cellState([], ChannelType.EMAIL, category) === 'locked';
        return (
          <tr key={category}>
            <td className="border-b border-line px-3.5 py-2 text-fg">
              {categoryLabel(category)}
              {(pinned || inAppOnly) && (
                <span className="text-[11px] text-fg-3">
                  {' '}
                  · {pinned ? 'always emails' : 'in-app only'}
                </span>
              )}
            </td>
            {children(category)}
          </tr>
        );
      })}
    </>
  );
}

function MatrixBox({
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
        –
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
      title={locked ? 'Critical notices always email' : undefined}
      disabled={locked || disabled}
      onClick={onToggle}
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

export function WebhookManager() {
  const webhooks = useNotificationsStore((s) => s.webhooks);
  const fetchWebhooks = useNotificationsStore((s) => s.fetchWebhooks);
  const createWebhook = useNotificationsStore((s) => s.createWebhook);
  const updateWebhook = useNotificationsStore((s) => s.updateWebhook);
  const deleteWebhook = useNotificationsStore((s) => s.deleteWebhook);
  const testWebhook = useNotificationsStore((s) => s.testWebhook);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchWebhooks().catch(() => undefined);
  }, [fetchWebhooks]);

  const run = (work: () => Promise<void>) => {
    setBusy(true);
    work()
      .catch((e: unknown) => setResult({ ok: false, text: errorText(e, 'Something went wrong.') }))
      .finally(() => setBusy(false));
  };

  const add = () => {
    if (!name.trim() || !url.trim()) {
      setResult({ ok: false, text: 'Enter a name and an https:// address.' });
      return;
    }
    if (!/^https:\/\//i.test(url.trim())) {
      setResult({ ok: false, text: 'Webhook addresses need to start with https://.' });
      return;
    }
    run(async () => {
      const { secret } = await createWebhook({ name: name.trim(), url: url.trim(), events: [] });
      setNewSecret(secret);
      setCopied(false);
      setName('');
      setUrl('');
      setResult(null);
    });
  };

  const test = (id: string) =>
    run(async () => {
      const r = await testWebhook(id);
      setResult(
        r.success
          ? { ok: true, text: `Test delivered, HTTP ${r.statusCode}.` }
          : { ok: false, text: `Test failed: ${r.message}` }
      );
    });

  return (
    <SettingsPanel title="Webhooks" aside="signed with HMAC-SHA256">
      <div className="grid gap-2.5 px-3.5 py-3">
        {newSecret && (
          <div className="grid gap-1.5 rounded-[8px] border border-line-strong bg-sunk px-3 py-2.5 text-[12.5px]">
            <span className="text-fg-2">
              Signing secret. It&apos;s shown once, so store it now.
            </span>
            <div className="flex items-center gap-2">
              <code className="num min-w-0 flex-1 break-all text-xs text-fg">{newSecret}</code>
              <button
                type="button"
                aria-label="Copy secret"
                className="btn btn-ghost btn-sm px-1.5"
                onClick={() => {
                  navigator.clipboard
                    .writeText(newSecret)
                    .then(() => setCopied(true))
                    .catch(() => undefined);
                }}
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm justify-self-start"
              onClick={() => setNewSecret(null)}
            >
              I&apos;ve stored it
            </button>
          </div>
        )}

        {webhooks.length === 0 ? (
          <p className="m-0 text-[12.5px] text-fg-3">
            No webhooks yet. Each one receives signed POSTs for the categories ticked above.
          </p>
        ) : (
          webhooks.map((w) => (
            <div key={w.id} className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1">
                <b className="block truncate font-semibold text-fg">{w.name}</b>
                <span className="block truncate text-[11.5px] text-fg-3">
                  {w.url.replace(/^https?:\/\//, '')}
                </span>
              </span>
              {!w.isActive && <span className="badge badge-danger">Disabled</span>}
              {w.isActive && w.failureCount > 0 && (
                <span className="badge badge-danger">{w.failureCount} failed</span>
              )}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={busy}
                onClick={() => test(w.id)}
              >
                Test
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={busy}
                onClick={() => run(() => updateWebhook({ ...w, isActive: !w.isActive }))}
              >
                {w.isActive ? 'Disable' : 'Enable'}
              </button>
              <button
                type="button"
                aria-label={`Delete ${w.name}`}
                className="btn btn-ghost btn-sm px-1.5"
                disabled={busy}
                onClick={() => run(() => deleteWebhook(w.id))}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}

        {result && (
          <p className={`m-0 text-xs ${result.ok ? 'text-fg-2' : 'text-risk'}`} role="status">
            {result.text}
          </p>
        )}

        <div className="grid gap-2 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)_auto]">
          <input
            className="input"
            aria-label="Webhook name"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="input"
            aria-label="Webhook address"
            placeholder="https://"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button type="button" className="btn btn-secondary h-9" disabled={busy} onClick={add}>
            <Plus className="h-3.5 w-3.5" />
            Add webhook
          </button>
        </div>
      </div>
    </SettingsPanel>
  );
}

export function AlertManager() {
  const alerts = useNotificationsStore((s) => s.alerts);
  const fetchAlerts = useNotificationsStore((s) => s.fetchAlerts);
  const createAlert = useNotificationsStore((s) => s.createAlert);
  const deleteAlert = useNotificationsStore((s) => s.deleteAlert);
  const toggleAlert = useNotificationsStore((s) => s.toggleAlert);
  const [name, setName] = useState('');
  const [symbol, setSymbol] = useState('');
  const [threshold, setThreshold] = useState('');
  const [conditionType, setConditionType] = useState(String(AlertConditionType.PRICE_ABOVE));
  const [emailToo, setEmailToo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAlerts().catch(() => undefined);
  }, [fetchAlerts]);

  const run = (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    work()
      .catch((e: unknown) => setError(errorText(e, 'Something went wrong.')))
      .finally(() => setBusy(false));
  };

  const add = () => {
    if (!name.trim()) {
      setError('Give the alert a name.');
      return;
    }
    if (threshold.trim() && !Number.isFinite(Number(threshold))) {
      setError('The threshold needs to be a number.');
      return;
    }
    run(async () => {
      await createAlert({
        name: name.trim(),
        description: '',
        condition: create(AlertConditionSchema, {
          type: Number(conditionType) as AlertConditionType,
          symbol: symbol.trim().toUpperCase(),
          threshold: { value: threshold.trim() || '0' },
        }),
        channels: emailToo ? [ChannelType.EMAIL] : [],
        cooldownMinutes: 60,
      });
      setName('');
      setSymbol('');
      setThreshold('');
    });
  };

  return (
    <SettingsPanel title="Price alerts" aside="one-hour cooldown">
      {alerts.length > 0 && (
        <table className="w-full text-[12.5px]">
          <thead>
            <tr>
              {['Alert', 'Condition', 'State', ''].map((h) => (
                <th
                  key={h}
                  className="border-b border-line px-3.5 py-2 text-left text-[11px] font-medium text-fg-3"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id}>
                <td className="border-b border-line px-3.5 py-2 text-fg">{a.name}</td>
                <td className="border-b border-line px-3.5 py-2 text-fg-2">
                  {alertConditionText(
                    a.condition?.type,
                    a.condition?.symbol,
                    a.condition?.threshold?.value
                  )}
                </td>
                <td
                  className={`border-b border-line px-3.5 py-2 ${a.isActive ? 'text-fg' : 'text-fg-3'}`}
                >
                  <button
                    type="button"
                    className="hover:underline disabled:opacity-60"
                    disabled={busy}
                    onClick={() => run(() => toggleAlert(a.id, !a.isActive))}
                    title={a.isActive ? 'Pause this alert' : 'Resume this alert'}
                  >
                    {a.isActive ? 'Active' : 'Paused'}
                  </button>
                </td>
                <td className="border-b border-line px-2 py-1 text-right">
                  <button
                    type="button"
                    aria-label={`Delete ${a.name}`}
                    className="btn btn-ghost btn-sm px-1.5"
                    disabled={busy}
                    onClick={() => run(() => deleteAlert(a.id))}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="grid gap-2 px-3.5 py-3">
        {alerts.length === 0 && (
          <p className="m-0 text-[12.5px] text-fg-3">
            No alerts yet. An alert adds a notice when its condition is met.
          </p>
        )}
        {error && <p className="m-0 text-xs text-risk">{error}</p>}
        <div className="grid grid-cols-2 gap-2">
          <input
            className="input"
            aria-label="Alert name"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select
            className="select"
            aria-label="Condition"
            value={conditionType}
            onChange={(e) => setConditionType(e.target.value)}
          >
            {CONDITION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            className="input"
            aria-label="Symbol"
            placeholder="Symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          />
          <input
            className="input num"
            aria-label="Threshold"
            placeholder="Threshold"
            inputMode="decimal"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-[12.5px] text-fg-2">
            <input
              type="checkbox"
              checked={emailToo}
              onChange={(e) => setEmailToo(e.target.checked)}
              className="h-4 w-4 accent-[rgb(var(--accent-fill))]"
            />
            Email me too
          </label>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={add}>
            <Plus className="h-3.5 w-3.5" />
            Add alert
          </button>
        </div>
      </div>
    </SettingsPanel>
  );
}
